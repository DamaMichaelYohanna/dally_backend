# Kashsum Bookkeeping API

A Django REST Framework backend for a bookkeeping MVP with multi-user support, JWT authentication, and offline-first capabilities.

## 🚀 Quick Start

**Interactive API Docs Available!** 

Start the server and visit: **http://localhost:8000/api/docs/**

```bash
python manage.py runserver
```

See [SWAGGER.md](SWAGGER.md) for the complete guide to testing with Swagger UI.

## Features

- **Multi-user system** with complete data isolation
- **JWT authentication** for secure API access
- **Transaction management** with nested line items
- **Soft delete** support for transactions
- **User-scoped data** - users can only access their own data
- **UUID primary keys** for client-side generation
- **Performance optimized** with select_related/prefetch_related
- **RESTful API** with filtering and summary endpoints
- **Interactive API documentation** with Swagger UI
- **Password recovery** with email-based reset

## Installation

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Run migrations:**
```bash
python manage.py migrate
```

3. **Create a superuser:**
```bash
python manage.py createsuperuser
```

4. **Run the development server:**
```bash
python manage.py runserver
```

5. **Access the API:**
- **Swagger UI**: http://localhost:8000/api/docs/
- **ReDoc**: http://localhost:8000/api/redoc/
- **Admin Panel**: http://localhost:8000/admin/

## 📖 Documentation

- **[SWAGGER.md](SWAGGER.md)** - Interactive API testing guide
- **[PASSWORD_RECOVERY.md](PASSWORD_RECOVERY.md)** - Password recovery & management
- **[QUICKSTART.md](QUICKSTART.md)** - Quick start guide with examples
- **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** - Complete project overview

## Data Models

### Business
- One-to-one relationship with User
- Each user has one business

### Transaction
- Belongs to a User and Business
- Can be either 'income' or 'expense'
- Contains multiple TransactionItems
- Supports soft delete (is_deleted flag)
- Total amount calculated from items

### TransactionItem
- Line items for each transaction
- Contains description, amount, and category
- Amount must be positive

## API Endpoints

### Authentication

**Obtain JWT Token:**
```
POST /api/token/
{
  "username": "user",
  "password": "password"
}
```

Response:
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Refresh Token:**
```
POST /api/token/refresh/
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Password Recovery:**
```
POST /api/auth/password-reset/
{
  "email": "user@example.com"
}
```

```
POST /api/auth/password-reset-confirm/
{
  "uid": "MQ",
  "token": "abc123-token",
  "new_password": "newpassword123",
  "new_password_confirm": "newpassword123"
}
```

```
POST /api/auth/change-password/
{
  "old_password": "currentpassword",
  "new_password": "newpassword123",
  "new_password_confirm": "newpassword123"
}
```

See [PASSWORD_RECOVERY.md](PASSWORD_RECOVERY.md) for complete documentation.
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### Business Endpoints

**List/Create Business:**
```
GET /api/businesses/
POST /api/businesses/
```

**Retrieve/Update/Delete Business:**
```
GET /api/businesses/{id}/
PUT /api/businesses/{id}/
PATCH /api/businesses/{id}/
DELETE /api/businesses/{id}/
```

### Transaction Endpoints

**List Transactions:**
```
GET /api/transactions/
```

Query parameters:
- `type` - Filter by 'income' or 'expense'
- `start_date` - Filter by start date (YYYY-MM-DD)
- `end_date` - Filter by end date (YYYY-MM-DD)

**Create Transaction with Items:**
```
POST /api/transactions/
{
  "transaction_type": "expense",
  "date": "2025-12-21",
  "description": "Office supplies",
  "items": [
    {
      "description": "Printer paper",
      "amount": "25.50",
      "category": "supplies"
    },
    {
      "description": "Pens",
      "amount": "15.00",
      "category": "supplies"
    }
  ]
}
```

**Retrieve Single Transaction:**
```
GET /api/transactions/{id}/
```

**Update Transaction:**
```
PUT /api/transactions/{id}/
PATCH /api/transactions/{id}/
{
  "transaction_type": "expense",
  "date": "2025-12-21",
  "description": "Updated description",
  "items": [
    {
      "description": "Updated item",
      "amount": "50.00",
      "category": "supplies"
    }
  ]
}
```

**Delete Transaction (Soft Delete):**
```
DELETE /api/transactions/{id}/
```

**Get Transaction Summary:**
```
GET /api/transactions/summary/
```

Response:
```json
{
  "income": {
    "total": "5000.00",
    "count": 10
  },
  "expense": {
    "total": "2500.00",
    "count": 25
  },
  "net": "2500.00",
  "total_transactions": 35
}
```

**List Deleted Transactions:**
```
GET /api/transactions/deleted/
```

**Restore Deleted Transaction:**
```
POST /api/transactions/{id}/restore/
```

### Transaction Items Endpoints

**List Items (ReadOnly):**
```
GET /api/transaction-items/
GET /api/transaction-items/{id}/
```

## Security Features

1. **JWT Authentication**: All endpoints require valid JWT token except auth endpoints
2. **User-scoped queries**: All querysets automatically filtered by authenticated user
3. **Permission classes**: Custom permissions enforce ownership
4. **No user_id in payload**: User automatically set from request.user
5. **Object-level permissions**: Users can only access their own data

## Making Authenticated Requests

Include the JWT token in the Authorization header:

```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

Example using curl:
```bash
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
     http://localhost:8000/api/transactions/
```

Example using JavaScript:
```javascript
fetch('http://localhost:8000/api/transactions/', {
  headers: {
    'Authorization': 'Bearer YOUR_ACCESS_TOKEN',
    'Content-Type': 'application/json'
  }
})
```

## Validation Rules

1. **Transactions must have at least one item**
2. **Transaction type must be 'income' or 'expense'**
3. **Item amounts must be positive (> 0)**
4. **Total amount is calculated server-side** (not editable)
5. **Business must belong to authenticated user**

## Offline-First Support

- **UUID primary keys** generated client-side
- **Explicit date fields** (no auto_now for business dates)
- **Conflict resolution** can be implemented using created_at/updated_at timestamps
- **Soft delete** allows for sync recovery

## Performance Optimizations

- **Indexed fields**: user_id, date, transaction_type, category
- **select_related**: Used for foreign keys (user, business)
- **prefetch_related**: Used for reverse relations (items)
- **Pagination**: 50 items per page by default

## Admin Interface

Access the Django admin at `/admin/` to manage:
- Users
- Businesses
- Transactions (with inline items)
- Transaction Items

## Project Structure

```
kashsum/
├── manage.py
├── kashsum/
│   ├── settings.py      # Django settings with DRF/JWT config
│   ├── urls.py          # Main URL configuration
│   └── ...
└── bookkeeping/
    ├── models.py        # Business, Transaction, TransactionItem
    ├── serializers.py   # DRF serializers with nested writes
    ├── views.py         # ViewSets with user scoping
    ├── permissions.py   # Custom permission classes
    ├── urls.py          # API routes
    └── admin.py         # Admin configuration
```

## Testing the API

You can use the Django REST Framework browsable API by visiting:
```
http://localhost:8000/api/
```

Or use tools like:
- Postman
- curl
- HTTPie
- Python requests

## Next Steps

1. Add user registration endpoint
2. Implement pagination customization
3. Add filtering by category
4. Create reports/analytics endpoints
5. Add bulk operations support
6. Implement webhook notifications
7. Add data export (CSV/Excel)
8. Implement audit logging
