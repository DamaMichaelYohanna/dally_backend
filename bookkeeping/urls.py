from django.urls import path
from .apis import DashboardView, TransactionCreateView, TransactionView, SummaryView, TaxView

urlpatterns = [
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path("transactions/", TransactionView.as_view(), name="transactions"),
    path('transactions/create/', TransactionCreateView.as_view(), name='transaction-create'),
    path("summary/", SummaryView.as_view(), name="summary"),
    path("tax/", TaxView.as_view(), name="tax"),
]
