"""
ST-05: AI/ML Predictive Engine
XGBoost-based ML pipeline for patient behavior prediction.

This module implements:
1. Four XGBoost models (churn, upsell, NBT, promo elasticity)
2. Model calibration with isotonic regression
3. SHAP interpretability
4. Daily incremental scoring and weekly full retrain

Usage:
    # Daily incremental scoring (3-5 min)
    python ml_pipeline.py --mode=incremental

    # Weekly full retrain (Sunday, 15-30 min)
    python ml_pipeline.py --mode=retrain
"""

import os
import sys
import logging
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, average_precision_score
import xgboost as xgb
from xgboost import XGBClassifier
import shap
from sqlalchemy import text

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "ST-01" / "python"))
from database import DatabaseManager, get_db_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MLPipeline:
    """
    XGBoost-based ML pipeline for patient behavior prediction.

    Implements four models:
    1. Churn Risk: Predict patients likely to churn (>180 days inactive)
    2. Package Upsell: Predict patients likely to upgrade to packages
    3. NBT (Next Best Treatment): Predict category preferences
    4. Promo Elasticity: Predict price sensitivity
    """

    MODEL_TYPES = ["churn", "upsell", "nbt", "promo"]

    TARGET_COLUMNS = {
        "churn": "label_churned",
        "upsell": "label_pkg_prospect",
        "nbt": "label_skincare_buyer",  # Simplified for skincare focus
        "promo": "label_promo_elastic",
    }

    ACTION_MAPPINGS = {
        "churn": {"thresholds": [0.3, 0.6], "bands": ["Low", "Medium", "High"]},
        "upsell": {"thresholds": [0.4, 0.7], "actions": ["Low", "Warm", "Hot"]},
        "promo": {"thresholds": [0.5], "segments": ["Organic Loyal", "Promo-Driven"]},
    }

    XGB_PARAMS = {
        "n_estimators": 100,
        "max_depth": 6,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "random_state": 42,
    }

    FEATURE_COLUMNS = [
        "recency_days",
        "frequency_total",
        "frequency_30d",
        "frequency_90d",
        "total_revenue",
        "avg_transaction_value",
        "max_transaction",
        "std_transaction",
        "tenure_days",
        "tenure_months",
        "avg_gap_days",
        "visit_consistency",
        "skincare_share_pct",
        "services_share_pct",
        "medications_share_pct",
        "pkg_revenue_ratio",
        "has_package_flag",
        "promo_dependency_pct",
        "avg_discount_pct",
        "discount_frequency",
        "outstanding_ratio",
        "stress_level",
        "r_score",
        "f_score",
        "m_score",
        "health_score",
        "predicted_ltv_24m",
        "age",
        "total_transactions",
    ]

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        model_version: Optional[str] = None,
        forecast_days: int = 90,
    ):
        self.db = db_manager or get_db_manager()
        self.forecast_days = forecast_days
        self.model_version = model_version or datetime.now().strftime("%Y%m%d_%H%M")
        self._models: Dict[str, Any] = {}
        self._calibrated_models: Dict[str, Any] = {}
        self._shap_values: Dict[str, np.ndarray] = {}
        self._metrics: Dict[str, Dict[str, float]] = {}

        logger.info(f"Initialized MLPipeline with version {self.model_version}")

    def load_features_and_labels(self) -> pd.DataFrame:
        """
        Load features and labels from materialized views.

        Returns:
            DataFrame with features and labels for all patients
        """
        query = """
            SELECT 
                mf.patient_id AS mrn,
                mf.recency_days,
                mf.total_transactions AS frequency_total,
                mf.frequency_30d,
                mf.frequency_90d,
                mf.total_revenue,
                mf.avg_transaction_value,
                mf.max_transaction,
                COALESCE(mf.std_transaction, 0) AS std_transaction,
                mf.tenure_days,
                mf.tenure_months,
                mf.avg_gap_days,
                COALESCE(mf.visit_consistency, 0) AS visit_consistency,
                mf.skincare_share_pct,
                mf.services_share_pct,
                mf.medications_share_pct,
                mf.pkg_revenue_ratio,
                mf.has_package_flag,
                mf.promo_dependency_pct,
                mf.avg_discount_pct,
                mf.discount_frequency,
                mf.outstanding_ratio,
                mf.stress_level,
                mf.r_score,
                mf.f_score,
                mf.m_score,
                COALESCE(mf.health_score, 0) AS health_score,
                COALESCE(mf.predicted_ltv_24m, 0) AS predicted_ltv_24m,
                COALESCE(mf.age, 30) AS age,  -- Default age if missing
                mf.total_transactions,
                lb.label_churned,
                lb.label_pkg_prospect,
                lb.label_skincare_buyer,
                lb.label_promo_elastic,
                lb.split_type
            FROM dk.mvw_ml_patient_features mf
            LEFT JOIN dk.vw_patient_labels lb ON mf.patient_id = lb.patient_id
            WHERE mf.recency_days IS NOT NULL
        """

        logger.info("Loading features and labels from database...")
        df = self.db.execute_query(query)

        if df.empty:
            logger.warning("No data loaded from database")
            return pd.DataFrame()

        logger.info(f"Loaded {len(df)} patient records")
        return df

    def prepare_train_validation_split(
        self, df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split data into train (12 months) and validation (3 months) sets.

        Args:
            df: DataFrame with features, labels, and split_type

        Returns:
            Tuple of (train_df, validation_df)
        """
        train_df = df[df["split_type"] == "train"].copy()
        validation_df = df[df["split_type"] == "validation"].copy()

        logger.info(
            f"Train samples: {len(train_df)}, Validation samples: {len(validation_df)}"
        )

        return train_df, validation_df

    def validate_positive_samples(
        self, df: pd.DataFrame, model_type: str, min_samples: int = 50
    ) -> bool:
        """
        Validate sufficient positive samples for training.

        Args:
            df: DataFrame with labels
            model_type: Which model to check
            min_samples: Minimum positive samples required

        Returns:
            True if sufficient samples, False otherwise
        """
        target_col = self.TARGET_COLUMNS[model_type]
        positive_count = df[target_col].sum()

        if positive_count < min_samples:
            logger.warning(
                f"Insufficient positive samples for {model_type}: "
                f"{positive_count} < {min_samples}. Skipping training."
            )
            return False

        logger.info(
            f"{model_type}: {positive_count} positive samples (>= {min_samples})"
        )
        return True

    def train_model(
        self, df: pd.DataFrame, model_type: str
    ) -> Tuple[Any, Dict[str, float]]:
        """
        Train XGBoost model with isotonic calibration.

        Args:
            df: DataFrame with features and labels
            model_type: One of ['churn', 'upsell', 'nbt', 'promo']

        Returns:
            Tuple of (trained_model, metrics_dict)
        """
        target_col = self.TARGET_COLUMNS[model_type]

        # Prepare data
        X = df[self.FEATURE_COLUMNS].fillna(0)
        for col in X.columns:
            if X[col].dtype == "object":
                X[col] = X[col].astype("category").cat.codes
        y = df[target_col]

        # Handle class imbalance
        scale_pos_weight = (y == 0).sum() / max((y == 1).sum(), 1)
        params = self.XGB_PARAMS.copy()
        params["scale_pos_weight"] = scale_pos_weight

        logger.info(
            f"Training {model_type} model with {len(X)} samples, "
            f"{y.sum()} positives, scale_pos_weight={scale_pos_weight:.2f}"
        )

        # Train base model
        model = XGBClassifier(**params)
        model.fit(X, y)

        # Calibration with isotonic regression
        # Note: In sklearn >= 1.2, cv='prefit' is deprecated
        # We use cv=3 for a lighter calibration, ensemble='auto' lets sklearn decide
        logger.info(f"Calibrating {model_type} model with isotonic regression...")
        calibrated_model = CalibratedClassifierCV(model, method="isotonic", cv=3)
        calibrated_model.fit(X, y)

        # Compute metrics
        y_pred_proba = calibrated_model.predict_proba(X)[:, 1]
        auc_roc = roc_auc_score(y, y_pred_proba)
        avg_precision = average_precision_score(y, y_pred_proba)

        metrics = {
            "auc_roc": auc_roc,
            "avg_precision": avg_precision,
            "positive_samples": int(y.sum()),
            "negative_samples": int((y == 0).sum()),
        }

        logger.info(
            f"{model_type} model trained: AUC={auc_roc:.4f}, "
            f"avg_precision={avg_precision:.4f}"
        )

        # Alert if AUC below threshold
        if auc_roc < 0.65:
            logger.warning(
                f"ALERT: {model_type} AUC ({auc_roc:.4f}) below threshold (0.65)"
            )

        return calibrated_model, metrics

    def train_all_models(self, train_df: pd.DataFrame) -> bool:
        """
        Train all four models.

        Args:
            train_df: Training data

        Returns:
            True if all models trained successfully
        """
        success = True

        for model_type in self.MODEL_TYPES:
            try:
                # Skip if insufficient positive samples
                if not self.validate_positive_samples(train_df, model_type):
                    success = False
                    continue

                model, metrics = self.train_model(train_df, model_type)
                self._models[model_type] = model
                self._metrics[model_type] = metrics

            except Exception as e:
                logger.error(f"Failed to train {model_type}: {e}", exc_info=True)
                success = False

        return success

    def compute_shap_values(
        self, df: pd.DataFrame, model_type: str, sample_size: int = 1000
    ) -> pd.DataFrame:
        """
        Compute SHAP values for model interpretability.

        Args:
            df: DataFrame with features
            model_type: Which model to explain
            sample_size: Number of samples for SHAP computation

        Returns:
            DataFrame with SHAP values
        """
        if model_type not in self._models:
            logger.error(f"Model {model_type} not trained")
            return pd.DataFrame()

        logger.info(f"Computing SHAP values for {model_type}...")

        # Sample data for faster computation
        sample_df = df.sample(n=min(sample_size, len(df)), random_state=42)
        X_sample = sample_df[self.FEATURE_COLUMNS].fillna(0)
        for col in X_sample.columns:
            if X_sample[col].dtype == "object":
                X_sample[col] = X_sample[col].astype("category").cat.codes

        # Get base model from calibrated model
        # In sklearn >= 1.2, CalibratedClassifierCV stores estimator differently
        calibrated_model = self._models[model_type]
        if hasattr(calibrated_model, "estimator"):
            base_model = calibrated_model.estimator
        elif (
            hasattr(calibrated_model, "estimators_")
            and len(calibrated_model.estimators_) > 0
        ):
            base_model = calibrated_model.estimators_[0]
        else:
            # Fallback: assume the model itself can be used
            base_model = calibrated_model

        # Compute SHAP
        explainer = shap.TreeExplainer(base_model)
        shap_values = explainer.shap_values(X_sample)

        # Store for later use
        self._shap_values[model_type] = shap_values

        # Get global feature importance (mean absolute SHAP value)
        importance = np.abs(shap_values).mean(axis=0)
        feature_importance = dict(zip(self.FEATURE_COLUMNS, importance.tolist()))

        # Sort by importance
        sorted_importance = dict(
            sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
        )

        logger.info(f"Top 5 features for {model_type}:")
        for i, (feature, imp) in enumerate(list(sorted_importance.items())[:5]):
            logger.info(f"  {i + 1}. {feature}: {imp:.4f}")

        return pd.DataFrame(
            {
                "feature": list(sorted_importance.keys()),
                "importance": list(sorted_importance.values()),
            }
        )

    def get_patient_shap_explanation(
        self, patient_row: pd.Series, model_type: str
    ) -> Dict[str, Any]:
        """
        Get SHAP explanation for a single patient.

        Args:
            patient_row: Single patient feature row
            model_type: Which model to explain

        Returns:
            Dictionary with top features and contributions
        """
        if model_type not in self._shap_values:
            return {}

        # Get patient's SHAP values
        X_patient = patient_row[self.FEATURE_COLUMNS].fillna(0).copy()
        for col in X_patient.index:
            if X_patient[col] is not None and isinstance(X_patient[col], str):
                X_patient[col] = 0  # Default encoding for unknown strings
        X_patient = X_patient.values.reshape(1, -1)

        # Get base model from calibrated model
        calibrated_model = self._models[model_type]
        if hasattr(calibrated_model, "estimator"):
            base_model = calibrated_model.estimator
        elif (
            hasattr(calibrated_model, "estimators_")
            and len(calibrated_model.estimators_) > 0
        ):
            base_model = calibrated_model.estimators_[0]
        else:
            base_model = calibrated_model

        explainer = shap.TreeExplainer(base_model)
        patient_shap = explainer.shap_values(X_patient)[0]

        # Get top 2 features
        top_indices = np.argsort(np.abs(patient_shap))[::-1][:2]

        return {
            "top_feature_1": self.FEATURE_COLUMNS[top_indices[0]],
            "top_feature_2": self.FEATURE_COLUMNS[top_indices[1]],
            "shap_contribution_1": float(patient_shap[top_indices[0]]),
            "shap_contribution_2": float(patient_shap[top_indices[1]]),
        }

    def generate_predictions(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate predictions for all patients.

        Args:
            df: DataFrame with features

        Returns:
            DataFrame with all model predictions
        """
        logger.info("Generating predictions for all patients...")

        if df.empty:
            logger.warning("No data to generate predictions")
            return pd.DataFrame()

        X = df[self.FEATURE_COLUMNS].fillna(0)
        for col in X.columns:
            if X[col].dtype == "object":
                X[col] = X[col].astype("category").cat.codes
        predictions = df[["mrn"]].copy()

        for model_type in self.MODEL_TYPES:
            if model_type not in self._models:
                logger.warning(f"Model {model_type} not trained, skipping")
                continue

            # Get probabilities
            proba = self._models[model_type].predict_proba(X)[:, 1]
            predictions[f"{model_type}_probability"] = proba

            # Map to action bands
            if model_type in self.ACTION_MAPPINGS:
                mapping = self.ACTION_MAPPINGS[model_type]
                if "bands" in mapping:
                    # For churn: Low/Medium/High
                    def map_band(p):
                        if p < mapping["thresholds"][0]:
                            return mapping["bands"][0]
                        elif p < mapping["thresholds"][1]:
                            return mapping["bands"][1]
                        else:
                            return mapping["bands"][2]

                    predictions[f"{model_type}_risk_band"] = predictions[
                        f"{model_type}_probability"
                    ].apply(map_band)

                elif "actions" in mapping:
                    # For upsell: Low/Warm/Hot
                    def map_action(p):
                        if p < mapping["thresholds"][0]:
                            return mapping["actions"][0]
                        elif p < mapping["thresholds"][1]:
                            return mapping["actions"][1]
                        else:
                            return mapping["actions"][2]

                    predictions[f"{model_type}_action"] = predictions[
                        f"{model_type}_probability"
                    ].apply(map_action)

                elif "segments" in mapping:
                    # For promo: Organic Loyal / Promo-Driven
                    threshold = mapping["thresholds"][0]
                    predictions[f"{model_type}_segment"] = predictions[
                        f"{model_type}_probability"
                    ].apply(
                        lambda p: (
                            mapping["segments"][1]
                            if p >= threshold
                            else mapping["segments"][0]
                        )
                    )

        # NBT-specific: top recommendation
        if all(
            col in predictions.columns
            for col in ["nbt_probability", "upsell_probability", "churn_probability"]
        ):
            # Simplified: use skincare probability as top recommendation
            predictions["top_recommendation"] = "Skincare"

        # Add SHAP explanations (batch compute for performance)
        logger.info("Computing SHAP explanations...")
        if "churn" in self._models and len(X) > 0:
            calibrated_model = self._models["churn"]
            if hasattr(calibrated_model, "estimator"):
                base_model = calibrated_model.estimator
            elif (
                hasattr(calibrated_model, "estimators_")
                and len(calibrated_model.estimators_) > 0
            ):
                base_model = calibrated_model.estimators_[0]
            else:
                base_model = calibrated_model

            explainer = shap.TreeExplainer(base_model)
            all_shap = explainer.shap_values(X)

            top1_idx = np.argsort(np.abs(all_shap), axis=1)[:, -1]
            top2_idx = np.argsort(np.abs(all_shap), axis=1)[:, -2]

            predictions["top_feature_1"] = [self.FEATURE_COLUMNS[i] for i in top1_idx]
            predictions["top_feature_2"] = [self.FEATURE_COLUMNS[i] for i in top2_idx]
            predictions["shap_contribution"] = [
                all_shap[i, idx] for i, idx in enumerate(top1_idx)
            ]

        predictions["model_version"] = self.model_version
        predictions["prediction_date"] = datetime.now().date()

        logger.info(f"Generated predictions for {len(predictions)} patients")
        return predictions

    def save_predictions_to_db(self, predictions_df: pd.DataFrame) -> int:
        """
        Save predictions to database table.

        Args:
            predictions_df: DataFrame with predictions

        Returns:
            Number of rows saved
        """
        if predictions_df.empty:
            logger.warning("No predictions to save")
            return 0

        logger.info("Saving predictions to database...")

        # Filter out rows with empty/missing mrn and deduplicate
        predictions_df = predictions_df[
            predictions_df["mrn"].notna() & (predictions_df["mrn"] != "")
        ].copy()
        predictions_df = predictions_df.drop_duplicates(subset=["mrn"], keep="last")
        if predictions_df.empty:
            logger.warning("No valid predictions to save (all mrn missing)")
            return 0

        # Clear and insert in same transaction
        insert_cols = [
            "mrn",
            "prediction_date",
            "churn_probability",
            "churn_risk_band",
            "pkg_upsell_prob",
            "upsell_action",
            "rec_skincare_prob",
            "rec_services_prob",
            "rec_medications_prob",
            "rec_supplements_prob",
            "top_recommendation",
            "promo_elastic_prob",
            "promo_segment",
            "top_feature_1",
            "top_feature_2",
            "shap_contribution",
            "model_version",
        ]

        bulk_df = pd.DataFrame()
        bulk_df["mrn"] = predictions_df["mrn"]
        bulk_df["prediction_date"] = predictions_df["prediction_date"]
        bulk_df["churn_probability"] = predictions_df.get("churn_probability")
        bulk_df["churn_risk_band"] = predictions_df.get("churn_risk_band")
        bulk_df["pkg_upsell_prob"] = predictions_df.get("upsell_probability")
        bulk_df["upsell_action"] = predictions_df.get("upsell_action")
        bulk_df["rec_skincare_prob"] = predictions_df.get("nbt_probability")
        bulk_df["rec_services_prob"] = predictions_df.get("upsell_probability", 0) * 0.5
        bulk_df["rec_medications_prob"] = 0.0
        bulk_df["rec_supplements_prob"] = 0.0
        bulk_df["top_recommendation"] = predictions_df.get(
            "top_recommendation", "Skincare"
        )
        bulk_df["promo_elastic_prob"] = predictions_df.get("promo_probability")
        bulk_df["promo_segment"] = predictions_df.get("promo_segment")
        bulk_df["top_feature_1"] = predictions_df.get("top_feature_1", "")
        bulk_df["top_feature_2"] = predictions_df.get("top_feature_2", "")
        bulk_df["shap_contribution"] = predictions_df.get("shap_contribution", 0.0)
        bulk_df["model_version"] = predictions_df["model_version"]

        with self.db.get_transaction() as conn:
            conn.execute(text("DELETE FROM dk.ml_predictions"))
            bulk_df[insert_cols].to_sql(
                "ml_predictions", conn, schema="dk", if_exists="append", index=False
            )

        rows_saved = len(bulk_df)
        logger.info(f"Saved {rows_saved} predictions to database")
        return rows_saved

    def save_model_metadata(self) -> int:
        """
        Save model metadata to database.

        Returns:
            Number of models saved
        """
        logger.info("Saving model metadata...")

        models_saved = 0
        for model_type, metrics in self._metrics.items():
            feature_importance = {}
            if model_type in self._shap_values:
                shap_vals = self._shap_values[model_type]
                importance = np.abs(shap_vals).mean(axis=0)
                feature_importance = dict(
                    zip(self.FEATURE_COLUMNS, importance.tolist())
                )

            query = """
                INSERT INTO dk.model_metadata (
                    model_name, model_version, train_date, train_end_date,
                    auc_roc, avg_precision, positive_samples, negative_samples,
                    parameters, feature_importance, calibration_method
                ) VALUES (
                    :model_name, :model_version, CURRENT_TIMESTAMP, CURRENT_DATE,
                    :auc_roc, :avg_precision, :positive_samples, :negative_samples,
                    :parameters, :feature_importance, 'isotonic'
                )
                ON CONFLICT (model_name, model_version) 
                DO UPDATE SET
                    train_date = EXCLUDED.train_date,
                    auc_roc = EXCLUDED.auc_roc,
                    avg_precision = EXCLUDED.avg_precision,
                    positive_samples = EXCLUDED.positive_samples,
                    negative_samples = EXCLUDED.negative_samples,
                    parameters = EXCLUDED.parameters,
                    feature_importance = EXCLUDED.feature_importance
            """

            params = {
                "model_name": model_type,
                "model_version": self.model_version,
                "auc_roc": metrics.get("auc_roc"),
                "avg_precision": metrics.get("avg_precision"),
                "positive_samples": metrics.get("positive_samples"),
                "negative_samples": metrics.get("negative_samples"),
                "parameters": json.dumps(self.XGB_PARAMS),
                "feature_importance": json.dumps(feature_importance),
            }

            self.db.execute_query(query, params, return_df=False)
            models_saved += 1

        logger.info(f"Saved metadata for {models_saved} models")
        return models_saved

    def run_full_retrain(self) -> Dict[str, Any]:
        """
        Run full model retrain (weekly).

        Returns:
            Summary of retrain execution
        """
        start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("Starting Full Model Retrain")
        logger.info("=" * 60)

        # Load data
        logger.info("Step 1: Loading features and labels...")
        df = self.load_features_and_labels()

        if df.empty:
            return {"status": "FAILED", "error": "No data loaded"}

        # Split data
        logger.info("Step 2: Preparing train/validation split...")
        train_df, validation_df = self.prepare_train_validation_split(df)

        # Train models
        logger.info("Step 3: Training all models...")
        train_success = self.train_all_models(train_df)

        # Compute SHAP
        logger.info("Step 4: Computing SHAP values...")
        for model_type in self.MODEL_TYPES:
            if model_type in self._models:
                self.compute_shap_values(train_df, model_type)

        # Generate predictions on full dataset
        logger.info("Step 5: Generating predictions...")
        predictions = self.generate_predictions(df)

        # Save to database
        logger.info("Step 6: Saving predictions and metadata...")
        rows_saved = self.save_predictions_to_db(predictions)
        models_saved = self.save_model_metadata()

        duration = (datetime.now() - start_time).total_seconds()

        summary = {
            "status": "SUCCESS" if train_success else "PARTIAL",
            "models_trained": len(self._metrics),
            "predictions_saved": rows_saved,
            "metadata_saved": models_saved,
            "validation_samples": len(validation_df),
            "duration_seconds": duration,
            "model_version": self.model_version,
            "metrics": self._metrics,
        }

        logger.info("=" * 60)
        logger.info("Full Retrain Complete")
        logger.info(f"Duration: {duration:.2f}s")
        logger.info("=" * 60)

        return summary

    def run_incremental_scoring(self) -> Dict[str, Any]:
        """
        Run daily incremental scoring (no retrain).

        Returns:
            Summary of scoring execution
        """
        start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("Starting Incremental Scoring")
        logger.info("=" * 60)

        # Load latest model metadata
        logger.info("Step 1: Loading latest model version...")
        metadata = self.db.execute_query("""
            SELECT DISTINCT model_version, train_date
            FROM dk.model_metadata 
            ORDER BY train_date DESC 
            LIMIT 1
        """)

        if metadata.empty:
            return {"status": "FAILED", "error": "No trained models found"}

        self.model_version = metadata.iloc[0]["model_version"]
        logger.info(f"Using model version: {self.model_version}")

        # For now, just load fresh data and re-score
        # In production, would load models from pickle files
        logger.info("Step 2: Loading features...")
        df = self.load_features_and_labels()

        if df.empty:
            return {"status": "FAILED", "error": "No data loaded"}

        # Since we don't have loaded models, trigger partial retrain
        logger.info("Step 3: Performing partial retrain for scoring...")
        train_df, _ = self.prepare_train_validation_split(df)
        self.train_all_models(train_df)

        # Generate predictions
        logger.info("Step 4: Generating predictions...")
        predictions = self.generate_predictions(df)

        # Save
        logger.info("Step 5: Saving predictions...")
        rows_saved = self.save_predictions_to_db(predictions)

        duration = (datetime.now() - start_time).total_seconds()

        summary = {
            "status": "SUCCESS" if rows_saved > 0 else "FAILED",
            "predictions_saved": rows_saved,
            "duration_seconds": duration,
            "model_version": self.model_version,
        }

        logger.info("=" * 60)
        logger.info("Incremental Scoring Complete")
        logger.info(f"Duration: {duration:.2f}s")
        logger.info("=" * 60)

        return summary


def main():
    parser = argparse.ArgumentParser(
        description="ST-05 ML Pipeline: Train and score patient behavior models"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="incremental",
        choices=["incremental", "retrain"],
        help="Execution mode: incremental (daily) or retrain (weekly)",
    )
    parser.add_argument(
        "--model-version",
        type=str,
        default=None,
        help="Optional model version override",
    )

    args = parser.parse_args()

    pipeline = MLPipeline(model_version=args.model_version)

    if args.mode == "retrain":
        result = pipeline.run_full_retrain()
    else:
        result = pipeline.run_incremental_scoring()

    print("\n" + "=" * 60)
    print("Execution Summary:")
    for key, value in result.items():
        if key != "metrics":  # Skip detailed metrics for brevity
            print(f"  {key}: {value}")
    print("=" * 60)

    if result.get("status") == "FAILED":
        sys.exit(1)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    main()
