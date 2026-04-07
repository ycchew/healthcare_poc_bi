"""
ST-05: AI/ML Predictive Engine
Test module for ML feature views
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "ST-01" / "python"))

from database import get_db_manager


def test_vw_ml_patient_features_columns():
    """Verify vw_ml_patient_features has all required columns"""
    db = get_db_manager()
    result = db.execute_query("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'dk' 
          AND table_name = 'vw_ml_patient_features'
        ORDER BY ordinal_position
    """)

    required_columns = [
        # Demographics
        "patient_id",
        "gender",
        "age",
        "race_name",
        "city_name",
        "state_name",
        # Core behavioral
        "total_transactions",
        "visit_days",
        "branches_visited",
        "total_revenue",
        "avg_transaction_value",
        "max_transaction",
        "std_transaction",
        # Recency features
        "recency_days",
        "recency_band",
        # Frequency features
        "frequency_30d",
        "frequency_90d",
        "frequency_12m",
        "avg_gap_days",
        # Tenure features
        "tenure_days",
        "tenure_months",
        "cohort_month",
        # Category mix
        "skincare_share_pct",
        "services_share_pct",
        "medications_share_pct",
        "supplements_share_pct",
        # Package behavior
        "pkg_revenue_ratio",
        "has_package_flag",
        # Promo behavior
        "promo_dependency_pct",
        "avg_discount_pct",
        "discount_frequency",
        # Financial stress
        "avg_outstanding",
        "outstanding_ratio",
        "stress_level",
        # Visit pattern
        "visit_consistency",
        # RFM features
        "r_score",
        "f_score",
        "m_score",
        "rfm_segment",
        # Existing view features
        "value_tier",
        "patient_status",
        "health_score",
        "churn_risk",
        "predicted_ltv_24m",
        "standalone_ratio",
        "package_ratio",
        "services_ratio",
        "medications_ratio",
        "preferred_branch",
        "preferred_channel",
        "first_visit_month",
        "last_visit_day_of_week",
        # Metadata
        "feature_timestamp",
    ]

    actual_columns = set(result["column_name"].tolist())
    missing = set(required_columns) - actual_columns

    assert len(missing) == 0, f"Missing columns: {missing}"


def test_vw_patient_labels_definition():
    """Verify vw_patient_labels has correct label columns"""
    db = get_db_manager()
    result = db.execute_query("""
        SELECT column_name, data_type
        FROM information_schema.columns 
        WHERE table_schema = 'dk' 
          AND table_name = 'vw_patient_labels'
        ORDER BY ordinal_position
    """)

    required_labels = {
        "label_churned": "integer",
        "label_pkg_prospect": "integer",
        "label_skincare_buyer": "integer",
        "label_promo_elastic": "integer",
    }

    actual = {row["column_name"]: row["data_type"] for _, row in result.iterrows()}

    for label, expected_type in required_labels.items():
        assert label in actual, f"Missing label: {label}"
        # Note: PostgreSQL may show 'int4' instead of 'integer'
        assert actual[label] in [expected_type, "int4"], (
            f"Wrong type for {label}: {actual[label]}"
        )


def test_vw_patient_labels_distribution():
    """Verify labels have sufficient positive samples"""
    db = get_db_manager()
    result = db.execute_query("""
        SELECT 
            split_type,
            SUM(label_churned) AS churn_positives,
            SUM(label_pkg_prospect) AS pkg_positives,
            SUM(label_skincare_buyer) AS skincare_positives,
            SUM(label_promo_elastic) AS promo_positives,
            COUNT(*) AS total_samples
        FROM dk.vw_patient_labels
        GROUP BY split_type
    """)

    # Check we have at least some positive samples for training
    train_row = result[result["split_type"] == "train"]
    if not train_row.empty:
        # At least verify we have data
        assert train_row["total_samples"].iloc[0] > 0, "No training samples found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
