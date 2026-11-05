import logging
from pathlib import PurePath
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from ai.models import (EvaluationRun, EvaluationResult, EvaluationTestCase,)
from ai.management.evaluation.test_case_generation_service import (TestCaseGenerationService,)
from ai.services.documents.answer_generation_service import (AnswerGenerationService,)
from ai.models import ChatMessage
from ai.services.evaluation.ragas_evaluation_service import (RagasEvaluationService,)
from celery import shared_task
from api_gateway.models import Tender
from ai.services.documents.document_pipeline_service import (DocumentPipelineService,)
import re, os

logger = logging.getLogger(__name__)


def normalize(text):
    """Normalize text to reduce failures caused by formatting differences."""
    text = str(text or "").lower().strip()

    # Normalize common abbreviations.
    replacements = {
        r"\bgoi\b": "government of india",
        r"\bgomp\b": "government of madhya pradesh",
        r"\brs\.?\b": "rupees",
        r"\binr\b": "rupees",
    }

    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)

    # Normalize common Indian currency expressions.
    text = re.sub(r"₹\s*", " rupees ", text)

    def remove_number_commas(match):
        return match.group(0).replace(",", "")

    text = re.sub(
        r"(?<!\w)\d{1,3}(?:,\d{2,3})+(?!\w)",
        remove_number_commas,
        text,
    )

    # Normalize multiplication and punctuation, including dates.
    text = text.replace("×", " x ")
    text = re.sub(r"[^a-z0-9]+", " ", text)

    return re.sub(r"\s+", " ", text).strip()


# Known wording variations. Add aliases only when they express the
# same requirement in your tender documents.
TERM_ALIASES = {
    "not allowed": [
        "not permitted",
        "is not allowed",
        "is not permitted",
        "no exemption is allowed",
        "no exemption is permitted",
        "exemption is not allowed",
        "exemption is not permitted",
    ],
    "not refundable": [
        "non refundable",
        "nonrefundable",
        "non refundable amount",
    ],
    "540 days": [
        "18 months",
        "eighteen months",
    ],
    "50 00 000": [
        "50 lakhs",
        "50 lakh",
        "5000000",
    ],
}


def term_is_present(answer, required_term):
    """Match a required term or an explicitly defined equivalent."""
    normalized_answer = normalize(answer)
    normalized_term = normalize(required_term)

    if not normalized_term:
        return True

    if normalized_term in normalized_answer:
        return True

    # Check configured aliases in both directions where applicable.
    aliases = TERM_ALIASES.get(normalized_term, [])

    for alias in aliases:
        if normalize(alias) in normalized_answer:
            return True

    # Also allow a required alias to match its canonical term.
    for canonical, configured_aliases in TERM_ALIASES.items():
        normalized_aliases = [normalize(item) for item in configured_aliases]

        if normalized_term in normalized_aliases:
            if normalize(canonical) in normalized_answer:
                return True

            if any(
                alias in normalized_answer
                for alias in normalized_aliases
            ):
                return True

    return False


def check_required_terms(answer, required_terms):
    """Return whether required information is present, with missing terms."""
    missing_terms = [
        term
        for term in (required_terms or [])
        if not term_is_present(answer, term)
    ]

    return not missing_terms, missing_terms


def normalize_document_name(name):
    """Compare filenames without case, path, or extension differences."""
    filename = str(name or "").replace("\\", "/").split("/")[-1]
    stem = PurePath(filename).stem
    return normalize(stem)


def check_citations(citations, expected_sources):
    """
    Pass when at least one citation matches an expected source and page,
    and every returned citation has a non-empty supporting quote.

    Extra citations do not automatically fail the answer.
    """
    if not citations or not expected_sources:
        return False

    valid_citations = []

    for citation in citations:
        if not isinstance(citation, dict):
            continue

        document = citation.get("document")
        page = citation.get("page")
        quote = str(citation.get("quote") or "").strip()

        # A citation without a quote cannot be checked for support.
        if not document or not quote:
            continue

        valid_citations.append(citation)

    if not valid_citations:
        return False

    # At least one citation must point to an expected document/page.
    for citation in valid_citations:
        citation_document = normalize_document_name(
            citation.get("document")
        )
        citation_page = citation.get("page")

        for expected in expected_sources:
            if not isinstance(expected, dict):
                continue

            expected_document = normalize_document_name(
                expected.get("document")
            )
            expected_pages = expected.get("pages") or []

            if citation_document != expected_document:
                continue

            # If the expected pages are specified, require a page match.
            if expected_pages:
                if citation_page is None:
                    continue

                try:
                    page_matches = int(citation_page) in {
                        int(expected_page) for expected_page in expected_pages
                    }
                except (TypeError, ValueError):
                    page_matches = citation_page in expected_pages

                if not page_matches:
                    continue

            return True

    return False



@shared_task(bind=True)
def run_rag_evaluation(self, run_id):
    """
    Execute a saved evaluation run in the Celery worker.
    """
    run = None

    try:
        with transaction.atomic():
            run = EvaluationRun.objects.select_for_update().get(
                id=run_id
            )

            # Prevent a duplicate task delivery from starting a
            # run that is already running or has already finished.
            if run.status != EvaluationRun.Status.QUEUED:
                return {
                    "run_id": str(run.id),
                    "status": run.status,
                    "message": "Evaluation is not queued.",
                }

            run.status = EvaluationRun.Status.RUNNING
            run.started_at = timezone.now()
            run.celery_task_id = self.request.id or ""
            run.save(
                update_fields=[
                    "status",
                    "started_at",
                    "celery_task_id",
                ]
            )

        test_cases = list(
            EvaluationTestCase.objects.filter(
                tender=run.tender,
                status=EvaluationTestCase.Status.VALIDATED,
            ).order_by("created_at")
        )

        # Generate test cases automatically if none exist.
        if not test_cases:
            logger.info(
                "No validated test cases found for tender %s. Generating them.",
                run.tender.tender_id,
            )

            TestCaseGenerationService.generate_for_tender(
                tender=run.tender,
                cases_per_batch=5,
            )

            # Fetch the newly generated and validated test cases.
            test_cases = list(
                EvaluationTestCase.objects.filter(
                    tender=run.tender,
                    status=EvaluationTestCase.Status.VALIDATED,
                ).order_by("created_at")
            )

        if not test_cases:
            raise ValueError(
                "No validated test cases are available. "
                "Generation may have produced no cases or validation "
                "may have rejected or left them pending."
            )

        run.total_cases = len(test_cases)
        run.save(update_fields=["total_cases"])

        service = AnswerGenerationService()

        for test in test_cases:
            result_data = {
                "run": run,
                "test_case": test,
                "question": test.question,
                "expected_answer": test.expected_answer,
            }

            try:
                answer_result = service.answer(
                    tender_id=run.tender.tender_id,
                    question=test.question,
                )

                answer = answer_result.get("answer", "")
                citations = answer_result.get("citations", [])
                insufficient = answer_result.get(
                    "insufficient_evidence", False
                )

                answer_pass, missing_terms = check_required_terms(
                    answer,
                    test.required_terms,
                )

                if test.expected_insufficient_evidence:
                    citation_pass = not citations
                else:
                    citation_pass = check_citations(
                        citations,
                        test.expected_sources,
                    )

                insufficient_pass = (
                    insufficient == test.expected_insufficient_evidence
                )

                overall_pass = (
                    answer_pass
                    and citation_pass
                    and insufficient_pass
                )

                result_data.update({
                    "actual_answer": answer,
                    "answer_pass": answer_pass,
                    "missing_terms": missing_terms,
                    "citation_pass": citation_pass,
                    "citations": citations,
                    "insufficient_evidence": insufficient,
                    "insufficient_evidence_pass": insufficient_pass,
                    "overall_pass": overall_pass,
                })

            except Exception as exc:
                logger.exception(
                    "Evaluation failed for test case %s",
                    test.id,
                )

                result_data.update({
                    "actual_answer": "",
                    "answer_pass": False,
                    "missing_terms": [],
                    "citation_pass": False,
                    "citations": [],
                    "insufficient_evidence": False,
                    "insufficient_evidence_pass": False,
                    "overall_pass": False,
                    "error_message": str(exc),
                })

            # Save each result and update progress together.
            with transaction.atomic():
                EvaluationResult.objects.create(**result_data)

                run.completed_cases += 1
                if result_data["overall_pass"]:
                    run.passed_cases += 1
                else:
                    run.failed_cases += 1

                run.save(
                    update_fields=[
                        "completed_cases",
                        "passed_cases",
                        "failed_cases",
                    ]
                )

        run.status = EvaluationRun.Status.COMPLETED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])

        return {
            "run_id": str(run.id),
            "status": run.status,
            "total_cases": run.total_cases,
            "passed_cases": run.passed_cases,
            "failed_cases": run.failed_cases,
        }

    except Exception as exc:
        logger.exception("RAG evaluation run failed: %s", run_id)

        if run is not None:
            EvaluationRun.objects.filter(id=run_id).update(
                status=EvaluationRun.Status.FAILED,
                error_message=str(exc),
                finished_at=timezone.now(),
            )

        raise




@shared_task
def evaluate_live_rag_answer(assistant_message_id,question,answer,retrieved_contexts,):
    try:
        evaluation = RagasEvaluationService().evaluate(
            question=question,
            answer=answer,
            retrieved_contexts=retrieved_contexts or [],
        )
        evaluation["status"] = "completed"

    except Exception as exc:
        logger.exception("Live Ragas evaluation failed")
        evaluation = {
            "status": "failed",
            "error": type(exc).__name__,
        }

    with transaction.atomic():
        message = ChatMessage.objects.select_for_update().filter(
            id=assistant_message_id
        ).first()

        if message:
            metadata = message.metadata or {}
            metadata["ragas_evaluation"] = evaluation
            message.metadata = metadata
            message.save(update_fields=["metadata"])

    return evaluation


@shared_task
def run_document_pipeline(tender_id):
    tender = Tender.objects.get(tender_id=tender_id)

    result = DocumentPipelineService.run(tender)

    return result