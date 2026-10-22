-- =====================================================================
-- Section 8.1 Key SQL Queries
-- =====================================================================

-- Query A: Monthly Budget vs. Actual Spending
-- For each budget category, compute total spent this month and compare to budget limit.
SELECT 
    b.month, 
    c.name AS category,
    b.limit_amount AS budget,
    COALESCE(SUM(t.amount), 0) AS spent,
    (b.limit_amount - COALESCE(SUM(t.amount), 0)) AS remaining_budget,
    ROUND((COALESCE(SUM(t.amount), 0) / b.limit_amount) * 100, 1) AS utilization_percent
FROM budgets b
JOIN categories c ON b.category_id = c.category_id
LEFT JOIN transactions t
    ON t.category_id = b.category_id
    AND DATE_FORMAT(t.date, '%Y-%m') = b.month
    AND t.txn_type = 'Expense'
    AND t.user_id = b.user_id
WHERE b.user_id = 1 AND b.month = '2026-10'
GROUP BY b.budget_id, b.month, c.name, b.limit_amount;


-- Query B: Transactions in Category per Month
-- Count number and sum of expenses in a given category over all months (for trend chart).
SELECT 
    DATE_FORMAT(t.date, '%Y-%m') AS month,
    COUNT(*) AS txn_count,
    SUM(t.amount) AS total_spent
FROM transactions t
WHERE t.user_id = 1 AND t.category_id = 2 AND t.txn_type = 'Expense'
GROUP BY month
ORDER BY month ASC;


-- Query C: Goal Progress
-- Retrieve each goal's saved vs. target amount, percentage completed, and remaining needed.
SELECT 
    name, 
    target_amount, 
    saved_amount,
    (target_amount - saved_amount) AS remaining_to_save,
    ROUND(saved_amount / target_amount * 100, 1) AS percent_done,
    due_date
FROM goals 
WHERE user_id = 1;


-- Query D: Account Balance Update (ACID Transaction)
-- After each transaction insert, update the account balance atomically.
START TRANSACTION;

-- Example: inserting an expense of 45.00 for account_id = 1
UPDATE accounts 
SET balance = balance + (CASE WHEN 'Expense' = 'Expense' THEN -45.00 ELSE 45.00 END)
WHERE account_id = 1;

INSERT INTO transactions (user_id, account_id, category_id, date, amount, description, txn_type)
VALUES (1, 1, 5, '2026-10-22', 45.00, 'Shell Gas refill', 'Expense');

COMMIT;
