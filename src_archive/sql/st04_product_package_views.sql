-- ============================================================
-- ST-04: Product & Package Performance
-- product_package_views.sql
-- Views for Product Mix and Package Analysis
-- ============================================================

-- ============================================================
-- VIEW 1: Product Performance Analysis
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_product_performance_analysis AS
SELECT 
    product_code,
    product_name,
    category,
    subcategory,
    transaction_year_month,
    SUM(units_sold) AS total_units_sold,
    SUM(total_quantity) AS total_quantity,
    SUM(gross_revenue) AS gross_revenue,
    SUM(total_discounts) AS total_discounts,
    SUM(net_revenue) AS net_revenue,
    AVG(avg_selling_price) AS avg_selling_price,
    SUM(unique_buyers) AS total_buyers,
    SUM(unique_orders) AS total_orders,
    COUNT(DISTINCT branch_code) AS branches_sold_in,
    -- Calculate metrics
    CASE WHEN SUM(unique_buyers) > 0 
         THEN SUM(net_revenue) / SUM(unique_buyers) 
         ELSE 0 
    END AS revenue_per_buyer,
    CASE WHEN SUM(total_orders) > 0 
         THEN SUM(net_revenue) / SUM(total_orders) 
         ELSE 0 
    END AS revenue_per_order,
    CASE WHEN SUM(gross_revenue) > 0 
         THEN (SUM(total_discounts) / SUM(gross_revenue)) * 100 
         ELSE 0 
    END AS discount_rate
FROM dk.mvw_product_performance
GROUP BY product_code, product_name, category, subcategory, transaction_year_month;

-- ============================================================
-- VIEW 2: Category Performance
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_category_performance AS
SELECT 
    category,
    subcategory,
    transaction_year_month,
    SUM(net_revenue) AS category_revenue,
    SUM(unique_buyers) AS unique_buyers,
    SUM(total_units_sold) AS total_units_sold,
    AVG(avg_selling_price) AS avg_price,
    COUNT(DISTINCT product_code) AS unique_products,
    -- Rank within month
    RANK() OVER (
        PARTITION BY transaction_year_month 
        ORDER BY SUM(net_revenue) DESC
    ) AS revenue_rank
FROM dk.mvw_product_performance
GROUP BY category, subcategory, transaction_year_month;

-- ============================================================
-- VIEW 3: Package Performance Analysis
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_package_performance AS
SELECT 
    package_code,
    package_name,
    transaction_year_month,
    branch_code,
    COUNT(*) AS packages_sold,
    SUM(net_amount) AS package_revenue,
    AVG(session_completion_pct) AS avg_completion_rate,
    COUNT(DISTINCT mrn) AS unique_patients,
    -- Calculate package metrics
    CASE WHEN COUNT(*) > 0 
         THEN SUM(net_amount) / COUNT(*) 
         ELSE 0 
    END AS avg_package_value,
    CASE WHEN COUNT(DISTINCT mrn) > 0 
         THEN SUM(net_amount) / COUNT(DISTINCT mrn) 
         ELSE 0 
    END AS revenue_per_patient
FROM dk.mvw_transaction_flat
WHERE is_package = TRUE
GROUP BY package_code, package_name, transaction_year_month, branch_code;

-- ============================================================
-- VIEW 4: Cross-sell Patterns
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_cross_sell_patterns AS
WITH patient_categories AS (
    SELECT DISTINCT
        mrn,
        transaction_date,
        category
    FROM dk.mvw_transaction_flat
),
category_combinations AS (
    SELECT 
        pc1.mrn,
        pc1.transaction_date,
        pc1.category AS category_a,
        pc2.category AS category_b
    FROM patient_categories pc1
    JOIN patient_categories pc2 ON pc1.mrn = pc2.mrn 
        AND pc1.transaction_date = pc2.transaction_date
    WHERE pc1.category < pc2.category
)
SELECT 
    category_a,
    category_b,
    COUNT(*) AS co_occurrence_count,
    COUNT(DISTINCT mrn) AS unique_patients,
    -- Calculate affinity score
    COUNT(*)::NUMERIC / (
        SELECT COUNT(DISTINCT mrn) 
        FROM dk.mvw_transaction_flat 
        WHERE category = category_a
    ) AS affinity_score
FROM category_combinations
GROUP BY category_a, category_b
HAVING COUNT(*) >= 10
ORDER BY co_occurrence_count DESC;

-- ============================================================
-- VIEW 5: Product Association Rules
-- ============================================================

CREATE OR REPLACE VIEW dk.vw_product_associations AS
WITH patient_products AS (
    SELECT DISTINCT
        mrn,
        sale_order_no,
        product_code,
        product_name,
        category
    FROM dk.mvw_transaction_flat
),
product_pairs AS (
    SELECT 
        pp1.product_code AS product_a,
        pp1.product_name AS product_a_name,
        pp1.category AS category_a,
        pp2.product_code AS product_b,
        pp2.product_name AS product_b_name,
        pp2.category AS category_b
    FROM patient_products pp1
    JOIN patient_products pp2 ON pp1.mrn = pp2.mrn 
        AND pp1.sale_order_no = pp2.sale_order_no
    WHERE pp1.product_code < pp2.product_code
),
support_calc AS (
    SELECT 
        product_a,
        product_a_name,
        category_a,
        product_b,
        product_b_name,
        category_b,
        COUNT(*) AS pair_count
    FROM product_pairs
    GROUP BY product_a, product_a_name, category_a, product_b, product_b_name, category_b
    HAVING COUNT(*) >= 5
)
SELECT 
    sc.*,
    -- Calculate support
    sc.pair_count::NUMERIC / (
        SELECT COUNT(DISTINCT sale_order_no) 
        FROM dk.mvw_transaction_flat
    ) AS support,
    -- Calculate confidence (A -> B)
    sc.pair_count::NUMERIC / NULLIF(
        (SELECT COUNT(DISTINCT sale_order_no) 
         FROM dk.mvw_transaction_flat 
         WHERE product_code = sc.product_a), 0
    ) AS confidence_a_to_b,
    -- Calculate confidence (B -> A)
    sc.pair_count::NUMERIC / NULLIF(
        (SELECT COUNT(DISTINCT sale_order_no) 
         FROM dk.mvw_transaction_flat 
         WHERE product_code = sc.product_b), 0
    ) AS confidence_b_to_a
FROM support_calc sc
ORDER BY pair_count DESC;

-- ============================================================
-- MATERIALIZED VIEW: Product Intelligence Summary
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS dk.mvw_product_intelligence CASCADE;

CREATE MATERIALIZED VIEW dk.mvw_product_intelligence AS
SELECT 
    pp.product_code,
    pp.product_name,
    pp.category,
    pp.subcategory,
    pp.is_package,
    pp.transaction_year_month,
    pp.branches_sold_in,
    pp.total_units_sold,
    pp.total_quantity,
    pp.gross_revenue,
    pp.total_discounts,
    pp.net_revenue,
    pp.avg_selling_price,
    pp.total_buyers,
    cp.revenue_rank AS category_rank,
    -- Product tier
    CASE 
        WHEN pp.net_revenue >= 10000 THEN 'Star'
        WHEN pp.net_revenue >= 5000 THEN 'Cash Cow'
        WHEN pp.net_revenue >= 1000 THEN 'Question Mark'
        ELSE 'Dog'
    END AS product_tier
FROM dk.vw_product_performance_analysis pp
LEFT JOIN dk.vw_category_performance cp ON pp.category = cp.category 
    AND pp.transaction_year_month = cp.transaction_year_month
    AND pp.subcategory = cp.subcategory;

CREATE UNIQUE INDEX idx_mvw_product_intel_pk 
ON dk.mvw_product_intelligence(product_code, transaction_year_month);

-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON VIEW dk.vw_product_performance_analysis IS 'Product-level performance metrics';
COMMENT ON VIEW dk.vw_category_performance IS 'Category performance with ranking';
COMMENT ON VIEW dk.vw_package_performance IS 'Package sales and completion analysis';
COMMENT ON VIEW dk.vw_cross_sell_patterns IS 'Category cross-sell patterns';
COMMENT ON VIEW dk.vw_product_associations IS 'Product association rules for recommendations';
COMMENT ON MATERIALIZED VIEW dk.mvw_product_intelligence IS 'Consolidated product intelligence';
