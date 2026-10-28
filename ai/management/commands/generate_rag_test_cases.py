
from django.core.management.base import BaseCommand, CommandError

from api_gateway.models import Tender
from ai.management.evaluation.test_case_generation_service import (
    TestCaseGenerationService,
)


class Command(BaseCommand):
    help = "Generate RAG evaluation test cases for a tender on demand."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tender-id",
            required=True,
            help="Internal tender ID, e.g. 220926-8218",
        )
        parser.add_argument(
            "--cases-per-batch",
            type=int,
            default=5,
            help="Maximum cases requested from each chunk batch.",
        )

    def handle(self, *args, **options):
        tender_id = options["tender_id"]
        cases_per_batch = options["cases_per_batch"]

        if cases_per_batch < 1:
            raise CommandError("--cases-per-batch must be at least 1.")

        tender = Tender.objects.filter(
            tender_id=tender_id
        ).first()

        if tender is None:
            raise CommandError(
                f"Tender with internal ID '{tender_id}' was not found."
            )

        try:
            result = TestCaseGenerationService.generate_for_tender(
                tender=tender,
                cases_per_batch=cases_per_batch,
            )
        except Exception as exc:
            raise CommandError(
                f"Test-case generation failed: {exc}"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Test-case generation finished for tender "
                f"{result['tender_id']}.\n"
                f"Chunks processed: {result['chunks_processed']}\n"
                f"Test cases generated: {result['test_cases_generated']}"
            )
        )
