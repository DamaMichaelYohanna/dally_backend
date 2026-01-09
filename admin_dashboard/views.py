from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from account.models import User, Subscription
from bookkeeping.models import Business, Transaction
from django.db.models import Count, Sum, Q

@staff_member_required
def dashboard(request):
    # Data for context (KPI cards, charts, etc.)
    context = get_dashboard_metrics()
    return render(request, 'admin_dashboard/dashboard.html', context)

@staff_member_required
def metrics_json(request):
    # JSON endpoint for Chart.js
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
        'recent_users': recent_users,
        'recent_transactions': recent_transactions,
    }
