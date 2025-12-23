from decimal import Decimal, ROUND_HALF_UP
from typing import Dict

from .config import (
    PIT_EXEMPT_THRESHOLD,
    PERSONAL_INCOME_TAX_BANDS_2026,
    VAT_RATE,
    TAX_DISCLAIMER,
    TAX_YEAR,
)


class NigeriaTaxCalculator2026:
    """
    Nigeria Personal Income Tax calculator (Tax Act 2025, effective 2026).

    Applies to:
    - Sole proprietors
    - Informal businesses

    Business profit is treated as personal income.
    """

    def __init__(self, vat_enabled: bool = False):
        self.vat_enabled = vat_enabled

    # =========================
    # PERSONAL INCOME TAX
    # =========================
    def calculate_personal_income_tax(self, taxable_income_kobo: int) -> int:
        """
        Calculate Personal Income Tax (PIT) for Nigeria (2026+).

        Args:
            taxable_income_kobo: Annual income in kobo

        Returns:
            PIT payable in kobo
        """

        if taxable_income_kobo <= 0:
            return 0

        # Convert kobo → naira
        gross_income = (
            Decimal(taxable_income_kobo) / Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Remove ₦800,000 exemption
        chargeable_income = max(
            Decimal("0.00"),
            gross_income - PIT_EXEMPT_THRESHOLD
        )

        if chargeable_income == 0:
            return 0

        tax_payable = Decimal("0.00")
        previous_limit = Decimal("0.00")

        for upper_limit, rate in PERSONAL_INCOME_TAX_BANDS_2026:
            if chargeable_income <= previous_limit:
                break

            band_upper = upper_limit
            band_rate = rate

            taxable_in_band = min(
                chargeable_income - previous_limit,
                band_upper - previous_limit
            )

            if taxable_in_band > 0:
                tax_payable += taxable_in_band * band_rate

            previous_limit = band_upper

        # Convert naira → kobo
        return int(
            (tax_payable * Decimal("100"))
            .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )

    # =========================
    # VAT
    # =========================
    def calculate_vat(self, revenue_kobo: int) -> int:
        if not self.vat_enabled or revenue_kobo <= 0:
            return 0

        vat = Decimal(revenue_kobo) * VAT_RATE
        return int(
            vat.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )

    # =========================
    # SUMMARY
    # =========================
    def calculate_tax_summary(
        self,
        total_revenue_kobo: int,
        total_expenses_kobo: int,
        business_id
    ) -> Dict:

        revenue = Decimal(total_revenue_kobo)
        expenses = Decimal(total_expenses_kobo)

        net_profit = max(Decimal("0.00"), revenue - expenses)

        pit = self.calculate_personal_income_tax(int(net_profit))
        vat = self.calculate_vat(int(revenue))

        effective_tax_rate = (
            Decimal(pit) / net_profit
            if net_profit > 0 else Decimal("0.00")
        )

        return {
            "total_revenue": int(revenue),
            "total_expenses": int(expenses),
            "net_profit": int(net_profit),
            "taxable_income": int(net_profit),
            "estimated_income_tax": pit,
            "effective_tax_rate": float(
                effective_tax_rate.quantize(Decimal("0.0001"))
            ),
            "vat_payable": vat,
            "tax_year": TAX_YEAR,
            "calculation_method": (
                "Nigeria Tax Act 2025 – PIT for Sole Proprietors "
                "(₦800,000 exemption applied)"
            ),
            "disclaimer": TAX_DISCLAIMER,
        }
