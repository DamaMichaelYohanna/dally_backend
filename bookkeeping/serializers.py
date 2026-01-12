from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Business, Transaction, TransactionItem, InventoryPeriod
from decimal import Decimal
from django.db import transaction


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
# Inventory Period Serializer
# ======================================================
class InventoryPeriodSerializer(serializers.ModelSerializer):
    """
    Serializer for recording closing stock values
    """
    class Meta:
        model = InventoryPeriod
        fields = ['id', 'business', 'period_end', 'closing_value', 'notes', 'created_at']
        read_only_fields = ['id', 'business', 'created_at']

    def create(self, validated_data):
        user = self.context['request'].user
        try:
            business = Business.objects.get(user=user)
        except Business.DoesNotExist:
            raise serializers.ValidationError({"detail": "User does not have a business configured."})
        
        validated_data['business'] = business
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
            'expense_type',
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
    
    def validate(self, data):
        """
        Custom validation for expense_type
        """
        if data.get('transaction_type') == 'expense':
            if not data.get('expense_type'):
                # Make it optional for backward compatibility, but recommended
                pass 
        elif data.get('transaction_type') == 'income':
            # Income shouldn't have expense_type
            if data.get('expense_type'):
                data['expense_type'] = None
        return data

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
            # Try to get user's default business, but it's optional now
            business = getattr(user, 'business', None).first() if hasattr(user, 'business') else None

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
            'expense_type',
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
            'expense_type',
            'date',
            'total_amount',
        ]



class TransactionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionItem
        fields = ['id', 'description', 'amount', 'category']
        read_only_fields = ['id']

class TransactionSerializer(serializers.ModelSerializer):
    items = TransactionItemSerializer(many=True, required=False)
    # items_count is read-only, useful if you decide to return the created object
    items_count = serializers.IntegerField(source='items.count', read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_type', 'expense_type', 'date', 'description', 
            'total_amount', 'items_count', 'created_at', 'items'
        ]
        read_only_fields = ['id', 'created_at', 'items_count']
        extra_kwargs = {
            'total_amount': {'required': False}  # Optional, calculated if items exist
        }
    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        user = self.context['request'].user
        
        try:
            business = Business.objects.get(user=user)
        except Business.DoesNotExist:
            business = None
        # Calculate Total:
        # If items exist, sum them up. Otherwise, require total_amount.
        if items_data:
            calculated_total = sum(Decimal(str(item['amount'])) for item in items_data)
            validated_data['total_amount'] = calculated_total
        elif validated_data.get('total_amount') is None:
             raise serializers.ValidationError({"total_amount": "This field is required if no items are provided."})
        validated_data['business'] = business
        validated_data['user'] = user
        with transaction.atomic():
            transaction_instance = Transaction.objects.create(**validated_data)
            
            for item_data in items_data:
                TransactionItem.objects.create(transaction=transaction_instance, **item_data)
        
        return transaction_instance


# very important serializer below
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
        help_text="Total expenses in Naira (Operating + COGS)"
    )
    # New fields for better transparency
    cogs = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        required=False,
        help_text="Cost of Goods Sold"
    )
    operating_expenses = serializers.DecimalField(
        max_digits=15, decimal_places=2,
        required=False,
        help_text="Operating (Rent, Utilities, etc.)"
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
            'taxable_income', 'estimated_income_tax', 'vat_payable',
            'cogs', 'operating_expenses'
        ]
        for field in monetary_fields:
            if field in instance:
                # representation[field] = str(Decimal(str(instance[field])) / Decimal('100'))
                representation[field] = str(Decimal(str(instance[field])))
        return representation
