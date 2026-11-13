
import logging
import re

from io import BytesIO

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from django.views.decorators.http import require_GET
from api_gateway.models import Tender


logger = logging.getLogger(__name__)


def safe_excel_value(value):
    """Prevent untrusted text from becoming an Excel formula."""

    if value is None:
        return ""

    value = str(value)

    if value.startswith(("=", "+", "-", "@")):
        return "'" + value

    return value


def build_tender_summary_excel(summary):

    wb = Workbook()
    ws = wb.active
    ws.title = "Tender Summary"

    # -------------------------------------------------
    # REPORT TITLE AND TENDER STATISTICS
    # -------------------------------------------------

    ws.merge_cells("A1:H1")
    ws["A1"] = "TENDER SUMMARY REPORT"
    ws["A1"].font = Font(
        bold=True,
        size=16,
        color="FFFFFF",
    )
    ws["A1"].fill = PatternFill(
        "solid",
        fgColor="1F4E78",
    )
    ws["A1"].alignment = Alignment(
        horizontal="center",
        vertical="center",
    )
    ws.row_dimensions[1].height = 32

    ws["A2"] = "Tender ID"
    ws["B2"] = safe_excel_value(summary.get("tender_id"))

    ws["D2"] = "Total Sections"
    ws["E2"] = summary.get("total_sections", 0)

    statistics = summary.get("statistics", {})

    ws["A3"] = "Found"
    ws["B3"] = statistics.get("found", 0)

    ws["C3"] = "Not Found"
    ws["D3"] = statistics.get("not_found", 0)

    ws["E3"] = "Unclear"
    ws["F3"] = statistics.get("unclear", 0)

    ws["G3"] = "Conflicting"
    ws["H3"] = statistics.get("conflicting", 0)

    # -------------------------------------------------
    # SUMMARY TABLE
    # -------------------------------------------------

    headers = [
        "Sr. No.",
        "Heading",
        "Category",
        "Key Point",
        "Summary",
        "Status",
        "Retrieval Status",
        "Citations",
    ]

    header_row = 5

    for col, header in enumerate(headers, start=1):
        ws.cell(
            row=header_row,
            column=col,
            value=header,
        )

    for section in summary.get("sections", []):

        # Build all citations into one cell.
        citation_lines = []

        for index, citation in enumerate(
            section.get("citations", []) or [],
            start=1,
        ):

            document = citation.get("document") or "Unknown document"
            page = citation.get("page")
            quote = citation.get("quote") or ""

            citation_text = (
                f"{index}. Document: {document}\n"
                f"Page: {page if page is not None else 'N/A'}\n"
                f"Quote: \"{quote}\""
            )

            citation_lines.append(citation_text)

        citations_text = (
            "\n\n".join(citation_lines)
            if citation_lines
            else "No citations available"
        )

        row = [
            section.get("sr_no"),
            safe_excel_value(section.get("heading")),
            safe_excel_value(section.get("category")),
            safe_excel_value(section.get("key_point")),
            safe_excel_value(section.get("summary")),
            safe_excel_value(section.get("status")),
            safe_excel_value(section.get("retrieval_status")),
            safe_excel_value(citations_text),
        ]

        ws.append(row)

    # -------------------------------------------------
    # FORMATTING
    # -------------------------------------------------

    header_fill = PatternFill(
        "solid",
        fgColor="1F4E78",
    )

    header_font = Font(
        bold=True,
        color="FFFFFF",
    )

    thin_border = Border(
        bottom=Side(
            style="thin",
            color="D9E2F3",
        )
    )

    for cell in ws[header_row]:

        cell.fill = header_fill
        cell.font = header_font

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

    ws.row_dimensions[header_row].height = 30

    for row in ws.iter_rows(
        min_row=header_row + 1,
        max_row=ws.max_row,
    ):

        for cell in row:

            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

            cell.border = thin_border

        # Give each summary row enough room.
        ws.row_dimensions[row[0].row].height = 90

    # -------------------------------------------------
    # COLUMN WIDTHS
    # -------------------------------------------------

    column_widths = {
        "A": 10,
        "B": 35,
        "C": 22,
        "D": 30,
        "E": 65,
        "F": 16,
        "G": 20,
        "H": 65,
    }

    for column, width in column_widths.items():
        ws.column_dimensions[column].width = width

    # Keep table headers visible while scrolling.
    ws.freeze_panes = "A6"

    # Enable Excel filters.
    ws.auto_filter.ref = (
        f"A{header_row}:H{ws.max_row}"
    )

    # Print settings.
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0

    # -------------------------------------------------
    # RETURN EXCEL FILE
    # -------------------------------------------------

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output.getvalue()
