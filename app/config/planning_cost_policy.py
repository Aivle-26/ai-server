from decimal import Decimal


CURRENCY = "KRW"

SERVER_MONTHLY_COST = {
    "SMALL": Decimal("300000"),
    "MEDIUM": Decimal("800000"),
    "LARGE": Decimal("2000000"),
}

AI_API_MONTHLY_COST = {
    "SMALL": Decimal("150000"),
    "MEDIUM": Decimal("500000"),
    "LARGE": Decimal("1500000"),
}

LICENSE_MONTHLY_UNIT_PRICE = Decimal("40000")
VAT_RATE = Decimal("0.10")
CONTINGENCY_RATE = Decimal("0.10")
