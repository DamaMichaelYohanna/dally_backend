"""
Summary calculation services for bookkeeping API.

All calculations are performed dynamically from Transaction and TransactionItem data.
No summary data is stored in the database.
All queries are filtered by authenticated user for data isolation.
"""
from datetime import date
from decimal import Decimal
from django.db.models import Sum, Q
from django.contrib.auth.models import User
from bookkeeping.models import Transaction, TransactionItem


def daily_summary(user: User, target_date: date, business_id=None):
    """
    Calculate daily income, expense, and net cash for a specific date.
    
    Args:
        user: Authenticated user
        target_date: Date to calculate summary for
        business_id: Optional business filter
    
    Returns:
        dict with:
            - date: target date
            - currency: 'NGN'
            - total_income: total income in kobo
            - total_expense: total expense in kobo
            - net_cash: income - expense in kobo
    """
    # Base queryset filtered by user and date
    queryset = Transaction.objects.filter(
        user=user,
        date=target_date,
        is_deleted=False
    )
    
    # Optional business filter
    if business_id:
        queryset = queryset.filter(business_id=business_id)
    
    # Calculate income
    income = queryset.filter(transaction_type='income').aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    # Calculate expense
    expense = queryset.filter(transaction_type='expense').aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    return {
        'date': target_date,
        'currency': 'NGN',
        'total_income': income,
        'total_expense': expense,
        'net_cash': income - expense
    }


def date_range_summary(user: User, start_date: date, end_date: date, business_id=None):
    """
    Calculate total income, expense, and net profit for a date range.
    
    Args:
        user: Authenticated user
        start_date: Start of date range
        end_date: End of date range (inclusive)
        business_id: Optional business filter
    
    Returns:
        dict with:
            - start_date
            - end_date
            - currency: 'NGN'
            - total_income: total income in kobo
            - total_expense: total expense in kobo
            - net_profit: income - expense in kobo
    """
    # Base queryset filtered by user and date range
    queryset = Transaction.objects.filter(
        user=user,
        date__gte=start_date,
        date__lte=end_date,
        is_deleted=False
    )
    
    # Optional business filter
    if business_id:
        queryset = queryset.filter(business_id=business_id)
    
    # Calculate income
    income = queryset.filter(transaction_type='income').aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    # Calculate expense
    expense = queryset.filter(transaction_type='expense').aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'currency': 'NGN',
        'total_income': income,
        'total_expense': expense,
        'net_profit': income - expense
    }


def profit_and_loss(user: User, start_date: date, end_date: date, business_id=None):
    """
    Calculate profit and loss statement for a date range.
    
    Args:
        user: Authenticated user
        start_date: Start of date range
        end_date: End of date range (inclusive)
        business_id: Optional business filter
    
    Returns:
        dict with:
            - start_date
            - end_date
            - currency: 'NGN'
            - total_sales: total income in kobo
            - total_purchases: total expense in kobo
            - gross_profit: sales - purchases in kobo
    """
    # Base queryset filtered by user and date range
    queryset = Transaction.objects.filter(
        user=user,
        date__gte=start_date,
        date__lte=end_date,
        is_deleted=False
    )
    
    # Optional business filter
    if business_id:
        queryset = queryset.filter(business_id=business_id)
    
    # Calculate sales (income transactions)
    sales = queryset.filter(transaction_type='income').aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    # Calculate purchases (expense transactions)
    purchases = queryset.filter(transaction_type='expense').aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'currency': 'NGN',
        'total_sales': sales,
        'total_purchases': purchases,
        'gross_profit': sales - purchases
    }
