from django import forms
from .models import WaitlistEntry


class WaitlistForm(forms.ModelForm):
    """
    Form for capturing waitlist signups
    """
    class Meta:
        model = WaitlistEntry
        fields = ['email', 'business_type']
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500',
                'placeholder': 'Enter your email address',
                'required': True,
            }),
            'business_type': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500',
            }),
        }
        labels = {
            'email': 'Email Address',
            'business_type': 'What type of business do you run?',
        }
        
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower().strip()
            # Check if email already exists
            if WaitlistEntry.objects.filter(email=email).exists():
                raise forms.ValidationError("This email is already on the waitlist.")
        return email
