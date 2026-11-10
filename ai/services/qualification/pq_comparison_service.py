
from decimal import Decimal, InvalidOperation
import re

from ai.services.qualification.company_credentials import COMPANY_CREDENTIALS


class PQComparisonService:

    def __init__(self, bid_capacity_mw=None):
        self.bid_capacity_mw = (
            Decimal(str(bid_capacity_mw))
            if bid_capacity_mw is not None
            else None
        )

    @staticmethod
    def _get(criterion, key, default=None):
        if isinstance(criterion, dict):
            return criterion.get(key, default)
        return getattr(criterion, key, default)

    @staticmethod
    def _to_decimal(value):
        try:
            if value is None:
                return None
            return Decimal(str(value).replace(",", "").strip())
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _financial_year(criterion):
        year = criterion.get("financial_years") if isinstance(
            criterion, dict
        ) else getattr(criterion, "financial_years", None)

        if isinstance(year, int):
            return f"{year - 1}-{str(year)[-2:]}"

        if isinstance(year, str):
            return year

        return "2025-26"

    def _get_financial_value(self, criterion):

        financials = COMPANY_CREDENTIALS["financials"]
        name = self._get(criterion, "criterion", "").lower()
        year = self._financial_year(criterion)

        if "turnover" in name:
            return (
                self._to_decimal(
                    financials.get("annual_turnover", {}).get(year)
                ),
                year,
            )

        if "net worth" in name:
            return (
                self._to_decimal(
                    financials.get("net_worth_by_year", {}).get(year)
                ),
                year,
            )

        if "pbdit" in name or "profit before depreciation" in name:
            return self._to_decimal(financials.get("pbdit")), year

        if "line of credit" in name:
            return self._to_decimal(
                financials.get("line_of_credit")
            ), year

        if "working capital" in name:
            return (
                self._to_decimal(
                    financials.get("working_capital_by_year", {}).get(year)
                ),
                year,
            )

        return None, year

    def _evaluate_financial_criterion(self, criterion):

        name = self._get(criterion, "criterion", "")
        requirement = self._get(criterion, "requirement", "")
        required_value = self._to_decimal(
            self._get(criterion, "required_value")
        )
        unit = self._get(criterion, "unit") or ""
        operator = self._get(criterion, "operator") or ">="

        company_value, year = self._get_financial_value(criterion)

        base = {
            "criterion": name,
            "category": "Financial",
            "tender_requirement": requirement,
            "source_document": self._get(
                criterion, "source_document", ""
            ),
            "page_number": self._get(criterion, "page_number"),
            "chunk_id": str(self._get(criterion, "chunk_id", "")),
            "evidence_quote": self._get(
                criterion, "evidence_quote", ""
            ),
        }

        if company_value is None or required_value is None:
            return {
                **base,
                "status": "INSUFFICIENT_INFORMATION",
                "company_evidence": (
                    f"No verified financial value available for FY {year}."
                ),
                "explanation": (
                    "The required company financial information is "
                    "not available in the supplied credentials."
                ),
            }

        # Per-MW criteria require the actual proposed bid capacity.
        is_per_mw = bool(
            re.search(r"/\s*mw|per\s*mw", unit, re.IGNORECASE)
        )

        if is_per_mw:

            if not self.bid_capacity_mw or self.bid_capacity_mw <= 0:
                return {
                    **base,
                    "status": "INSUFFICIENT_INFORMATION",
                    "company_evidence": (
                        f"FY {year} value: INR {company_value:,.2f}. "
                        "Proposed bid capacity is not provided."
                    ),
                    "explanation": (
                        "The financial requirement is per MW. "
                        "Provide the proposed bid capacity to calculate "
                        "the total eligibility requirement."
                    ),
                }

            required_total = (
                required_value * self.bid_capacity_mw
            )

            comparison_value = company_value

            evidence = (
                f"FY {year} company value: INR {company_value:,.2f}; "
                f"Bid capacity: {self.bid_capacity_mw} MW; "
                f"Required total: INR {required_total:,.2f}."
            )

        else:
            required_total = required_value
            comparison_value = company_value

            evidence = (
                f"FY {year} company value: INR {company_value:,.2f}."
            )

        comparisons = {
            ">=": comparison_value >= required_total,
            ">": comparison_value > required_total,
            "<=": comparison_value <= required_total,
            "<": comparison_value < required_total,
            "=": comparison_value == required_total,
            "==": comparison_value == required_total,
        }

        if operator not in comparisons:
            return {
                **base,
                "status": "INSUFFICIENT_INFORMATION",
                "company_evidence": evidence,
                "explanation": f"Unsupported operator: {operator}",
            }

        meets = comparisons[operator]

        return {
            **base,
            "status": "MEETS" if meets else "DOES_NOT_MEET",
            "company_evidence": evidence,
            "explanation": (
                f"Company value INR {comparison_value:,.2f} "
                f"{'meets' if meets else 'does not meet'} "
                f"the required amount INR {required_total:,.2f}."
            ),
        }
