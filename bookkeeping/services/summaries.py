"""
Summary calculation services for bookkeeping API.

All calculations are performed dynamically from Transaction and TransactionItem data.
No summary data is stored in the database.
All queries are filtered by authenticated user for data isolation.
"""
from datetime import date, timedelta
from decimal import Decimal
from django.db.models import Sum, Q
from django.contrib.auth.models import User
from bookkeeping.models import Transaction, TransactionItem
from bookkeeping.models import InventoryPeriod



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
    Calculate profit and loss statement for a date range with proper COGS.
    
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
            - total_sales: total income
            - cogs: cost of goods sold
            - operating_expenses: other expenses
            - gross_profit: sales - cogs
            - net_profit: gross - operating
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
    )['total'] or Decimal('0.00')
    
    # Calculate Inventory Purchases (COGS additions)
    inventory_purchases = queryset.filter(
        transaction_type='expense',
        expense_type='inventory'
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    
    # Calculate Operating Expenses
    operating_expenses = queryset.filter(
        transaction_type='expense',
        expense_type='operating'
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    
    # Legacy expenses (no type set) - treat as operating expenses for safety
    # Or you could ask user to categorize them. For now, we assume operating.
    legacy_expenses = queryset.filter(
        transaction_type='expense',
        expense_type__isnull=True
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    
    total_operating_expenses = operating_expenses + legacy_expenses
    
    # Determine business context
    # If business_id is passed, use it. If not, try to find user's business.
    # If neither, we are in "Individual Mode" -> No COGS, simple Income - Expense.
    if not business_id:
        try:
            # We strictly check if they have a business link
            # But here `queryset` is already filtered by user.
            # If we want to support multiple businesses later, we might need more logic.
            # For now, if no business_id is passed, we check if the user has ANY business.
            user_business = Business.objects.filter(user=user).first()
            business_id = user_business.id if user_business else None
        except Exception:
            business_id = None

    if not business_id:
        # --- INDIVIDUAL MODE (No Business) ---
        # No inventory tracking.
        # All expenses are effectively operating expenses.
        
        # Recalculate expenses effectively
        total_expense = queryset.filter(transaction_type='expense').aggregate(
            total=Sum('total_amount'))['total'] or Decimal('0.00')
        
        cogs = Decimal('0.00')
        inventory_purchases = Decimal('0.00') 
        opening_stock_value = Decimal('0.00')
        closing_stock_value = Decimal('0.00')
        total_operating_expenses = total_expense
        
    else:
        # --- BUSINESS MODE (Inventory Tracking) ---
        
        # Get closing inventory value for this period
        # We look for an inventory record exactly on the end_date
        closing_inventory = InventoryPeriod.objects.filter(
            business_id=business_id,
            period_end=end_date
        ).first()
        
        closing_stock_value = closing_inventory.closing_value if closing_inventory else Decimal('0.00')
        
        # COGS Logic:
        # COGS = Opening Stock + Purchases - Closing Stock
        
        # Let's try to find opening stock (closing stock of previous day/period)
        opening_stock_date = start_date - timedelta(days=1)
        opening_inventory = InventoryPeriod.objects.filter(
            business_id=business_id,
            period_end__lte=opening_stock_date
        ).order_by('-period_end').first()
        
        opening_stock_value = opening_inventory.closing_value if opening_inventory else Decimal('0.00')
        
        # Goods Available for Sale = Opening Stock + Purchases
        goods_available = opening_stock_value + inventory_purchases
        
        # COGS = Goods Available - Closing Stock
        cogs = max(goods_available - closing_stock_value, Decimal('0.00'))
    
    gross_profit = sales - cogs
    net_profit = gross_profit - total_operating_expenses

    return {
        'start_date': start_date,
        'end_date': end_date,
        'currency': 'NGN',
        'total_sales': sales,
        'opening_stock': opening_stock_value,
        'inventory_purchases': inventory_purchases,
        'closing_stock': closing_stock_value,
        'cogs': cogs,
        'operating_expenses': total_operating_expenses,
        'gross_profit': gross_profit,
        'net_profit': net_profit
    }
