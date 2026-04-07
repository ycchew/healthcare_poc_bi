"""
ST-05: AI/ML Predictive Models
Python module for ML model training and predictions
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import json
from database import execute_query, execute_sql


def get_ml_features() -> pd.DataFrame:
    """Get ML feature store data."""
    return execute_query("SELECT * FROM dk.vw_ml_feature_store")


def get_propensity_predictions(mrn: Optional[str] = None) -> pd.DataFrame:
    """Get propensity to return predictions."""
    query = "SELECT * FROM dk.vw_propensity_predictions WHERE 1=1"
    if mrn:
        query += f" AND mrn = '{mrn}'"
    query += " ORDER BY predicted_propensity_score DESC"
    return execute_query(query)


def get_churn_risk_scores(mrn: Optional[str] = None) -> pd.DataFrame:
    """Get churn risk scores."""
    query = "SELECT * FROM dk.vw_churn_risk_scoring WHERE 1=1"
    if mrn:
        query += f" AND mrn = '{mrn}'"
    query += " ORDER BY churn_probability DESC"
    return execute_query(query)


def get_next_best_treatment(mrn: Optional[str] = None) -> pd.DataFrame:
    """Get next best treatment recommendations."""
    query = "SELECT * FROM dk.vw_next_best_treatment WHERE 1=1"
    if mrn:
        query += f" AND mrn = '{mrn}'"
    query += " ORDER BY recommendation_strength DESC"
    return execute_query(query)


def register_ml_model(
    model_name: str,
    model_type: str,
    algorithm: str,
    metrics: Dict,
    feature_columns: List[str],
    hyperparameters: Dict,
) -> Optional[int]:
    """Register a trained ML model in the registry."""
    query = """
    INSERT INTO dk.ml_model_registry (
        model_name, model_type, model_algorithm, auc_roc_score,
        accuracy_score, precision_score, recall_score, f1_score,
        feature_columns, hyperparameters, is_active
    ) VALUES (
        :model_name, :model_type, :algorithm, :auc_roc,
        :accuracy, :precision, :recall, :f1,
        :features, :hyperparams, TRUE
    ) RETURNING model_id
    """

    params = {
        "model_name": model_name,
        "model_type": model_type,
        "algorithm": algorithm,
        "auc_roc": metrics.get("auc_roc", 0),
        "accuracy": metrics.get("accuracy", 0),
        "precision": metrics.get("precision", 0),
        "recall": metrics.get("recall", 0),
        "f1": metrics.get("f1", 0),
        "features": feature_columns,
        "hyperparams": json.dumps(hyperparameters),
    }

    df = execute_query(query, params)
    return df["model_id"].iloc[0] if not df.empty else None


def save_prediction(
    model_id: int,
    mrn: str,
    prediction_type: str,
    score: float,
    pred_class: str,
    features: Dict,
) -> None:
    """Save a prediction to the database."""
    query = """
    INSERT INTO dk.ml_predictions (
        model_id, mrn, prediction_type, prediction_score,
        prediction_class, feature_values
    ) VALUES (
        :model_id, :mrn, :pred_type, :score,
        :pred_class, :features
    )
    """

    params = {
        "model_id": model_id,
        "mrn": mrn,
        "pred_type": prediction_type,
        "score": score,
        "pred_class": pred_class,
        "features": json.dumps(features),
    }

    execute_sql(query, params)


def create_ab_test(
    test_name: str,
    test_type: str,
    control_size: int,
    treatment_size: int,
    target_mrns: List[str],
) -> int:
    """Create an A/B test with patient assignments."""
    # Insert test
    test_query = """
    INSERT INTO dk.ab_tests (
        test_name, test_type, status,
        control_group_size, treatment_group_size
    ) VALUES (
        :name, :type, 'running',
        :control_size, :treatment_size
    ) RETURNING test_id
    """

    test_params = {
        "name": test_name,
        "type": test_type,
        "control_size": control_size,
        "treatment_size": treatment_size,
    }

    test_df = execute_query(test_query, test_params)
    test_id = test_df["test_id"].iloc[0]

    # Assign patients to variants
    import random

    random.shuffle(target_mrns)

    control_mrns = target_mrns[:control_size]
    treatment_mrns = target_mrns[control_size : control_size + treatment_size]

    for mrn in control_mrns:
        execute_sql(
            "INSERT INTO dk.ab_test_assignments (test_id, mrn, variant) VALUES (:test_id, :mrn, 'control')",
            {"test_id": test_id, "mrn": mrn},
        )

    for mrn in treatment_mrns:
        execute_sql(
            "INSERT INTO dk.ab_test_assignments (test_id, mrn, variant) VALUES (:test_id, :mrn, 'treatment')",
            {"test_id": test_id, "mrn": mrn},
        )

    return test_id


def analyze_ab_test(test_id: int) -> Dict:
    """Analyze A/B test results."""
    query = f"""
    SELECT 
        variant,
        COUNT(*) AS assigned,
        COUNT(*) FILTER (WHERE converted = TRUE) AS converted,
        SUM(revenue_impact) AS total_revenue
    FROM dk.ab_test_assignments
    WHERE test_id = {test_id}
    GROUP BY variant
    """

    df = execute_query(query)

    results = {}
    for _, row in df.iterrows():
        results[row["variant"]] = {
            "assigned": row["assigned"],
            "converted": row["converted"],
            "conversion_rate": row["converted"] / row["assigned"]
            if row["assigned"] > 0
            else 0,
            "total_revenue": row["total_revenue"],
        }

    return results


def get_high_propensity_patients(
    min_score: float = 0.7, max_recency: int = 60
) -> pd.DataFrame:
    """Get patients with high propensity to return."""
    query = f"""
    SELECT 
        pp.mrn,
        pp.patient_name,
        pp.phone,
        pp.email,
        pp.predicted_propensity_score,
        pp.propensity_class,
        pt.total_orders,
        pt.total_net_revenue,
        pt.days_since_last_transaction
    FROM dk.vw_propensity_predictions pp
    JOIN dk.mvw_patient_transactions pt ON pp.mrn = pt.mrn
    WHERE pp.predicted_propensity_score >= {min_score}
      AND pt.days_since_last_transaction <= {max_recency}
    ORDER BY pp.predicted_propensity_score DESC
    """
    return execute_query(query)


def export_ml_predictions(
    output_path: str = "./docs/output/ml_predictions.xlsx",
) -> str:
    """Export ML predictions to Excel."""
    propensity = get_propensity_predictions()
    churn = get_churn_risk_scores()
    nbt = get_next_best_treatment()

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        propensity.to_excel(writer, sheet_name="Propensity", index=False)
        churn.to_excel(writer, sheet_name="Churn Risk", index=False)
        nbt.to_excel(writer, sheet_name="Next Best Treatment", index=False)

    return output_path


if __name__ == "__main__":
    print("ST-05 ML Models Module")
    print("=" * 50)

    high_prop = get_high_propensity_patients(min_score=0.7)
    print(f"\nHigh Propensity Patients: {len(high_prop)}")
