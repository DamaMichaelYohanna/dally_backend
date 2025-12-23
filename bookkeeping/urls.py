from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BusinessViewSet, TransactionViewSet, TransactionItemViewSet, SummaryViewSet, TaxViewSet

router = DefaultRouter()
router.register(r'businesses', BusinessViewSet, basename='business')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'transaction-items', TransactionItemViewSet, basename='transactionitem')
router.register(r'summary', SummaryViewSet, basename='summary')
router.register(r'tax', TaxViewSet, basename='tax')

urlpatterns = [
    path('', include(router.urls)),
]
