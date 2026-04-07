"""
ST-03: CLTV Model Tests
Test suite for the Customer Lifetime Value model.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from cltv_model import CLTVModel


class TestCLTVModel(unittest.TestCase):
    """Test suite for CLTV Model."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_db = Mock()
        self.model = CLTVModel(db_manager=self.mock_db)

    def test_init(self):
        """Test model initialization."""
        self.assertIsNotNone(self.model.db)
        self.assertIsNotNone(self.model.model_version)
        self.assertIsNone(self.model.bg_nbd_model)
        self.assertIsNone(self.model.gamma_gamma_model)

    def test_load_transaction_data(self):
        """Test loading transaction data."""
        sample_data = pd.DataFrame(
            {
                "patient_id": ["MRN001", "MRN002"],
                "transaction_date": ["2024-01-01", "2024-01-15"],
                "amount": [100.0, 250.0],
            }
        )
        self.mock_db.execute_query.return_value = sample_data

        result = self.model.load_transaction_data()

        self.assertEqual(len(result), 2)
        self.assertIn("patient_id", result.columns)
        self.assertIn("transaction_date", result.columns)
        self.assertIn("amount", result.columns)

    def test_prepare_rfm_features(self):
        """Test RFM feature preparation."""
        transactions = pd.DataFrame(
            {
                "patient_id": ["MRN001", "MRN001", "MRN002", "MRN002", "MRN002"],
                "transaction_date": [
                    "2024-01-01",
                    "2024-02-01",
                    "2024-01-15",
                    "2024-02-15",
                    "2024-03-15",
                ],
                "amount": [100.0, 150.0, 200.0, 250.0, 300.0],
            }
        )

        try:
            from lifetimes.utils import summary_data_from_transaction_data

            rfm = self.model.prepare_rfm_features(transactions)

            self.assertIn("patient_id", rfm.columns)
            self.assertIn("frequency", rfm.columns)
            self.assertIn("recency", rfm.columns)
            self.assertIn("T", rfm.columns)
            self.assertIn("monetary_value", rfm.columns)
            self.assertGreater(len(rfm), 0)
        except ImportError:
            self.skipTest("lifetimes library not installed")

    @patch("cltv_model.BetaGeoFitter")
    def test_train_bg_nbd(self, mock_bgf_class):
        """Test BG/NBD model training."""
        mock_bgf = Mock()
        mock_bgf.params_ = {"r": 0.5, "alpha": 10.0, "a": 0.5, "b": 1.0}
        mock_bgf_class.return_value = mock_bgf

        rfm = pd.DataFrame(
            {
                "patient_id": ["MRN001", "MRN002"],
                "frequency": [2, 5],
                "recency": [30, 60],
                "T": [90, 120],
                "monetary_value": [150.0, 250.0],
            }
        )

        result = self.model.train_bg_nbd(rfm)

        self.assertIsNotNone(result)
        mock_bgf.fit.assert_called_once()
        self.assertIsNotNone(self.model.bg_nbd_model)

    @patch("cltv_model.GammaGammaFitter")
    def test_train_gamma_gamma(self, mock_ggf_class):
        """Test Gamma-Gamma model training."""
        mock_ggf = Mock()
        mock_ggf.params_ = {"p": 6.0, "q": 4.0, "v": 15.0}
        mock_ggf_class.return_value = mock_ggf

        rfm = pd.DataFrame(
            {
                "patient_id": ["MRN001", "MRN002"],
                "frequency": [2, 5],
                "recency": [30, 60],
                "T": [90, 120],
                "monetary_value": [150.0, 250.0],
            }
        )

        result = self.model.train_gamma_gamma(rfm)

        self.assertIsNotNone(result)
        mock_ggf.fit.assert_called_once()
        self.assertIsNotNone(self.model.gamma_gamma_model)

    def test_predict_cltv_models_not_trained(self):
        """Test predict_cltv raises error when models not trained."""
        rfm = pd.DataFrame({"frequency": [2], "recency": [30], "T": [90]})

        with self.assertRaises(ValueError) as context:
            self.model.predict_cltv(rfm)

        self.assertIn("Models not trained", str(context.exception))

    @patch("cltv_model.BetaGeoFitter")
    @patch("cltv_model.GammaGammaFitter")
    def test_predict_cltv(self, mock_ggf_class, mock_bgf_class):
        """Test CLTV prediction generation."""
        # Setup mock BG/NBD model
        mock_bgf = Mock()
        mock_bgf.conditional_expected_number_of_purchases_up_to_time.return_value = (
            pd.Series([2.5, 5.0])
        )
        mock_bgf.conditional_probability_alive.return_value = pd.Series([0.95, 0.85])
        mock_bgf_class.return_value = mock_bgf

        # Setup mock Gamma-Gamma model
        mock_ggf = Mock()
        mock_ggf.conditional_expected_average_profit.return_value = pd.Series(
            [200.0, 300.0]
        )
        mock_ggf_class.return_value = mock_ggf

        # Train models first
        rfm = pd.DataFrame(
            {
                "patient_id": ["MRN001", "MRN002"],
                "frequency": [2, 5],
                "recency": [30, 60],
                "T": [90, 120],
                "monetary_value": [150.0, 250.0],
            }
        )

        self.model.train_bg_nbd(rfm)
        self.model.train_gamma_gamma(rfm)

        # Predict
        predictions = self.model.predict_cltv(rfm)

        self.assertIn("predicted_clv_12m", predictions.columns)
        self.assertIn("predicted_clv_24m", predictions.columns)
        self.assertIn("probability_alive", predictions.columns)
        self.assertIn("clv_tier", predictions.columns)
        self.assertEqual(len(predictions), 2)

    def test_save_predictions_to_db(self):
        """Test saving predictions to database."""
        predictions = pd.DataFrame(
            {
                "patient_id": ["MRN001", "MRN002"],
                "frequency": [2, 5],
                "recency": [30, 60],
                "T": [90, 120],
                "monetary_value": [150.0, 250.0],
                "predicted_purchases_12m": [2.5, 5.0],
                "predicted_purchases_90d": [0.8, 1.5],
                "probability_alive": [0.95, 0.85],
                "predicted_avg_order_value": [200.0, 300.0],
                "predicted_clv_12m": [500.0, 1500.0],
                "predicted_clv_24m": [1000.0, 3000.0],
                "clv_tier": ["MEDIUM", "HIGH"],
            }
        )

        rows_saved = self.model.save_predictions_to_db(predictions)

        self.assertEqual(rows_saved, 2)
        self.mock_db.execute_query.assert_called()

    def test_refresh_materialized_view(self):
        """Test refreshing materialized view."""
        self.mock_db.execute_query.return_value = None

        self.model.refresh_materialized_view()

        self.mock_db.execute_query.assert_called()

    def test_refresh_materialized_view_fallback(self):
        """Test refreshing materialized view with fallback."""
        self.mock_db.execute_query.side_effect = [
            Exception("Concurrent refresh failed"),
            None,
        ]

        self.model.refresh_materialized_view()

        self.assertEqual(self.mock_db.execute_query.call_count, 2)


class TestCLTVModelIntegration(unittest.TestCase):
    """Integration tests for CLTV Model (requires database)."""

    @classmethod
    def setUpClass(cls):
        """Set up real database connection for integration tests."""
        try:
            from dotenv import load_dotenv

            load_dotenv()

            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            sys.path.insert(
                0, str(Path(__file__).parent.parent.parent / "ST-01" / "python")
            )
            from database import get_db_manager

            cls.db = get_db_manager()
            cls.skip_integration = False
        except Exception as e:
            cls.skip_integration = True
            print(f"Skipping integration tests: {e}")

    def setUp(self):
        """Skip if no database connection."""
        if self.skip_integration:
            self.skipTest("Database connection not available")

    def test_real_load_transaction_data(self):
        """Test loading real transaction data from database."""
        model = CLTVModel(db_manager=self.db)
        transactions = model.load_transaction_data()

        if len(transactions) > 0:
            self.assertIn("patient_id", transactions.columns)
            self.assertIn("transaction_date", transactions.columns)
            self.assertIn("amount", transactions.columns)
            print(f"Loaded {len(transactions)} real transactions")
        else:
            print("No transaction data available in database")


if __name__ == "__main__":
    unittest.main(verbosity=2)
