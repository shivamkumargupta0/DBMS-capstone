from datetime import datetime, timezone
from decimal import Decimal
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

def utc_now():
    return datetime.now(timezone.utc)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, server_default=db.func.now())
    
    # Relationships
    accounts = db.relationship('Account', backref='owner', cascade='all, delete-orphan', lazy='dynamic')
    transactions = db.relationship('Transaction', backref='owner', cascade='all, delete-orphan', lazy='dynamic')
    budgets = db.relationship('Budget', backref='owner', cascade='all, delete-orphan', lazy='dynamic')
    goals = db.relationship('Goal', backref='owner', cascade='all, delete-orphan', lazy='dynamic')
    investments = db.relationship('Investment', backref='owner', cascade='all, delete-orphan', lazy='dynamic')
    categories = db.relationship('Category', backref='owner', cascade='all, delete-orphan', lazy='dynamic')

    def get_id(self):
        return str(self.user_id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username!r}>'


class Account(db.Model):
    __tablename__ = 'accounts'
    
    account_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.Enum('Checking', 'Savings', 'Credit', 'Cash', name='account_types'), nullable=False)
    balance = db.Column(db.Numeric(12, 2), default=Decimal('0.00'), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, server_default=db.func.now())
    
    transactions = db.relationship('Transaction', backref='account', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f'<Account {self.name!r} ({self.type}) Balance: {self.balance}>'


class Category(db.Model):
    __tablename__ = 'categories'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', name='uq_user_category_name'),
    )
    
    category_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=True, index=True)
    name = db.Column(db.String(50), nullable=False)
    type = db.Column(db.Enum('Expense', 'Income', name='category_types'), nullable=False)
    
    transactions = db.relationship('Transaction', backref='category', lazy='dynamic')
    budgets = db.relationship('Budget', backref='category', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f'<Category {self.name!r} ({self.type})>'


class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    txn_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id', ondelete='CASCADE'), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.category_id', ondelete='CASCADE'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.Text, nullable=True)
    txn_type = db.Column(db.Enum('Expense', 'Income', name='txn_types'), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, server_default=db.func.now())

    def __repr__(self):
        return f'<Transaction {self.txn_id}: {self.txn_type} {self.amount} on {self.date}>'


class Budget(db.Model):
    __tablename__ = 'budgets'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'category_id', 'month', name='uq_user_category_month'),
    )
    
    budget_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.category_id', ondelete='CASCADE'), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # Stored as 'YYYY-MM'
    limit_amount = db.Column(db.Numeric(10, 2), nullable=False)

    def __repr__(self):
        return f'<Budget User:{self.user_id} Cat:{self.category_id} Month:{self.month} Limit:{self.limit_amount}>'


class Goal(db.Model):
    __tablename__ = 'goals'
    
    goal_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Numeric(10, 2), nullable=False)
    saved_amount = db.Column(db.Numeric(10, 2), default=Decimal('0.00'), nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, server_default=db.func.now())

    @property
    def percent_complete(self):
        if not self.target_amount or self.target_amount <= 0:
            return 0.0
        return min(100.0, round(float(self.saved_amount / self.target_amount) * 100, 1))

    def __repr__(self):
        return f'<Goal {self.name!r} Saved: {self.saved_amount}/{self.target_amount}>'


class Investment(db.Model):
    __tablename__ = 'investments'
    
    inv_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    instrument = db.Column(db.String(100), nullable=False)  # Stock ticker or fund name
    quantity = db.Column(db.Integer, nullable=False)
    buy_price = db.Column(db.Numeric(10, 2), nullable=False)
    buy_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, server_default=db.func.now())

    @property
    def total_cost(self):
        return Decimal(self.quantity) * self.buy_price

    def __repr__(self):
        return f'<Investment {self.instrument!r} Qty: {self.quantity} @ {self.buy_price}>'

