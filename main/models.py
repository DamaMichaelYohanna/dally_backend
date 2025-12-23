from django.db import models
from django.utils import timezone


class WaitlistEntry(models.Model):
    """
    Waitlist signups for Dally app early access
    """
    BUSINESS_TYPES = [
        ('', 'Prefer not to say'),
        ('retail', 'Retail/Shop'),
        ('services', 'Services'),
        ('food', 'Food/Restaurant'),
        ('trade', 'Trading/Import-Export'),
        ('manufacturing', 'Manufacturing'),
        ('other', 'Other'),
    ]
    
    email = models.EmailField(unique=True, db_index=True)
    business_type = models.CharField(
        max_length=50, 
        choices=BUSINESS_TYPES, 
        blank=True,
        default=''
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    
    class Meta:
        verbose_name = 'Waitlist Entry'
        verbose_name_plural = 'Waitlist Entries'
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.email} - {self.created_at.strftime('%Y-%m-%d')}"

