from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Q
from decimal import Decimal
from datetime import datetime, date
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
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


@extend_schema_view(
    list=extend_schema(
        summary="List all businesses",
        description="Get a list of all businesses owned by the authenticated user.",
        tags=["Businesses"]
    ),
    create=extend_schema(
        summary="Create a business",
        description="Create a new business for the authenticated user. Each user can have one business.",
        tags=["Businesses"]
    ),
    retrieve=extend_schema(
        summary="Get business details",
        description="Retrieve details of a specific business.",
        tags=["Businesses"]
    ),
    update=extend_schema(
        summary="Update business",
        description="Update business information.",
        tags=["Businesses"]
    ),
    partial_update=extend_schema(
        summary="Partial update business",
        description="Partially update business information.",
        tags=["Businesses"]
    ),
    destroy=extend_schema(
        summary="Delete business",
        description="Delete a business.",
        tags=["Businesses"]
    ),
)
class BusinessViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Business
    Users can only access their own business
    """
    serializer_class = BusinessSerializer
    permission_classes = [IsAuthenticated, IsBusinessOwner]

    def get_queryset(self):
        """
        Filter to only return businesses owned by the authenticated user
        """
        return Business.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        """
        Automatically set the user when creating a business
        """
        serializer.save(user=self.request.user)


@extend_schema_view(
    list=extend_schema(
        summary="List transactions",
        description="Get a paginated list of transactions with filtering options.",
        tags=["Transactions"],
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
        ]
    ),
    create=extend_schema(
        summary="Create transaction",
        description="Create a new transaction with nested items. Total amount is calculated automatically from items.",
        tags=["Transactions"],
        examples=[
            OpenApiExample(
                'Transaction Example',
                value={
                    'transaction_type': 'expense',
                    'date': '2025-12-21',
                    'description': 'Office supplies',
                    'items': [
                        {
                            'description': 'Printer paper',
                            'amount': '25.50',
                            'category': 'supplies'
                        },
                        {
                            'description': 'Pens',
                            'amount': '15.00',
                            'category': 'supplies'
                        }
                    ]
                },
                request_only=True
            )
        ]
    ),
    retrieve=extend_schema(
        summary="Get transaction details",
        description="Retrieve a specific transaction with all its items.",
        tags=["Transactions"]
    ),
    update=extend_schema(
        summary="Update transaction",
        description="Update a transaction and its items. Total amount is recalculated automatically.",
        tags=["Transactions"]
    ),
    partial_update=extend_schema(
        summary="Partial update transaction",
        description="Partially update a transaction.",
        tags=["Transactions"]
    ),
    destroy=extend_schema(
        summary="Delete transaction (soft delete)",
        description="Soft delete a transaction. It will be marked as deleted but not removed from database.",
        tags=["Transactions"]
    ),
)
class TransactionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Transactions with nested items
    Supports CRUD operations with proper user scoping
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get_serializer_class(self):
        """
        Use different serializers for list and detail views
        """
        if self.action == 'list':
            return TransactionListSerializer
        return TransactionSerializer

    def get_queryset(self):
        """
        Filter transactions to only those owned by the authenticated user
        Exclude soft-deleted transactions by default
        Use select_related and prefetch_related for performance
        """
        queryset = Transaction.objects.filter(
            user=self.request.user,
            is_deleted=False
        ).select_related('business', 'user').prefetch_related('items')

        # Filter by transaction type if provided
        transaction_type = self.request.query_params.get('type', None)
        if transaction_type in ['income', 'expense']:
            queryset = queryset.filter(transaction_type=transaction_type)

        # Filter by date range
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        return queryset

    def perform_create(self, serializer):
        """
        Automatically set the user and business when creating a transaction
        """
        serializer.save()

    def perform_destroy(self, instance):
        """
        Soft delete - set is_deleted to True instead of actually deleting
        """
        instance.is_deleted = True
        instance.save()

    @extend_schema(
        summary="Get transaction summary",
        description="Get aggregated statistics including total income, expenses, and net amount.",
        tags=["Transactions"],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'income': {
                        'type': 'object',
                        'properties': {
                            'total': {'type': 'number'},
                            'count': {'type': 'integer'}
                        }
                    },
                    'expense': {
                        'type': 'object',
                        'properties': {
                            'total': {'type': 'number'},
                            'count': {'type': 'integer'}
                        }
                    },
                    'net': {'type': 'number'},
                    'total_transactions': {'type': 'integer'}
                }
            }
        }
    )
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get summary statistics for user's transactions
        """
        queryset = self.get_queryset()
        
        # Calculate totals
        income_total = queryset.filter(
            transaction_type='income'
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        
        expense_total = queryset.filter(
            transaction_type='expense'
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        
        net_total = income_total - expense_total
        
        # Count transactions
        income_count = queryset.filter(transaction_type='income').count()
        expense_count = queryset.filter(transaction_type='expense').count()
        
        return Response({
            'income': {
                'total': income_total,
                'count': income_count,
            },
            'expense': {
                'total': expense_total,
                'count': expense_count,
            },
            'net': net_total,
            'total_transactions': income_count + expense_count,
        })

    @extend_schema(
        summary="List deleted transactions",
        description="Get a list of soft-deleted transactions.",
        tags=["Transactions"]
    )
    @action(detail=False, methods=['get'])
    def deleted(self, request):
        """
        List soft-deleted transactions
        """
        deleted_transactions = Transaction.objects.filter(
            user=request.user,
            is_deleted=True
        ).select_related('business', 'user').prefetch_related('items')
        
        serializer = self.get_serializer(deleted_transactions, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Restore deleted transaction",
        description="Restore a soft-deleted transaction back to active state.",
        tags=["Transactions"]
    )
    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """
        Restore a soft-deleted transaction
        """
        transaction = self.get_object()
        
        if not transaction.is_deleted:
            return Response(
                {'error': 'Transaction is not deleted'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        transaction.is_deleted = False
        transaction.save()
        
        serializer = self.get_serializer(transaction)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        summary="List transaction items",
        description="Get a list of all transaction items for the authenticated user.",
        tags=["Transaction Items"]
    ),
    retrieve=extend_schema(
        summary="Get transaction item details",
        description="Retrieve details of a specific transaction item.",
        tags=["Transaction Items"]
    ),
)
class TransactionItemViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ReadOnly ViewSet for TransactionItems
    Items should be managed through the Transaction endpoint
    This is mainly for querying/viewing items
    """
    serializer_class = TransactionItemSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        """
        Filter items to only those belonging to user's transactions
        """
        return TransactionItem.objects.filter(
            transaction__user=self.request.user
        ).select_related('transaction')


@extend_schema_view(
    list=extend_schema(
        summary="Summary endpoints",
        description="Access various summary and analytics endpoints for bookkeeping data.",
        tags=["Summaries"]
    )
)
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


@extend_schema_view(
    list=extend_schema(
        summary="Tax calculation endpoints",
        description="Access Nigerian tax calculation endpoints based on Nigeria Tax Act 2025.",
        tags=["Tax"]
    )
)
class TaxViewSet(viewsets.ViewSet):
    """
    ViewSet for Nigerian tax calculations.
    
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
    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
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
