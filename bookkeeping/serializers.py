from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Business, Transaction, TransactionItem
from decimal import Decimal


class BusinessSerializer(serializers.ModelSerializer):
    """
    Serializer for Business model
    """    
    class Meta:
        model = Business
        fields = ['id', 'user', 'name', 'description', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def create(self, validated_data):
        # Automatically set user from request context
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


# ======================================================
# my updated serializers below
class TransactionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionItem
        fields = ['id', 'description', 'amount', 'category']
        read_only_fields = ['id']


# ======================================================
# Transaction create serializer
class TransactionCreateSerializer(serializers.ModelSerializer):
    items = TransactionItemSerializer(many=True)
    business_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = Transaction
        fields = [
            'transaction_type',
            'date',
            'description',
            'business_id',
            'items',
        ]

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError(
                "At least one transaction item is required."
            )
        return value

    def validate_transaction_type(self, value):
        if value not in ['income', 'expense']:
            raise serializers.ValidationError(
                "Transaction type must be 'income' or 'expense'."
            )
        return value

    def validate_business_id(self, value):
        user = self.context['request'].user
        try:
            return Business.objects.get(id=value, user=user)
        except Business.DoesNotExist:
            raise serializers.ValidationError(
                "Business not found or does not belong to you."
            )

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        business = validated_data.pop('business_id', None)
        user = self.context['request'].user

        if not business:
            business = user.business

        total_amount = sum(
            Decimal(item['amount']) for item in items_data
        )

        transaction = Transaction.objects.create(
            user=user,
            business=business,
            total_amount=total_amount,
            **validated_data
        )

        TransactionItem.objects.bulk_create([
            TransactionItem(
                transaction=transaction,
                **item
            )
            for item in items_data
        ])

        return transaction

# 
# =====================================================
# Transaction update serializers going here
class TransactionUpdateSerializer(serializers.ModelSerializer):
    items = TransactionItemSerializer(many=True, required=False)
    business_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = Transaction
        fields = [
            'transaction_type',
            'date',
            'description',
            'business_id',
            'items',
        ]

    def validate_business_id(self, value):
        user = self.context['request'].user
        try:
            return Business.objects.get(id=value, user=user)
        except Business.DoesNotExist:
            raise serializers.ValidationError(
                "Business not found or does not belong to you."
            )

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        business = validated_data.pop('business_id', None)

        if business:
            instance.business = business

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if items_data is not None:
            instance.items.all().delete()
            TransactionItem.objects.bulk_create([
                TransactionItem(
                    transaction=instance,
                    **item
                )
                for item in items_data
            ])
            instance.total_amount = sum(
                Decimal(item['amount']) for item in items_data
            )

        instance.save()
        return instance

# =====================================================
# Transaction list serializer here 
class TransactionListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'id',
            'transaction_type',
            'date',
            'total_amount',
        ]





class TransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for Transaction model with nested items.
    Supports creating and updating transactions with items in a single request.
    All amounts are in Naira (NGN).
    """
    items = TransactionItemSerializer(many=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    business = serializers.PrimaryKeyRelatedField(read_only=True)
    business_id = serializers.UUIDField(write_only=True, required=False)
    total_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True,
        help_text="Total amount in Naira (NGN)"
    )
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'user', 'business', 'business_id', 'transaction_type', 
            'date', 'description', 'total_amount', 'items', 
            'is_deleted', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'business', 'total_amount', 'created_at', 'updated_at']

    def validate_items(self, value):
        """
        Validate that at least one item is provided
        """
        if not value or len(value) == 0:
            raise serializers.ValidationError("At least one transaction item is required.")
        return value

    def validate_transaction_type(self, value):
        """
        Validate transaction type
        """
        if value not in ['income', 'expense']:
            raise serializers.ValidationError("Transaction type must be 'income' or 'expense'.")
        return value

    def validate_business_id(self, value):
        """
        Validate that the business belongs to the user
        """
        user = self.context['request'].user
        try:
            business = Business.objects.get(id=value, user=user)
            return business
        except Business.DoesNotExist:
            raise serializers.ValidationError("Business not found or does not belong to you.")

    def create(self, validated_data):
        """
        Create transaction with nested items
        """
        items_data = validated_data.pop('items')
        user = self.context['request'].user
        
        # Get business - either from business_id or user's default business
        business = validated_data.pop('business_id', None)
        if not business:
            business = user.business
        
        # Calculate total from items
        total_amount = sum(Decimal(str(item['amount'])) for item in items_data)
        # convert sum from naira to kobo
        total_amount = total_amount * Decimal('100')
        
        # Create transaction
        transaction = Transaction.objects.create(
            user=user,
            business=business,
            total_amount=total_amount,
            **validated_data
        )
        
        # Create items
        for item_data in items_data:
            TransactionItem.objects.create(transaction=transaction, **item_data)
        
        # Refresh to get updated values
        transaction.refresh_from_db()
        
        return transaction

    def update(self, instance, validated_data):
        """
        Update transaction and its items
        """
        items_data = validated_data.pop('items', None)
        business = validated_data.pop('business_id', None)
        
        # Update business if provided
        if business:
            instance.business = business
        
        # Update transaction fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Update items if provided
        if items_data is not None:
            # Delete existing items
            instance.items.all().delete()
            
            # Create new items
            for item_data in items_data:
                TransactionItem.objects.create(transaction=instance, **item_data)
            
            # Recalculate total
            instance.total_amount = sum(Decimal(str(item['amount'])) for item in items_data)
        
        instance.save()
        return instance


class TransactionListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing transactions.
    All amounts are in Naira (NGN).
    """
    items_count = serializers.SerializerMethodField()
    total_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True,
        help_text="Total amount in Naira (NGN)"
    )
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_type', 'date', 'description', 
            'total_amount', 'items_count', 'created_at'
        ]
        read_only_fields = fields

    def get_items_count(self, obj):
        return obj.items.count()


# Summary Serializers

class DailySummarySerializer(serializers.Serializer):
    """
    Serializer for daily summary response.
    All monetary values are output in Naira (NGN).
    """
    date = serializers.DateField()
    currency = serializers.CharField()
    total_income = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Total income in Naira"
    )
    total_expense = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Total expense in Naira"
    )
    net_cash = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Net cash (income - expense) in Naira"
    )
    
    def to_representation(self, instance):
        """Convert kobo to Naira for output"""
        representation = super().to_representation(instance)
        # Convert from kobo to naira
        for field in ['total_income', 'total_expense', 'net_cash']:
            if field in instance:
                representation[field] = str(Decimal(str(instance[field])) / Decimal('100'))
        return representation


class DateRangeSummarySerializer(serializers.Serializer):
    """
    Serializer for date range summary response.
    All monetary values are output in Naira (NGN).
    """
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    currency = serializers.CharField()
    total_income = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Total income in Naira"
    )
    total_expense = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Total expense in Naira"
    )
    net_profit = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Net profit (income - expense) in Naira"
    )
    
    def to_representation(self, instance):
        """Convert kobo to Naira for output"""
        representation = super().to_representation(instance)
        # Convert from kobo to naira
        for field in ['total_income', 'total_expense', 'net_profit']:
            if field in instance:
                representation[field] = str(Decimal(str(instance[field])) / Decimal('100'))
        return representation


class ProfitLossSerializer(serializers.Serializer):
    """
    Serializer for profit and loss statement response.
    All monetary values are output in Naira (NGN).
    """
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    currency = serializers.CharField()
    total_sales = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Total sales (income) in Naira"
    )
    total_purchases = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Total purchases (expense) in Naira"
    )
    gross_profit = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Gross profit (sales - purchases) in Naira"
    )
    
    def to_representation(self, instance):
        """Convert kobo to Naira for output"""
        representation = super().to_representation(instance)
        # Convert from kobo to naira
        for field in ['total_sales', 'total_purchases', 'gross_profit']:
            if field in instance:
                representation[field] = str(Decimal(str(instance[field])) / Decimal('100'))
        return representation


class TaxSummarySerializer(serializers.Serializer):
    """
    Serializer for Nigerian tax summary response.
    
    Based on Nigeria Tax Act 2025 (effective January 1, 2026).
    All monetary values are output in Naira (NGN).
    Internal calculations done in kobo for precision.
    
    Key Legal Points:
    - First ₦800,000 of annual income is tax-exempt (0%)
    - PIT applies only to income exceeding ₦800,000
    - Progressive rates with top marginal rate of 25%
    """
    total_revenue = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Total revenue/income in Naira"
    )
    total_expenses = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Total expenses in Naira"
    )
    net_profit = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Net profit (revenue - expenses) in Naira"
    )
    taxable_income = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Income subject to tax in Naira"
    )
    estimated_income_tax = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Estimated Personal Income Tax in Naira (Nigeria Tax Act 2025)"
    )
    effective_tax_rate = serializers.FloatField(
        help_text="Actual tax rate as percentage (0-100)"
    )
    vat_payable = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        help_text="Value Added Tax payable in Naira (7.5% if VAT enabled)"
    )
    disclaimer = serializers.CharField(
        help_text="Legal disclaimer - not an official FIRS filing"
    )
    tax_year = serializers.IntegerField(
        help_text="Applicable tax year"
    )
    calculation_method = serializers.CharField(
        help_text="Tax calculation approach used"
    )
    period_start = serializers.DateField(
        required=False,
        help_text="Start date of reporting period"
    )
    period_end = serializers.DateField(
        required=False,
        help_text="End date of reporting period"
    )
    
    def to_representation(self, instance):
        """Convert kobo to Naira for output"""
        representation = super().to_representation(instance)
        # Convert monetary fields from kobo to naira
        monetary_fields = [
            'total_revenue', 'total_expenses', 'net_profit', 
            'taxable_income', 'estimated_income_tax', 'vat_payable'
        ]
        for field in monetary_fields:
            if field in instance:
                representation[field] = str(Decimal(str(instance[field])) / Decimal('100'))
        return representation
