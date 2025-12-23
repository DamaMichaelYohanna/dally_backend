from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from .forms import WaitlistForm


def home(request):
    """
    Home page with hero, features, and waitlist form
    """
    form = WaitlistForm()
    return render(request, 'main/home.html', {'form': form})


def pricing(request):
    """
    Pricing page
    """
    return render(request, 'main/pricing.html')


def privacy(request):
    """
    Privacy policy page (NDPR-compliant)
    """
    return render(request, 'main/privacy.html')


def terms(request):
    """
    Terms of service page
    """
    return render(request, 'main/terms.html')


@require_http_methods(["POST"])
def waitlist_signup(request):
    """
    Handle waitlist form submission
    """
    form = WaitlistForm(request.POST)
    
    if form.is_valid():
        form.save()
        messages.success(
            request,
            "Thanks! We'll notify you when Dally is ready."
        )
        return redirect('main:home')
    else:
        # Return to home with errors
        messages.error(
            request,
            "There was an error with your submission. Please check your email and try again."
        )
        return render(request, 'main/home.html', {'form': form})

