import re
from decimal import Decimal


class TenderPriorityService:

    CAPACITY_THRESHOLD_MW = Decimal("40")
    AMOUNT_THRESHOLD_CRORE = Decimal("100")

    @staticmethod
    def extract_capacity_mw(title):

        if not title:
            return None

        patterns = [
            r'(\d+(?:\.\d+)?)\s*MW\b',
            r'(\d+(?:\.\d+)?)\s*MEGA\s*WATT',
            r'(\d+(?:\.\d+)?)\s*MEGAWATT',
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                title,
                re.IGNORECASE
            )

            if match:
                return Decimal(match.group(1))

        return None

    @staticmethod
    def extract_amount_crore(tender_data):

        if not tender_data:
            return None

        # TenderTiger's tender value
        tender_value = tender_data.get("tendervalue")

        if tender_value not in (None, "", "0", 0, 0.0):

            try:
                tender_value = Decimal(str(tender_value))

                # ₹1 Crore = ₹10,000,000
                return tender_value / Decimal("10000000")

            except (ValueError, TypeError, ArithmeticError):
                pass

        return None

    @classmethod
    def analyze(cls, tender_data):

        title = (
            tender_data.get("tendersbriefnew")
            or tender_data.get("tendersbrief")
            or ""
        )

        capacity = cls.extract_capacity_mw(title)

        amount = cls.extract_amount_crore(tender_data)

        is_high_priority = (
            (
                capacity is not None
                and capacity >= cls.CAPACITY_THRESHOLD_MW
            )
            or
            (
                amount is not None
                and amount >= cls.AMOUNT_THRESHOLD_CRORE
            )
        )

        return {
            "capacity_mw": capacity,
            "amount_crore": amount,
            "is_high_priority": is_high_priority,
        }