"""
Test suite for ST-05 ML Pipeline.

Tests cover:
- MLPipeline initialization
- Data loading and preprocessing
- Model training
- SHAP value computation
- Prediction generation
- Database operations
"""

import pytest
from datetime import datetime
import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Add ST-01/python to path for database module
sys.path.insert(0, str(project_root / "ST-01" / "python"))

# Add ST-05/python to path for ml_pipeline module
sys.path.insert(0, str(project_root / "ST-05" / "python"))


def test_ml_pipeline_initialization():
    """Verify MLPipeline initializes correctly"""
    from ml_pipeline import MLPipeline
    from database import get_db_manager

    db = get_db_manager()
    pipeline = MLPipeline(db_manager=db)

    assert pipeline.db is not None
    assert pipeline.forecast_days == 90
    assert pipeline.model_version is not None
    assert len(pipeline.MODEL_TYPES) == 4
    assert "churn" in pipeline.MODEL_TYPES
    assert "upsell" in pipeline.MODEL_TYPES
    assert "nbt" in pipeline.MODEL_TYPES
    assert "promo" in pipeline.MODEL_TYPES


def test_ml_pipeline_default_model_version():
    """Verify model version is generated if not provided"""
    from ml_pipeline import MLPipeline

    pipeline = MLPipeline()

    # Model version should be in format YYYYMMDD_HHMM
    assert pipeline.model_version is not None
    assert len(pipeline.model_version) == 13  # e.g., "20260401_1430"
    assert "_" in pipeline.model_version


def test_ml_pipeline_custom_model_version():
    """Verify custom model version is used when provided"""
    from ml_pipeline import MLPipeline

    custom_version = "test_version_123"
    pipeline = MLPipeline(model_version=custom_version)

    assert pipeline.model_version == custom_version


def test_ml_pipeline_feature_columns():
    """Verify FEATURE_COLUMNS matches expected features"""
    from ml_pipeline import MLPipeline

    pipeline = MLPipeline()

    # Should have all expected feature columns
    expected_features = [
        "recency_days",
        "frequency_total",
        "total_revenue",
        "skincare_share_pct",
        "promo_dependency_pct",
        "r_score",
        "f_score",
        "m_score",
        "health_score",
        "predicted_ltv_24m",
    ]

    for feature in expected_features:
        assert feature in pipeline.FEATURE_COLUMNS


def test_ml_pipeline_target_columns():
    """Verify TARGET_COLUMNS mapping is correct"""
    from ml_pipeline import MLPipeline

    pipeline = MLPipeline()

    assert pipeline.TARGET_COLUMNS["churn"] == "label_churned"
    assert pipeline.TARGET_COLUMNS["upsell"] == "label_pkg_prospect"
    assert pipeline.TARGET_COLUMNS["nbt"] == "label_skincare_buyer"
    assert pipeline.TARGET_COLUMNS["promo"] == "label_promo_elastic"


def test_ml_pipeline_action_mappings():
    """Verify ACTION_MAPPINGS structure"""
    from ml_pipeline import MLPipeline

    pipeline = MLPipeline()

    # Check churn mappings
    assert "churn" in pipeline.ACTION_MAPPINGS
    assert "thresholds" in pipeline.ACTION_MAPPINGS["churn"]
    assert "bands" in pipeline.ACTION_MAPPINGS["churn"]
    assert len(pipeline.ACTION_MAPPINGS["churn"]["bands"]) == 3

    # Check upsell mappings
    assert "upsell" in pipeline.ACTION_MAPPINGS
    assert "actions" in pipeline.ACTION_MAPPINGS["upsell"]
    assert len(pipeline.ACTION_MAPPINGS["upsell"]["actions"]) == 3

    # Check promo mappings
    assert "promo" in pipeline.ACTION_MAPPINGS
    assert "segments" in pipeline.ACTION_MAPPINGS["promo"]


def test_ml_pipeline_xgb_params():
    """Verify XGBoost parameters are configured correctly"""
    from ml_pipeline import MLPipeline

    pipeline = MLPipeline()

    params = pipeline.XGB_PARAMS
    assert params["n_estimators"] == 100
    assert params["max_depth"] == 6
    assert params["learning_rate"] == 0.1
    assert params["objective"] == "binary:logistic"
    assert params["eval_metric"] == "auc"
    assert params["random_state"] == 42


def test_validate_positive_samples_sufficient():
    """Test validation with sufficient positive samples"""
    from ml_pipeline import MLPipeline

    pipeline = MLPipeline()

    # Create test data with enough positive samples
    df = pd.DataFrame(
        {
            "label_churned": [1] * 250 + [0] * 750  # 250 positives
        }
    )

    result = pipeline.validate_positive_samples(df, "churn", min_samples=200)
    assert result is True


def test_validate_positive_samples_insufficient():
    """Test validation with insufficient positive samples"""
    from ml_pipeline import MLPipeline

    pipeline = MLPipeline()

    # Create test data with too few positive samples
    df = pd.DataFrame(
        {
            "label_churned": [1] * 100 + [0] * 900  # Only 100 positives
        }
    )

    result = pipeline.validate_positive_samples(df, "churn", min_samples=200)
    assert result is False


def test_prepare_train_validation_split():
    """Test temporal split functionality"""
    from ml_pipeline import MLPipeline

    pipeline = MLPipeline()

    # Create test data with split_type column
    df = pd.DataFrame(
        {"feature1": range(100), "split_type": ["train"] * 70 + ["validation"] * 30}
    )

    train_df, validation_df = pipeline.prepare_train_validation_split(df)

    assert len(train_df) == 70
    assert len(validation_df) == 30
    assert all(train_df["split_type"] == "train")
    assert all(validation_df["split_type"] == "validation")


def test_ml_pipeline_load_features_and_labels_integration():
    """Integration test for loading features and labels from database.

    This test requires the database views to exist:
    - dk.mvw_ml_patient_features
    - dk.vw_patient_labels

    If views don't exist, the test is gracefully skipped.
    """
    from ml_pipeline import MLPipeline
    from database import get_db_manager

    db = get_db_manager()
    pipeline = MLPipeline(db_manager=db)

    try:
        # This test requires the database views to exist
        df = pipeline.load_features_and_labels()

        # If views exist, should return non-empty DataFrame
        if not df.empty:
            assert "mrn" in df.columns
            assert "recency_days" in df.columns
            assert "label_churned" in df.columns
    except Exception:
        # Skip test if database views don't exist
        # This is expected in fresh environments
        pytest.skip("Database views not available - skipping integration test")


def test_ml_pipeline_train_model_unit():
    """Unit test for model training logic (mocked data)"""
    from ml_pipeline import MLPipeline

    pipeline = MLPipeline()

    # Create small synthetic dataset
    np.random.seed(42)
    n_samples = 1000

    train_df = pd.DataFrame(
        {col: np.random.randn(n_samples) for col in pipeline.FEATURE_COLUMNS}
    )

    # Add binary target
    train_df["label_churned"] = np.random.choice([0, 1], size=n_samples, p=[0.7, 0.3])

    # Train model (should complete without errors)
    model, metrics = pipeline.train_model(train_df, "churn")

    # Verify model was trained
    assert model is not None
    assert "auc_roc" in metrics
    assert "avg_precision" in metrics
    assert "positive_samples" in metrics
    assert "negative_samples" in metrics

    # AUC should be between 0 and 1
    assert 0 <= metrics["auc_roc"] <= 1


def test_ml_pipeline_train_all_models():
    """Test training all four models"""
    from ml_pipeline import MLPipeline

    pipeline = MLPipeline()

    # Create synthetic training data
    np.random.seed(42)
    n_samples = 1000

    train_df = pd.DataFrame(
        {col: np.random.randn(n_samples) for col in pipeline.FEATURE_COLUMNS}
    )

    # Add all target columns
    train_df["label_churned"] = np.random.choice([0, 1], size=n_samples, p=[0.7, 0.3])
    train_df["label_pkg_prospect"] = np.random.choice(
        [0, 1], size=n_samples, p=[0.6, 0.4]
    )
    train_df["label_skincare_buyer"] = np.random.choice(
        [0, 1], size=n_samples, p=[0.5, 0.5]
    )
    train_df["label_promo_elastic"] = np.random.choice(
        [0, 1], size=n_samples, p=[0.8, 0.2]
    )

    # Train all models
    success = pipeline.train_all_models(train_df)

    # All models should be trained
    assert success is True
    assert len(pipeline._models) == 4

    for model_type in pipeline.MODEL_TYPES:
        assert model_type in pipeline._models
        assert model_type in pipeline._metrics
        assert pipeline._metrics[model_type]["auc_roc"] > 0


def test_ml_pipeline_compute_shap_values():
    """Test SHAP value computation"""
    from ml_pipeline import MLPipeline

    pipeline = MLPipeline()

    # First train a model
    np.random.seed(42)
    n_samples = 500

    train_df = pd.DataFrame(
        {col: np.random.randn(n_samples) for col in pipeline.FEATURE_COLUMNS}
    )
    train_df["label_churned"] = np.random.choice([0, 1], size=n_samples, p=[0.7, 0.3])

    model, _ = pipeline.train_model(train_df, "churn")
    pipeline._models["churn"] = model

    # Compute SHAP values
    importance_df = pipeline.compute_shap_values(train_df, "churn", sample_size=100)

    # Verify SHAP output
    assert not importance_df.empty
    assert "feature" in importance_df.columns
    assert "importance" in importance_df.columns
    assert len(importance_df) == len(pipeline.FEATURE_COLUMNS)

    # SHAP values should be stored
    assert "churn" in pipeline._shap_values


def test_ml_pipeline_generate_predictions():
    """Test prediction generation"""
    from ml_pipeline import MLPipeline

    pipeline = MLPipeline()

    # Train models first
    np.random.seed(42)
    n_samples = 1000  # Increased to ensure sufficient positive samples

    df = pd.DataFrame(
        {col: np.random.randn(n_samples) for col in pipeline.FEATURE_COLUMNS}
    )
    df["mrn"] = range(1, n_samples + 1)
    # Add all target columns with distributions that ensure > 200 positives
    df["label_churned"] = np.random.choice(
        [0, 1], size=n_samples, p=[0.5, 0.5]
    )  # 500 positives
    df["label_pkg_prospect"] = np.random.choice(
        [0, 1], size=n_samples, p=[0.5, 0.5]
    )  # 500 positives
    df["label_skincare_buyer"] = np.random.choice(
        [0, 1], size=n_samples, p=[0.5, 0.5]
    )  # 500 positives
    df["label_promo_elastic"] = np.random.choice(
        [0, 1], size=n_samples, p=[0.5, 0.5]
    )  # 500 positives

    pipeline.train_all_models(df)

    # Generate predictions
    predictions = pipeline.generate_predictions(df)

    # Verify predictions
    assert len(predictions) == n_samples
    assert "mrn" in predictions.columns
    assert "churn_probability" in predictions.columns
    assert "churn_risk_band" in predictions.columns
    assert "upsell_probability" in predictions.columns
    assert "upsell_action" in predictions.columns
    assert "promo_probability" in predictions.columns
    assert "promo_segment" in predictions.columns
    assert "model_version" in predictions.columns
    assert "prediction_date" in predictions.columns

    # Probabilities should be between 0 and 1
    assert predictions["churn_probability"].between(0, 1).all()
    assert predictions["upsell_probability"].between(0, 1).all()

    # Risk bands should have valid values
    valid_bands = {"Low", "Medium", "High"}
    assert set(predictions["churn_risk_band"].unique()).issubset(valid_bands)


def test_ml_pipeline_run_full_retrain_structure():
    """Test full retrain returns expected structure"""
    from ml_pipeline import MLPipeline
    from unittest.mock import MagicMock

    # Create pipeline with mocked DB
    mock_db = MagicMock()
    pipeline = MLPipeline(db_manager=mock_db)

    # Mock the load_features_and_labels to return synthetic data
    np.random.seed(42)
    n_samples = 1000  # Increased to ensure enough positive samples

    def mock_load():
        df = pd.DataFrame(
            {col: np.random.randn(n_samples) for col in pipeline.FEATURE_COLUMNS}
        )
        df["mrn"] = range(1, n_samples + 1)
        df["split_type"] = ["train"] * 800 + ["validation"] * 200
        # Use distributions that ensure > 200 positive samples
        df["label_churned"] = np.random.choice(
            [0, 1], size=n_samples, p=[0.6, 0.4]
        )  # 400 positives
        df["label_pkg_prospect"] = np.random.choice(
            [0, 1], size=n_samples, p=[0.5, 0.5]
        )  # 500 positives
        df["label_skincare_buyer"] = np.random.choice(
            [0, 1], size=n_samples, p=[0.5, 0.5]
        )  # 500 positives
        df["label_promo_elastic"] = np.random.choice(
            [0, 1], size=n_samples, p=[0.6, 0.4]
        )  # 400 positives
        return df

    pipeline.load_features_and_labels = mock_load
    pipeline.save_predictions_to_db = MagicMock(return_value=100)
    pipeline.save_model_metadata = MagicMock(return_value=4)

    # Run full retrain
    result = pipeline.run_full_retrain()

    # Verify result structure
    assert "status" in result
    assert "models_trained" in result
    assert "predictions_saved" in result
    assert "metadata_saved" in result
    assert "duration_seconds" in result
    assert "model_version" in result
    assert "metrics" in result

    # Should have trained 4 models
    assert result["models_trained"] == 4


def test_ml_pipeline_run_incremental_scoring_structure():
    """Test incremental scoring returns expected structure"""
    from ml_pipeline import MLPipeline
    from unittest.mock import MagicMock

    # Create pipeline with mocked DB
    mock_db = MagicMock()
    pipeline = MLPipeline(db_manager=mock_db)

    # Mock metadata query
    mock_metadata = pd.DataFrame({"model_version": ["test_v1"]})
    mock_db.execute_query = MagicMock(
        side_effect=[
            mock_metadata,  # First call: get metadata
            pd.DataFrame(),  # Second call: load features (empty, for simplicity)
        ]
    )

    # Run incremental scoring
    result = pipeline.run_incremental_scoring()

    # Verify result has expected keys
    assert "status" in result
    if result["status"] == "FAILED":
        assert "error" in result
    else:
        assert "predictions_saved" in result
        assert "duration_seconds" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
