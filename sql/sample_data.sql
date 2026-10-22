-- =====================================================================
-- Sample Data Script: AI-Based Personal Finance & Investment Management
-- Section 4.3 Reference Data
-- =====================================================================

USE finance_db;

-- 1. Users (Passwords hashed via Werkzeug scrypt/pbkdf2: password 'password123')
INSERT INTO users (user_id, username, email, password_hash) VALUES
(1, 'alice', 'alice@example.com', 'scrypt:32768:8:1$x8k4y7H9oP2q$0f2e2fa9d6bf08ceca761be945ea45cfddadfaae4714bf485e9e8f1bb8ec19ff1c9bcf281a8c9b33a76ef4829ad4dc351fc8aa7899be4ea5bc755609ff0e2712'),
(2, 'bob', 'bob@example.com', 'scrypt:32768:8:1$x8k4y7H9oP2q$0f2e2fa9d6bf08ceca761be945ea45cfddadfaae4714bf485e9e8f1bb8ec19ff1c9bcf281a8c9b33a76ef4829ad4dc351fc8aa7899be4ea5bc755609ff0e2712')
ON DUPLICATE KEY UPDATE username=username;

-- 2. Accounts (Alice has Checking and Savings, Bob has Checking)
INSERT INTO accounts (account_id, user_id, name, type, balance) VALUES
(1, 1, 'Checking Account', 'Checking', 1500.00),
(2, 1, 'Savings Account', 'Savings', 5000.00),
(3, 2, 'Bob Checking', 'Checking', 1200.00)
ON DUPLICATE KEY UPDATE balance=VALUES(balance);

-- 3. Categories (Global categories have user_id = NULL)
INSERT INTO categories (category_id, user_id, name, type) VALUES
(1, NULL, 'Salary', 'Income'),
(2, NULL, 'Food', 'Expense'),
(3, NULL, 'Rent', 'Expense'),
(4, NULL, 'Utilities', 'Expense'),
(5, NULL, 'Transportation', 'Expense'),
(6, NULL, 'Entertainment', 'Expense'),
(7, 1, 'Gaming', 'Expense') -- Alice-specific custom category
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- 4. Transactions (Sample historical & current transactions)
INSERT INTO transactions (txn_id, user_id, account_id, category_id, date, amount, description, txn_type) VALUES
(1, 1, 1, 1, '2026-10-01', 3000.00, 'Monthly Salary Deposit', 'Income'),
(2, 1, 1, 2, '2026-10-02', 50.00, 'Groceries at Whole Foods', 'Expense'),
(3, 1, 2, 3, '2026-10-03', 1200.00, 'October Apartment Rent', 'Expense'),
(4, 2, 3, 2, '2026-10-01', 100.00, 'Dinner at Italian Bistro', 'Expense'),
(5, 1, 1, 2, '2026-10-10', 120.00, 'Supermarket Stockup', 'Expense'),
(6, 1, 1, 5, '2026-10-12', 45.00, 'Shell Gas Station Petrol', 'Expense'),
(7, 1, 1, 6, '2026-10-15', 18.00, 'Netflix Subscription', 'Expense'),
(8, 1, 1, 7, '2026-10-18', 60.00, 'Steam Game Sale', 'Expense')
ON DUPLICATE KEY UPDATE amount=VALUES(amount);

-- 5. Budgets (Alice sets a $500 food budget and $1300 rent budget for October 2026)
INSERT INTO budgets (budget_id, user_id, category_id, month, limit_amount) VALUES
(1, 1, 2, '2026-10', 500.00),
(2, 1, 3, '2026-10', 1300.00),
(3, 1, 6, '2026-10', 100.00)
ON DUPLICATE KEY UPDATE limit_amount=VALUES(limit_amount);

-- 6. Goals (Alice has a $10,000 car fund goal by Dec 2026)
INSERT INTO goals (goal_id, user_id, name, target_amount, saved_amount, due_date) VALUES
(1, 1, 'Car Savings', 10000.00, 2000.00, '2026-12-31'),
(2, 1, 'Emergency Fund', 5000.00, 3500.00, '2027-06-30')
ON DUPLICATE KEY UPDATE saved_amount=VALUES(saved_amount);

-- 7. Investments (Alice bought 10 shares of AAPL and 5 shares of NVDA)
INSERT INTO investments (inv_id, user_id, instrument, quantity, buy_price, buy_date) VALUES
(1, 1, 'AAPL', 10, 150.00, '2026-09-15'),
(2, 1, 'NVDA', 5, 120.00, '2026-10-05')
ON DUPLICATE KEY UPDATE quantity=VALUES(quantity);
