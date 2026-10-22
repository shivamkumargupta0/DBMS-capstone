"""
AI & Analytics Engine for Personal Finance Management System
Implements:
1. Heuristic Rule-Based Budget & Goal Analysis (over-budget, pacing, savings velocity)
2. Machine Learning Transaction Classifier (Scikit-Learn NLP text classification)
3. Spending Forecasting (Scikit-Learn Linear Regression & Time-Series projections)
4. Spending Anomaly Detection (Statistical Z-score deviations)
5. Mandatory Financial Disclaimer & Transparency Reporting
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, mean_absolute_error
from sklearn.pipeline import Pipeline
from sqlalchemy import func

from models import db, Transaction, Budget, Goal, Category, Account

AI_DISCLAIMER = (
    "AI Advisory Disclaimer: All spending forecasts, anomaly flags, and recommendations "
    "are statistical approximations and rule-based guidance. They do not constitute certified "
    "financial, tax, or investment advice. As highlighted by Intuit AI research, 'any AI suggestion "
    "is only as good as the data behind it... a useful starting point, not a final answer.' "
    "Data remains private and processed locally on your server."
)

# Seed corpus for initial cold-start transaction classification
DEFAULT_TRANSACTION_CORPUS = [
    # Food / Groceries / Dining
    ("Whole Foods groceries weekly shopping", "Food"),
    ("Trader Joe's fruits and snacks", "Food"),
    ("Kroger supermarket food bill", "Food"),
    ("Starbucks coffee latte and croissant", "Food"),
    ("McDonald's burger dinner with friends", "Food"),
    ("Chipotle mexican grill lunch burrito", "Food"),
    ("Subway sandwich combo meal", "Food"),
    ("Uber Eats pizza delivery dinner", "Food"),
    ("Doordash sushi takeout order", "Food"),
    ("Local farmer market fresh vegetables", "Food"),
    
    # Housing / Rent / Utilities
    ("Monthly apartment lease rent payment", "Rent"),
    ("Landlord property rent transfer", "Rent"),
    ("Electric utility bill energy power", "Utilities"),
    ("City water and sewage utility payment", "Utilities"),
    ("Home internet fiber wifi broadband bill", "Utilities"),
    
    # Transportation
    ("Shell gas station fuel refill petrol", "Transportation"),
    ("Chevron gasoline full tank", "Transportation"),
    ("Uber ride downtown meeting taxi", "Transportation"),
    ("Lyft airport ride shared transit", "Transportation"),
    ("Metro subway train card recharge pass", "Transportation"),
    
    # Entertainment / Shopping
    ("Netflix streaming monthly subscription", "Entertainment"),
    ("Spotify music premium streaming plan", "Entertainment"),
    ("Steam video game purchase summer sale", "Entertainment"),
    ("Amazon prime online shopping electronics", "Shopping"),
    ("Nike shoes clothing purchase mall", "Shopping"),
    ("Cinema movie tickets popcorn weekend", "Entertainment"),
    
    # Income / Salary
    ("Monthly corporate payroll direct deposit salary", "Salary"),
    ("Bi-weekly employee wage paycheck deposit", "Salary"),
    ("Freelance consulting project client fee", "Freelance"),
    ("Investment dividend payout quarterly", "Investment"),
]


def get_month_range(year, month):
    """Returns start and end dates for a given year and month."""
    import calendar
    _, last_day = calendar.monthrange(year, month)
    return date(year, month, 1), date(year, month, last_day)

def get_month_expr(column):
    """Returns dialect-aware SQL expression for YYYY-MM formatting."""
    try:
        bind = db.session.get_bind()
        if bind and 'mysql' in bind.dialect.name:
            return func.date_format(column, '%Y-%m')
    except Exception:
        pass
    return func.strftime('%Y-%m', column)


class SmartTransactionClassifier:
    """Auto-categorizes transactions from text descriptions using Scikit-Learn NLP pipeline."""
    
    def __init__(self):
        self.pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(ngram_range=(1, 2), lowercase=True, stop_words='english')),
            ('clf', MultinomialNB(alpha=0.5))
        ])
        self.is_trained = False
        self._train_initial_model()

    def _train_initial_model(self):
        texts = [x[0] for x in DEFAULT_TRANSACTION_CORPUS]
        labels = [x[1] for x in DEFAULT_TRANSACTION_CORPUS]
        self.pipeline.fit(texts, labels)
        self.is_trained = True

    def retrain_with_user_data(self, user_id=None):
        """Retrains the model incorporating user's historical transactions."""
        query = db.session.query(Transaction.description, Category.name).\
            join(Category, Transaction.category_id == Category.category_id).\
            filter(Transaction.description.isnot(None), Transaction.description != '')
        
        if user_id:
            query = query.filter(Transaction.user_id == user_id)
            
        rows = query.all()
        texts = [x[0] for x in DEFAULT_TRANSACTION_CORPUS]
        labels = [x[1] for x in DEFAULT_TRANSACTION_CORPUS]
        
        for desc, cat_name in rows:
            if desc and cat_name and len(desc.strip()) > 2:
                texts.append(desc.strip())
                labels.append(cat_name.strip())
                
        if len(set(labels)) > 1:
            self.pipeline.fit(texts, labels)
            self.is_trained = True

    def predict(self, description_text):
        if not description_text or not self.is_trained:
            return None, 0.0
            
        text = str(description_text).strip()
        if len(text) < 2:
            return None, 0.0
            
        try:
            pred_label = self.pipeline.predict([text])[0]
            probs = self.pipeline.predict_proba([text])[0]
            confidence = float(np.max(probs))
            return pred_label, round(confidence, 3)
        except Exception:
            return None, 0.0


# Global singleton classifier instance
classifier = SmartTransactionClassifier()


def analyze_spending(user_id, target_month=None):
    """
    Analyzes user financial standing:
    - Budget adherence & mid-month pacing warnings
    - Goal progress & required monthly savings velocity
    - Unusual spending anomalies
    - Actionable recommendations list
    """
    today = date.today()
    if not target_month:
        target_month = today.strftime('%Y-%m')
        
    year, month = map(int, target_month.split('-'))
    days_in_month = (date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1) - timedelta(days=1)).day
    current_day = min(today.day if today.year == year and today.month == month else days_in_month, days_in_month)
    month_progress_pct = round((current_day / days_in_month) * 100, 1)

    recommendations = []
    budget_insights = []
    
    start_date, end_date = get_month_range(year, month)
    
    # 1. Budget vs Actual Spending Check
    user_budgets = Budget.query.filter_by(user_id=user_id, month=target_month).all()
    
    for b in user_budgets:
        cat = db.session.get(Category, b.category_id)
        cat_name = cat.name if cat else f"Category {b.category_id}"
        
        # Total spent in category for target_month (using portable date range)
        spent_sum = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.user_id == user_id,
            Transaction.category_id == b.category_id,
            Transaction.txn_type == 'Expense',
            Transaction.date >= start_date,
            Transaction.date <= end_date
        ).scalar()
        
        spent = float(spent_sum or 0.0)
        limit = float(b.limit_amount)
        utilization_pct = round((spent / limit * 100), 1) if limit > 0 else 0.0
        
        # Pacing analysis: projected spending at month end
        daily_rate = spent / max(current_day, 1)
        projected_total = daily_rate * days_in_month
        projected_over = projected_total > limit
        
        status = "normal"
        if spent > limit:
            status = "exceeded"
            recommendations.append({
                "type": "danger",
                "category": cat_name,
                "title": f"Over Budget in {cat_name}",
                "message": (
                    f"You have spent ${spent:,.2f} of your ${limit:,.2f} budget "
                    f"({utilization_pct}%). You have exceeded your planned limit by ${spent - limit:,.2f}."
                ),
                "action": f"Freeze or minimize any optional spending in {cat_name} for the remainder of the month."
            })
        elif utilization_pct >= 85 or (utilization_pct >= 60 and projected_over and month_progress_pct < 75):
            status = "warning"
            recommendations.append({
                "type": "warning",
                "category": cat_name,
                "title": f"High Spending Pace in {cat_name}",
                "message": (
                    f"You have reached {utilization_pct}% (${spent:,.2f} / ${limit:,.2f}) on day {current_day} of {days_in_month}. "
                    f"At this current daily pace of ${daily_rate:.2f}/day, you are projected to reach ${projected_total:,.2f}."
                ),
                "action": f"Aim to cap remaining spending in {cat_name} to ${(limit - spent) / max(days_in_month - current_day, 1):.2f} per day."
            })
        else:
            status = "on_track"
            
        budget_insights.append({
            "category": cat_name,
            "budget": limit,
            "spent": spent,
            "remaining": max(0.0, limit - spent),
            "utilization_pct": utilization_pct,
            "projected_total": round(projected_total, 2),
            "status": status
        })

    # 2. Goal Velocity & Completion Analysis
    user_goals = Goal.query.filter_by(user_id=user_id).all()
    goal_insights = []
    
    for g in user_goals:
        target = float(g.target_amount)
        saved = float(g.saved_amount)
        pct = g.percent_complete
        
        status = "on_track"
        advice = ""
        months_left = None
        
        if g.due_date:
            days_until = (g.due_date - today).days
            months_left = max(round(days_until / 30.4, 1), 0.1)
            remaining_amount = max(0.0, target - saved)
            
            if days_until <= 0 and saved < target:
                status = "overdue"
                advice = f"Deadline passed on {g.due_date.strftime('%b %d, %Y')}. ${remaining_amount:,.2f} still needed."
                recommendations.append({
                    "type": "danger",
                    "category": "Goals",
                    "title": f"Goal '{g.name}' Missed Target Date",
                    "message": advice,
                    "action": "Consider updating target date or adjusting contribution plan."
                })
            elif saved >= target:
                status = "achieved"
                advice = f"Congratulations! You reached 100% of your target amount."
                recommendations.append({
                    "type": "success",
                    "category": "Goals",
                    "title": f"Goal '{g.name}' Achieved!",
                    "message": f"You've successfully saved ${saved:,.2f} for '{g.name}'.",
                    "action": "You can mark this goal complete or allocate future savings to investments."
                })
            else:
                required_monthly = remaining_amount / months_left
                advice = f"${remaining_amount:,.2f} remaining. Save approx ${required_monthly:,.2f}/month to reach target."
                if pct < 30 and months_left < 3:
                    status = "behind"
                    recommendations.append({
                        "type": "warning",
                        "category": "Goals",
                        "title": f"Goal '{g.name}' Behind Schedule",
                        "message": (
                            f"Only {pct}% saved with ~{months_left:.1f} months remaining before {g.due_date}. "
                            f"You will need ${required_monthly:,.2f}/month to succeed."
                        ),
                        "action": "Redirect discretionary funds or extend the target completion date."
                    })
        else:
            advice = f"${saved:,.2f} saved of ${target:,.2f} ({pct}%)."
            
        goal_insights.append({
            "name": g.name,
            "target": target,
            "saved": saved,
            "pct": pct,
            "due_date": g.due_date.strftime('%Y-%m-%d') if g.due_date else "No deadline",
            "status": status,
            "advice": advice
        })

    # 3. Anomaly Detection (Statistical Z-score on Category Expenses)
    anomalies = detect_spending_anomalies(user_id)
    for anom in anomalies:
        recommendations.append({
            "type": "info",
            "category": "Anomaly Alert",
            "title": f"Unusual High Spending in {anom['category']}",
            "message": (
                f"Transaction of ${anom['amount']:,.2f} ('{anom['description']}') on {anom['date']} "
                f"is significantly higher than your typical average (${anom['avg_category_amount']:,.2f})."
            ),
            "action": "Review this expense to ensure it was expected or properly categorized."
        })

    # 4. If no alerts triggered, add positive confirmation
    if not recommendations:
        recommendations.append({
            "type": "success",
            "category": "General",
            "title": "Finances In Great Shape",
            "message": "All current budgets are pacing within normal parameters, and no unusual anomalies were detected.",
            "action": "Maintain your disciplined spending habit!"
        })

    return {
        "target_month": target_month,
        "month_progress_pct": month_progress_pct,
        "recommendations": recommendations,
        "budget_insights": budget_insights,
        "goal_insights": goal_insights,
        "anomalies": anomalies,
        "disclaimer": AI_DISCLAIMER
    }


def detect_spending_anomalies(user_id, lookback_days=60, threshold_z=2.0):
    """Identifies outlier transactions where amount > mean + threshold * std for that category."""
    start_date = date.today() - timedelta(days=lookback_days)
    
    txns = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.txn_type == 'Expense',
        Transaction.date >= start_date
    ).all()
    
    if len(txns) < 5:
        return []
        
    records = []
    for t in txns:
        records.append({
            "txn_id": t.txn_id,
            "date": t.date.strftime('%Y-%m-%d'),
            "amount": float(t.amount),
            "category_id": t.category_id,
            "category": t.category.name if t.category else "Other",
            "description": t.description or "No description"
        })
        
    df = pd.DataFrame(records)
    anomalies = []
    
    for cat_id, group in df.groupby('category_id'):
        if len(group) < 3:
            continue
        mean_amt = group['amount'].mean()
        std_amt = group['amount'].std()
        
        if std_amt > 0:
            outliers = group[(group['amount'] - mean_amt) / std_amt >= threshold_z]
            for _, row in outliers.iterrows():
                # Avoid tiny amounts flagging as anomaly
                if row['amount'] > 50.0:
                    anomalies.append({
                        "txn_id": int(row['txn_id']),
                        "date": row['date'],
                        "amount": row['amount'],
                        "category": row['category'],
                        "description": row['description'],
                        "avg_category_amount": round(mean_amt, 2)
                    })
                    
    return anomalies[:5]


def forecast_spending(user_id, horizon_months=3):
    """
    Historical time-series spending forecaster using Scikit-learn Linear Regression.
    Evaluates historical trend and predicts future monthly expenses.
    """
    # Group past expenses by month using dialect-aware month formatting
    month_col = get_month_expr(Transaction.date)
    monthly_data = db.session.query(
        month_col.label('month'),
        func.sum(Transaction.amount).label('total_spent')
    ).filter(
        Transaction.user_id == user_id,
        Transaction.txn_type == 'Expense'
    ).group_by(month_col).order_by(month_col).all()
    
    if not monthly_data or len(monthly_data) < 2:
        # Fallback projection based on recent data or available transactions
        recent_total = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.user_id == user_id,
            Transaction.txn_type == 'Expense'
        ).scalar()
        base = float(recent_total or 500.0)
        months = ["Month +1", "Month +2", "Month +3"]
        return {
            "historical_months": ["Prior Months"],
            "historical_values": [base],
            "forecast_months": months[:horizon_months],
            "forecast_values": [round(base * 1.02, 2) for _ in range(horizon_months)],
            "trend_direction": "stable",
            "model_r2": 0.0,
            "mae": 0.0,
            "disclaimer": AI_DISCLAIMER
        }

    months = [r[0] for r in monthly_data]
    values = [float(r[1]) for r in monthly_data]
    
    X = np.arange(len(values)).reshape(-1, 1)
    y = np.array(values)
    
    reg = LinearRegression()
    reg.fit(X, y)
    
    # Model evaluation on training set
    preds = reg.predict(X)
    mae = float(mean_absolute_error(y, preds))
    rmse = float(np.sqrt(mean_squared_error(y, preds)))
    slope = float(reg.coef_[0])
    
    trend = "increasing" if slope > 15 else ("decreasing" if slope < -15 else "stable")
    
    # Generate future month labels
    last_month_str = months[-1]
    last_year, last_m = map(int, last_month_str.split('-'))
    
    future_months = []
    future_X = []
    cur_y, cur_m = last_year, last_m
    
    for i in range(1, horizon_months + 1):
        cur_m += 1
        if cur_m > 12:
            cur_m = 1
            cur_y += 1
        future_months.append(f"{cur_y:04d}-{cur_m:02d}")
        future_X.append(len(values) + i - 1)
        
    future_preds = reg.predict(np.array(future_X).reshape(-1, 1))
    # Expenses cannot be negative
    future_values = [max(0.0, round(float(val), 2)) for val in future_preds]
    
    return {
        "historical_months": months,
        "historical_values": [round(v, 2) for v in values],
        "forecast_months": future_months,
        "forecast_values": future_values,
        "trend_direction": trend,
        "monthly_slope": round(slope, 2),
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "disclaimer": AI_DISCLAIMER
    }
