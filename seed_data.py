"""
Seed Data Script for FinAI Manager
Populates database with sample users, accounts, categories, transactions,
budgets, goals, and investment assets according to the capstone specification.
"""

from datetime import date, timedelta
from decimal import Decimal
from app import create_app
from models import db, User, Account, Category, Transaction, Budget, Goal, Investment
from ai_engine import classifier

def seed_database():
    app = create_app()
    with app.app_context():
        # Create all tables
        db.create_all()
        print("Database tables verified.")

        # 1. Global Categories
        global_categories = [
            ("Salary", "Income"),
            ("Freelance", "Income"),
            ("Investment Payout", "Income"),
            ("Food", "Expense"),
            ("Rent", "Expense"),
            ("Utilities", "Expense"),
            ("Transportation", "Expense"),
            ("Entertainment", "Expense"),
            ("Shopping", "Expense"),
            ("Healthcare", "Expense")
        ]

        cat_map = {}
        for name, c_type in global_categories:
            existing = Category.query.filter_by(name=name, user_id=None).first()
            if not existing:
                cat = Category(name=name, type=c_type, user_id=None)
                db.session.add(cat)
                db.session.flush()
                cat_map[name] = cat
            else:
                cat_map[name] = existing

        # 2. Users: Alice and Bob
        alice = User.query.filter_by(username='alice').first()
        if not alice:
            alice = User(username='alice', email='alice@example.com')
            alice.set_password('password123')
            db.session.add(alice)
            db.session.flush()
            print("Created user 'alice' (password: password123)")

        bob = User.query.filter_by(username='bob').first()
        if not bob:
            bob = User(username='bob', email='bob@example.com')
            bob.set_password('password123')
            db.session.add(bob)
            db.session.flush()
            print("Created user 'bob' (password: password123)")

        # 3. Custom Category for Alice
        gaming_cat = Category.query.filter_by(name='Gaming', user_id=alice.user_id).first()
        if not gaming_cat:
            gaming_cat = Category(name='Gaming', type='Expense', user_id=alice.user_id)
            db.session.add(gaming_cat)
            db.session.flush()
        cat_map['Gaming'] = gaming_cat

        # 4. Accounts
        alice_checking = Account.query.filter_by(user_id=alice.user_id, name='Checking Account').first()
        if not alice_checking:
            alice_checking = Account(user_id=alice.user_id, name='Checking Account', type='Checking', balance=Decimal('2850.00'))
            db.session.add(alice_checking)

        alice_savings = Account.query.filter_by(user_id=alice.user_id, name='Savings Account').first()
        if not alice_savings:
            alice_savings = Account(user_id=alice.user_id, name='Savings Account', type='Savings', balance=Decimal('5000.00'))
            db.session.add(alice_savings)

        bob_checking = Account.query.filter_by(user_id=bob.user_id, name='Bob Checking').first()
        if not bob_checking:
            bob_checking = Account(user_id=bob.user_id, name='Bob Checking', type='Checking', balance=Decimal('1200.00'))
            db.session.add(bob_checking)

        db.session.flush()

        # 5. Transactions for Alice (Multi-month history for rich Chart.js & ML forecasting)
        today = date.today()
        cur_year, cur_month = today.year, today.month
        cur_month_str = today.strftime('%Y-%m')

        existing_txns = Transaction.query.filter_by(user_id=alice.user_id).count()
        if existing_txns == 0:
            sample_txns = [
                # 3 Months ago
                (today - timedelta(days=90), 'Income', Decimal('3000.00'), cat_map['Salary'], 'Monthly Corporate Salary', alice_checking),
                (today - timedelta(days=88), 'Expense', Decimal('1200.00'), cat_map['Rent'], 'Apartment Rent payment', alice_checking),
                (today - timedelta(days=85), 'Expense', Decimal('320.00'), cat_map['Food'], 'Weekly groceries Whole Foods', alice_checking),
                (today - timedelta(days=80), 'Expense', Decimal('65.00'), cat_map['Utilities'], 'Electric utility bill', alice_checking),
                (today - timedelta(days=75), 'Expense', Decimal('90.00'), cat_map['Transportation'], 'Gasoline and vehicle fuel', alice_checking),

                # 2 Months ago
                (today - timedelta(days=60), 'Income', Decimal('3000.00'), cat_map['Salary'], 'Monthly Corporate Salary', alice_checking),
                (today - timedelta(days=58), 'Expense', Decimal('1200.00'), cat_map['Rent'], 'Apartment Rent payment', alice_checking),
                (today - timedelta(days=55), 'Expense', Decimal('360.00'), cat_map['Food'], 'Groceries and snacks Kroger', alice_checking),
                (today - timedelta(days=50), 'Expense', Decimal('80.00'), cat_map['Utilities'], 'Water and power bill', alice_checking),
                (today - timedelta(days=45), 'Expense', Decimal('45.00'), cat_map['Entertainment'], 'Movie theater & concessions', alice_checking),

                # Last Month
                (today - timedelta(days=30), 'Income', Decimal('3200.00'), cat_map['Salary'], 'Salary + performance bonus', alice_checking),
                (today - timedelta(days=28), 'Expense', Decimal('1200.00'), cat_map['Rent'], 'Apartment Rent payment', alice_checking),
                (today - timedelta(days=25), 'Expense', Decimal('390.00'), cat_map['Food'], 'Supermarket groceries', alice_checking),
                (today - timedelta(days=22), 'Expense', Decimal('110.00'), cat_map['Transportation'], 'Shell gas refill & subway pass', alice_checking),
                (today - timedelta(days=20), 'Expense', Decimal('15.99'), cat_map['Entertainment'], 'Netflix monthly plan', alice_checking),

                # Current Month Transactions
                (date(cur_year, cur_month, 1), 'Income', Decimal('3000.00'), cat_map['Salary'], 'Monthly Salary Direct Deposit', alice_checking),
                (date(cur_year, cur_month, 2), 'Expense', Decimal('1200.00'), cat_map['Rent'], 'Apartment Rent Payment', alice_checking),
                (date(cur_year, cur_month, 4), 'Expense', Decimal('115.50'), cat_map['Food'], 'Groceries at Whole Foods', alice_checking),
                (date(cur_year, cur_month, 8), 'Expense', Decimal('85.20'), cat_map['Food'], 'Trader Joe organic supplies', alice_checking),
                (date(cur_year, cur_month, 12), 'Expense', Decimal('55.00'), cat_map['Transportation'], 'Shell Gas Station Petrol', alice_checking),
                (date(cur_year, cur_month, 15), 'Expense', Decimal('19.99'), cat_map['Entertainment'], 'Spotify Premium and Hulu', alice_checking),
                (date(cur_year, cur_month, 18), 'Expense', Decimal('60.00'), cat_map['Gaming'], 'Steam video game summer sale', alice_checking),
                (date(cur_year, cur_month, 20), 'Expense', Decimal('420.00'), cat_map['Food'], 'Gourmet banquet dinner (Spike Anomaly)', alice_checking)
            ]

            for dt, ttype, amt, cat_obj, desc, acct in sample_txns:
                txn = Transaction(
                    user_id=alice.user_id,
                    account_id=acct.account_id,
                    category_id=cat_obj.category_id,
                    date=dt,
                    amount=amt,
                    description=desc,
                    txn_type=ttype
                )
                db.session.add(txn)

            # Bob transaction
            bob_txn = Transaction(
                user_id=bob.user_id,
                account_id=bob_checking.account_id,
                category_id=cat_map['Food'].category_id,
                date=today,
                amount=Decimal('100.00'),
                description='Dinner at Italian Bistro',
                txn_type='Expense'
            )
            db.session.add(bob_txn)
            print("Populated realistic historical and current transactions.")

        # 6. Budgets for Alice
        existing_budgets = Budget.query.filter_by(user_id=alice.user_id, month=cur_month_str).count()
        if existing_budgets == 0:
            b1 = Budget(user_id=alice.user_id, category_id=cat_map['Food'].category_id, month=cur_month_str, limit_amount=Decimal('500.00'))
            b2 = Budget(user_id=alice.user_id, category_id=cat_map['Rent'].category_id, month=cur_month_str, limit_amount=Decimal('1300.00'))
            b3 = Budget(user_id=alice.user_id, category_id=cat_map['Entertainment'].category_id, month=cur_month_str, limit_amount=Decimal('100.00'))
            db.session.add_all([b1, b2, b3])
            print("Configured monthly budgets.")

        # 7. Goals for Alice
        existing_goals = Goal.query.filter_by(user_id=alice.user_id).count()
        if existing_goals == 0:
            g1 = Goal(user_id=alice.user_id, name='Car Savings', target_amount=Decimal('10000.00'), saved_amount=Decimal('2500.00'), due_date=date(2026, 12, 31))
            g2 = Goal(user_id=alice.user_id, name='Emergency Fund', target_amount=Decimal('5000.00'), saved_amount=Decimal('3750.00'), due_date=date(2027, 6, 30))
            db.session.add_all([g1, g2])
            print("Established savings goals.")

        # 8. Investments for Alice
        existing_invs = Investment.query.filter_by(user_id=alice.user_id).count()
        if existing_invs == 0:
            inv1 = Investment(user_id=alice.user_id, instrument='AAPL', quantity=10, buy_price=Decimal('150.00'), buy_date=date(2026, 9, 15))
            inv2 = Investment(user_id=alice.user_id, instrument='NVDA', quantity=5, buy_price=Decimal('120.00'), buy_date=date(2026, 10, 5))
            inv3 = Investment(user_id=alice.user_id, instrument='VOO', quantity=4, buy_price=Decimal('480.00'), buy_date=date(2026, 8, 20))
            db.session.add_all([inv1, inv2, inv3])
            print("Recorded investment portfolio.")

        db.session.commit()
        
        # Retrain NLP classifier with seed data
        classifier.retrain_with_user_data()
        print("FinAI Manager seed completed successfully!")

if __name__ == '__main__':
    seed_database()
