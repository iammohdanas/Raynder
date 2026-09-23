import re
from decimal import Decimal

class TenderPriorityService:
    CAPACITY_THRESHOLD_MW=Decimal("40")
    AMOUNT_THRESHOLD_CRORE=Decimal("100")

    @staticmethod
    def extract_capacity_mw(title):
        if not title:
            return None

        patterns=[
            r'(\d[\d,]*(?:\.\d+)?)\s*MW\b',
            r'(\d[\d,]*(?:\.\d+)?)\s*MEGA\s*WATT',
            r'(\d[\d,]*(?:\.\d+)?)\s*MEGAWATT',
            r'(\d[\d,]*(?:\.\d+)?)\s*MWh\b',
            r'(\d[\d,]*(?:\.\d+)?)\s*MEGA\s*WATT\s*HOUR',
        ]

        for pattern in patterns:
            match=re.search(pattern,title,re.IGNORECASE)
            if match:
                return Decimal(match.group(1).replace(",",""))

        return None

    @staticmethod
    def extract_amount_crore(tender_data):
        if not tender_data:
            return None

        value=tender_data.get("amount_crore")

        if value is not None:
            try:
                return Decimal(str(value).replace(",",""))
            except (ValueError,TypeError,ArithmeticError):
                pass

        value=tender_data.get("tender_value")

        if value not in (None,"","null",0,"0"):
            try:
                if isinstance(value,(int,float,Decimal)):
                    return Decimal(str(value))/Decimal("10000000")

                value=str(value).strip().lower()
                value=re.sub(r'₹|rs\.?|inr','',value).strip()
                value=value.replace(",","")

                match=re.search(
                    r'(\d+(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lakh|lac)\b',
                    value,
                    re.IGNORECASE
                )

                if match:
                    amount=Decimal(match.group(1))
                    unit=match.group(2).lower()

                    if unit.startswith(("crore","cr")):
                        return amount

                    return amount/Decimal("100")

                return Decimal(value)/Decimal("10000000")

            except (ValueError,TypeError,ArithmeticError):
                pass

        title=tender_data.get("title") or ""

        match=re.search(
            r'(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lakh|lac)\b',
            title,
            re.IGNORECASE
        )

        if match:
            amount=Decimal(match.group(1).replace(",",""))
            unit=match.group(2).lower()

            if unit.startswith(("crore","cr")):
                return amount

            return amount/Decimal("100")

        return None

    @classmethod
    def analyze(cls,tender_data):
        title=tender_data.get("title") or ""

        capacity=tender_data.get("capacity_mw")

        if capacity is not None:
            try:
                capacity=Decimal(str(capacity).replace(",",""))
            except (ValueError,TypeError,ArithmeticError):
                capacity=None

        if capacity is None:
            raw=tender_data.get("raw_data") or {}
            capacity=(
                raw.get("ac_capacity_mw")
                or raw.get("dc_capacity_mw")
                or raw.get("bess_capacity_mw")
            )

            if capacity is not None:
                try:
                    capacity=Decimal(str(capacity).replace(",",""))
                except (ValueError,TypeError,ArithmeticError):
                    capacity=None

        if capacity is None:
            capacity=cls.extract_capacity_mw(title)

        amount=cls.extract_amount_crore(tender_data)

        is_high_priority=(
            (capacity is not None and capacity>=cls.CAPACITY_THRESHOLD_MW)
            or
            (amount is not None and amount>=cls.AMOUNT_THRESHOLD_CRORE)
        )

        return {
            "capacity_mw":capacity,
            "amount_crore":amount,
            "is_high_priority":is_high_priority,
        }