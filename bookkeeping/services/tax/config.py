"""
Tax configuration for Nigeria Tax Act 2025 (effective January 1, 2026).

Acts signed into law: June 26, 2025
Effective date: January 1, 2026

Target:
- Nigerian sole proprietors / informal businesses
- Business profit treated as personal income (PIT)
- Companies Income Tax (CIT) does NOT apply

Key Legal Changes (2026):
- First ₦800,000 of annual income is FULLY EXEMPT from PIT
- PIT applies ONLY to income above ₦800,000
- Progressive PIT regime with top marginal rate of 25%
- CRA is no longer used

IMPORTANT:
- PIT bands below apply ONLY to CHARGEABLE income
  (i.e. income AFTER removing ₦800,000 exemption)
"""

from decimal import Decimal

# =========================
# PIT EXEMPTION THRESHOLD
# =========================
PIT_EXEMPT_THRESHOLD = Decimal("800000")  # ₦800,000


# =========================
# PERSONAL INCOME TAX BANDS (2026)
# =========================
# These are cumulative upper limits on CHARGEABLE INCOME
# (i.e. income exceeding ₦800,000)

PERSONAL_INCOME_TAX_BANDS_2026 = [
    # (upper_limit_ngn, marginal_rate)
    (Decimal("2200000"), Decimal("0.15")),   # First ₦2.2m @ 15%
    (Decimal("11200000"), Decimal("0.18")),  # Next ₦9m @ 18%
    (Decimal("24200000"), Decimal("0.21")),  # Next ₦13m @ 21%
    (Decimal("49200000"), Decimal("0.23")),  # Next ₦25m @ 23%
    (Decimal("Infinity"), Decimal("0.25")),  # Above ₦50m @ 25%
]


# =========================
# VAT (OPTIONAL)
# =========================
VAT_RATE = Decimal("0.075")  # 7.5%


# =========================
# METADATA
# =========================
TAX_YEAR = 2026

TAX_DISCLAIMER = (
    "These are estimates only and do not constitute official tax filing with FIRS "
    "(Federal Inland Revenue Service). Consult a licensed tax professional for "
    "accurate tax computation and filing."
)
