-- =====================================================================
-- Section 8.2 Stored Procedures (MySQL)
-- =====================================================================

USE finance_db;

DELIMITER $$

DROP PROCEDURE IF EXISTS monthly_summary $$
CREATE PROCEDURE monthly_summary(IN uid INT, IN target_month CHAR(7))
BEGIN
    SELECT 
        IFNULL(SUM(CASE WHEN txn_type = 'Income' THEN amount ELSE 0 END), 0) AS total_income,
        IFNULL(SUM(CASE WHEN txn_type = 'Expense' THEN amount ELSE 0 END), 0) AS total_expense,
        IFNULL(SUM(CASE WHEN txn_type = 'Income' THEN amount ELSE -amount END), 0) AS net_cashflow
    FROM transactions 
    WHERE user_id = uid AND DATE_FORMAT(date, '%Y-%m') = target_month;
END $$

DROP PROCEDURE IF EXISTS update_account_balance_on_txn $$
CREATE PROCEDURE update_account_balance_on_txn(
    IN p_user_id INT,
    IN p_account_id INT,
    IN p_category_id INT,
    IN p_date DATE,
    IN p_amount DECIMAL(10,2),
    IN p_desc TEXT,
    IN p_type ENUM('Expense', 'Income')
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;
        -- Atomically adjust account balance
        UPDATE accounts
        SET balance = balance + (CASE WHEN p_type = 'Expense' THEN -p_amount ELSE p_amount END)
        WHERE account_id = p_account_id AND user_id = p_user_id;

        -- Record transaction
        INSERT INTO transactions (user_id, account_id, category_id, date, amount, description, txn_type)
        VALUES (p_user_id, p_account_id, p_category_id, p_date, p_amount, p_desc, p_type);
    COMMIT;
END $$

DELIMITER ;
