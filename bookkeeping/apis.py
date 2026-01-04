import os
from urllib.parse import urlencode
from rest_framework import viewsets, status
from django.http import HttpResponse
from django.conf import settings
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Q
from decimal import Decimal
from datetime import datetime, date, timedelta
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample
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
from rest_framework.generics import ListAPIView, CreateAPIView, RetrieveAPIView

from .models import Business, Transaction, TransactionItem
from .serializers import (
    BusinessSerializer, 
    TransactionSerializer, 
    TransactionListSerializer,
    TransactionItemSerializer,
    DailySummarySerializer,
    DateRangeSummarySerializer,
    ProfitLossSerializer,
    TaxSummarySerializer
)
from .permissions import IsOwner, IsBusinessOwner
from .services.summaries import daily_summary, date_range_summary, profit_and_loss
from .services.tax.nigeria_2026 import NigeriaTaxCalculator2026

from rest_framework.views import APIView
from django.core.cache import cache
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.pagination import PageNumberPagination


class DashboardView(APIView):
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        user = request.user
        cach_key = f'dashboard:{user.id}'
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
        # Create a unique cache key based on user and query params
        # TODO: Consider more advanced cache key generation if needed
        cache_key = f"transaction_list:{user.id}:{urlencode(sorted(params.items()))}"

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
        cache_key = f'summary:{user.id}'
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


        


# @extend_schema_view(
#     list=extend_schema(
#         summary="List all businesses",
#         description="Get a list of all businesses owned by the authenticated user.",
#         tags=["Businesses"]
#     ),
#     create=extend_schema(
#         summary="Create a business",
#         description="Create a new business for the authenticated user. Each user can have multiple businesses.",
#         tags=["Businesses"]
#     ),
#     retrieve=extend_schema(
#         summary="Get business details",
#         description="Retrieve details of a specific business.",
#         tags=["Businesses"]
#     ),
#     update=extend_schema(
#         summary="Update business",
#         description="Update business information.",
#         tags=["Businesses"]
#     ),
#     partial_update=extend_schema(
#         summary="Partial update business",
#         description="Partially update business information.",
#         tags=["Businesses"]
#     ),
#     destroy=extend_schema(
#         summary="Delete business",
#         description="Delete a business.",
#         tags=["Businesses"]
#     ),
# )
# class BusinessViewSet(viewsets.ModelViewSet):
#     """
#     ViewSet for managing Business
#     Users can only access their own business
#     """
#     serializer_class = BusinessSerializer
#     permission_classes = [IsAuthenticated, IsBusinessOwner]

#     def get_queryset(self):
#         """
#         Filter to only return businesses owned by the authenticated user
#         """
#         return Business.objects.filter(user=self.request.user)

#     def perform_create(self, serializer):
#         """
#         Automatically set the user when creating a business
#         """
#         serializer.save(user=self.request.user)


# @extend_schema_view(
#     list=extend_schema(
#         summary="List transactions",
#         description="Get a paginated list of transactions with filtering options.",
#         tags=["Transactions"],
#         parameters=[
#             OpenApiParameter(
#                 name='type',
#                 type=OpenApiTypes.STR,
#                 enum=['income', 'expense'],
#                 description='Filter by transaction type'
#             ),
#             OpenApiParameter(
#                 name='start_date',
#                 type=OpenApiTypes.DATE,
#                 description='Filter transactions from this date (YYYY-MM-DD)'
#             ),
#             OpenApiParameter(
#                 name='end_date',
#                 type=OpenApiTypes.DATE,
#                 description='Filter transactions until this date (YYYY-MM-DD)'
#             ),
#         ]
#     ),
#     create=extend_schema(
#         summary="Create transaction",
#         description="Create a new transaction with nested items. Total amount is calculated automatically from items.",
#         tags=["Transactions"],
#         examples=[
#             OpenApiExample(
#                 'Transaction Example',
#                 value={
#                     'transaction_type': 'expense',
#                     'date': '2025-12-21',
#                     'description': 'Office supplies',
#                     'items': [
#                         {
#                             'description': 'Printer paper',
#                             'amount': '25.50',
#                             'category': 'supplies'
#                         },
#                         {
#                             'description': 'Pens',
#                             'amount': '15.00',
#                             'category': 'supplies'
#                         }
#                     ]
#                 },
#                 request_only=True
#             )
#         ]
#     ),
#     retrieve=extend_schema(
#         summary="Get transaction details",
#         description="Retrieve a specific transaction with all its items.",
#         tags=["Transactions"]
#     ),
#     update=extend_schema(
#         summary="Update transaction",
#         description="Update a transaction and its items. Total amount is recalculated automatically.",
#         tags=["Transactions"]
#     ),
#     partial_update=extend_schema(
#         summary="Partial update transaction",
#         description="Partially update a transaction.",
#         tags=["Transactions"]
#     ),
#     destroy=extend_schema(
#         summary="Delete transaction (soft delete)",
#         description="Soft delete a transaction. It will be marked as deleted but not removed from database.",
#         tags=["Transactions"]
#     ),
# )
# class TransactionViewSet(viewsets.ModelViewSet):
#     """
#     ViewSet for managing Transactions with nested items
#     Supports CRUD operations with proper user scoping
#     """
#     permission_classes = [IsAuthenticated, IsOwner]

#     def get_serializer_class(self):
#         """
#         Use different serializers for list and detail views
#         """
#         if self.action == 'list':
#             return TransactionListSerializer
#         return TransactionSerializer

#     def get_queryset(self):
#         """
#         Filter transactions to only those owned by the authenticated user
#         Exclude soft-deleted transactions by default
#         Use select_related and prefetch_related for performance
#         """
#         queryset = Transaction.objects.filter(
#             user=self.request.user,
#             is_deleted=False
#         ).select_related('business', 'user').prefetch_related('items')

#         # Filter by transaction type if provided
#         transaction_type = self.request.query_params.get('type', None)
#         if transaction_type in ['income', 'expense']:
#             queryset = queryset.filter(transaction_type=transaction_type)

#         # Filter by date range
#         start_date = self.request.query_params.get('start_date', None)
#         end_date = self.request.query_params.get('end_date', None)
        
#         if start_date:
#             queryset = queryset.filter(date__gte=start_date)
#         if end_date:
#             queryset = queryset.filter(date__lte=end_date)

#         return queryset

#     def perform_create(self, serializer):
#         """
#         Automatically set the user and business when creating a transaction
#         """
#         serializer.save()

#     def perform_destroy(self, instance):
#         """
#         Soft delete - set is_deleted to True instead of actually deleting
#         """
#         instance.is_deleted = True
#         instance.save()

#     @extend_schema(
#         summary="Get transaction summary",
#         description="Get aggregated statistics including total income, expenses, and net amount.",
#         tags=["Transactions"],
#         responses={
#             200: {
#                 'type': 'object',
#                 'properties': {
#                     'income': {
#                         'type': 'object',
#                         'properties': {
#                             'total': {'type': 'number'},
#                             'count': {'type': 'integer'}
#                         }
#                     },
#                     'expense': {
#                         'type': 'object',
#                         'properties': {
#                             'total': {'type': 'number'},
#                             'count': {'type': 'integer'}
#                         }
#                     },
#                     'net': {'type': 'number'},
#                     'total_transactions': {'type': 'integer'}
#                 }
#             }
#         }
#     )
#     @action(detail=False, methods=['get'])
#     def summary(self, request):
#         """
#         Get summary statistics for user's transactions
#         """
#         queryset = self.get_queryset()
        
#         # Calculate totals
#         income_total = queryset.filter(
#             transaction_type='income'
#         ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        
#         expense_total = queryset.filter(
#             transaction_type='expense'
#         ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        
#         net_total = income_total - expense_total
        
#         # Count transactions
#         income_count = queryset.filter(transaction_type='income').count()
#         expense_count = queryset.filter(transaction_type='expense').count()
        
#         return Response({
#             'income': {
#                 'total': income_total,
#                 'count': income_count,
#             },
#             'expense': {
#                 'total': expense_total,
#                 'count': expense_count,
#             },
#             'net': net_total,
#             'total_transactions': income_count + expense_count,
#         })

#     @extend_schema(
#         summary="List deleted transactions",
#         description="Get a list of soft-deleted transactions.",
#         tags=["Transactions"]
#     )
#     @action(detail=False, methods=['get'])
#     def deleted(self, request):
#         """
#         List soft-deleted transactions
#         """
#         deleted_transactions = Transaction.objects.filter(
#             user=request.user,
#             is_deleted=True
#         ).select_related('business', 'user').prefetch_related('items')
        
#         serializer = self.get_serializer(deleted_transactions, many=True)
#         return Response(serializer.data)

#     @extend_schema(
#         summary="Restore deleted transaction",
#         description="Restore a soft-deleted transaction back to active state.",
#         tags=["Transactions"]
#     )
#     @action(detail=True, methods=['post'])
#     def restore(self, request, pk=None):
#         """
#         Restore a soft-deleted transaction
#         """
#         transaction = self.get_object()
        
#         if not transaction.is_deleted:
#             return Response(
#                 {'error': 'Transaction is not deleted'},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
        
#         transaction.is_deleted = False
#         transaction.save()
        
#         serializer = self.get_serializer(transaction)
#         return Response(serializer.data)

#     @action(detail=False, methods=['get'], url_path='export/pdf')
#     def export_pdf(self, request):
#         """
#         Export filtered transactions as a detailed PDF report for the logged-in business owner.
#         Filters: type, start_date, end_date, date (YYYY-MM-DD)
#         """
#         FONT_PATH = os.path.join(
#             settings.BASE_DIR,
#             'staticfiles',
#             "fonts",
#             "DejaVuSans.ttf"
#         )
#         # Register Unicode font
#         pdfmetrics.registerFont(TTFont('DejaVu', FONT_PATH))
#         queryset = self.get_queryset()

#         buffer = BytesIO()
#         doc = SimpleDocTemplate(
#             buffer,
#             pagesize=A4,
#             rightMargin=40,
#             leftMargin=40,
#             topMargin=40,
#             bottomMargin=40
#         )

#         styles = getSampleStyleSheet()
#         styles["Normal"].fontName = "DejaVu"
#         styles["Heading1"].fontName = "DejaVu"
#         styles["Heading2"].fontName = "DejaVu"

#         elements = []

#         # Title
#         elements.append(Paragraph("<b>Dally Bookkeeping Report</b>", styles["Heading1"]))
#         elements.append(Spacer(1, 10))

#         elements.append(Paragraph(
#             f"User: {request.user.email}<br/>"
#             f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
#             styles["Normal"]
#         ))
#         elements.append(Spacer(1, 20))

#         # ================= SUMMARY TABLE =================
#         income = queryset.filter(transaction_type='income').aggregate(
#             total=Sum('total_amount')
#         )['total'] or 0

#         expense = queryset.filter(transaction_type='expense').aggregate(
#             total=Sum('total_amount')
#         )['total'] or 0

#         net = income - expense

#         summary_data = [
#             ["Metric", "Amount (₦)"],
#             ["Total Income", f"{income:,.2f}"],
#             ["Total Expense", f"{expense:,.2f}"],
#             ["Net", f"{net:,.2f}"],
#         ]

#         summary_table = Table(summary_data, colWidths=[200, 200])
#         summary_table.setStyle(TableStyle([
#             ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
#             ("GRID", (0, 0), (-1, -1), 1, colors.grey),
#             ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
#             ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
#         ]))

#         elements.append(Paragraph("<b>Summary</b>", styles["Heading2"]))
#         elements.append(summary_table)
#         elements.append(Spacer(1, 20))

#         # ================= TRANSACTIONS =================
#         elements.append(Paragraph("<b>Detailed Transactions</b>", styles["Heading2"]))
#         elements.append(Spacer(1, 10))

#         tx_table_data = [
#             ["Date", "Type", "Description", "Amount (₦)"]
#         ]

#         for tx in queryset.order_by("-date"):
#             tx_table_data.append([
#                 tx.date.strftime("%Y-%m-%d"),
#                 tx.get_transaction_type_display(),
#                 tx.description,
#                 f"{tx.total_amount:,.2f}"
#             ])

#             # Items (indented rows)
#             for item in tx.items.all():
#                 tx_table_data.append([
#                     "",
#                     "↳ Item",
#                     f"{item.description} ({item.category or '-'})",
#                     f"{item.amount:,.2f}"
#                 ])

#         tx_table = Table(tx_table_data, colWidths=[70, 70, 230, 90])
#         tx_table.setStyle(TableStyle([
#             ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
#             ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
#             ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
#             ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
#             ("VALIGN", (0, 0), (-1, -1), "TOP"),
#         ]))

#         elements.append(tx_table)

#         # Build PDF
#         doc.build(elements)
#         buffer.seek(0)

#         return FileResponse(
#             buffer,
#             as_attachment=True,
#             filename="dally_report.pdf",
#             content_type="application/pdf"
#         )



# @extend_schema_view(
#     list=extend_schema(
#         summary="List transaction items",
#         description="Get a list of all transaction items for the authenticated user.",
#         tags=["Transaction Items"]
#     ),
#     retrieve=extend_schema(
#         summary="Get transaction item details",
#         description="Retrieve details of a specific transaction item.",
#         tags=["Transaction Items"]
#     ),
# )
# class TransactionItemViewSet(viewsets.ReadOnlyModelViewSet):
#     """
#     ReadOnly ViewSet for TransactionItems
#     Items should be managed through the Transaction endpoint
#     This is mainly for querying/viewing items
#     """
#     serializer_class = TransactionItemSerializer
#     permission_classes = [IsAuthenticated, IsOwner]

#     def get_queryset(self):
#         """
#         Filter items to only those belonging to user's transactions
#         """
#         return TransactionItem.objects.filter(
#             transaction__user=self.request.user
#         ).select_related('transaction')



class SummaryViewSet(viewsets.ViewSet):
    """
    ViewSet for summary and analytics endpoints.
    All calculations are performed dynamically from transaction data.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get daily summary",
        description="Calculate total income, expense, and net cash for a specific date. All amounts are in Naira (NGN).",
        parameters=[
            OpenApiParameter(
                name='date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=True,
                description='Date to calculate summary for (YYYY-MM-DD)'
            ),
            OpenApiParameter(
                name='business_id',
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Optional: Filter by specific business'
            ),
        ],
        responses={200: DailySummarySerializer},
        tags=["Summaries"]
    )
    @action(detail=False, methods=['get'], url_path='daily')
    def daily(self, request):
        """
        GET /api/summary/daily/?date=YYYY-MM-DD&business_id=uuid
        
        Returns daily income, expense, and net cash.
        """
        # Validate date parameter
        date_str = request.query_params.get('date')
        if not date_str:
            return Response(
                {'error': 'date parameter is required (YYYY-MM-DD)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Optional business filter
        business_id = request.query_params.get('business_id')
        
        # Calculate summary
        summary = daily_summary(
            user=request.user,
            target_date=target_date,
            business_id=business_id
        )
        
        serializer = DailySummarySerializer(summary)
        return Response(serializer.data)

    @extend_schema(
        summary="Get date range summary",
        description="Calculate total income, expense, and net profit for a date range. All amounts are in Naira (NGN).",
        parameters=[
            OpenApiParameter(
                name='start_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=True,
                description='Start date (YYYY-MM-DD)'
            ),
            OpenApiParameter(
                name='end_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=True,
                description='End date (YYYY-MM-DD)'
            ),
            OpenApiParameter(
                name='business_id',
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Optional: Filter by specific business'
            ),
        ],
        responses={200: DateRangeSummarySerializer},
        tags=["Summaries"]
    )
    @action(detail=False, methods=['get'], url_path='range')
    def range(self, request):
        """
        GET /api/summary/range/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&business_id=uuid
        
        Returns total income, expense, and net profit for date range.
        """
        # Validate parameters
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        
        if not start_date_str or not end_date_str:
            return Response(
                {'error': 'start_date and end_date parameters are required (YYYY-MM-DD)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if start_date > end_date:
            return Response(
                {'error': 'start_date must be before or equal to end_date'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Optional business filter
        business_id = request.query_params.get('business_id')
        
        # Calculate summary
        summary = date_range_summary(
            user=request.user,
            start_date=start_date,
            end_date=end_date,
            business_id=business_id
        )
        
        serializer = DateRangeSummarySerializer(summary)
        return Response(serializer.data)

    @extend_schema(
        summary="Get profit and loss statement",
        description="Calculate profit and loss statement for a date range. All amounts are in Naira (NGN).",
        parameters=[
            OpenApiParameter(
                name='start_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=True,
                description='Start date (YYYY-MM-DD)'
            ),
            OpenApiParameter(
                name='end_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=True,
                description='End date (YYYY-MM-DD)'
            ),
            OpenApiParameter(
                name='business_id',
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Optional: Filter by specific business'
            ),
        ],
        responses={200: ProfitLossSerializer},
        tags=["Summaries"]
    )
    @action(detail=False, methods=['get'], url_path='profit-loss')
    def profit_loss(self, request):
        """
        GET /api/summary/profit-loss/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&business_id=uuid
        
        Returns profit and loss statement with sales, purchases, and gross profit.
        """
        # Validate parameters
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        
        if not start_date_str or not end_date_str:
            return Response(
                {'error': 'start_date and end_date parameters are required (YYYY-MM-DD)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if start_date > end_date:
            return Response(
                {'error': 'start_date must be before or equal to end_date'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Optional business filter
        business_id = request.query_params.get('business_id')
        
        # Calculate profit and loss
        pl_data = profit_and_loss(
            user=request.user,
            start_date=start_date,
            end_date=end_date,
            business_id=business_id
        )
        
        serializer = ProfitLossSerializer(pl_data)
        return Response(serializer.data)

