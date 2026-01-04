from django.urls import path, include
from rest_framework.routers import DefaultRouter
# from .apis import BusinessViewSet, TransactionList, TransactionViewSet, TransactionItemViewSet, SummaryViewSet, TaxViewSet
from .apis import DashboardView, TransactionView, SummaryView, TaxView
# router = DefaultRouter()
# router.register(r'businesses', BusinessViewSet, basename='business')
# router.register(r'transactions', TransactionViewSet, basename='transaction')
# router.register(r'transaction-items', TransactionItemViewSet, basename='transactionitem')
# router.register(r'summary', SummaryViewSet, basename='summary')
# router.register(r'tax', TaxViewSet, basename='tax')

urlpatterns = [
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path("transactions/", TransactionView.as_view(), name="transactions"),
    path("summary/", SummaryView.as_view(), name="summary"),
    path("tax/", TaxView.as_view(), name="tax"),
    # path('', include(router.urls)),
]
