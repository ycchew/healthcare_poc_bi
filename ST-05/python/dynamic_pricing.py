"""
ST-05: AI/ML Predictive Engine
Dynamic Pricing Engine for personalized offers.

This module implements:
1. Dynamic pricing based on ML predictions (promo elasticity, churn risk, package upsell)
2. Offer priority scoring
3. Maximum discount caps based on value tier
4. Personalized offer generation

Usage:
    # Initialize pricing engine
    from ST_05.python.dynamic_pricing import PricingEngine
    from ST_01.python.database import get_db_manager

    db = get_db_manager()
    engine = PricingEngine(db_manager=db)

    # Generate offers for all patients
    offers_df = engine.generate_all_offers()

    # Get personalized offer for specific patient
    offer = engine.get_patient_offer("patient_mrn_123")

    # Calculate discount for specific scenario
    discount = engine.calculate_discount(
        promo_elastic_prob=0.75,
        churn_prob=0.3,
        upsell_prob=0.6,
        value_tier="High"
    )
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

import pandas as pd
import numpy as np

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "ST-01" / "python"))
from database import DatabaseManager, get_db_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class OfferType(Enum):
    """Types of offers in the dynamic pricing engine."""

    DISCOUNT = "discount"
    BUNDLE = "bundle"
    RETENTION = "retention"
    VIP_PERK = "vip_perk"
    WIN_BACK = "win_back"
    WELCOME = "welcome"
    STANDARD = "standard"


class RFMSegment(Enum):
    """RFM customer segments."""

    CHAMPIONS = "Champions"
    LOYAL_CUSTOMERS = "Loyal Customers"
    NEW_CUSTOMERS = "New Customers"
    POTENTIAL_LOYALISTS = "Potential Loyalists"
    NEED_ATTENTION = "Need Attention"
    AT_RISK = "At Risk"
    CANNOT_LOSE_THEM = "Cannot Lose Them"
    LOST = "Lost"
    HIBERNATING = "Hibernating"


@dataclass
class OfferConfig:
    """Configuration for offer generation."""

    offer_type: str
    discount_pct: int
    max_discount_rm: float
    priority_score: int
    recommended_action: str


class PricingEngine:
    """
    Dynamic pricing engine for personalized offers.

    Uses ML predictions (churn risk, promo elasticity, package upsell)
    combined with RFM segmentation to generate personalized pricing offers.

    Features:
    - Dynamic pricing based on ML predictions
    - Offer priority scoring
    - Maximum discount caps based on value tier
    - Personalized offer generation
    """

    # Value tier discount caps (in RM)
    VALUE_TIER_CAPS = {
        "Premium": 500,
        "High": 300,
        "Medium": 150,
        "Low": 100,
        "default": 100,
    }

    # Promo elasticity discount thresholds
    ELASTICITY_THRESHOLDS = [
        (0.8, 25),  # >80% elasticity = 25% discount
        (0.7, 20),  # >70% elasticity = 20% discount
        (0.6, 15),  # >60% elasticity = 15% discount
    ]

    # Churn risk discount thresholds
    CHURN_THRESHOLDS = [
        (0.8, 20),  # >80% churn risk = 20% discount
        (0.7, 15),  # >70% churn risk = 15% discount
    ]

    # Package upsell discount thresholds
    UPSELL_THRESHOLDS = [
        (0.7, 15),  # >70% upsell probability = 15% discount
    ]

    # RFM segment discounts
    RFM_DISCOUNTS = {
        "Champions": 10,
        "Loyal Customers": 10,
        "At Risk": 15,
        "Cannot Lose Them": 15,
        "New Customers": 10,
        "default": 5,
    }

    # Offer priority weights
    PRIORITY_WEIGHTS = {"churn": 0.4, "promo": 0.3, "upsell": 0.3}

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        default_forecast_days: int = 90,
    ):
        """
        Initialize the pricing engine.

        Args:
            db_manager: Database manager instance
            default_forecast_days: Days to look ahead for predictions
        """
        self.db = db_manager or get_db_manager()
        self.default_forecast_days = default_forecast_days
        self._offer_cache: Dict[str, OfferConfig] = {}

        logger.info("Initialized PricingEngine")

    def get_patient_scores(self, mrn: Optional[str] = None) -> pd.DataFrame:
        """
        Get ML prediction scores for patient(s).

        Args:
            mrn: Patient MRN (optional, returns all if None)

        Returns:
            DataFrame with promo_elastic_prob, pkg_upsell_prob,
            churn_probability, value_tier, rfm_segment
        """
        if mrn:
            where_clause = f"WHERE mp.mrn = '{mrn}'"
        else:
            where_clause = ""

        query = f"""
            SELECT 
                mp.mrn,
                COALESCE(mp.promo_elastic_prob, 0) AS promo_elastic_prob,
                COALESCE(mp.pkg_upsell_prob, 0) AS pkg_upsell_prob,
                COALESCE(mp.churn_probability, 0) AS churn_probability,
                COALESCE(mp.promo_segment, 'Organic Loyal') AS promo_segment,
                COALESCE(mp.upsell_action, 'Low') AS upsell_action,
                COALESCE(mp.churn_risk_band, 'Low') AS churn_risk_band,
                COALESCE(pe.value_tier, 'Low') AS value_tier,
                COALESCE(pe.patient_status, 'Active') AS patient_status,
                COALESCE(pr.segment, 'Hibernating') AS rfm_segment,
                COALESCE(pr.priority, 7) AS rfm_priority
            FROM dk.ml_predictions mp
            LEFT JOIN dk.vw_patient_enriched pe ON mp.mrn = pe.mrn
            LEFT JOIN dk.vw_patient_rfm pr ON mp.mrn = pr.patient_id
            {where_clause}
        """

        logger.info(f"Fetching patient scores{' for ' + mrn if mrn else ''}")
        result = self.db.execute_query(query)

        if result.empty:
            logger.warning(
                f"No scores found for patient {mrn}" if mrn else "No scores found"
            )
            return pd.DataFrame()

        logger.info(f"Retrieved scores for {len(result)} patient(s)")
        return result

    def determine_offer_type(self, row: pd.Series) -> str:
        """
        Determine offer type based on ML predictions and segmentation.

        Logic (from SQL view vw_dynamic_pricing):
        - High promo elasticity (>0.7): offer discount
        - Package upsell opportunity (>0.6): offer bundle
        - High churn risk (>0.7): offer retention deal
        - Loyal customer (Champions, Loyal): offer VIP perk
        - At risk: offer win-back deal
        - New customer: offer welcome deal
        - Default: standard offer

        Args:
            row: Patient score row

        Returns:
            Offer type string
        """
        promo_elastic_prob = row.get("promo_elastic_prob", 0)
        pkg_upsell_prob = row.get("pkg_upsell_prob", 0)
        churn_probability = row.get("churn_probability", 0)
        rfm_segment = row.get("rfm_segment", "")

        # High promo elasticity: offer discount
        if promo_elastic_prob > 0.7:
            return OfferType.DISCOUNT.value

        # Package upsell opportunity: offer bundle
        if pkg_upsell_prob > 0.6:
            return OfferType.BUNDLE.value

        # High churn risk: offer retention deal
        if churn_probability > 0.7:
            return OfferType.RETENTION.value

        # Loyal customer: offer VIP perk
        if rfm_segment in ["Champions", "Loyal Customers"]:
            return OfferType.VIP_PERK.value

        # At risk: offer win-back deal
        if rfm_segment in ["At Risk", "Cannot Lose Them"]:
            return OfferType.WIN_BACK.value

        # New customer: offer welcome deal
        if rfm_segment == "New Customers":
            return OfferType.WELCOME.value

        # Default: standard offer
        return OfferType.STANDARD.value

    def calculate_discount_percentage(self, row: pd.Series) -> int:
        """
        Calculate discount percentage based on elasticity and segment.

        Logic (from SQL view vw_dynamic_pricing):
        - Promo elasticity driven: 15-25%
        - Package upsell: 15%
        - Churn risk: 15-20%
        - Loyal customers: 10%
        - At risk: 15%
        - New customers: 10%
        - Default: 5%

        Args:
            row: Patient score row

        Returns:
            Discount percentage (5-25)
        """
        promo_elastic_prob = row.get("promo_elastic_prob", 0)
        pkg_upsell_prob = row.get("pkg_upsell_prob", 0)
        churn_probability = row.get("churn_probability", 0)
        rfm_segment = row.get("rfm_segment", "")

        # Promo elasticity driven (highest priority)
        if promo_elastic_prob > 0.8:
            return 25
        if promo_elastic_prob > 0.7:
            return 20
        if promo_elastic_prob > 0.6:
            return 15

        # Package upsell
        if pkg_upsell_prob > 0.7:
            return 15

        # Churn risk
        if churn_probability > 0.8:
            return 20
        if churn_probability > 0.7:
            return 15

        # RFM segments
        if rfm_segment in ["Champions", "Loyal Customers"]:
            return 10
        if rfm_segment in ["At Risk", "Cannot Lose Them"]:
            return 15
        if rfm_segment == "New Customers":
            return 10

        # Default
        return 5

    def calculate_max_discount_cap(self, value_tier: str) -> float:
        """
        Calculate maximum discount cap based on value tier.

        Args:
            value_tier: Patient value tier (Premium, High, Medium, Low)

        Returns:
            Maximum discount in RM
        """
        return self.VALUE_TIER_CAPS.get(value_tier, self.VALUE_TIER_CAPS["default"])

    def calculate_offer_priority(self, row: pd.Series) -> int:
        """
        Calculate offer priority score (higher = more urgent).

        Formula (from SQL view):
        priority = (churn_prob * 0.4 + promo_elastic * 0.3 + upsell_prob * 0.3) * 100

        Args:
            row: Patient score row

        Returns:
            Priority score (0-100)
        """
        churn_prob = row.get("churn_probability", 0)
        promo_elastic = row.get("promo_elastic_prob", 0)
        upsell_prob = row.get("pkg_upsell_prob", 0)

        priority = (
            churn_prob * self.PRIORITY_WEIGHTS["churn"]
            + promo_elastic * self.PRIORITY_WEIGHTS["promo"]
            + upsell_prob * self.PRIORITY_WEIGHTS["upsell"]
        ) * 100

        return round(priority)

    def get_recommended_action(self, row: pd.Series) -> str:
        """
        Get recommended action based on patient scores.

        Args:
            row: Patient score row

        Returns:
            Recommended action string
        """
        churn_probability = row.get("churn_probability", 0)
        pkg_upsell_prob = row.get("pkg_upsell_prob", 0)
        promo_elastic_prob = row.get("promo_elastic_prob", 0)
        rfm_segment = row.get("rfm_segment", "")

        if churn_probability > 0.7:
            return "Immediate outreach with retention offer"

        if pkg_upsell_prob > 0.6:
            return "Suggest package bundle during next visit"

        if promo_elastic_prob > 0.7:
            return "Send targeted promo campaign"

        if rfm_segment in ["Champions", "Loyal Customers"]:
            return "Invite to VIP program"

        return "Standard engagement"

    def generate_patient_offer(self, row: pd.Series) -> OfferConfig:
        """
        Generate complete offer configuration for a patient.

        Args:
            row: Patient score row

        Returns:
            OfferConfig with all offer details
        """
        offer_type = self.determine_offer_type(row)
        discount_pct = self.calculate_discount_percentage(row)
        value_tier = row.get("value_tier", "Low")
        max_discount_rm = self.calculate_max_discount_cap(value_tier)
        priority_score = self.calculate_offer_priority(row)
        recommended_action = self.get_recommended_action(row)

        return OfferConfig(
            offer_type=offer_type,
            discount_pct=discount_pct,
            max_discount_rm=max_discount_rm,
            priority_score=priority_score,
            recommended_action=recommended_action,
        )

    def get_patient_offer(self, mrn: str) -> Optional[Dict[str, Any]]:
        """
        Get personalized offer for a specific patient.

        Args:
            mrn: Patient MRN

        Returns:
            Dictionary with offer details or None if patient not found
        """
        scores_df = self.get_patient_scores(mrn)

        if scores_df.empty:
            return None

        row = scores_df.iloc[0]
        offer = self.generate_patient_offer(row)

        result = {
            "mrn": mrn,
            "offer_type": offer.offer_type,
            "discount_pct": offer.discount_pct,
            "max_discount_rm": offer.max_discount_rm,
            "offer_priority": offer.priority_score,
            "recommended_action": offer.recommended_action,
            "generated_at": datetime.now().isoformat(),
            # Include underlying scores for transparency
            "promo_elastic_prob": row.get("promo_elastic_prob", 0),
            "pkg_upsell_prob": row.get("pkg_upsell_prob", 0),
            "churn_probability": row.get("churn_probability", 0),
            "value_tier": row.get("value_tier", "Low"),
            "rfm_segment": row.get("rfm_segment", "Hibernating"),
        }

        logger.info(
            f"Generated offer for {mrn}: {offer.offer_type} ({offer.discount_pct}% discount)"
        )
        return result

    def generate_all_offers(self) -> pd.DataFrame:
        """
        Generate offers for all patients with ML predictions.

        Returns:
            DataFrame with all patient offers
        """
        logger.info("Generating offers for all patients...")
        scores_df = self.get_patient_scores()

        if scores_df.empty:
            logger.warning("No patient scores available for offer generation")
            return pd.DataFrame()

        # Generate offers for each patient
        offers = []
        for idx, row in scores_df.iterrows():
            offer = self.generate_patient_offer(row)
            offers.append(
                {
                    "mrn": row["mrn"],
                    "offer_type": offer.offer_type,
                    "discount_pct": offer.discount_pct,
                    "max_discount_rm": offer.max_discount_rm,
                    "offer_priority": offer.priority_score,
                    "recommended_action": offer.recommended_action,
                    "promo_elastic_prob": row.get("promo_elastic_prob", 0),
                    "pkg_upsell_prob": row.get("pkg_upsell_prob", 0),
                    "churn_probability": row.get("churn_probability", 0),
                    "value_tier": row.get("value_tier", "Low"),
                    "rfm_segment": row.get("rfm_segment", "Hibernating"),
                    "generated_at": datetime.now(),
                }
            )

        offers_df = pd.DataFrame(offers)

        # Sort by priority (highest first)
        offers_df = offers_df.sort_values("offer_priority", ascending=False)

        logger.info(f"Generated {len(offers_df)} offers")

        # Log offer type distribution
        offer_dist = offers_df["offer_type"].value_counts()
        logger.info(f"Offer distribution:\n{offer_dist}")

        return offers_df

    def save_offers_to_db(self, offers_df: pd.DataFrame) -> int:
        """
        Save generated offers to database.

        Args:
            offers_df: DataFrame with offer data

        Returns:
            Number of rows saved
        """
        if offers_df.empty:
            logger.warning("No offers to save")
            return 0

        logger.info("Saving offers to database...")

        # Use upsert logic (DELETE + INSERT)
        self.db.execute_query("DELETE FROM dk.dynamic_pricing_offers", return_df=False)

        rows_saved = 0
        for _, row in offers_df.iterrows():
            query = """
                INSERT INTO dk.dynamic_pricing_offers (
                    mrn, offer_type, discount_pct, max_discount_rm,
                    offer_priority, recommended_action,
                    promo_elastic_prob, pkg_upsell_prob, churn_probability,
                    value_tier, rfm_segment, generated_at, created_at
                ) VALUES (
                    :mrn, :offer_type, :discount_pct, :max_discount_rm,
                    :offer_priority, :recommended_action,
                    :promo_elastic_prob, :pkg_upsell_prob, :churn_probability,
                    :value_tier, :rfm_segment, :generated_at, CURRENT_TIMESTAMP
                )
            """

            params = {
                "mrn": row["mrn"],
                "offer_type": row["offer_type"],
                "discount_pct": row["discount_pct"],
                "max_discount_rm": row["max_discount_rm"],
                "offer_priority": row["offer_priority"],
                "recommended_action": row["recommended_action"],
                "promo_elastic_prob": row["promo_elastic_prob"],
                "pkg_upsell_prob": row["pkg_upsell_prob"],
                "churn_probability": row["churn_probability"],
                "value_tier": row["value_tier"],
                "rfm_segment": row["rfm_segment"],
                "generated_at": row["generated_at"],
            }

            try:
                self.db.execute_query(query, params=params, return_df=False)
                rows_saved += 1
            except Exception as e:
                logger.error(f"Failed to save offer for {row['mrn']}: {e}")

        logger.info(f"Saved {rows_saved}/{len(offers_df)} offers to database")
        return rows_saved

    def get_offers_by_priority(
        self, min_priority: int = 0, limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Get offers filtered by minimum priority score.

        Args:
            min_priority: Minimum priority score (0-100)
            limit: Maximum number of offers to return

        Returns:
            DataFrame with filtered offers
        """
        all_offers = self.generate_all_offers()

        if all_offers.empty:
            return pd.DataFrame()

        filtered = all_offers[all_offers["offer_priority"] >= min_priority]

        if limit:
            filtered = filtered.head(limit)

        logger.info(f"Found {len(filtered)} offers with priority >= {min_priority}")
        return filtered

    def get_offers_by_type(self, offer_type: str) -> pd.DataFrame:
        """
        Get offers filtered by offer type.

        Args:
            offer_type: Type of offer (discount, bundle, retention, etc.)

        Returns:
            DataFrame with filtered offers
        """
        all_offers = self.generate_all_offers()

        if all_offers.empty:
            return pd.DataFrame()

        filtered = all_offers[all_offers["offer_type"] == offer_type]

        logger.info(f"Found {len(filtered)} offers of type '{offer_type}'")
        return filtered

    def get_offer_statistics(self) -> Dict[str, Any]:
        """
        Get summary statistics for generated offers.

        Returns:
            Dictionary with offer statistics
        """
        all_offers = self.generate_all_offers()

        if all_offers.empty:
            return {}

        stats = {
            "total_offers": len(all_offers),
            "offer_type_distribution": all_offers["offer_type"]
            .value_counts()
            .to_dict(),
            "avg_discount_pct": float(all_offers["discount_pct"].mean()),
            "avg_priority": float(all_offers["offer_priority"].mean()),
            "max_priority": int(all_offers["offer_priority"].max()),
            "min_priority": int(all_offers["offer_priority"].min()),
            "avg_max_discount_rm": float(all_offers["max_discount_rm"].mean()),
            "high_priority_count": int(
                len(all_offers[all_offers["offer_priority"] >= 70])
            ),
            "generated_at": datetime.now().isoformat(),
        }

        logger.info(
            f"Offer statistics: {stats['total_offers']} offers, "
            f"avg discount {stats['avg_discount_pct']:.1f}%"
        )

        return stats


def calculate_discount(
    promo_elastic_prob: float,
    churn_prob: float,
    upsell_prob: float,
    value_tier: str = "Medium",
    rfm_segment: str = "Hibernating",
) -> Dict[str, Any]:
    """
    Standalone function to calculate discount for given parameters.

    Useful for quick calculations without initializing the full engine.

    Args:
        promo_elastic_prob: Promo elasticity probability (0-1)
        churn_prob: Churn probability (0-1)
        upsell_prob: Package upsell probability (0-1)
        value_tier: Value tier (Premium, High, Medium, Low)
        rfm_segment: RFM segment

    Returns:
        Dictionary with discount details
    """
    engine = PricingEngine()

    # Create a mock row
    mock_row = pd.Series(
        {
            "promo_elastic_prob": promo_elastic_prob,
            "churn_probability": churn_prob,
            "pkg_upsell_prob": upsell_prob,
            "value_tier": value_tier,
            "rfm_segment": rfm_segment,
        }
    )

    offer_type = engine.determine_offer_type(mock_row)
    discount_pct = engine.calculate_discount_percentage(mock_row)
    max_discount_rm = engine.calculate_max_discount_cap(value_tier)
    priority = engine.calculate_offer_priority(mock_row)
    action = engine.get_recommended_action(mock_row)

    return {
        "offer_type": offer_type,
        "discount_pct": discount_pct,
        "max_discount_rm": max_discount_rm,
        "offer_priority": priority,
        "recommended_action": action,
        "inputs": {
            "promo_elastic_prob": promo_elastic_prob,
            "churn_prob": churn_prob,
            "upsell_prob": upsell_prob,
            "value_tier": value_tier,
            "rfm_segment": rfm_segment,
        },
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ST-05 Dynamic Pricing Engine")
    parser.add_argument(
        "--mode",
        choices=["generate", "stats", "test"],
        default="generate",
        help="Operation mode: generate offers, show stats, or run test",
    )
    parser.add_argument(
        "--min-priority", type=int, default=0, help="Minimum priority score (0-100)"
    )
    parser.add_argument(
        "--offer-type",
        type=str,
        choices=[
            "discount",
            "bundle",
            "retention",
            "vip_perk",
            "win_back",
            "welcome",
            "standard",
        ],
        help="Filter by offer type",
    )
    parser.add_argument("--mrn", type=str, help="Get offer for specific patient MRN")
    parser.add_argument("--save", action="store_true", help="Save offers to database")

    args = parser.parse_args()

    # Initialize engine
    db = get_db_manager()
    engine = PricingEngine(db_manager=db)

    if args.mode == "test":
        # Run quick test
        print("Running pricing engine test...")
        test_params = {
            "promo_elastic_prob": 0.75,
            "churn_prob": 0.3,
            "upsell_prob": 0.6,
            "value_tier": "High",
            "rfm_segment": "Potential Loyalists",
        }
        result = calculate_discount(**test_params)
        print(f"\nTest Result: {result}")

    elif args.mrn:
        # Get offer for specific patient
        offer = engine.get_patient_offer(args.mrn)
        if offer:
            print(f"\nOffer for {args.mrn}:")
            for key, value in offer.items():
                print(f"  {key}: {value}")
        else:
            print(f"No offer found for patient {args.mrn}")

    elif args.offer_type:
        # Get offers by type
        offers = engine.get_offers_by_type(args.offer_type)
        print(f"\nFound {len(offers)} offers of type '{args.offer_type}'")
        if not offers.empty:
            print(
                offers[
                    ["mrn", "discount_pct", "max_discount_rm", "offer_priority"]
                ].to_string()
            )

    elif args.min_priority > 0:
        # Get high priority offers
        offers = engine.get_offers_by_priority(min_priority=args.min_priority)
        print(f"\nFound {len(offers)} offers with priority >= {args.min_priority}")
        if not offers.empty:
            print(
                offers[["mrn", "offer_type", "discount_pct", "offer_priority"]]
                .head(20)
                .to_string()
            )

    else:
        # Generate all offers
        print("Generating offers for all patients...")
        offers = engine.generate_all_offers()

        if not offers.empty:
            print(f"\nGenerated {len(offers)} offers")
            print("\nTop 10 priority offers:")
            print(
                offers[["mrn", "offer_type", "discount_pct", "offer_priority"]]
                .head(10)
                .to_string()
            )

            # Show statistics
            stats = engine.get_offer_statistics()
            print(f"\nStatistics:")
            print(f"  Average discount: {stats['avg_discount_pct']:.1f}%")
            print(f"  Average priority: {stats['avg_priority']:.1f}")
            print(f"  High priority count (>=70): {stats['high_priority_count']}")

            if args.save:
                saved = engine.save_offers_to_db(offers)
                print(f"\nSaved {saved} offers to database")
