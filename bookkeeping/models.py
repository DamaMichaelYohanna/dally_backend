import uuid
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

from account.models import User

class Business(models.Model):
    """
    Business model - one user has one business
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='business')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Businesses'
        indexes = [
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.name} - {self.user.username}"


class Transaction(models.Model):
    """
    Transaction model - can be income or expense
    Contains multiple line items
    """
    TRANSACTION_TYPES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
    ]

    EXPENSE_TYPES = [
        ('operating', 'Operating Expense'),      # Rent, utilities, salaries, etc.
        ('inventory', 'Inventory Purchase'),      # Stock/goods purchased for resale
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='transactions', blank=True, null=True)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    expense_type = models.CharField(
        max_length=20, 
        choices=EXPENSE_TYPES, 
        blank=True, 
        null=True,
        help_text="Categorize expenses for tax purposes (Operating vs Inventory)"
    )
    date = models.DateField()
    description = models.TextField(blank=True)
    total_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    is_deleted = models.BooleanField(default=False)  # Soft delete
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['business', 'date']),
            models.Index(fields=['user', 'is_deleted']),
            models.Index(fields=['transaction_type']),
        ]

    def __str__(self):
        return f"{self.transaction_type.title()} - {self.date} - {self.total_amount}"

    def calculate_total(self):
        """
        Calculate total amount from all transaction items
        """
        total = self.items.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        return total

    def save(self, *args, **kwargs):
        """
        Recalculate total_amount before saving
        Only recalculate on update, not on initial creation
        """
        # Check if this is an update (object already exists in DB)
        is_update = self.pk is not None and Transaction.objects.filter(pk=self.pk).exists()
        
        if is_update:
            self.total_amount = self.calculate_total()
        
        super().save(*args, **kwargs)


class InventoryPeriod(models.Model):
    """
    Track inventory values at period boundaries for COGS calculation.
    Used to store the 'Closing Stock' value provided by the user.
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='inventory_periods')
    period_end = models.DateField(help_text="End date of the period (e.g., 2026-12-31)")
    closing_value = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total value of unsold stock at the end of this period"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period_end']
        unique_together = ['business', 'period_end']
        indexes = [
            models.Index(fields=['business', 'period_end']),
        ]

    def __str__(self):
        return f"{self.business.name} - {self.period_end}: {self.closing_value}"


class TransactionItem(models.Model):
    """
    Line items for each transaction
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(
        Transaction, 
        on_delete=models.CASCADE, 
        related_name='items'
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    category = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['transaction']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return f"{self.description} - {self.amount}"
