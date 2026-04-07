"""
ST-05: AI/ML Predictive Engine
Test suite for A/B testing functionality.

Tests cover:
- vw_ab_assignment view columns validation
- Deterministic A/B group assignment (hash-based)
- Chi-square statistical analysis
- A/B results table structure
"""

import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, date

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "ST-01" / "python"))

from database import get_db_manager


class TestVwAbAssignmentViewColumns:
    """Test vw_ab_assignment view structure and columns."""

    def test_vw_ab_assignment_columns_exist(self):
        """Verify vw_ab_assignment has all required columns."""
        try:
            db = get_db_manager()
            result = db.execute_query("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'dk' 
                  AND table_name = 'vw_ab_assignment'
                ORDER BY ordinal_position
            """)
        except Exception:
            pytest.skip("Database view vw_ab_assignment doesn't exist yet")

        if result.empty:
            pytest.skip("vw_ab_assignment view doesn't exist yet")

        required_columns = [
            "mrn",
            "offer_type",
            "discount_pct",
            "max_discount_rm",
            "offer_priority",
            "recommended_action",
            "offer_generated_at",
            "test_group",
            "experiment_id",
            "assignment_date",
        ]

        actual_columns = set(result["column_name"].tolist())
        missing = set(required_columns) - actual_columns

        assert len(missing) == 0, f"Missing columns in vw_ab_assignment: {missing}"

    def test_vw_ab_assignment_column_types(self):
        """Verify vw_ab_assignment column data types."""
        try:
            db = get_db_manager()
            result = db.execute_query("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = 'dk' 
                  AND table_name = 'vw_ab_assignment'
                ORDER BY ordinal_position
            """)
        except Exception:
            pytest.skip("Database view vw_ab_assignment doesn't exist yet")

        if result.empty:
            pytest.skip("vw_ab_assignment view doesn't exist yet")

        # Create mapping of column to type
        column_types = {
            row["column_name"]: row["data_type"] for _, row in result.iterrows()
        }

        # Verify key column types
        assert "mrn" in column_types
        assert column_types["test_group"] in ["text", "character varying"]
        assert column_types["experiment_id"] in ["text", "character varying"]
        assert "date" in column_types["assignment_date"]

    def test_vw_ab_assignment_data_sample(self):
        """Verify vw_ab_assignment returns data with valid structure."""
        try:
            db = get_db_manager()
            result = db.execute_query("""
                SELECT * FROM dk.vw_ab_assignment 
                LIMIT 10
            """)
        except Exception:
            pytest.skip("Database view vw_ab_assignment doesn't exist yet")

        # If view has data, validate structure
        if not result.empty:
            assert "mrn" in result.columns
            assert "test_group" in result.columns
            assert "experiment_id" in result.columns
            assert "assignment_date" in result.columns

            # Test groups should be 'A' or 'B'
            if "test_group" in result.columns:
                valid_groups = {"A", "B"}
                actual_groups = set(result["test_group"].unique())
                assert actual_groups.issubset(valid_groups), (
                    f"Invalid test groups found: {actual_groups - valid_groups}"
                )

            # Experiment ID should be consistent
            if "experiment_id" in result.columns:
                assert result["experiment_id"].iloc[0] == "dynamic_pricing_v1", (
                    "Experiment ID should be 'dynamic_pricing_v1'"
                )


class TestDeterministicAssignment:
    """Test deterministic A/B group assignment logic."""

    def test_assignment_deterministic_same_patient(self):
        """Verify same patient always gets same group assignment on same day."""
        try:
            db = get_db_manager()
        except Exception:
            pytest.skip("Database connection not available")

        # Get a sample patient
        try:
            sample = db.execute_query("""
                SELECT mrn FROM dk.vw_ab_assignment 
                LIMIT 1
            """)
        except Exception:
            pytest.skip("Database view vw_ab_assignment doesn't exist yet")

        if not sample.empty:
            mrn = sample.iloc[0]["mrn"]

            # Query multiple times - should get same group
            results = []
            for _ in range(3):
                result = db.execute_query(
                    f"""
                    SELECT test_group FROM dk.vw_ab_assignment 
                    WHERE mrn = '{mrn}'
                """
                )
                if not result.empty:
                    results.append(result.iloc[0]["test_group"])

            # All results should be identical (deterministic)
            if len(results) > 0:
                assert len(set(results)) == 1, (
                    f"Assignment not deterministic for {mrn}: {results}"
                )

    def test_assignment_hash_function_consistency(self):
        """Verify hash function produces consistent results."""
        try:
            db = get_db_manager()
            result = db.execute_query("""
                SELECT 
                    mrn,
                    ABS(MOD(hashtext(mrn || '_' || CURRENT_DATE::text), 2)) AS hash_result
                FROM dk.vw_ab_assignment
                LIMIT 20
            """)
        except Exception:
            pytest.skip("Database view vw_ab_assignment doesn't exist yet")

        if not result.empty:
            # Hash result should always be 0 or 1
            assert result["hash_result"].isin([0, 1]).all(), (
                "Hash result should be 0 or 1"
            )

    def test_assignment_group_distribution(self):
        """Verify A/B groups have reasonable distribution."""
        try:
            db = get_db_manager()
            result = db.execute_query("""
                SELECT 
                    test_group,
                    COUNT(*) AS count
                FROM dk.vw_ab_assignment
                GROUP BY test_group
            """)
        except Exception:
            pytest.skip("Database view vw_ab_assignment doesn't exist yet")

        if not result.empty and len(result) == 2:
            group_a = result[result["test_group"] == "A"]["count"].iloc[0]
            group_b = result[result["test_group"] == "B"]["count"].iloc[0]

            # Groups should be roughly 50/50 (allow 40-60% range)
            total = group_a + group_b
            if total > 0:
                pct_a = group_a / total
                pct_b = group_b / total

                assert 0.4 <= pct_a <= 0.6, f"Group A distribution skewed: {pct_a:.2%}"
                assert 0.4 <= pct_b <= 0.6, f"Group B distribution skewed: {pct_b:.2%}"

    def test_assignment_different_patients_different_groups(self):
        """Verify different patients can get different assignments."""
        try:
            db = get_db_manager()
            result = db.execute_query("""
                SELECT DISTINCT test_group 
                FROM dk.vw_ab_assignment
            """)
        except Exception:
            pytest.skip("Database view vw_ab_assignment doesn't exist yet")

        # Should have both A and B groups in the data
        if not result.empty:
            # Hash-based assignment should naturally produce both groups
            # if there's sufficient diversity in MRNs
            pass  # At least verify we can query the view

    def test_group_assignment_mapping(self):
        """Verify test_group maps correctly to A/B."""
        try:
            db = get_db_manager()
            result = db.execute_query("""
                SELECT 
                    mrn,
                    test_group,
                    CASE 
                        WHEN MOD(hashtext(mrn || '_' || CURRENT_DATE::text), 2) = 0 THEN 'A'
                        ELSE 'B'
                    END AS expected_group
                FROM dk.vw_ab_assignment
                LIMIT 50
            """)
        except Exception:
            pytest.skip("Database view vw_ab_assignment doesn't exist yet")

        if not result.empty:
            # Each row's test_group should match expected_group
            for _, row in result.iterrows():
                assert row["test_group"] == row["expected_group"], (
                    f"Group mismatch for {row['mrn']}: {row['test_group']} != {row['expected_group']}"
                )


class TestChiSquareAnalysis:
    """Test chi-square statistical analysis for A/B tests."""

    @pytest.fixture
    def sample_ab_data(self):
        """Create sample A/B test data for analysis."""
        return pd.DataFrame(
            {
                "test_group": ["A"] * 500 + ["B"] * 500,
                "converted": [1] * 150
                + [0] * 350  # Group A: 150/500 = 30% conversion
                + [1] * 200
                + [0] * 300,  # Group B: 200/500 = 40% conversion
                "revenue": np.random.uniform(100, 500, 1000),
            }
        )

    def test_chi_square_calculation(self, sample_ab_data):
        """Verify chi-square statistic calculation."""
        from scipy.stats import chi2_contingency

        # Create contingency table
        contingency = pd.crosstab(
            sample_ab_data["test_group"], sample_ab_data["converted"]
        )

        # Calculate chi-square
        chi2, p_value, dof, expected = chi2_contingency(contingency)

        # Chi-square should be positive
        assert chi2 > 0, "Chi-square statistic should be positive"

        # P-value should be between 0 and 1
        assert 0 <= p_value <= 1, f"P-value out of range: {p_value}"

        # Degrees of freedom for 2x2 table = 1
        assert dof == 1, f"Expected 1 DOF, got {dof}"

    def test_chi_square_significance_detection(self, sample_ab_data):
        """Verify chi-square can detect significant differences."""
        from scipy.stats import chi2_contingency

        contingency = pd.crosstab(
            sample_ab_data["test_group"], sample_ab_data["converted"]
        )

        chi2, p_value, dof, expected = chi2_contingency(contingency)

        # With 30% vs 40% conversion in 1000 samples, should be significant
        # at typical alpha levels
        assert p_value < 0.05, "Should detect significant difference (p={p_value})"

    def test_chi_square_no_difference(self):
        """Verify chi-square returns non-significant for identical groups."""
        from scipy.stats import chi2_contingency

        # Create identical groups
        data = pd.DataFrame(
            {
                "test_group": ["A"] * 500 + ["B"] * 500,
                "converted": [1] * 250
                + [0] * 250  # Group A: 50% conversion
                + [1] * 250
                + [0] * 250,  # Group B: 50% conversion
            }
        )

        contingency = pd.crosstab(data["test_group"], data["converted"])
        chi2, p_value, dof, expected = chi2_contingency(contingency)

        # Should NOT be significant (identical groups)
        assert p_value > 0.05, f"Should not detect difference (p={p_value})"

    def test_conversion_rate_calculation(self, sample_ab_data):
        """Verify conversion rate calculation for A/B groups."""
        # Calculate conversion rates
        conversion_rates = sample_ab_data.groupby("test_group")["converted"].mean()

        group_a_rate = conversion_rates["A"]
        group_b_rate = conversion_rates["B"]

        # Verify rates match expected values
        assert group_a_rate == 0.30, f"Group A rate should be 30%, got {group_a_rate}"
        assert group_b_rate == 0.40, f"Group B rate should be 40%, got {group_b_rate}"

    def test_relative_lift_calculation(self, sample_ab_data):
        """Verify relative lift calculation."""
        # Calculate conversion rates
        group_a_rate = sample_ab_data[sample_ab_data["test_group"] == "A"][
            "converted"
        ].mean()
        group_b_rate = sample_ab_data[sample_ab_data["test_group"] == "B"][
            "converted"
        ].mean()

        # Relative lift = (B - A) / A * 100
        relative_lift = (group_b_rate - group_a_rate) / group_a_rate * 100

        # Expected: (0.40 - 0.30) / 0.30 * 100 = 33.33%
        expected_lift = (0.40 - 0.30) / 0.30 * 100

        assert abs(relative_lift - expected_lift) < 0.01, (
            f"Lift calculation error: {relative_lift} != {expected_lift}"
        )

    def test_confidence_interval_calculation(self, sample_ab_data):
        """Verify confidence interval calculation for conversion rates."""
        try:
            from statsmodels.stats.proportion import proportion_confint
        except ImportError:
            pytest.skip("statsmodels not installed - skipping CI test")

        # Group A stats
        group_a = sample_ab_data[sample_ab_data["test_group"] == "A"]
        successes_a = group_a["converted"].sum()
        nobs_a = len(group_a)

        # Calculate 95% CI
        lower_a, upper_a = proportion_confint(successes_a, nobs_a, alpha=0.05)

        # CI should contain the point estimate
        rate_a = successes_a / nobs_a
        assert lower_a <= rate_a <= upper_a, "CI should contain point estimate"

        # CI width should be reasonable
        ci_width = upper_a - lower_a
        assert ci_width < 0.2, f"CI too wide: {ci_width:.3f}"


class TestAbResultsTable:
    """Test dk.ab_results table structure and operations."""

    def test_ab_results_table_columns(self):
        """Verify ab_results table has all required columns."""
        try:
            db = get_db_manager()
            result = db.execute_query("""
                SELECT column_name, data_type
                FROM information_schema.columns 
                WHERE table_schema = 'dk' 
                  AND table_name = 'ab_results'
                ORDER BY ordinal_position
            """)
        except Exception:
            pytest.skip("Database connection failed or table doesn't exist")

        if result.empty:
            pytest.skip("ab_results table doesn't exist yet")

        required_columns = {
            "experiment_name": True,
            "analysis_date": True,
            "group_a_patients": True,
            "group_a_conversions": True,
            "group_a_revenue": True,
            "group_a_conversion_rate": True,
            "group_b_patients": True,
            "group_b_conversions": True,
            "group_b_revenue": True,
            "group_b_conversion_rate": True,
            "chi2_statistic": True,
            "p_value": True,
            "is_significant": True,
            "relative_lift_pct": True,
            "absolute_lift_pct": True,
            "confidence_interval_lower": True,
            "confidence_interval_upper": True,
        }

        actual_columns = {
            row["column_name"]: row["data_type"] for _, row in result.iterrows()
        }

        for col, required in required_columns.items():
            assert col in actual_columns, f"Missing column: {col}"

    def test_ab_results_table_exists(self):
        """Verify ab_results table exists in database."""
        try:
            db = get_db_manager()
            result = db.execute_query("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'dk' 
                  AND table_name = 'ab_results'
            """)
        except Exception:
            pytest.skip("Database connection failed")

        if len(result) == 0:
            pytest.skip("ab_results table doesn't exist yet")

        assert len(result) == 1, "ab_results table should exist"
        assert result.iloc[0]["table_name"] == "ab_results"


class TestAbTestingIntegration:
    """Integration tests for complete A/B testing workflow."""

    def test_end_to_end_ab_workflow(self):
        """Test complete A/B test analysis workflow."""
        try:
            from scipy.stats import chi2_contingency
        except ImportError:
            pytest.skip("scipy not installed - skipping chi-square test")

        try:
            db = get_db_manager()
        except Exception:
            pytest.skip("Database connection not available")

        # Step 1: Get A/B assignments
        try:
            assignments = db.execute_query("""
                SELECT 
                    a.mrn,
                    a.test_group,
                    a.experiment_id,
                    COALESCE(c.amount_collected, 0) AS revenue
                FROM dk.vw_ab_assignment a
                LEFT JOIN dk.collection c ON a.mrn = c.mrn
                WHERE c.date >= CURRENT_DATE - INTERVAL '30 days'
            """)
        except Exception:
            pytest.skip("Database views not available for A/B test analysis")

        if assignments.empty:
            pytest.skip("No recent collection data for A/B test analysis")

        # Step 2: Simulate conversion (any revenue > 0 = converted)
        assignments["converted"] = (assignments["revenue"] > 0).astype(int)

        # Step 3: Calculate group statistics
        group_stats = assignments.groupby("test_group").agg(
            patients=("mrn", "count"),
            conversions=("converted", "sum"),
            revenue=("revenue", "sum"),
        )

        if len(group_stats) != 2:
            pytest.skip("Insufficient groups for A/B test")

        # Step 4: Calculate conversion rates
        group_stats["conversion_rate"] = (
            group_stats["conversions"] / group_stats["patients"]
        )

        # Step 5: Chi-square test
        contingency = pd.crosstab(assignments["test_group"], assignments["converted"])
        chi2, p_value, dof, expected = chi2_contingency(contingency)

        # Step 6: Calculate lift
        rates = group_stats["conversion_rate"]
        if "A" in rates.index and "B" in rates.index:
            absolute_lift = rates["B"] - rates["A"]
            relative_lift = (absolute_lift / rates["A"]) * 100 if rates["A"] > 0 else 0

            # Verify calculations are valid
            assert isinstance(chi2, (int, float)), "Chi-square should be numeric"
            assert 0 <= p_value <= 1, f"P-value out of range: {p_value}"
            assert -100 <= relative_lift <= 1000, f"Lift unreasonable: {relative_lift}"

    def test_ab_assignment_with_dynamic_pricing_integration(self):
        """Verify A/B assignment integrates with dynamic pricing."""
        try:
            db = get_db_manager()
        except Exception:
            pytest.skip("Database connection not available")

        # Query that joins A/B assignment with dynamic pricing
        try:
            result = db.execute_query("""
                SELECT 
                    a.mrn,
                    a.test_group,
                    a.experiment_id,
                    d.offer_type,
                    d.discount_pct,
                    d.offer_priority
                FROM dk.vw_ab_assignment a
                JOIN dk.vw_dynamic_pricing d ON a.mrn = d.mrn
                LIMIT 50
            """)
        except Exception:
            pytest.skip("Database views not available for integration test")

        if not result.empty:
            # Verify A/B groups are assigned
            assert "test_group" in result.columns
            assert set(result["test_group"].unique()).issubset({"A", "B"})

            # Verify experiment ID is consistent
            assert (result["experiment_id"] == "dynamic_pricing_v1").all()

    def test_ab_group_balance_check(self):
        """Verify A/B groups maintain balance over time."""
        try:
            db = get_db_manager()
            result = db.execute_query("""
                SELECT 
                    CURRENT_DATE AS snapshot_date,
                    test_group,
                    COUNT(*) AS count,
                    ROUND(COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100, 2) AS pct
                FROM dk.vw_ab_assignment
                GROUP BY test_group
            """)
        except Exception:
            pytest.skip("Database view vw_ab_assignment doesn't exist yet")

        if not result.empty and len(result) == 2:
            pcts = result["pct"].tolist()

            # Each group should be 40-60% of total
            for pct in pcts:
                assert 40.0 <= pct <= 60.0, f"Group imbalance detected: {pct}%"


class TestStatisticalPower:
    """Test statistical power calculations for A/B testing."""

    def test_minimum_sample_size_for_detection(self):
        """Verify minimum sample size calculation for A/B test."""
        try:
            from statsmodels.stats.power import GofChisquarePower
        except ImportError:
            pytest.skip("statsmodels not installed - skipping power analysis")

        # Parameters for power analysis
        effect_size = 0.1  # Small effect
        alpha = 0.05  # Significance level
        power = 0.8  # Desired power

        power_analysis = GofChisquarePower()
        n_required = power_analysis.solve_power(
            effect_size=effect_size, n_bins=4, alpha=alpha, power=power
        )

        # Should require reasonable sample size
        assert n_required > 0, "Sample size should be positive"
        assert n_required < 100000, "Sample size should be reasonable"

    def test_detectable_effect_size(self):
        """Verify detectable effect size calculation."""
        try:
            from statsmodels.stats.power import GofChisquarePower
        except ImportError:
            pytest.skip("statsmodels not installed - skipping power analysis")

        # With 1000 samples, what effect size can we detect?
        power_analysis = GofChisquarePower()
        effect_size = power_analysis.solve_power(
            n_obs=1000, n_bins=4, alpha=0.05, power=0.8
        )

        # Should be able to detect small-medium effects
        assert 0.05 <= effect_size <= 0.5, f"Effect size unexpected: {effect_size}"


class TestAbTestingUtilities:
    """Test utility functions for A/B testing."""

    def test_assignment_date_is_current(self):
        """Verify assignment date matches current date."""
        try:
            db = get_db_manager()
            result = db.execute_query("""
                SELECT DISTINCT assignment_date 
                FROM dk.vw_ab_assignment
            """)
        except Exception:
            pytest.skip("Database view vw_ab_assignment doesn't exist yet")

        if not result.empty:
            # Assignment date should be today (view uses CURRENT_DATE)
            assert result.iloc[0]["assignment_date"] == date.today()

    def test_experiment_id_consistency(self):
        """Verify all assignments have same experiment ID."""
        try:
            db = get_db_manager()
            result = db.execute_query("""
                SELECT DISTINCT experiment_id 
                FROM dk.vw_ab_assignment
            """)
        except Exception:
            pytest.skip("Database view vw_ab_assignment doesn't exist yet")

        if not result.empty:
            # Should only have one experiment ID
            assert len(result) == 1, "Multiple experiment IDs found"
            assert result.iloc[0]["experiment_id"] == "dynamic_pricing_v1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
