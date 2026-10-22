import io
import csv
from datetime import datetime, date, timedelta
from decimal import Decimal
import pandas as pd
from flask import Flask, render_template, request, redirect, flash, url_for, jsonify, Response, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, or_, and_

from config import Config
from models import db, User, Account, Category, Transaction, Budget, Goal, Investment
from ai_engine import classifier, analyze_spending, forecast_spending, detect_spending_anomalies, get_month_range

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Helper context processor for templates
    @app.context_processor
    def inject_now():
        return {
            'now': datetime.now(),
            'current_month_str': date.today().strftime('%Y-%m'),
            'today_date': date.today().strftime('%Y-%m-%d')
        }

    # -------------------------------------------------------------
    # Authentication Routes
    # -------------------------------------------------------------
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')

            if not username or not email or not password:
                flash('All fields are required.', 'danger')
                return render_template('register.html')

            if password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return render_template('register.html')

            if len(password) < 6:
                flash('Password must be at least 6 characters long.', 'danger')
                return render_template('register.html')

            if User.query.filter_by(username=username).first():
                flash('Username already registered. Please choose another.', 'danger')
                return render_template('register.html')

            if User.query.filter_by(email=email).first():
                flash('Email already registered. Please log in.', 'danger')
                return render_template('register.html')

            # Create user with hashed password
            new_user = User(username=username, email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            
            try:
                db.session.commit()
                # Create default primary accounts for new user
                checking = Account(user_id=new_user.user_id, name='Primary Checking', type='Checking', balance=Decimal('1000.00'))
                savings = Account(user_id=new_user.user_id, name='High Yield Savings', type='Savings', balance=Decimal('2500.00'))
                db.session.add_all([checking, savings])
                db.session.commit()

                flash('Account created successfully! Please log in.', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback()
                flash(f'Registration error: {str(e)}', 'danger')
                return render_template('register.html')

        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')

            user = User.query.filter((User.username == username) | (User.email == username.lower())).first()

            if user and user.check_password(password):
                login_user(user, remember=request.form.get('remember') == 'on')
                flash(f'Welcome back, {user.username}!', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('dashboard'))
            else:
                flash('Invalid username or password.', 'danger')

        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('You have been logged out safely.', 'info')
        return redirect(url_for('login'))

    # -------------------------------------------------------------
    # Dashboard Route
    # -------------------------------------------------------------
    @app.route('/')
    @app.route('/dashboard')
    @login_required
    def dashboard():
        today = date.today()
        current_month = today.strftime('%Y-%m')
        start_date, end_date = get_month_range(today.year, today.month)

        # 1. Accounts Summary
        accounts = Account.query.filter_by(user_id=current_user.user_id).all()
        total_balance = sum([float(a.balance) for a in accounts])

        # 2. Monthly Income & Expense
        monthly_income = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.user_id == current_user.user_id,
            Transaction.txn_type == 'Income',
            Transaction.date >= start_date,
            Transaction.date <= end_date
        ).scalar()

        monthly_expense = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.user_id == current_user.user_id,
            Transaction.txn_type == 'Expense',
            Transaction.date >= start_date,
            Transaction.date <= end_date
        ).scalar()

        monthly_income = float(monthly_income or 0.0)
        monthly_expense = float(monthly_expense or 0.0)
        net_savings = monthly_income - monthly_expense
        savings_rate = round((net_savings / monthly_income * 100), 1) if monthly_income > 0 else 0.0

        # 3. Category Expenses Breakdown (for Chart.js Doughnut)
        category_spending_raw = db.session.query(
            Category.name,
            func.sum(Transaction.amount)
        ).join(Category, Transaction.category_id == Category.category_id).filter(
            Transaction.user_id == current_user.user_id,
            Transaction.txn_type == 'Expense',
            Transaction.date >= start_date,
            Transaction.date <= end_date
        ).group_by(Category.name).all()

        chart_category_labels = [row[0] for row in category_spending_raw]
        chart_category_values = [float(row[1]) for row in category_spending_raw]

        # 4. Last 6 Months Income vs Expense (for Trend Chart)
        six_months_ago = today - timedelta(days=180)
        trend_records = db.session.query(
            Transaction.date,
            Transaction.txn_type,
            Transaction.amount
        ).filter(
            Transaction.user_id == current_user.user_id,
            Transaction.date >= six_months_ago
        ).order_by(Transaction.date.asc()).all()

        monthly_trends = {}
        for r in trend_records:
            m_key = r.date.strftime('%Y-%m')
            if m_key not in monthly_trends:
                monthly_trends[m_key] = {'Income': 0.0, 'Expense': 0.0}
            monthly_trends[m_key][r.txn_type] += float(r.amount)

        sorted_months = sorted(monthly_trends.keys())[-6:]
        trend_labels = sorted_months
        trend_income = [round(monthly_trends[m]['Income'], 2) for m in sorted_months]
        trend_expense = [round(monthly_trends[m]['Expense'], 2) for m in sorted_months]

        # 5. Investments Total
        investments = Investment.query.filter_by(user_id=current_user.user_id).all()
        total_invested = sum([float(inv.total_cost) for inv in investments])

        # 6. Active Goals
        goals = Goal.query.filter_by(user_id=current_user.user_id).order_by(Goal.due_date.asc().nullslast()).limit(4).all()

        # 7. Recent Transactions
        recent_txns = Transaction.query.filter_by(user_id=current_user.user_id)\
            .order_by(Transaction.date.desc(), Transaction.txn_id.desc())\
            .limit(6).all()

        # 8. AI Quick Advisory
        ai_analysis = analyze_spending(current_user.user_id, current_month)

        return render_template(
            'dashboard.html',
            total_balance=total_balance,
            monthly_income=monthly_income,
            monthly_expense=monthly_expense,
            net_savings=net_savings,
            savings_rate=savings_rate,
            total_invested=total_invested,
            accounts=accounts,
            goals=goals,
            recent_transactions=recent_txns,
            chart_category_labels=chart_category_labels,
            chart_category_values=chart_category_values,
            trend_labels=trend_labels,
            trend_income=trend_income,
            trend_expense=trend_expense,
            ai_recommendations=ai_analysis['recommendations'][:3],
            budget_insights=ai_analysis['budget_insights']
        )

    # -------------------------------------------------------------
    # Transactions Routes (CRUD + CSV)
    # -------------------------------------------------------------
    @app.route('/transactions')
    @login_required
    def view_transactions():
        query = Transaction.query.filter_by(user_id=current_user.user_id)

        # Filters
        account_id = request.args.get('account_id', type=int)
        category_id = request.args.get('category_id', type=int)
        txn_type = request.args.get('txn_type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search_query = request.args.get('q', '').strip()

        if account_id:
            query = query.filter(Transaction.account_id == account_id)
        if category_id:
            query = query.filter(Transaction.category_id == category_id)
        if txn_type in ('Expense', 'Income'):
            query = query.filter(Transaction.txn_type == txn_type)
        if start_date:
            try:
                s_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
                query = query.filter(Transaction.date >= s_dt)
            except ValueError:
                pass
        if end_date:
            try:
                e_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
                query = query.filter(Transaction.date <= e_dt)
            except ValueError:
                pass
        if search_query:
            query = query.filter(Transaction.description.ilike(f'%{search_query}%'))

        transactions = query.order_by(Transaction.date.desc(), Transaction.txn_id.desc()).all()

        total_income = sum([float(t.amount) for t in transactions if t.txn_type == 'Income'])
        total_expense = sum([float(t.amount) for t in transactions if t.txn_type == 'Expense'])

        accounts = Account.query.filter_by(user_id=current_user.user_id).all()
        categories = Category.query.filter(
            or_(Category.user_id == current_user.user_id, Category.user_id.is_(None))
        ).order_by(Category.name.asc()).all()

        return render_template(
            'transactions.html',
            transactions=transactions,
            accounts=accounts,
            categories=categories,
            total_income=total_income,
            total_expense=total_expense,
            selected_account=account_id,
            selected_category=category_id,
            selected_type=txn_type,
            selected_start=start_date,
            selected_end=end_date,
            search_query=search_query
        )

    @app.route('/transactions/add', methods=['GET', 'POST'])
    @login_required
    def add_transaction():
        accounts = Account.query.filter_by(user_id=current_user.user_id).all()
        categories = Category.query.filter(
            or_(Category.user_id == current_user.user_id, Category.user_id.is_(None))
        ).order_by(Category.name.asc()).all()

        if request.method == 'POST':
            account_id = request.form.get('account_id', type=int)
            category_id = request.form.get('category_id', type=int)
            date_str = request.form.get('date')
            amount_val = request.form.get('amount')
            description = request.form.get('description', '').strip()
            txn_type = request.form.get('txn_type')

            if not account_id or not category_id or not date_str or not amount_val or not txn_type:
                flash('Please fill in all required fields.', 'danger')
                return render_template('add_transaction.html', accounts=accounts, categories=categories)

            try:
                txn_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                amount = Decimal(str(amount_val))
                if amount <= 0:
                    flash('Amount must be positive.', 'danger')
                    return render_template('add_transaction.html', accounts=accounts, categories=categories)

                account = Account.query.filter_by(account_id=account_id, user_id=current_user.user_id).first()
                if not account:
                    flash('Invalid account selected.', 'danger')
                    return render_template('add_transaction.html', accounts=accounts, categories=categories)

                # ACID Transaction: Insert record & adjust account balance atomically
                txn = Transaction(
                    user_id=current_user.user_id,
                    account_id=account_id,
                    category_id=category_id,
                    date=txn_date,
                    amount=amount,
                    description=description,
                    txn_type=txn_type
                )
                db.session.add(txn)

                if txn_type == 'Expense':
                    account.balance -= amount
                else:
                    account.balance += amount

                db.session.commit()
                flash('Transaction recorded successfully.', 'success')
                return redirect(url_for('view_transactions'))
            except Exception as e:
                db.session.rollback()
                flash(f'Failed to add transaction: {str(e)}', 'danger')

        return render_template('add_transaction.html', accounts=accounts, categories=categories)

    @app.route('/transactions/edit/<int:id>', methods=['GET', 'POST'])
    @login_required
    def edit_transaction(id):
        txn = Transaction.query.filter_by(txn_id=id, user_id=current_user.user_id).first_or_404()
        accounts = Account.query.filter_by(user_id=current_user.user_id).all()
        categories = Category.query.filter(
            or_(Category.user_id == current_user.user_id, Category.user_id.is_(None))
        ).order_by(Category.name.asc()).all()

        if request.method == 'POST':
            new_account_id = request.form.get('account_id', type=int)
            new_category_id = request.form.get('category_id', type=int)
            new_date_str = request.form.get('date')
            new_amount_val = request.form.get('amount')
            new_desc = request.form.get('description', '').strip()
            new_type = request.form.get('txn_type')

            try:
                new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
                new_amount = Decimal(str(new_amount_val))
                if new_amount <= 0:
                    flash('Amount must be positive.', 'danger')
                    return render_template('edit_transaction.html', txn=txn, accounts=accounts, categories=categories)

                # Revert old balance adjustment
                old_account = db.session.get(Account, txn.account_id)
                if old_account:
                    if txn.txn_type == 'Expense':
                        old_account.balance += txn.amount
                    else:
                        old_account.balance -= txn.amount

                # Update transaction fields
                txn.account_id = new_account_id
                txn.category_id = new_category_id
                txn.date = new_date
                txn.amount = new_amount
                txn.description = new_desc
                txn.txn_type = new_type

                # Apply new balance adjustment
                new_account = db.session.get(Account, new_account_id)
                if new_account:
                    if new_type == 'Expense':
                        new_account.balance -= new_amount
                    else:
                        new_account.balance += new_amount

                db.session.commit()
                flash('Transaction updated successfully.', 'success')
                return redirect(url_for('view_transactions'))
            except Exception as e:
                db.session.rollback()
                flash(f'Failed to update transaction: {str(e)}', 'danger')

        return render_template('edit_transaction.html', txn=txn, accounts=accounts, categories=categories)

    @app.route('/transactions/delete/<int:id>', methods=['POST'])
    @login_required
    def delete_transaction(id):
        txn = Transaction.query.filter_by(txn_id=id, user_id=current_user.user_id).first_or_404()
        account = db.session.get(Account, txn.account_id)
        
        try:
            # Revert balance
            if account:
                if txn.txn_type == 'Expense':
                    account.balance += txn.amount
                else:
                    account.balance -= txn.amount
                    
            db.session.delete(txn)
            db.session.commit()
            flash('Transaction removed.', 'info')
        except Exception as e:
            db.session.rollback()
            flash(f'Error deleting transaction: {str(e)}', 'danger')
            
        return redirect(url_for('view_transactions'))

    @app.route('/transactions/import', methods=['POST'])
    @login_required
    def import_transactions():
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No file selected.', 'warning')
            return redirect(url_for('view_transactions'))

        try:
            df = pd.read_csv(file)
            # Standardize column headers to lowercase
            df.columns = [c.strip().lower() for c in df.columns]

            required_cols = {'date', 'amount', 'type'}
            if not required_cols.issubset(set(df.columns)):
                flash("CSV must contain at least: 'date', 'amount', and 'type' (Expense/Income) columns.", 'danger')
                return redirect(url_for('view_transactions'))

            # Default account if missing
            default_account = Account.query.filter_by(user_id=current_user.user_id).first()
            if not default_account:
                flash("No accounts found. Please create an account before importing transactions.", 'warning')
                return redirect(url_for('accounts'))

            # Default categories
            default_expense_cat = Category.query.filter_by(name='Food').first() or Category.query.first()
            default_income_cat = Category.query.filter_by(name='Salary').first() or Category.query.first()

            count = 0
            for _, row in df.iterrows():
                # Extract date
                t_date = pd.to_datetime(row['date']).date()
                amt = Decimal(str(abs(float(row['amount']))))
                raw_type = str(row['type']).strip().capitalize()
                t_type = 'Expense' if raw_type not in ('Income', 'Expense') else raw_type
                desc = str(row.get('description', '')).strip()

                # Determine account
                acct_id = default_account.account_id
                if 'account_id' in row and pd.notna(row['account_id']):
                    target_acct = Account.query.filter_by(account_id=int(row['account_id']), user_id=current_user.user_id).first()
                    if target_acct:
                        acct_id = target_acct.account_id

                # Determine category: check column or predict using AI!
                cat_id = (default_expense_cat.category_id if t_type == 'Expense' else default_income_cat.category_id)
                if 'category' in row and pd.notna(row['category']):
                    matched_cat = Category.query.filter(Category.name.ilike(str(row['category']).strip())).first()
                    if matched_cat:
                        cat_id = matched_cat.category_id
                elif desc:
                    # AI-powered auto classification on import!
                    pred_name, _ = classifier.predict(desc)
                    if pred_name:
                        matched = Category.query.filter(Category.name.ilike(pred_name)).first()
                        if matched:
                            cat_id = matched.category_id

                txn = Transaction(
                    user_id=current_user.user_id,
                    account_id=acct_id,
                    category_id=cat_id,
                    date=t_date,
                    amount=amt,
                    description=desc,
                    txn_type=t_type
                )
                db.session.add(txn)

                # Adjust balance
                target_acc = db.session.get(Account, acct_id)
                if target_acc:
                    if t_type == 'Expense':
                        target_acc.balance -= amt
                    else:
                        target_acc.balance += amt

                count += 1

            db.session.commit()
            flash(f'Successfully imported {count} transactions from CSV!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'CSV import failed: {str(e)}', 'danger')

        return redirect(url_for('view_transactions'))

    @app.route('/transactions/export')
    @login_required
    def export_transactions():
        txns = Transaction.query.filter_by(user_id=current_user.user_id).order_by(Transaction.date.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['txn_id', 'date', 'account', 'category', 'amount', 'type', 'description'])

        for t in txns:
            writer.writerow([
                t.txn_id,
                t.date.strftime('%Y-%m-%d'),
                t.account.name if t.account else '',
                t.category.name if t.category else '',
                float(t.amount),
                t.txn_type,
                t.description or ''
            ])

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename=transactions_{datetime.utcnow().strftime('%Y%m%d')}.csv"}
        )

    # -------------------------------------------------------------
    # Accounts Routes
    # -------------------------------------------------------------
    @app.route('/accounts')
    @login_required
    def accounts():
        user_accounts = Account.query.filter_by(user_id=current_user.user_id).all()
        total_balance = sum([float(a.balance) for a in user_accounts])
        return render_template('accounts.html', accounts=user_accounts, total_balance=total_balance)

    @app.route('/accounts/add', methods=['POST'])
    @login_required
    def add_account():
        name = request.form.get('name', '').strip()
        acc_type = request.form.get('type')
        balance_val = request.form.get('balance', '0.00')

        if not name or acc_type not in ('Checking', 'Savings', 'Credit', 'Cash'):
            flash('Valid account name and type required.', 'danger')
            return redirect(url_for('accounts'))

        try:
            bal = Decimal(str(balance_val))
            acc = Account(user_id=current_user.user_id, name=name, type=acc_type, balance=bal)
            db.session.add(acc)
            db.session.commit()
            flash(f"Account '{name}' created successfully.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Failed to create account: {str(e)}", 'danger')

        return redirect(url_for('accounts'))

    @app.route('/accounts/edit/<int:id>', methods=['POST'])
    @login_required
    def edit_account(id):
        acc = Account.query.filter_by(account_id=id, user_id=current_user.user_id).first_or_404()
        name = request.form.get('name', '').strip()
        acc_type = request.form.get('type')
        balance_val = request.form.get('balance')

        if name:
            acc.name = name
        if acc_type in ('Checking', 'Savings', 'Credit', 'Cash'):
            acc.type = acc_type
        if balance_val is not None:
            try:
                acc.balance = Decimal(str(balance_val))
            except Exception:
                pass

        db.session.commit()
        flash('Account updated successfully.', 'success')
        return redirect(url_for('accounts'))

    @app.route('/accounts/delete/<int:id>', methods=['POST'])
    @login_required
    def delete_account(id):
        acc = Account.query.filter_by(account_id=id, user_id=current_user.user_id).first_or_404()
        db.session.delete(acc)
        db.session.commit()
        flash(f"Account '{acc.name}' deleted.", 'info')
        return redirect(url_for('accounts'))

    # -------------------------------------------------------------
    # Categories Routes
    # -------------------------------------------------------------
    @app.route('/categories')
    @login_required
    def categories():
        user_categories = Category.query.filter(
            or_(Category.user_id == current_user.user_id, Category.user_id.is_(None))
        ).order_by(Category.name.asc()).all()
        return render_template('categories.html', categories=user_categories)

    @app.route('/categories/add', methods=['POST'])
    @login_required
    def add_category():
        name = request.form.get('name', '').strip()
        c_type = request.form.get('type')

        if not name or c_type not in ('Expense', 'Income'):
            flash('Category name and valid type required.', 'danger')
            return redirect(url_for('categories'))

        # Check duplicate for user
        exists = Category.query.filter(
            Category.name == name,
            or_(Category.user_id == current_user.user_id, Category.user_id.is_(None))
        ).first()

        if exists:
            flash(f"Category '{name}' already exists.", 'warning')
            return redirect(url_for('categories'))

        try:
            cat = Category(user_id=current_user.user_id, name=name, type=c_type)
            db.session.add(cat)
            db.session.commit()
            flash(f"Custom category '{name}' added.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Failed to add category: {str(e)}", 'danger')

        return redirect(url_for('categories'))

    @app.route('/categories/delete/<int:id>', methods=['POST'])
    @login_required
    def delete_category(id):
        cat = Category.query.filter_by(category_id=id, user_id=current_user.user_id).first_or_404()
        db.session.delete(cat)
        db.session.commit()
        flash('Custom category removed.', 'info')
        return redirect(url_for('categories'))

    # -------------------------------------------------------------
    # Budgets Routes
    # -------------------------------------------------------------
    @app.route('/budgets')
    @login_required
    def budgets():
        target_month = request.args.get('month', date.today().strftime('%Y-%m'))
        year, month = map(int, target_month.split('-'))
        start_date, end_date = get_month_range(year, month)

        user_budgets = Budget.query.filter_by(user_id=current_user.user_id, month=target_month).all()

        budget_cards = []
        total_budgeted = 0.0
        total_spent = 0.0

        for b in user_budgets:
            spent = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
                Transaction.user_id == current_user.user_id,
                Transaction.category_id == b.category_id,
                Transaction.txn_type == 'Expense',
                Transaction.date >= start_date,
                Transaction.date <= end_date
            ).scalar()

            spent_amt = float(spent or 0.0)
            limit_amt = float(b.limit_amount)
            pct = round((spent_amt / limit_amt * 100), 1) if limit_amt > 0 else 0.0
            remaining = max(0.0, limit_amt - spent_amt)

            total_budgeted += limit_amt
            total_spent += spent_amt

            budget_cards.append({
                'budget_id': b.budget_id,
                'category_id': b.category_id,
                'category_name': b.category.name if b.category else 'Unknown',
                'limit_amount': limit_amt,
                'spent_amount': spent_amt,
                'remaining': remaining,
                'percent': min(pct, 100.0),
                'actual_percent': pct,
                'status': 'danger' if pct > 100 else ('warning' if pct >= 85 else 'success')
            })

        categories = Category.query.filter(
            Category.type == 'Expense',
            or_(Category.user_id == current_user.user_id, Category.user_id.is_(None))
        ).order_by(Category.name.asc()).all()

        return render_template(
            'budgets.html',
            budgets=budget_cards,
            categories=categories,
            target_month=target_month,
            total_budgeted=total_budgeted,
            total_spent=total_spent,
            total_remaining=max(0.0, total_budgeted - total_spent)
        )

    @app.route('/budgets/add', methods=['POST'])
    @login_required
    def add_budget():
        category_id = request.form.get('category_id', type=int)
        target_month = request.form.get('month', date.today().strftime('%Y-%m'))
        limit_val = request.form.get('limit_amount')

        if not category_id or not limit_val:
            flash('Category and monthly limit are required.', 'danger')
            return redirect(url_for('budgets', month=target_month))

        try:
            limit = Decimal(str(limit_val))
            existing = Budget.query.filter_by(
                user_id=current_user.user_id,
                category_id=category_id,
                month=target_month
            ).first()

            if existing:
                existing.limit_amount = limit
                flash(f'Budget for {target_month} updated.', 'info')
            else:
                new_budget = Budget(
                    user_id=current_user.user_id,
                    category_id=category_id,
                    month=target_month,
                    limit_amount=limit
                )
                db.session.add(new_budget)
                flash(f'Budget for {target_month} created.', 'success')

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to save budget: {str(e)}', 'danger')

        return redirect(url_for('budgets', month=target_month))

    @app.route('/budgets/delete/<int:id>', methods=['POST'])
    @login_required
    def delete_budget(id):
        b = Budget.query.filter_by(budget_id=id, user_id=current_user.user_id).first_or_404()
        m = b.month
        db.session.delete(b)
        db.session.commit()
        flash('Budget removed.', 'info')
        return redirect(url_for('budgets', month=m))

    # -------------------------------------------------------------
    # Goals Routes
    # -------------------------------------------------------------
    @app.route('/goals')
    @login_required
    def goals():
        user_goals = Goal.query.filter_by(user_id=current_user.user_id).order_by(Goal.due_date.asc().nullslast()).all()
        accounts = Account.query.filter_by(user_id=current_user.user_id).all()
        return render_template('goals.html', goals=user_goals, accounts=accounts)

    @app.route('/goals/add', methods=['POST'])
    @login_required
    def add_goal():
        name = request.form.get('name', '').strip()
        target_val = request.form.get('target_amount')
        saved_val = request.form.get('saved_amount', '0.00')
        due_date_str = request.form.get('due_date')

        if not name or not target_val:
            flash('Goal name and target amount required.', 'danger')
            return redirect(url_for('goals'))

        try:
            target = Decimal(str(target_val))
            saved = Decimal(str(saved_val or '0.00'))
            due = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None

            goal = Goal(
                user_id=current_user.user_id,
                name=name,
                target_amount=target,
                saved_amount=saved,
                due_date=due
            )
            db.session.add(goal)
            db.session.commit()
            flash(f"Goal '{name}' established!", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating goal: {str(e)}", 'danger')

        return redirect(url_for('goals'))

    @app.route('/goals/contribute/<int:id>', methods=['POST'])
    @login_required
    def contribute_goal(id):
        goal = Goal.query.filter_by(goal_id=id, user_id=current_user.user_id).first_or_404()
        amount_val = request.form.get('amount')
        account_id = request.form.get('account_id', type=int)

        if not amount_val:
            flash('Contribution amount is required.', 'danger')
            return redirect(url_for('goals'))

        try:
            amt = Decimal(str(amount_val))
            if amt <= 0:
                flash('Contribution must be positive.', 'danger')
                return redirect(url_for('goals'))

            # Optional: Deduct from selected account
            if account_id:
                acc = Account.query.filter_by(account_id=account_id, user_id=current_user.user_id).first()
                if acc:
                    if acc.balance < amt:
                        flash(f"Insufficient funds in account '{acc.name}'.", 'warning')
                        return redirect(url_for('goals'))
                    acc.balance -= amt

            goal.saved_amount += amt
            db.session.commit()
            flash(f"Successfully contributed ${amt:,.2f} towards '{goal.name}'!", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Failed to contribute: {str(e)}", 'danger')

        return redirect(url_for('goals'))

    @app.route('/goals/delete/<int:id>', methods=['POST'])
    @login_required
    def delete_goal(id):
        goal = Goal.query.filter_by(goal_id=id, user_id=current_user.user_id).first_or_404()
        db.session.delete(goal)
        db.session.commit()
        flash('Goal removed.', 'info')
        return redirect(url_for('goals'))

    # -------------------------------------------------------------
    # Investments Routes
    # -------------------------------------------------------------
    @app.route('/investments')
    @login_required
    def investments():
        user_invs = Investment.query.filter_by(user_id=current_user.user_id).order_by(Investment.buy_date.desc()).all()
        total_cost = sum([float(inv.total_cost) for inv in user_invs])

        # Instrument allocation for Chart.js
        allocation = {}
        for inv in user_invs:
            allocation[inv.instrument] = allocation.get(inv.instrument, 0.0) + float(inv.total_cost)

        alloc_labels = list(allocation.keys())
        alloc_values = [round(v, 2) for v in allocation.values()]

        return render_template(
            'investments.html',
            investments=user_invs,
            total_invested=total_cost,
            alloc_labels=alloc_labels,
            alloc_values=alloc_values
        )

    @app.route('/investments/add', methods=['POST'])
    @login_required
    def add_investment():
        instrument = request.form.get('instrument', '').strip().upper()
        quantity_val = request.form.get('quantity')
        price_val = request.form.get('buy_price')
        date_str = request.form.get('buy_date')

        if not instrument or not quantity_val or not price_val or not date_str:
            flash('All investment fields are required.', 'danger')
            return redirect(url_for('investments'))

        try:
            qty = int(quantity_val)
            price = Decimal(str(price_val))
            b_date = datetime.strptime(date_str, '%Y-%m-%d').date()

            inv = Investment(
                user_id=current_user.user_id,
                instrument=instrument,
                quantity=qty,
                buy_price=price,
                buy_date=b_date
            )
            db.session.add(inv)
            db.session.commit()
            flash(f"Investment in {instrument} ({qty} shares) recorded.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Error recording investment: {str(e)}", 'danger')

        return redirect(url_for('investments'))

    @app.route('/investments/delete/<int:id>', methods=['POST'])
    @login_required
    def delete_investment(id):
        inv = Investment.query.filter_by(inv_id=id, user_id=current_user.user_id).first_or_404()
        db.session.delete(inv)
        db.session.commit()
        flash('Investment holding removed.', 'info')
        return redirect(url_for('investments'))

    # -------------------------------------------------------------
    # AI Recommendations & Forecasting Routes
    # -------------------------------------------------------------
    @app.route('/recommendations')
    @login_required
    def recommendations():
        target_month = request.args.get('month', date.today().strftime('%Y-%m'))
        analysis = analyze_spending(current_user.user_id, target_month)
        forecast = forecast_spending(current_user.user_id, horizon_months=3)
        return render_template(
            'recommendations.html',
            analysis=analysis,
            forecast=forecast,
            target_month=target_month
        )

    @app.route('/api/predict-category', methods=['POST'])
    @login_required
    def api_predict_category():
        data = request.get_json() or {}
        description = data.get('description', '')
        if not description:
            return jsonify({'predicted_category': None, 'confidence': 0.0})

        pred_name, confidence = classifier.predict(description)
        return jsonify({
            'predicted_category': pred_name,
            'confidence': confidence
        })

    return app

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
