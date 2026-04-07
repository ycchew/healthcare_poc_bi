"""
ST-05: AI/ML Predictive Engine
Test suite for dynamic pricing engine.

Tests cover:
- PricingEngine initialization
- Offer type determination
- Discount percentage calculations
- Max discount cap logic
- Offer priority scoring
- Personalized offer generation
- Database integration
"""

import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "ST-05" / "python"))

from dynamic_pricing import (
    PricingEngine,
    OfferConfig,
    OfferType,
    RFMSegment,
    calculate_discount,
)


class TestPricingEngineInitialization:
    """Test PricingEngine initialization."""

    def test_init_with_default_db(self):
        """Verify PricingEngine initializes with default database manager."""
        with patch("dynamic_pricing.get_db_manager") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value = mock_db

            engine = PricingEngine()

            assert engine.db is not None
            assert engine.default_forecast_days == 90
            assert isinstance(engine._offer_cache, dict)

    def test_init_with_custom_db(self):
        """Verify PricingEngine initializes with custom database manager."""
        mock_db = Mock()
        engine = PricingEngine(db_manager=mock_db, default_forecast_days=30)

        assert engine.db == mock_db
        assert engine.default_forecast_days == 30

    def test_value_tier_caps(self):
        """Verify value tier discount caps are correctly defined."""
        mock_db = Mock()
        engine = PricingEngine(db_manager=mock_db)

        assert engine.VALUE_TIER_CAPS["Premium"] == 500
        assert engine.VALUE_TIER_CAPS["High"] == 300
        assert engine.VALUE_TIER_CAPS["Medium"] == 150
        assert engine.VALUE_TIER_CAPS["Low"] == 100
        assert engine.VALUE_TIER_CAPS["default"] == 100

    def test_priority_weights(self):
        """Verify offer priority weights sum to 1.0."""
        mock_db = Mock()
        engine = PricingEngine(db_manager=mock_db)

        weights = engine.PRIORITY_WEIGHTS
        total = sum(weights.values())

        assert abs(total - 1.0) < 0.001  # Allow floating point tolerance
        assert weights["churn"] == 0.4
        assert weights["promo"] == 0.3
        assert weights["upsell"] == 0.3


class TestOfferTypeDetermination:
    """Test offer type determination logic."""

    @pytest.fixture
    def engine(self):
        """Create engine instance."""
        mock_db = Mock()
        return PricingEngine(db_manager=mock_db)

    def test_offer_type_discount_high_elasticity(self, engine):
        """Verify discount offer for high promo elasticity."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.75,
                "pkg_upsell_prob": 0.3,
                "churn_probability": 0.2,
                "rfm_segment": "Potential Loyalists",
            }
        )

        offer_type = engine.determine_offer_type(row)
        assert offer_type == OfferType.DISCOUNT.value

    def test_offer_type_bundle_high_upsell(self, engine):
        """Verify bundle offer for high package upsell probability."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.65,
                "churn_probability": 0.2,
                "rfm_segment": "Potential Loyalists",
            }
        )

        offer_type = engine.determine_offer_type(row)
        assert offer_type == OfferType.BUNDLE.value

    def test_offer_type_retention_high_churn(self, engine):
        """Verify retention offer for high churn risk."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.75,
                "rfm_segment": "Potential Loyalists",
            }
        )

        offer_type = engine.determine_offer_type(row)
        assert offer_type == OfferType.RETENTION.value

    def test_offer_type_vip_perk_champions(self, engine):
        """Verify VIP perk offer for Champions segment."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "Champions",
            }
        )

        offer_type = engine.determine_offer_type(row)
        assert offer_type == OfferType.VIP_PERK.value

    def test_offer_type_vip_perk_loyal(self, engine):
        """Verify VIP perk offer for Loyal Customers segment."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "Loyal Customers",
            }
        )

        offer_type = engine.determine_offer_type(row)
        assert offer_type == OfferType.VIP_PERK.value

    def test_offer_type_win_back_at_risk(self, engine):
        """Verify win-back offer for At Risk segment."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "At Risk",
            }
        )

        offer_type = engine.determine_offer_type(row)
        assert offer_type == OfferType.WIN_BACK.value

    def test_offer_type_win_back_cannot_lose(self, engine):
        """Verify win-back offer for Cannot Lose Them segment."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "Cannot Lose Them",
            }
        )

        offer_type = engine.determine_offer_type(row)
        assert offer_type == OfferType.WIN_BACK.value

    def test_offer_type_welcome_new_customer(self, engine):
        """Verify welcome offer for New Customers segment."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "New Customers",
            }
        )

        offer_type = engine.determine_offer_type(row)
        assert offer_type == OfferType.WELCOME.value

    def test_offer_type_standard_default(self, engine):
        """Verify standard offer as default."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "Hibernating",
            }
        )

        offer_type = engine.determine_offer_type(row)
        assert offer_type == OfferType.STANDARD.value


class TestDiscountPercentageCalculation:
    """Test discount percentage calculation."""

    @pytest.fixture
    def engine(self):
        """Create engine instance."""
        mock_db = Mock()
        return PricingEngine(db_manager=mock_db)

    def test_discount_25_pct_high_elasticity(self, engine):
        """Verify 25% discount for very high promo elasticity."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.85,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "Potential Loyalists",
            }
        )

        discount = engine.calculate_discount_percentage(row)
        assert discount == 25

    def test_discount_20_pct_high_elasticity(self, engine):
        """Verify 20% discount for high promo elasticity."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.75,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "Potential Loyalists",
            }
        )

        discount = engine.calculate_discount_percentage(row)
        assert discount == 20

    def test_discount_15_pct_elasticity(self, engine):
        """Verify 15% discount for moderate-high promo elasticity."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.65,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "Potential Loyalists",
            }
        )

        discount = engine.calculate_discount_percentage(row)
        assert discount == 15

    def test_discount_20_pct_high_churn(self, engine):
        """Verify 20% discount for very high churn risk."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.85,
                "rfm_segment": "Potential Loyalists",
            }
        )

        discount = engine.calculate_discount_percentage(row)
        assert discount == 20

    def test_discount_15_pct_churn(self, engine):
        """Verify 15% discount for high churn risk."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.75,
                "rfm_segment": "Potential Loyalists",
            }
        )

        discount = engine.calculate_discount_percentage(row)
        assert discount == 15

    def test_discount_15_pct_upsell(self, engine):
        """Verify 15% discount for high upsell probability."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.75,
                "churn_probability": 0.3,
                "rfm_segment": "Potential Loyalists",
            }
        )

        discount = engine.calculate_discount_percentage(row)
        assert discount == 15

    def test_discount_10_pct_loyal(self, engine):
        """Verify 10% discount for loyal customers."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "Champions",
            }
        )

        discount = engine.calculate_discount_percentage(row)
        assert discount == 10

    def test_discount_15_pct_at_risk(self, engine):
        """Verify 15% discount for at-risk customers."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "At Risk",
            }
        )

        discount = engine.calculate_discount_percentage(row)
        assert discount == 15

    def test_discount_10_pct_new_customer(self, engine):
        """Verify 10% discount for new customers."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "New Customers",
            }
        )

        discount = engine.calculate_discount_percentage(row)
        assert discount == 10

    def test_discount_5_pct_default(self, engine):
        """Verify 5% default discount."""
        row = pd.Series(
            {
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.4,
                "churn_probability": 0.3,
                "rfm_segment": "Hibernating",
            }
        )

        discount = engine.calculate_discount_percentage(row)
        assert discount == 5


class TestMaxDiscountCap:
    """Test maximum discount cap calculation."""

    @pytest.fixture
    def engine(self):
        """Create engine instance."""
        mock_db = Mock()
        return PricingEngine(db_manager=mock_db)

    def test_max_cap_premium(self, engine):
        """Verify max discount cap for Premium tier."""
        cap = engine.calculate_max_discount_cap("Premium")
        assert cap == 500

    def test_max_cap_high(self, engine):
        """Verify max discount cap for High tier."""
        cap = engine.calculate_max_discount_cap("High")
        assert cap == 300

    def test_max_cap_medium(self, engine):
        """Verify max discount cap for Medium tier."""
        cap = engine.calculate_max_discount_cap("Medium")
        assert cap == 150

    def test_max_cap_low(self, engine):
        """Verify max discount cap for Low tier."""
        cap = engine.calculate_max_discount_cap("Low")
        assert cap == 100

    def test_max_cap_unknown(self, engine):
        """Verify max discount cap defaults to Low for unknown tier."""
        cap = engine.calculate_max_discount_cap("Unknown")
        assert cap == 100


class TestOfferPriorityScoring:
    """Test offer priority score calculation."""

    @pytest.fixture
    def engine(self):
        """Create engine instance."""
        mock_db = Mock()
        return PricingEngine(db_manager=mock_db)

    def test_priority_high_all_factors(self, engine):
        """Verify high priority when all factors are high."""
        row = pd.Series(
            {
                "churn_probability": 0.9,
                "promo_elastic_prob": 0.9,
                "pkg_upsell_prob": 0.9,
            }
        )

        priority = engine.calculate_offer_priority(row)
        # (0.9 * 0.4 + 0.9 * 0.3 + 0.9 * 0.3) * 100 = 90
        assert priority == 90

    def test_priority_low_all_factors(self, engine):
        """Verify low priority when all factors are low."""
        row = pd.Series(
            {
                "churn_probability": 0.1,
                "promo_elastic_prob": 0.1,
                "pkg_upsell_prob": 0.1,
            }
        )

        priority = engine.calculate_offer_priority(row)
        # (0.1 * 0.4 + 0.1 * 0.3 + 0.1 * 0.3) * 100 = 10
        assert priority == 10

    def test_priority_churn_weighted(self, engine):
        """Verify churn has highest weight (40%)."""
        row = pd.Series(
            {
                "churn_probability": 1.0,  # Max
                "promo_elastic_prob": 0.0,
                "pkg_upsell_prob": 0.0,
            }
        )

        priority = engine.calculate_offer_priority(row)
        # (1.0 * 0.4 + 0 + 0) * 100 = 40
        assert priority == 40

    def test_priority_medium_mixed(self, engine):
        """Verify medium priority for mixed factors."""
        row = pd.Series(
            {
                "churn_probability": 0.5,
                "promo_elastic_prob": 0.5,
                "pkg_upsell_prob": 0.5,
            }
        )

        priority = engine.calculate_offer_priority(row)
        # (0.5 * 0.4 + 0.5 * 0.3 + 0.5 * 0.3) * 100 = 50
        assert priority == 50


class TestRecommendedAction:
    """Test recommended action generation."""

    @pytest.fixture
    def engine(self):
        """Create engine instance."""
        mock_db = Mock()
        return PricingEngine(db_manager=mock_db)

    def test_action_retention(self, engine):
        """Verify retention action for high churn."""
        row = pd.Series(
            {
                "churn_probability": 0.8,
                "pkg_upsell_prob": 0.4,
                "promo_elastic_prob": 0.5,
                "rfm_segment": "Potential Loyalists",
            }
        )

        action = engine.get_recommended_action(row)
        assert action == "Immediate outreach with retention offer"

    def test_action_bundle(self, engine):
        """Verify bundle suggestion for high upsell."""
        row = pd.Series(
            {
                "churn_probability": 0.3,
                "pkg_upsell_prob": 0.7,
                "promo_elastic_prob": 0.5,
                "rfm_segment": "Potential Loyalists",
            }
        )

        action = engine.get_recommended_action(row)
        assert action == "Suggest package bundle during next visit"

    def test_action_promo(self, engine):
        """Verify promo campaign for high elasticity."""
        row = pd.Series(
            {
                "churn_probability": 0.3,
                "pkg_upsell_prob": 0.4,
                "promo_elastic_prob": 0.8,
                "rfm_segment": "Potential Loyalists",
            }
        )

        action = engine.get_recommended_action(row)
        assert action == "Send targeted promo campaign"

    def test_action_vip(self, engine):
        """Verify VIP invitation for loyal customers."""
        row = pd.Series(
            {
                "churn_probability": 0.3,
                "pkg_upsell_prob": 0.4,
                "promo_elastic_prob": 0.5,
                "rfm_segment": "Champions",
            }
        )

        action = engine.get_recommended_action(row)
        assert action == "Invite to VIP program"

    def test_action_standard(self, engine):
        """Verify standard engagement as default."""
        row = pd.Series(
            {
                "churn_probability": 0.3,
                "pkg_upsell_prob": 0.4,
                "promo_elastic_prob": 0.5,
                "rfm_segment": "Hibernating",
            }
        )

        action = engine.get_recommended_action(row)
        assert action == "Standard engagement"


class TestGetPatientOffer:
    """Test get_patient_offer method."""

    def test_get_patient_offer_success(self):
        """Verify successful offer generation for patient."""
        mock_db = Mock()

        # Mock database response
        mock_df = pd.DataFrame(
            [
                {
                    "mrn": "TEST123",
                    "promo_elastic_prob": 0.75,
                    "pkg_upsell_prob": 0.6,
                    "churn_probability": 0.3,
                    "value_tier": "High",
                    "rfm_segment": "Potential Loyalists",
                }
            ]
        )
        mock_db.execute_query.return_value = mock_df

        engine = PricingEngine(db_manager=mock_db)
        offer = engine.get_patient_offer("TEST123")

        assert offer is not None
        assert offer["mrn"] == "TEST123"
        assert offer["discount_pct"] == 20  # High elasticity
        assert offer["max_discount_rm"] == 300  # High tier
        assert "offer_type" in offer
        assert "offer_priority" in offer

    def test_get_patient_offer_not_found(self):
        """Verify None returned for unknown patient."""
        mock_db = Mock()
        mock_db.execute_query.return_value = pd.DataFrame()

        engine = PricingEngine(db_manager=mock_db)
        offer = engine.get_patient_offer("UNKNOWN")

        assert offer is None


class TestGenerateAllOffers:
    """Test generate_all_offers method."""

    def test_generate_all_offers(self):
        """Verify offer generation for all patients."""
        mock_db = Mock()

        # Mock database response with multiple patients
        mock_df = pd.DataFrame(
            [
                {
                    "mrn": "P1",
                    "promo_elastic_prob": 0.8,
                    "pkg_upsell_prob": 0.3,
                    "churn_probability": 0.2,
                    "value_tier": "Premium",
                    "rfm_segment": "Champions",
                },
                {
                    "mrn": "P2",
                    "promo_elastic_prob": 0.3,
                    "pkg_upsell_prob": 0.7,
                    "churn_probability": 0.8,
                    "value_tier": "Medium",
                    "rfm_segment": "At Risk",
                },
            ]
        )
        mock_db.execute_query.return_value = mock_df

        engine = PricingEngine(db_manager=mock_db)
        offers = engine.generate_all_offers()

        assert len(offers) == 2
        assert "mrn" in offers.columns
        assert "offer_type" in offers.columns
        assert "discount_pct" in offers.columns
        assert "offer_priority" in offers.columns

        # Check sorting by priority (descending)
        priorities = offers["offer_priority"].tolist()
        assert priorities == sorted(priorities, reverse=True)


class TestCalculateDiscountStandalone:
    """Test standalone calculate_discount function."""

    def test_calculate_discount_standalone(self):
        """Verify standalone discount calculation."""
        result = calculate_discount(
            promo_elastic_prob=0.75,
            churn_prob=0.3,
            upsell_prob=0.6,
            value_tier="High",
            rfm_segment="Potential Loyalists",
        )

        assert result["offer_type"] == OfferType.DISCOUNT.value
        assert result["discount_pct"] == 20
        assert result["max_discount_rm"] == 300
        assert "offer_priority" in result
        assert "recommended_action" in result
        assert "inputs" in result


class TestDatabaseIntegration:
    """Test database integration methods."""

    @pytest.fixture
    def mock_engine(self):
        """Create engine with mocked database."""
        mock_db = Mock()
        engine = PricingEngine(db_manager=mock_db)

        # Mock the scores response
        mock_scores = pd.DataFrame(
            [
                {
                    "mrn": "TEST1",
                    "promo_elastic_prob": 0.75,
                    "pkg_upsell_prob": 0.6,
                    "churn_probability": 0.3,
                    "value_tier": "High",
                    "rfm_segment": "Potential Loyalists",
                }
            ]
        )
        engine.get_patient_scores = Mock(return_value=mock_scores)

        return engine

    def test_save_offers_to_db(self, mock_engine):
        """Verify saving offers to database."""
        offers_df = pd.DataFrame(
            [
                {
                    "mrn": "TEST1",
                    "offer_type": "discount",
                    "discount_pct": 20,
                    "max_discount_rm": 300,
                    "offer_priority": 60,
                    "recommended_action": "Send targeted promo",
                    "promo_elastic_prob": 0.75,
                    "pkg_upsell_prob": 0.6,
                    "churn_probability": 0.3,
                    "value_tier": "High",
                    "rfm_segment": "Potential Loyalists",
                    "generated_at": datetime.now(),
                }
            ]
        )

        # Mock successful insert
        mock_engine.db.execute_query.return_value = None

        saved = mock_engine.save_offers_to_db(offers_df)

        assert saved == 1
        mock_engine.db.execute_query.assert_called()

    def test_get_offers_by_priority(self, mock_engine):
        """Verify filtering offers by priority."""
        offers = mock_engine.get_offers_by_priority(min_priority=50)

        assert not offers.empty

    def test_get_offers_by_type(self, mock_engine):
        """Verify filtering offers by type."""
        offers = mock_engine.get_offers_by_type("discount")

        assert not offers.empty

    def test_get_offer_statistics(self, mock_engine):
        """Verify offer statistics generation."""
        stats = mock_engine.get_offer_statistics()

        assert stats["total_offers"] == 1
        assert "avg_discount_pct" in stats
        assert "avg_priority" in stats
        assert "offer_type_distribution" in stats


class TestOfferConfigDataclass:
    """Test OfferConfig dataclass."""

    def test_offer_config_creation(self):
        """Verify OfferConfig creation."""
        config = OfferConfig(
            offer_type="discount",
            discount_pct=20,
            max_discount_rm=300,
            priority_score=75,
            recommended_action="Send promo",
        )

        assert config.offer_type == "discount"
        assert config.discount_pct == 20
        assert config.max_discount_rm == 300
        assert config.priority_score == 75
        assert config.recommended_action == "Send promo"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
