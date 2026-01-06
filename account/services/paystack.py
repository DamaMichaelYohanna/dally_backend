import requests
from django.conf import settings

class PaystackService:
    BASE_URL = "https://api.paystack.co"
    SECRET_KEY = settings.PAYSTACK_SECRET_KEY

    @classmethod
    def get_headers(cls):
        return {
            "Authorization": f"Bearer {cls.SECRET_KEY}",
            "Content-Type": "application/json"
        }

    @classmethod
    def initialize_transaction(cls, email, amount, plan_id=None, callback_url=None):
        url = f"{cls.BASE_URL}/transaction/initialize"
        payload = {
            "email": email,
            "amount": int(amount * 100), # Paystack expects amount in Kobo
        }
        if plan_id:
            payload["plan"] = plan_id
        if callback_url:
            payload["callback_url"] = callback_url
        
        response = requests.post(url, json=payload, headers=cls.get_headers())
        return response.json()

    @classmethod
    def verify_transaction(cls, reference):
        url = f"{cls.BASE_URL}/transaction/verify/{reference}"
        response = requests.get(url, headers=cls.get_headers())
        return response.json()

    @classmethod
    def create_customer(cls, user):
        url = f"{cls.BASE_URL}/customer"
        payload = {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }
        response = requests.post(url, json=payload, headers=cls.get_headers())
        return response.json()
