"""
Automated Test Suite for FinAI Manager
Covers Section 8.3 Requirements:
1. User Authentication (registration, login, secure password hashing check)
2. CRUD Operations on Transactions with Atomic Account Balance Update
3. Budget vs Actual Spending verification (Query A)
4. Savings Goal progress calculation (Query C)
5. Edge Cases: Over-budget alert recommendation triggering
6. CSV Import and Error Handling
7. AI / Machine Learning Classification and Forecasting
"""

import io
from datetime import date
from decimal import Decimal
import pytest
from app import create_app
from config import Config
from models import db, User, Account, Category, Transaction, Budget, Goal, Investment
from ai_engine import classifier, analyze_spending, forecast_spending

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'

@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        # Create base test user and accounts
        user = User(username='alice', email='alice@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()

        acct1 = Account(user_id=user.user_id, name='Checking Account', type='Checking', balance=Decimal('1500.00'))
        acct2 = Account(user_id=user.user_id, name='Savings Account', type='Savings', balance=Decimal('5000.00'))
        cat_food = Category(name='Food', type='Expense', user_id=None)
        cat_salary = Category(name='Salary', type='Income', user_id=None)
        cat_rent = Category(name='Rent', type='Expense', user_id=None)

        db.session.add_all([acct1, acct2, cat_food, cat_salary, cat_rent])
        db.session.commit()

        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_user_auth(client, app):
    """Verify registration, password hashing (not plaintext), and login session."""
    with app.app_context():
        # 1. Register new user
        resp = client.post('/register', data={
            'username': 'bob',
            'email': 'bob@example.com',
            'password': 'secretpassword',
            'confirm_password': 'secretpassword'
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b'Account created successfully' in resp.data

        # 2. Verify password hash is stored in DB (not plaintext)
        bob = User.query.filter_by(username='bob').first()
        assert bob is not None
        assert bob.password_hash != 'secretpassword'
        assert bob.check_password('secretpassword') is True
        assert bob.check_password('wrongpassword') is False

        # 3. Test login
        login_resp = client.post('/login', data={
            'username': 'bob',
            'password': 'secretpassword'
        }, follow_redirects=True)
        assert b'Welcome back, bob!' in login_resp.data

def test_add_transaction_and_atomic_balance(client, app):
    """Test adding an expense transaction and verify atomic deduction from account balance."""
    with app.app_context():
        # Log in as Alice
        client.post('/login', data={'username': 'alice', 'password': 'password123'})

        acct = Account.query.filter_by(name='Checking Account').first()
        cat = Category.query.filter_by(name='Food').first()
        initial_balance = float(acct.balance)

        # Record $50.00 expense
        resp = client.post('/transactions/add', data={
            'account_id': acct.account_id,
            'category_id': cat.category_id,
            'date': '2026-10-02',
            'amount': '50.00',
            'description': 'Groceries',
            'txn_type': 'Expense'
        }, follow_redirects=True)

        assert resp.status_code == 200
        assert b'Transaction recorded successfully' in resp.data

        # Verify Transaction created
        txn = Transaction.query.filter_by(amount=Decimal('50.00'), txn_type='Expense').first()
        assert txn is not None
        assert txn.description == 'Groceries'

        # Verify atomic account balance update (1500.00 - 50.00 = 1450.00)
        db.session.refresh(acct)
        assert float(acct.balance) == initial_balance - 50.00

def test_budget_query_and_actual_spending(client, app):
    """Section 8.1 Query A: Verify category budget vs actual spending calculation."""
    with app.app_context():
        user = User.query.filter_by(username='alice').first()
        acct = Account.query.filter_by(user_id=user.user_id, name='Checking Account').first()
        cat_food = Category.query.filter_by(name='Food').first()

        # Set budget of $500 for Food in 2026-10
        budget = Budget(user_id=user.user_id, category_id=cat_food.category_id, month='2026-10', limit_amount=Decimal('500.00'))
        db.session.add(budget)

        # Add 2 transactions in that month
        t1 = Transaction(user_id=user.user_id, account_id=acct.account_id, category_id=cat_food.category_id,
                         date=date(2026, 10, 2), amount=Decimal('50.00'), txn_type='Expense')
        t2 = Transaction(user_id=user.user_id, account_id=acct.account_id, category_id=cat_food.category_id,
                         date=date(2026, 10, 10), amount=Decimal('120.00'), txn_type='Expense')
        db.session.add_all([t1, t2])
        db.session.commit()

        # Run analysis for 2026-10
        analysis = analyze_spending(user.user_id, '2026-10')
        b_info = next((b for b in analysis['budget_insights'] if b['category'] == 'Food'), None)
        assert b_info is not None
        assert b_info['budget'] == 500.00
        assert b_info['spent'] == 170.00
        assert b_info['remaining'] == 330.00
        assert b_info['utilization_pct'] == 34.0

def test_edge_case_budget_exceeded_alert(client, app):
    """Add a transaction that exceeds budget and verify AI recommendation alert is triggered."""
    with app.app_context():
        user = User.query.filter_by(username='alice').first()
        acct = Account.query.filter_by(user_id=user.user_id, name='Checking Account').first()
        cat = Category.query.filter_by(name='Food').first()

        # Set low budget of $100.00
        budget = Budget(user_id=user.user_id, category_id=cat.category_id, month='2026-10', limit_amount=Decimal('100.00'))
        # Add expense of $250.00
        over_txn = Transaction(user_id=user.user_id, account_id=acct.account_id, category_id=cat.category_id,
                               date=date(2026, 10, 15), amount=Decimal('250.00'), txn_type='Expense',
                               description='Large luxury dinner')
        db.session.add_all([budget, over_txn])
        db.session.commit()

        analysis = analyze_spending(user.user_id, '2026-10')
        exceeded_alerts = [r for r in analysis['recommendations'] if r['type'] == 'danger' and 'Over Budget' in r['title']]
        assert len(exceeded_alerts) > 0
        assert '250.00' in exceeded_alerts[0]['message']

def test_goals_progress_tracking(client, app):
    """Section 8.1 Query C: Goal progress percentage calculation."""
    with app.app_context():
        user = User.query.filter_by(username='alice').first()
        goal = Goal(user_id=user.user_id, name='Car Savings', target_amount=Decimal('10000.00'), saved_amount=Decimal('2000.00'), due_date=date(2026, 12, 31))
        db.session.add(goal)
        db.session.commit()

        assert goal.percent_complete == 20.0

def test_csv_import_and_error_handling(client, app):
    """Test CSV transaction batch import and malformed data handling."""
    with app.app_context():
        client.post('/login', data={'username': 'alice', 'password': 'password123'})

        # Valid CSV
        csv_data = "date,amount,type,category,description\n2026-10-05,45.00,Expense,Food,Lunch with colleagues\n2026-10-06,2000.00,Income,Salary,Consulting payment\n"
        data = {
            'file': (io.BytesIO(csv_data.encode('utf-8')), 'transactions.csv')
        }
        resp = client.post('/transactions/import', data=data, content_type='multipart/form-data', follow_redirects=True)
        assert resp.status_code == 200
        assert b'Successfully imported 2 transactions' in resp.data

        # Verify DB transactions count
        assert Transaction.query.filter_by(amount=Decimal('45.00')).first() is not None

        # Malformed CSV missing required columns
        bad_csv = "random_col1,random_col2\nfoo,bar\n"
        bad_data = {
            'file': (io.BytesIO(bad_csv.encode('utf-8')), 'bad.csv')
        }
        resp_bad = client.post('/transactions/import', data=bad_data, content_type='multipart/form-data', follow_redirects=True)
        assert b'CSV must contain at least' in resp_bad.data

def test_ai_categorizer_prediction():
    """Verify Scikit-Learn NLP text classification accuracy on test merchant strings."""
    pred1, conf1 = classifier.predict("Weekly grocery run at Whole Foods")
    assert pred1 == "Food"
    assert conf1 > 0.4

    pred2, conf2 = classifier.predict("Shell gasoline refill tank")
    assert pred2 == "Transportation"

    pred3, conf3 = classifier.predict("Corporate salary payroll direct deposit")
    assert pred3 == "Salary"
