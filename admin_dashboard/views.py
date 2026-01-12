from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Count, Sum, Q
from django.contrib import messages
from datetime import timedelta
from account.models import User, Subscription, SubscriptionPlan
from bookkeeping.models import Business, Transaction


# ============================================
# Dashboard Views
# ============================================

@staff_member_required
def dashboard(request):
    context = get_dashboard_metrics()
    return render(request, 'admin_dashboard/dashboard.html', context)


@staff_member_required
def metrics_json(request):
    data = get_dashboard_metrics()
    return JsonResponse(data)


def get_dashboard_metrics():
    now = timezone.now()
    last_30 = now - timedelta(days=30)
    today = now.date()
    month_start = now.replace(day=1)

    total_users = User.objects.count()
    active_users = User.objects.filter(last_login__gte=last_30).count()
    total_businesses = Business.objects.count()
    total_transactions = Transaction.objects.count()
    transactions_today = Transaction.objects.filter(created_at__date=today).count()
    transactions_month = Transaction.objects.filter(created_at__gte=month_start).count()
    total_revenue = Transaction.objects.aggregate(total=Sum('total_amount'))['total'] or 0

    # Subscription breakdown
    free_count = Subscription.objects.filter(plan__name="Free").count()
    paid_count = Subscription.objects.filter(plan__name="Pro").count()

    # New signups
    signups_daily = list(User.objects.extra({'day': "date(date_joined)"})
        .values('day').annotate(count=Count('id')).order_by('-day')[:14])
    signups_weekly = list(User.objects.extra({'week': "strftime('%%W', date_joined)"})
        .values('week').annotate(count=Count('id')).order_by('-week')[:8])

    # Recent activity
    recent_users = list(User.objects.order_by('-date_joined').values('id', 'email', 'date_joined')[:10])
    recent_transactions = list(Transaction.objects.select_related('business').order_by('-created_at')
        .values('id', 'total_amount', 'created_at', 'business__name')[:10])

    # Daily transactions for bar chart
    transactions_daily = list(Transaction.objects.extra({'day': "date(created_at)"})
        .values('day').annotate(count=Count('id')).order_by('-day')[:14])

    return {
        'total_users': total_users,
        'active_users': active_users,
        'total_businesses': total_businesses,
        'total_transactions': total_transactions,
        'transactions_today': transactions_today,
        'transactions_month': transactions_month,
        'total_revenue': total_revenue,
        'subscription_breakdown': {'free': free_count, 'paid': paid_count},
        'signups_daily': signups_daily,
        'signups_weekly': signups_weekly,
        'transactions_daily': transactions_daily,
        'recent_users': recent_users,
        'recent_transactions': recent_transactions,
    }


# ============================================
# Users Management
# ============================================

@staff_member_required
def users_list(request):
    users = User.objects.all().order_by('-date_joined')
    
    # Search
    search = request.GET.get('search', '')
    if search:
        users = users.filter(Q(email__icontains=search) | Q(username__icontains=search))
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    elif status_filter == 'staff':
        users = users.filter(is_staff=True)
    
    # Pagination
    paginator = Paginator(users, 20)
    page = request.GET.get('page', 1)
    users_page = paginator.get_page(page)
    
    context = {
        'users': users_page,
        'search': search,
        'status_filter': status_filter,
        'total_count': paginator.count,
    }
    return render(request, 'admin_dashboard/users_list.html', context)


@staff_member_required
def user_detail(request, pk):
    user = get_object_or_404(User, pk=pk)
    businesses = Business.objects.filter(user=user)
    transactions_count = Transaction.objects.filter(user=user).count()
    subscription = getattr(user, 'subscription', None)
    
    context = {
        'user_obj': user,
        'businesses': businesses,
        'transactions_count': transactions_count,
        'subscription': subscription,
    }
    return render(request, 'admin_dashboard/user_detail.html', context)


@staff_member_required
def user_toggle_active(request, pk):
    if request.method == 'POST':
        user = get_object_or_404(User, pk=pk)
        user.is_active = not user.is_active
        user.save()
        status = 'activated' if user.is_active else 'deactivated'
        messages.success(request, f'User {user.email} has been {status}.')
    return redirect('admin_dashboard:user_detail', pk=pk)


# ============================================
# Businesses Management
# ============================================

@staff_member_required
def businesses_list(request):
    businesses = Business.objects.select_related('user').annotate(
        tx_count=Count('transactions')
    ).order_by('-created_at')
    
    # Search
    search = request.GET.get('search', '')
    if search:
        businesses = businesses.filter(
            Q(name__icontains=search) | Q(user__email__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(businesses, 20)
    page = request.GET.get('page', 1)
    businesses_page = paginator.get_page(page)
    
    context = {
        'businesses': businesses_page,
        'search': search,
        'total_count': paginator.count,
    }
    return render(request, 'admin_dashboard/businesses_list.html', context)


# ============================================
# Transactions Management
# ============================================

@staff_member_required
def transactions_list(request):
    transactions = Transaction.objects.select_related('business', 'user').order_by('-created_at')
    
    # Search
    search = request.GET.get('search', '')
    if search:
        transactions = transactions.filter(
            Q(business__name__icontains=search) | Q(description__icontains=search)
        )
    
    # Filter by type
    tx_type = request.GET.get('type', '')
    if tx_type in ['income', 'expense']:
        transactions = transactions.filter(transaction_type=tx_type)
    
    # Date range filter
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        transactions = transactions.filter(date__gte=date_from)
    if date_to:
        transactions = transactions.filter(date__lte=date_to)
    
    # Pagination
    paginator = Paginator(transactions, 25)
    page = request.GET.get('page', 1)
    transactions_page = paginator.get_page(page)
    
    # Stats
    total_income = Transaction.objects.filter(transaction_type='income').aggregate(
        total=Sum('total_amount'))['total'] or 0
    total_expense = Transaction.objects.filter(transaction_type='expense').aggregate(
        total=Sum('total_amount'))['total'] or 0
    
    context = {
        'transactions': transactions_page,
        'search': search,
        'tx_type': tx_type,
        'date_from': date_from,
        'date_to': date_to,
        'total_count': paginator.count,
        'total_income': total_income,
        'total_expense': total_expense,
    }
    return render(request, 'admin_dashboard/transactions_list.html', context)


# ============================================
# Subscriptions Management
# ============================================

@staff_member_required
def subscriptions_list(request):
    subscriptions = Subscription.objects.select_related('user', 'plan').order_by('-created_at')
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        subscriptions = subscriptions.filter(status=status_filter)
    
    # Filter by plan
    plan_filter = request.GET.get('plan', '')
    if plan_filter:
        subscriptions = subscriptions.filter(plan__name__iexact=plan_filter)
    
    # Pagination
    paginator = Paginator(subscriptions, 20)
    page = request.GET.get('page', 1)
    subscriptions_page = paginator.get_page(page)
    
    # Stats
    active_count = Subscription.objects.filter(status='active').count()
    total_count = Subscription.objects.count()
    plans = SubscriptionPlan.objects.all()
    
    context = {
        'subscriptions': subscriptions_page,
        'status_filter': status_filter,
        'plan_filter': plan_filter,
        'active_count': active_count,
        'total_count': total_count,
        'plans': plans,
    }
    return render(request, 'admin_dashboard/subscriptions_list.html', context)
