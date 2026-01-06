from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Transaction, TransactionItem

def increment_user_cache_version(user_id):
    """
    Increment the cache version for a specific user.
    """
    version_key = f'user_cache_version:{user_id}'
    try:
        cache.incr(version_key)
    except ValueError:
        # Key doesn't exist, initialize it
        cache.set(version_key, 1, timeout=None)

@receiver(post_save, sender=Transaction)
@receiver(post_delete, sender=Transaction)
def transaction_changed(sender, instance, **kwargs):
    """
    Clear cache when a transaction is added, updated, or deleted.
    """
    increment_user_cache_version(instance.user.id)

@receiver(post_save, sender=TransactionItem)
@receiver(post_delete, sender=TransactionItem)
def transaction_item_changed(sender, instance, **kwargs):
    """
    Clear cache when a transaction item is changed.
    """
    if instance.transaction and instance.transaction.user:
        increment_user_cache_version(instance.transaction.user.id)
