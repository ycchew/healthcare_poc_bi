"""
ST-03: Patient Lifetime Value (CLTV) Model
Implements BG/NBD + Gamma-Gamma models for predicting patient lifetime value.

This module trains CLTV models using the lifetimes library and stores predictions
in the database for downstream analytics.

Usage:
    python cltv_model.py --train  # Train and save model
    python cltv_model.py --predict  # Generate predictions
    python cltv_model.py --full  # Train + predict in one run
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import pandas as pd
import numpy as np
from sqlalchemy import text

try:
    from lifetimes import BetaGeoFitter, GammaGammaFitter
    from lifetimes.utils import summary_data_from_transaction_data

    LIFETIMES_AVAILABLE = True
except ImportError:
    BetaGeoFitter = None
    GammaGammaFitter = None
    summary_data_from_transaction_data = None
    LIFETIMES_AVAILABLE = False

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "ST-01" / "python"))
from database import DatabaseManager, get_db_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CLTVModel:
    """
    Customer Lifetime Value model using BG/NBD + Gamma-Gamma approach.

    This class implements:
    1. BG/NBD model for predicting purchase frequency and churn probability
    2. Gamma-Gamma model for predicting average order value
    3. Combined CLTV calculation for 12-month and 24-month horizons
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or get_db_manager()
        self.model_version = f"cltv_v1_{datetime.now().strftime('%Y%m%d')}"
        self.bg_nbd_model = None
        self.gamma_gamma_model = None

    def load_transaction_data(self) -> pd.DataFrame:
        """
        Load patient transaction data for model training.

        Returns DataFrame with columns:
        - patient_id: Patient MRN
        - transaction_date: Date of transaction
        - amount: Transaction amount
        """
        query = """
            SELECT DISTINCT ON (c.mrn, c.date)
                c.mrn AS patient_id,
                c.date AS transaction_date,
                c.amount_collected AS amount
            FROM dk.collection c
            WHERE c.date IS NOT NULL
              AND c.amount_collected IS NOT NULL
            ORDER BY c.mrn, c.date DESC
        """
        return self.db.execute_query(query)

    def prepare_rfm_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert transaction data to RFM features for CLTV modeling.

        Args:
            df: DataFrame with patient_id, transaction_date, amount

        Returns:
            DataFrame with frequency, recency, T, and monetary_value
        """
        if not LIFETIMES_AVAILABLE:
            raise ImportError(
                "lifetimes library not installed. Install with: pip install lifetimes"
            )

        df["transaction_date"] = pd.to_datetime(df["transaction_date"])

        rfm = summary_data_from_transaction_data(
            df,
            customer_id_col="patient_id",
            datetime_col="transaction_date",
            monetary_value_col="amount",
            observation_period_end=df["transaction_date"].max(),
        )

        rfm = rfm.reset_index()
        rfm.columns = ["patient_id", "frequency", "recency", "T", "monetary_value"]

        # Filter out customers with non-positive values that would cause errors in Gamma-Gamma model
        rfm = rfm[(rfm["frequency"] > 0) & (rfm["monetary_value"] > 0)]

        return rfm

    def train_bg_nbd(self, rfm_df: pd.DataFrame) -> Any:
        """
        Train BG/NBD model for predicting purchase frequency.

        Args:
            rfm_df: DataFrame with frequency, recency, T columns

        Returns:
            Trained BetaGeoFitter model
        """
        if not LIFETIMES_AVAILABLE:
            raise ImportError(
                "lifetimes library not installed. Install with: pip install lifetimes"
            )

        logger.info("Training BG/NBD model...")

        bgf = BetaGeoFitter(penalizer_coef=0.01)
        bgf.fit(rfm_df["frequency"], rfm_df["recency"], rfm_df["T"])

        logger.info(f"BG/NBD model trained successfully")
        logger.info(f"  Parameters: {bgf.params_}")

        self.bg_nbd_model = bgf
        return bgf

    def train_gamma_gamma(self, rfm_df: pd.DataFrame) -> Any:
        """
        Train Gamma-Gamma model for predicting average order value.

        Args:
            rfm_df: DataFrame with frequency and monetary_value columns

        Returns:
            Trained GammaGammaFitter model
        """
        if not LIFETIMES_AVAILABLE:
            raise ImportError(
                "lifetimes library not installed. Install with: pip install lifetimes"
            )

        logger.info("Training Gamma-Gamma model...")

        ggf = GammaGammaFitter(penalizer_coef=0.01)
        ggf.fit(rfm_df["frequency"], rfm_df["monetary_value"])

        logger.info(f"Gamma-Gamma model trained successfully")
        logger.info(f"  Parameters: {ggf.params_}")

        self.gamma_gamma_model = ggf
        return ggf

    def predict_cltv(self, rfm_df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate CLTV predictions using trained models.

        Args:
            rfm_df: DataFrame with RFM features

        Returns:
            DataFrame with CLTV predictions
        """
        if self.bg_nbd_model is None or self.gamma_gamma_model is None:
            raise ValueError(
                "Models not trained. Call train_bg_nbd() and train_gamma_gamma() first."
            )

        logger.info("Generating CLTV predictions...")

        # Calculate conditional expected purchases for next 12 months
        rfm_df["predicted_purchases_12m"] = (
            self.bg_nbd_model.conditional_expected_number_of_purchases_up_to_time(
                12,  # 12 months
                rfm_df["frequency"],
                rfm_df["recency"],
                rfm_df["T"],
            )
        )

        # Calculate conditional expected purchases for next 3 months (90 days)
        rfm_df["predicted_purchases_90d"] = (
            self.bg_nbd_model.conditional_expected_number_of_purchases_up_to_time(
                3,  # 3 months
                rfm_df["frequency"],
                rfm_df["recency"],
                rfm_df["T"],
            )
        )

        # Calculate probability of being alive
        rfm_df["probability_alive"] = self.bg_nbd_model.conditional_probability_alive(
            rfm_df["frequency"], rfm_df["recency"], rfm_df["T"]
        )

        # Predict average order value
        rfm_df["predicted_avg_order_value"] = (
            self.gamma_gamma_model.conditional_expected_average_profit(
                rfm_df["frequency"], rfm_df["monetary_value"]
            )
        )

        # Calculate CLTV for 12 months
        rfm_df["predicted_clv_12m"] = (
            rfm_df["predicted_purchases_12m"] * rfm_df["predicted_avg_order_value"]
        )

        # Calculate CLTV for 24 months
        predicted_purchases_24m = (
            self.bg_nbd_model.conditional_expected_number_of_purchases_up_to_time(
                24, rfm_df["frequency"], rfm_df["recency"], rfm_df["T"]
            )
        )
        rfm_df["predicted_clv_24m"] = (
            predicted_purchases_24m * rfm_df["predicted_avg_order_value"]
        )

        # Assign CLV tier
        rfm_df["clv_tier"] = pd.cut(
            rfm_df["predicted_clv_24m"],
            bins=[-float("inf"), 500, 2000, 5000, 15000, float("inf")],
            labels=["LOW", "MEDIUM", "HIGH", "PREMIUM", "VIP"],
        ).astype(str)

        logger.info(f"CLTV predictions generated for {len(rfm_df)} patients")

        return rfm_df

    def save_predictions_to_db(self, predictions_df: pd.DataFrame) -> int:
        """
        Save CLTV predictions to the database.

        Args:
            predictions_df: DataFrame with CLTV predictions

        Returns:
            Number of rows inserted
        """
        logger.info("Saving predictions to database...")

        # Clear existing predictions
        self.db.execute_query("DELETE FROM dk.patient_ltv_predictions", return_df=False)

        # Prepare data for insertion
        insert_data = []
        for _, row in predictions_df.iterrows():
            insert_data.append(
                {
                    "patient_id": row["patient_id"],
                    "frequency": int(row["frequency"]),
                    "recency_days": int(row["recency"]),
                    "T_days": int(row["T"]),
                    "monetary_avg": float(row["monetary_value"]),
                    "predicted_purchases_12m": float(row["predicted_purchases_12m"]),
                    "probability_alive": float(row["probability_alive"]),
                    "predicted_clv_12m": float(row["predicted_clv_12m"]),
                    "predicted_clv_24m": float(row["predicted_clv_24m"]),
                    "clv_tier": row["clv_tier"],
                    "model_version": self.model_version,
                }
            )

        # Insert data
        query = """
            INSERT INTO dk.patient_ltv_predictions
            (patient_id, frequency, recency_days, T_days, monetary_avg,
             predicted_purchases_12m, probability_alive, predicted_clv_12m,
             predicted_clv_24m, clv_tier, model_version, calculated_at)
            VALUES
            (:patient_id, :frequency, :recency_days, :T_days, :monetary_avg,
             :predicted_purchases_12m, :probability_alive, :predicted_clv_12m,
             :predicted_clv_24m, :clv_tier, :model_version, CURRENT_TIMESTAMP)
        """

        for data in insert_data:
            self.db.execute_query(query, data, return_df=False)

        logger.info(f"Saved {len(insert_data)} predictions to database")
        return len(insert_data)

    def refresh_materialized_view(self) -> None:
        """Refresh the LTV predictions materialized view."""
        logger.info("Refreshing mvw_patient_ltv_predictions...")
        try:
            self.db.execute_query(
                "REFRESH MATERIALIZED VIEW CONCURRENTLY dk.mvw_patient_ltv_predictions",
                return_df=False,
            )
            logger.info("Materialized view refreshed successfully")
        except Exception as e:
            logger.warning(
                f"Could not refresh concurrently, falling back to regular refresh: {e}"
            )
            self.db.execute_query(
                "REFRESH MATERIALIZED VIEW dk.mvw_patient_ltv_predictions",
                return_df=False,
            )
            logger.info("Materialized view refreshed (non-concurrent)")

    def run_full_pipeline(self) -> Dict[str, Any]:
        """
        Run the complete CLTV modeling pipeline.

        Returns:
            Dictionary with execution summary
        """
        start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("Starting CLTV Model Pipeline")
        logger.info("=" * 60)

        try:
            # Step 1: Load data
            logger.info("Step 1: Loading transaction data...")
            transactions = self.load_transaction_data()
            logger.info(f"  Loaded {len(transactions)} transactions")

            # Step 2: Prepare RFM features
            logger.info("Step 2: Preparing RFM features...")
            rfm = self.prepare_rfm_features(transactions)
            logger.info(f"  Prepared features for {len(rfm)} patients")
            logger.info(f"  Average frequency: {rfm['frequency'].mean():.2f}")
            logger.info(
                f"  Average monetary value: ${rfm['monetary_value'].mean():.2f}"
            )

            # Step 3: Train models
            logger.info("Step 3: Training models...")
            self.train_bg_nbd(rfm)
            self.train_gamma_gamma(rfm)

            # Step 4: Generate predictions
            logger.info("Step 4: Generating predictions...")
            predictions = self.predict_cltv(rfm)

            # Log prediction statistics
            logger.info(
                f"  Average predicted CLTV (12m): ${predictions['predicted_clv_12m'].mean():.2f}"
            )
            logger.info(
                f"  Average predicted CLTV (24m): ${predictions['predicted_clv_24m'].mean():.2f}"
            )
            logger.info(
                f"  Average probability alive: {predictions['probability_alive'].mean():.2%}"
            )
            logger.info("  CLV Tier distribution:")
            for tier, count in (
                predictions["clv_tier"].value_counts().sort_index().items()
            ):
                logger.info(
                    f"    {tier}: {count} patients ({count / len(predictions) * 100:.1f}%)"
                )

            # Step 5: Save to database
            logger.info("Step 5: Saving predictions to database...")
            rows_saved = self.save_predictions_to_db(predictions)

            # Step 6: Refresh materialized view
            logger.info("Step 6: Refreshing materialized view...")
            self.refresh_materialized_view()

            duration = (datetime.now() - start_time).total_seconds()

            logger.info("=" * 60)
            logger.info("CLTV Model Pipeline Complete")
            logger.info(f"  Duration: {duration:.2f} seconds")
            logger.info(f"  Patients processed: {len(predictions)}")
            logger.info(f"  Predictions saved: {rows_saved}")
            logger.info("=" * 60)

            return {
                "status": "SUCCESS",
                "patients_processed": len(predictions),
                "predictions_saved": rows_saved,
                "duration_seconds": duration,
                "model_version": self.model_version,
                "avg_clv_12m": float(predictions["predicted_clv_12m"].mean()),
                "avg_clv_24m": float(predictions["predicted_clv_24m"].mean()),
                "avg_probability_alive": float(predictions["probability_alive"].mean()),
            }

        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            return {
                "status": "FAILED",
                "error": str(e),
                "duration_seconds": (datetime.now() - start_time).total_seconds(),
            }


def main():
    parser = argparse.ArgumentParser(description="CLTV Model for Patient Intelligence")
    parser.add_argument("--train", action="store_true", help="Train models only")
    parser.add_argument(
        "--predict", action="store_true", help="Generate predictions only"
    )
    parser.add_argument(
        "--full", action="store_true", help="Run full pipeline (train + predict)"
    )
    parser.add_argument(
        "--refresh-only", action="store_true", help="Refresh materialized view only"
    )

    args = parser.parse_args()

    if not any([args.train, args.predict, args.full, args.refresh_only]):
        parser.print_help()
        return

    model = CLTVModel()

    if args.refresh_only:
        model.refresh_materialized_view()
        return

    if args.full:
        result = model.run_full_pipeline()
        print("\n" + "=" * 60)
        print("Execution Summary:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        print("=" * 60)
    elif args.train:
        logger.info("Training mode not yet implemented separately. Use --full.")
    elif args.predict:
        logger.info("Prediction mode not yet implemented separately. Use --full.")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    main()
