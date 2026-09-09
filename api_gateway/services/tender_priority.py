import re


class TenderPriorityService:

    CAPACITY_THRESHOLD_MW = 40
    AMOUNT_THRESHOLD_CRORE = 100

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
            match = re.search(pattern, title, re.IGNORECASE)

            if match:
                return float(match.group(1))

        return None

    @staticmethod
    def extract_amount_crore(title):
        if not title:
            return None

        patterns = [
            r'(?:₹|rs\.?|inr)?\s*'
            r'(\d+(?:\.\d+)?)\s*'
            r'(?:crore|crores|cr)\b'
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)

            if match:
                return float(match.group(1))

        return None

    @classmethod
    def is_high_priority(cls, title):

        capacity = cls.extract_capacity_mw(title)
        amount = cls.extract_amount_crore(title)

        return (
            (capacity is not None and capacity >= cls.CAPACITY_THRESHOLD_MW)
            or
            (amount is not None and amount >= cls.AMOUNT_THRESHOLD_CRORE)
        )