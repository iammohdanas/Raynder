
import csv
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from ai.services.documents.answer_generation_service import (
    AnswerGenerationService,
)


def normalize(text):
    """Normalize text for simple, case-insensitive matching."""
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def check_required_terms(answer, required_terms):
    normalized_answer = normalize(answer)

    missing_terms = [
        term
        for term in required_terms
        if normalize(term) not in normalized_answer
    ]

    return not missing_terms, missing_terms



def check_citations(citations, expected_sources):
    """Validate citations and print why validation fails."""

    if not citations:
        print("CITATION DEBUG: No citations returned.")
        return False

    if not expected_sources:
        print("CITATION DEBUG: No expected sources configured.")
        return False

    for citation in citations:
        document = citation.get("document")
        page = citation.get("page")
        quote = citation.get("quote", "").strip()

        matching_source = any(
            document == expected["document"]
            and page in expected["pages"]
            for expected in expected_sources
        )

        if not quote:
            print(
                f"CITATION DEBUG: Empty quote: "
                f"{document}, page {page}"
            )
            return False

        if not matching_source:
            print(
                f"CITATION DEBUG: Unexpected citation: "
                f"document={document}, page={page}"
            )
            print(f"Expected sources: {expected_sources}")
            return False

    return True



def evaluate_conversation_case(service, tender_id, test):
    """Evaluate a follow-up question using its prior conversation."""
    history = test.get("history", [])

    result = service.answer(
        tender_id=tender_id,
        question=test["question"],
        conversation_history=history,
    )

    answer = result.get("answer", "")
    citations = result.get("citations", [])
    expected_insufficient = test.get(
        "expected_insufficient_evidence", False
    )

    answer_pass, missing_terms = check_required_terms(
        answer,
        test.get("required_terms", []),
    )

    if expected_insufficient:
        citation_pass = len(citations) == 0
    else:
        citation_pass = check_citations(
            citations,
            test.get("expected_sources", []),
        )

    insufficient_pass = (
        result.get("insufficient_evidence", False)
        == expected_insufficient
    )

    return {
        "question": test["question"],
        "expected_answer": test.get("expected_answer", ""),
        "actual_answer": answer,
        "answer_pass": answer_pass,
        "missing_terms": "; ".join(missing_terms),
        "citation_pass": citation_pass,
        "insufficient_evidence": result.get(
            "insufficient_evidence", False
        ),
        "insufficient_evidence_pass": insufficient_pass,
        "overall_pass": (
            answer_pass and citation_pass and insufficient_pass
        ),
        "citations": json.dumps(citations, ensure_ascii=False),
        "error": "",
        "test_type": "conversation",
        "test_name": test.get("name", ""),
    }


class Command(BaseCommand):
    help = "Evaluate Raynder's tender RAG pipeline."

    def add_arguments(self, parser):
        parser.add_argument("--tender-id", default="220926-8218")
        parser.add_argument("--dataset", default=None)
        parser.add_argument("--output", default=None)
        parser.add_argument("--conversation-dataset",default=None,)

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)

        dataset_path = Path(
            options["dataset"]
            or base_dir / "ai" / "evaluation" / "tender_qa.json"
        )

        output_path = Path(
            options["output"]
            or base_dir / "ai" / "evaluation" / "rag_results.csv"
        )

        with dataset_path.open("r", encoding="utf-8") as file:
            test_cases = json.load(file)

        service = AnswerGenerationService()
        rows = []

        for index, test in enumerate(test_cases, start=1):
            self.stdout.write(
                f"[{index}/{len(test_cases)}] {test['question']}"
            )

            try:
                result = service.answer(
                    tender_id=options["tender_id"],
                    question=test["question"],
                )

                answer = result.get("answer", "")
                citations = result.get("citations", [])

                expected_insufficient = test.get(
                    "expected_insufficient_evidence", False
                )

                answer_pass, missing_terms = check_required_terms(
                    answer,
                    test.get("required_terms", []),
                )

                
                if expected_insufficient:
                    # A refusal should not cite passages as evidence
                    # for the missing fact.
                    citation_pass = len(citations) == 0
                else:
                    citation_pass = check_citations(
                        citations,
                        test.get("expected_sources", [])
                    )


                insufficient_evidence_pass = (
                    result.get("insufficient_evidence", False)
                    == expected_insufficient
                )

                overall_pass = (
                    answer_pass
                    and citation_pass
                    and insufficient_evidence_pass
                )

                rows.append({
                    "question": test["question"],
                    "expected_answer": test["expected_answer"],
                    "actual_answer": answer,
                    "answer_pass": answer_pass,
                    "missing_terms": "; ".join(missing_terms),
                    "citation_pass": citation_pass,
                    "insufficient_evidence": result.get(
                        "insufficient_evidence", False
                    ),
                    "insufficient_evidence_pass": (
                        insufficient_evidence_pass
                    ),
                    "overall_pass": overall_pass,
                    "citations": json.dumps(
                        citations, ensure_ascii=False
                    ),
                    "error": "",
                    "test_type": "standalone",
                    "test_name": test.get("name", ""),
                })

                status = "PASS" if overall_pass else "FAIL"
                self.stdout.write(f"  Result: {status}")

                if not overall_pass:
                    self.stdout.write(
                        f"  Answer check: {answer_pass}"
                    )
                    self.stdout.write(
                        f"  Citation check: {citation_pass}"
                    )
                    self.stdout.write(
                        "  Insufficient-evidence check: "
                        f"{insufficient_evidence_pass}"
                    )

            except Exception as exc:
                rows.append({
                    "question": test["question"],
                    "expected_answer": test.get("expected_answer", ""),
                    "actual_answer": "",
                    "answer_pass": False,
                    "missing_terms": "",
                    "citation_pass": False,
                    "insufficient_evidence": "",
                    "insufficient_evidence_pass": False,
                    "overall_pass": False,
                    "citations": "[]",
                    "error": str(exc),
                })

                self.stderr.write(f"  Error: {exc}")
        
        # Optional conversational-memory evaluation
        conversation_dataset_path = Path(
            options["conversation_dataset"]
            or base_dir
            / "ai"
            / "evaluation"
            / "tender_conversation_qa.json"
        )

        if conversation_dataset_path.exists():
            with conversation_dataset_path.open(
                "r", encoding="utf-8"
            ) as file:
                conversation_tests = json.load(file)

            self.stdout.write(
                "\nEvaluating conversational memory..."
            )

            for index, test in enumerate(
                conversation_tests, start=1
            ):
                self.stdout.write(
                    f"[Memory {index}/{len(conversation_tests)}] "
                    f"{test['question']}"
                )

                try:
                    row = evaluate_conversation_case(
                        service,
                        options["tender_id"],
                        test,
                    )
                    rows.append(row)

                    status = (
                        "PASS" if row["overall_pass"] else "FAIL"
                    )
                    self.stdout.write(f"  Result: {status}")

                except Exception as exc:
                    rows.append({
                        "question": test["question"],
                        "expected_answer": test.get(
                            "expected_answer", ""
                        ),
                        "actual_answer": "",
                        "answer_pass": False,
                        "missing_terms": "",
                        "citation_pass": False,
                        "insufficient_evidence": "",
                        "insufficient_evidence_pass": False,
                        "overall_pass": False,
                        "citations": "[]",
                        "error": str(exc),
                        "test_type": "conversation",
                        "test_name": test.get("name", ""),
                    })

                    self.stderr.write(f"  Error: {exc}")
        else:
            self.stdout.write(
                "\nNo conversation dataset found; "
                "skipping memory evaluation."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "question",
            "expected_answer",
            "actual_answer",
            "answer_pass",
            "missing_terms",
            "citation_pass",
            "insufficient_evidence",
            "insufficient_evidence_pass",
            "overall_pass",
            "citations",
            "error",
            "test_type",
            "test_name",
        ]

        with output_path.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        passed = sum(row["overall_pass"] is True for row in rows)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nEvaluation complete: {passed}/{len(rows)} passed."
            )
        )
        self.stdout.write(f"Report saved to: {output_path}")
