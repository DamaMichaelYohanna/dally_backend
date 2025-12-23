from django.contrib import admin
from .models import Business, Transaction, TransactionItem


class TransactionItemInline(admin.TabularInline):
    model = TransactionItem
    extra = 1


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'created_at']
    search_fields = ['name', 'user__username']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['date', 'transaction_type', 'total_amount', 'user', 'business', 'is_deleted']
    list_filter = ['transaction_type', 'is_deleted', 'date']
    search_fields = ['description', 'user__username']
    readonly_fields = ['id', 'created_at', 'updated_at', 'total_amount']
    inlines = [TransactionItemInline]


@admin.register(TransactionItem)
class TransactionItemAdmin(admin.ModelAdmin):
    list_display = ['description', 'amount', 'category', 'transaction']
    list_filter = ['category']
    search_fields = ['description', 'category']
    readonly_fields = ['id', 'created_at', 'updated_at']
