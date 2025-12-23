from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal
from .models import Business, Transaction, TransactionItem


class BusinessModelTest(TestCase):
    """Test Business model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_create_business(self):
        """Test creating a business"""
        business = Business.objects.create(
            user=self.user,
            name="Test Business",
            description="A test business"
        )
        self.assertEqual(business.name, "Test Business")
        self.assertEqual(business.user, self.user)
        self.assertIsNotNone(business.id)


class TransactionModelTest(TestCase):
    """Test Transaction model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.business = Business.objects.create(
            user=self.user,
            name="Test Business"
        )
    
    def test_create_transaction_with_items(self):
        """Test creating a transaction with items"""
        transaction = Transaction.objects.create(
            user=self.user,
            business=self.business,
            transaction_type='income',
            date='2025-12-21',
            description='Test transaction',
            total_amount=Decimal('0.00')
        )
        
        # Create items
        TransactionItem.objects.create(
            transaction=transaction,
            description='Item 1',
            amount=Decimal('100.00')
        )
        TransactionItem.objects.create(
            transaction=transaction,
            description='Item 2',
            amount=Decimal('50.00')
        )
        
        # Test calculate_total
        self.assertEqual(transaction.calculate_total(), Decimal('150.00'))
        
        # Test save recalculates total
        transaction.save()
        transaction.refresh_from_db()
        self.assertEqual(transaction.total_amount, Decimal('150.00'))


class TransactionAPITest(APITestCase):
    """Test Transaction API endpoints"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.business = Business.objects.create(
            user=self.user,
            name="Test Business"
        )
        self.client.force_authenticate(user=self.user)
    
    def test_create_transaction(self):
        """Test creating a transaction via API"""
        data = {
            'transaction_type': 'expense',
            'date': '2025-12-21',
            'description': 'Office supplies',
            'items': [
                {
                    'description': 'Paper',
                    'amount': '25.50',
                    'category': 'supplies'
                },
                {
                    'description': 'Pens',
                    'amount': '15.00',
                    'category': 'supplies'
                }
            ]
        }
        
        response = self.client.post('/api/transactions/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['total_amount'], '40.50')
        self.assertEqual(len(response.data['items']), 2)
    
    def test_list_transactions(self):
        """Test listing transactions"""
        # Create a transaction
        transaction = Transaction.objects.create(
            user=self.user,
            business=self.business,
            transaction_type='income',
            date='2025-12-21',
            description='Test',
            total_amount=Decimal('100.00')
        )
        TransactionItem.objects.create(
            transaction=transaction,
            description='Item',
            amount=Decimal('100.00')
        )
        transaction.save()  # Recalculate total
        
        response = self.client.get('/api/transactions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_filter_by_type(self):
        """Test filtering transactions by type"""
        # Create income
        income = Transaction.objects.create(
            user=self.user,
            business=self.business,
            transaction_type='income',
            date='2025-12-21',
            total_amount=Decimal('100.00')
        )
        TransactionItem.objects.create(
            transaction=income,
            description='Income item',
            amount=Decimal('100.00')
        )
        income.save()  # Recalculate total
        
        # Create expense
        expense = Transaction.objects.create(
            user=self.user,
            business=self.business,
            transaction_type='expense',
            date='2025-12-21',
            total_amount=Decimal('50.00')
        )
        TransactionItem.objects.create(
            transaction=expense,
            description='Expense item',
            amount=Decimal('50.00')
        )
        expense.save()  # Recalculate total
        
        # Filter for income only
        response = self.client.get('/api/transactions/?type=income')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['transaction_type'], 'income')
    
    def test_soft_delete(self):
        """Test soft delete functionality"""
        transaction = Transaction.objects.create(
            user=self.user,
            business=self.business,
            transaction_type='income',
            date='2025-12-21',
            total_amount=Decimal('100.00')
        )
        TransactionItem.objects.create(
            transaction=transaction,
            description='Item',
            amount=Decimal('100.00')
        )
        transaction.save()  # Recalculate total
        
        # Delete transaction
        response = self.client.delete(f'/api/transactions/{transaction.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify it's not in normal list
        response = self.client.get('/api/transactions/')
        self.assertEqual(len(response.data['results']), 0)
        
        # Verify it still exists in database
        transaction.refresh_from_db()
        self.assertTrue(transaction.is_deleted)
    
    def test_user_isolation(self):
        """Test that users can only see their own transactions"""
        # Create another user
        other_user = User.objects.create_user(
            username='otheruser',
            password='otherpass123'
        )
        other_business = Business.objects.create(
            user=other_user,
            name="Other Business"
        )
        
        # Create transaction for other user
        other_transaction = Transaction.objects.create(
            user=other_user,
            business=other_business,
            transaction_type='income',
            date='2025-12-21',
            total_amount=Decimal('1000.00')
        )
        TransactionItem.objects.create(
            transaction=other_transaction,
            description='Other item',
            amount=Decimal('1000.00')
        )
        other_transaction.save()  # Recalculate total
        
        # Try to access as first user
        response = self.client.get('/api/transactions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)
        
        # Try to directly access other user's transaction
        response = self.client.get(f'/api/transactions/{other_transaction.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_transaction_summary(self):
        """Test transaction summary endpoint"""
        # Create income
        income = Transaction.objects.create(
            user=self.user,
            business=self.business,
            transaction_type='income',
            date='2025-12-21',
            total_amount=Decimal('1000.00')
        )
        TransactionItem.objects.create(
            transaction=income,
            description='Income',
            amount=Decimal('1000.00')
        )
        # Save again to recalculate total
        income.save()
        
        # Create expense
        expense = Transaction.objects.create(
            user=self.user,
            business=self.business,
            transaction_type='expense',
            date='2025-12-21',
            total_amount=Decimal('300.00')
        )
        TransactionItem.objects.create(
            transaction=expense,
            description='Expense',
            amount=Decimal('300.00')
        )
        # Save again to recalculate total
        expense.save()
        
        response = self.client.get('/api/transactions/summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['income']['total'], Decimal('1000.00'))
        self.assertEqual(response.data['expense']['total'], Decimal('300.00'))
        self.assertEqual(response.data['net'], Decimal('700.00'))


class PasswordRecoveryTest(APITestCase):
    """Test password recovery functionality"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='oldpassword123'
        )
    
    def test_password_reset_request(self):
        """Test requesting a password reset"""
        response = self.client.post('/api/auth/password-reset/', {
            'email': 'test@example.com'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        # In debug mode, should return reset_url
        if 'reset_url' in response.data:
            self.assertIn('uid', response.data)
            self.assertIn('token', response.data)
    
    def test_password_reset_request_invalid_email(self):
        """Test password reset with non-existent email"""
        response = self.client.post('/api/auth/password-reset/', {
            'email': 'nonexistent@example.com'
        })
        # Should still return 200 to prevent email enumeration
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_password_reset_confirm(self):
        """Test confirming password reset with valid token"""
        # Generate token
        token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        
        # Reset password
        response = self.client.post('/api/auth/password-reset-confirm/', {
            'uid': uid,
            'token': token,
            'new_password': 'newpassword123',
            'new_password_confirm': 'newpassword123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify password was changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpassword123'))
        self.assertFalse(self.user.check_password('oldpassword123'))
    
    def test_password_reset_confirm_mismatched_passwords(self):
        """Test password reset with mismatched passwords"""
        token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        
        response = self.client.post('/api/auth/password-reset-confirm/', {
            'uid': uid,
            'token': token,
            'new_password': 'newpassword123',
            'new_password_confirm': 'differentpassword'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_password_reset_confirm_invalid_token(self):
        """Test password reset with invalid token"""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        
        response = self.client.post('/api/auth/password-reset-confirm/', {
            'uid': uid,
            'token': 'invalid-token',
            'new_password': 'newpassword123',
            'new_password_confirm': 'newpassword123'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_password_reset_verify_valid_token(self):
        """Test verifying a valid reset token"""
        token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        
        response = self.client.get(f'/api/auth/password-reset-verify/{uid}/{token}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['valid'])
    
    def test_password_reset_verify_invalid_token(self):
        """Test verifying an invalid reset token"""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        
        response = self.client.get(f'/api/auth/password-reset-verify/{uid}/invalid-token/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['valid'])
    
    def test_change_password(self):
        """Test changing password while authenticated"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.post('/api/auth/change-password/', {
            'old_password': 'oldpassword123',
            'new_password': 'newpassword456',
            'new_password_confirm': 'newpassword456'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify password was changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpassword456'))
        self.assertFalse(self.user.check_password('oldpassword123'))
    
    def test_change_password_wrong_old_password(self):
        """Test changing password with incorrect old password"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.post('/api/auth/change-password/', {
            'old_password': 'wrongpassword',
            'new_password': 'newpassword456',
            'new_password_confirm': 'newpassword456'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Verify password was NOT changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('oldpassword123'))
    
    def test_change_password_unauthenticated(self):
        """Test changing password without authentication"""
        response = self.client.post('/api/auth/change-password/', {
            'old_password': 'oldpassword123',
            'new_password': 'newpassword456',
            'new_password_confirm': 'newpassword456'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_change_password_mismatched(self):
        """Test changing password with mismatched new passwords"""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.post('/api/auth/change-password/', {
            'old_password': 'oldpassword123',
            'new_password': 'newpassword456',
            'new_password_confirm': 'differentpassword'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
