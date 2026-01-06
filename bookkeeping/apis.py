import os
from decimal import Decimal
from urllib.parse import urlencode
from rest_framework import status
from django.conf import settings
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Q
from datetime import datetime, date, timedelta
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        )
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from django.http import FileResponse
from io import BytesIO
from datetime import datetime
from rest_framework.generics import ListAPIView, CreateAPIView

from .models import Business, Transaction, TransactionItem
from .serializers import (
    BusinessSerializer, 
    TransactionSerializer, 
    TransactionListSerializer,
    TaxSummarySerializer
)
from .permissions import IsOwner
from account.permissions import IsProUser
from .services.summaries import daily_summary, date_range_summary, profit_and_loss
from .services.tax.nigeria_2026 import NigeriaTaxCalculator2026

from rest_framework.views import APIView
from django.core.cache import cache
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework import generics



def get_user_cache_version(user_id):
    """
    Get the current cache version for a user, initializing it if it doesn't exist.
    """
    version_key = f'user_cache_version:{user_id}'
    version = cache.get(version_key)
    if version is None:
        version = 1
        cache.set(version_key, version, timeout=None)
    return version


class DashboardView(APIView):
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        user = request.user
        version = get_user_cache_version(user.id)
        cach_key = f'dashboard:{user.id}:v{version}'
        cached_data = cache.get(cach_key)
        if cached_data:
            return Response(cached_data)
        
        base_qs = Transaction.objects.filter(user=request.user, is_deleted=False)
        today = date.today()

        def summarize(qs):
            income = qs.filter(transaction_type='income').aggregate(
                total=Sum('total_amount'),
                count=Count('id')
            )
            expense = qs.filter(transaction_type='expense').aggregate(
                total=Sum('total_amount'),
                count=Count('id')
            )

            total_income = income['total'] or 0
            total_expense = expense['total'] or 0

            return {
                'income': {
                    'total': total_income,
                    'count': income['count'],
                },
                'expense': {
                    'total': total_expense,
                    'count': expense['count'],
                },
                'net': total_income - total_expense,
                'total_transactions': income['count'] + expense['count'],
            }

        business = Business.objects.filter(user=request.user).first()
        data = {
            "business": BusinessSerializer(business).data if business else None,
            "transactions_today": summarize(base_qs.filter(date=today)),
            "transactions_week": summarize(base_qs.filter(date__gte=date.today()-timedelta(days=7))),
            "transactions_month": summarize(base_qs.filter(date__gte=date.today()-timedelta(days=30))),
        }
        cache.set(cach_key, data, timeout=300)
        return Response(data)


class TransactionPagination(PageNumberPagination):
    page_size = 20

@extend_schema(
    summary="List transactions (cached, paginated)",
    description="Get a paginated list of transactions for the authenticated user. Supports filtering by type, start_date, and end_date. Results are cached for 60 seconds.",
    tags=["Dashboard - Transactions"],
    parameters=[
        OpenApiParameter(
            name='type',
            type=OpenApiTypes.STR,
            enum=['income', 'expense'],
            description='Filter by transaction type'
        ),
        OpenApiParameter(
            name='start_date',
            type=OpenApiTypes.DATE,
            description='Filter transactions from this date (YYYY-MM-DD)'
        ),
        OpenApiParameter(
            name='end_date',
            type=OpenApiTypes.DATE,
            description='Filter transactions until this date (YYYY-MM-DD)'
        ),
        OpenApiParameter(
            name='page',
            type=OpenApiTypes.INT,
            description='Page number for pagination'
        ),
    ],
    responses={200: TransactionListSerializer(many=True)},
)
class TransactionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        params = request.query_params.dict()
        version = get_user_cache_version(user.id)
        # Create a unique cache key based on user, query params and version
        cache_key = f"transaction_list:{user.id}:v{version}:{urlencode(sorted(params.items()))}"

        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        queryset = Transaction.objects.filter(
            user=user,
            is_deleted=False
        )

        tx_type = params.get('type')
        if tx_type in ['income', 'expense']:
            queryset = queryset.filter(transaction_type=tx_type)

        start_date = params.get('start_date')
        end_date = params.get('end_date')

        if start_date:
            start_date = parse_date(start_date)
            if not start_date:
                return Response(
                    {"error": "Invalid start_date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            queryset = queryset.filter(date__gte=start_date)

        if end_date:
            end_date = parse_date(end_date)
            if not end_date:
                return Response(
                    {"error": "Invalid end_date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            queryset = queryset.filter(date__lte=end_date)

        paginator = TransactionPagination()
        page = paginator.paginate_queryset(queryset, request)

        serializer = TransactionListSerializer(page, many=True)

        response_data = {
            "count": paginator.page.paginator.count,
            "results": serializer.data
        }

        cache.set(cache_key, response_data, timeout=60)

        return Response(response_data)
    

class SummaryView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        user = request.user
        version = get_user_cache_version(user.id)
        cache_key = f'summary:{user.id}:v{version}'
        cached_data = cache.get(cache_key)  
        if cached_data:
            return Response(cached_data)
        
        base_qs = Transaction.objects.filter(user=request.user, is_deleted=False)
        # overall highs and lows
        highest_income = base_qs.filter(transaction_type='income').order_by('-total_amount').first()
        lowest_income = base_qs.filter(transaction_type='income').order_by('total_amount').first()
        highest_expense = base_qs.filter(transaction_type='expense').order_by('-total_amount').first()
        lowest_expense = base_qs.filter(transaction_type='expense').order_by('total_amount').first()
        # weekly highs and lows
        highest_weekly_income = base_qs.filter(
            transaction_type='income', 
            date__gte=date.today()-timedelta(days=7)).order_by('-total_amount').first()
        lowest_weekly_income = base_qs.filter(
            transaction_type='income',
            date__gte=date.today()-timedelta(days=7)).order_by('total_amount').first()
        highest_weekly_expense = base_qs.filter(
            transaction_type='expense', 
            date__gte=date.today()-timedelta(days=7)).order_by('-total_amount').first()
        lowest_weekly_expense = base_qs.filter(
            transaction_type='expense',
            date__gte=date.today()-timedelta(days=7)).order_by('total_amount').first()
       
        top_categories = (
        TransactionItem.objects
            .filter(transaction__in=base_qs)
            .values('category')           # Group by 'category'
            .annotate(count=Count('category'))  # Count occurrences
            .order_by('-count')[:3]      # Order descending and take top 3
        )
        data = {
            "highest_income": highest_income.total_amount if highest_income else 0,
            "lowest_income": lowest_income.total_amount if lowest_income else 0,
            "highest_expense": highest_expense.total_amount if highest_expense else 0,
            "lowest_expense": lowest_expense.total_amount if lowest_expense else 0,
            "highest_weekly_income": highest_weekly_income.total_amount if highest_weekly_income else 0,
            "lowest_weekly_income": lowest_weekly_income.total_amount if lowest_weekly_income else 0,
            "highest_weekly_expense": highest_weekly_expense.total_amount if highest_weekly_expense else 0,
            "lowest_weekly_expense": lowest_weekly_expense.total_amount if lowest_weekly_expense else 0,
            "top_categories": [
                {"category": item["category"], "count": item["count"]} for item in top_categories
            ],
        }
        cache.set(cache_key, data, timeout=300)  # Cache for 5 minutes
        return Response(data)


# task calculations goes here
# =====================================
class TaxView(APIView):
    """
    APIView for Nigerian tax calculations.
    
    Implements simplified tax calculations for sole proprietors and informal
    businesses based on Nigeria Tax Act 2025 (effective January 1, 2026).
    
    All calculations are performed dynamically from transaction data.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get annual tax summary",
        description=(
            "Calculate tax summary for a full year. Returns revenue, expenses, "
            "profit, taxable income, estimated Personal Income Tax, and optional VAT. "
            "All amounts in Naira (NGN)."
        ),
        parameters=[
            OpenApiParameter(
                name='year',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description='Tax year (e.g., 2026)'
            ),
            OpenApiParameter(
                name='business_id',
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Optional: Filter by specific business'
            ),
            OpenApiParameter(
                name='vat_enabled',
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Enable VAT calculation (7.5%) - default: false'
            ),
        ],
        responses={200: TaxSummarySerializer},
        tags=["Tax"]
    )
    def get(self, request):
        """
        GET /api/tax/summary/?year=2026&business_id=uuid&vat_enabled=true
        Returns annual tax summary with PIT and optional VAT calculations.
        """
        # Get year parameter
        year_str = request.query_params.get('year')
        month_str = request.query_params.get('month')
        
        if not year_str and not month_str:
            return Response(
                {'error': 'Either year (YYYY) or month (YYYY-MM) parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Handle monthly summary
        if month_str:
            try:
                period_date = datetime.strptime(month_str, '%Y-%m')
                year = period_date.year
                month = period_date.month
                
                # Calculate start and end dates for the month
                start_date = date(year, month, 1)
                if month == 12:
                    end_date = date(year + 1, 1, 1)
                    from datetime import timedelta
                    end_date = end_date - timedelta(days=1)
                else:
                    end_date = date(year, month + 1, 1)
                    from datetime import timedelta
                    end_date = end_date - timedelta(days=1)
                
            except ValueError:
                return Response(
                    {'error': 'Invalid month format. Use YYYY-MM'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Handle annual summary
        elif year_str:
            try:
                year = int(year_str)
                start_date = date(year, 1, 1)
                end_date = date(year, 12, 31)
            except ValueError:
                return Response(
                    {'error': 'Invalid year format. Use YYYY'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Optional business filter
        business_id = request.query_params.get('business_id')
        
        # Optional VAT calculation
        vat_enabled = request.query_params.get('vat_enabled', 'false').lower() == 'true'
        
        # Get profit/loss data for the period
        pl_data = profit_and_loss(
            user=request.user,
            start_date=start_date,
            end_date=end_date,
            business_id=business_id
        )
        
        # Calculate tax using Nigeria 2026 calculator
        calculator = NigeriaTaxCalculator2026(vat_enabled=vat_enabled)
        tax_summary = calculator.calculate_tax_summary(
            total_revenue_kobo=pl_data['total_sales'],
            total_expenses_kobo=pl_data['total_purchases'],
            business_id=business_id
        )
        
        # Add period information
        tax_summary['period_start'] = start_date
        tax_summary['period_end'] = end_date
        
        serializer = TaxSummarySerializer(tax_summary)
        return Response(serializer.data)



class TransactionCreateView(generics.CreateAPIView):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]




class TransactionPDFExportView(APIView):
    """
    Export filtered transactions as a detailed PDF report for the logged-in business owner.
    Filters: type, start_date, end_date (YYYY-MM-DD)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = request.query_params
        is_pro = request.user.is_pro
        is_download_request = params.get('download', 'false').lower() == 'true'

        # Gate download for only pro users
        if is_download_request and not is_pro:
            return Response(
                {"error": "Subscription required to download or share reports."},
                status=status.HTTP_402_PAYMENT_REQUIRED
            )
        
        queryset = Transaction.objects.filter(
            user=request.user,
            is_deleted=False
        ).select_related('business', 'user').prefetch_related('items')

        # Filter by transaction type
        tx_type = params.get('type')
        if tx_type in ['income', 'expense']:
            queryset = queryset.filter(transaction_type=tx_type)

        # Filter by date range
        start_date = params.get('start_date')
        end_date = params.get('end_date')
        
        if start_date:
            parsed_start = parse_date(start_date)
            if parsed_start:
                queryset = queryset.filter(date__gte=parsed_start)
        
        if end_date:
            parsed_end = parse_date(end_date)
            if parsed_end:
                queryset = queryset.filter(date__lte=parsed_end)

        # PDF Generation
        FONT_PATH = os.path.join(
            settings.BASE_DIR,
            'staticfiles',
            "fonts",
            "DejaVuSans.ttf"
        )
        
        # Register Unicode font
        try:
            pdfmetrics.registerFont(TTFont('DejaVu', FONT_PATH))
        except Exception:
            # Font might be already registered
            pass

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )

        styles = getSampleStyleSheet()
        styles["Normal"].fontName = "DejaVu"
        styles["Heading1"].fontName = "DejaVu"
        styles["Heading2"].fontName = "DejaVu"

        elements = []

        # Title
        elements.append(Paragraph("<b>Dally Bookkeeping Report</b>", styles["Heading1"]))
        elements.append(Spacer(1, 10))

        elements.append(Paragraph(
            f"User: {request.user.email}<br/>"
            f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            styles["Normal"]
        ))
        elements.append(Spacer(1, 20))

        # ================= SUMMARY TABLE =================
        income_agg = queryset.filter(transaction_type='income').aggregate(
            total=Sum('total_amount')
        )
        income = income_agg['total'] or Decimal('0.00')

        expense_agg = queryset.filter(transaction_type='expense').aggregate(
            total=Sum('total_amount')
        )
        expense = expense_agg['total'] or Decimal('0.00')

        net = income - expense

        summary_data = [
            ["Metric", "Amount (₦)"],
            ["Total Income", f"{income:,.2f}"],
            ["Total Expense", f"{expense:,.2f}"],
            ["Net", f"{net:,.2f}"],
        ]

        summary_table = Table(summary_data, colWidths=[200, 200])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 1, colors.grey),
            ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ]))

        elements.append(Paragraph("<b>Summary</b>", styles["Heading2"]))
        elements.append(summary_table)
        elements.append(Spacer(1, 20))

        # ================= TRANSACTIONS =================
        elements.append(Paragraph("<b>Detailed Transactions</b>", styles["Heading2"]))
        elements.append(Spacer(1, 10))

        tx_table_data = [
            ["Date", "Type", "Description", "Amount (₦)"]
        ]

        for tx in queryset.order_by("-date"):
            tx_table_data.append([
                tx.date.strftime("%Y-%m-%d"),
                tx.get_transaction_type_display(),
                tx.description,
                f"{tx.total_amount:,.2f}"
            ])

            # Items (indented rows)
            for item in tx.items.all():
                tx_table_data.append([
                    "",
                    "↳ Item",
                    f"{item.description} ({item.category or '-'})",
                    f"{item.amount:,.2f}"
                ])

        tx_table = Table(tx_table_data, colWidths=[70, 70, 230, 90])
        tx_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))

        elements.append(tx_table)

        # Background Watermark for free users
        def add_watermark(canvas, doc):
            if not is_pro:
                canvas.saveState()
                canvas.setFont('DejaVu', 60)
                canvas.setStrokeColor(colors.lightgrey)
                canvas.setFillColor(colors.lightgrey, alpha=0.3)
                # Rotate and draw watermark
                canvas.translate(A4[0]/2, A4[1]/2)
                canvas.rotate(45)
                canvas.drawCentredString(0, 0, "PREVIEW - UPGRADE TO PRO")
                canvas.setFont('DejaVu', 20)
                canvas.drawCentredString(0, -60, "NO DOWNLOAD/SHARING ALLOWED")
                canvas.restoreState()

        # Build PDF
        doc.build(elements, onFirstPage=add_watermark, onLaterPages=add_watermark)
        buffer.seek(0)

        return FileResponse(
            buffer,
            as_attachment=True,
            filename=f"dally_report_{datetime.now().strftime('%Y%m%d')}.pdf",
            content_type="application/pdf"
        )
