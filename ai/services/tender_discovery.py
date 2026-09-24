from pathlib import Path
from openai import OpenAI

from Raynder.settings import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_DEPLOYMENT_NAME,
    BASE_DIR,
)

from ai.schemas.tender_discovery import TenderDiscoveryResult


class TenderDiscoveryService:
    """
    AI-powered tender discovery service.

    Responsibilities:
    - Build the research prompt
    - Perform live web research using Azure OpenAI
    - Extract structured tender information
    - Preserve source-specific information in raw_data

    This service does NOT perform final business validation,
    relevance scoring, or database persistence.
    """

    def __init__(self):
        self.client = OpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            base_url=(
                AZURE_OPENAI_ENDPOINT.rstrip("/")
                + "/openai/v1/"
            ),
        )

        self.model = AZURE_OPENAI_DEPLOYMENT_NAME

        self.prompt_path = (
            Path(BASE_DIR)
            / "ai"
            / "prompts"
            / "tender_discovery.txt"
        )

    def _load_prompt(self) -> str:
        """
        Load the main tender discovery prompt.
        """

        if not self.prompt_path.exists():
            raise FileNotFoundError(
                f"Tender discovery prompt not found: "
                f"{self.prompt_path}"
            )

        return self.prompt_path.read_text(
            encoding="utf-8"
        )

    def _build_input(self, keywords=None, location="India", research_scope=None) -> str:
        """
        Build the runtime research request.

        The reusable research instructions are stored in
        tender_discovery.txt.

        Runtime parameters such as location and keywords
        are appended here.
        """

        prompt = self._load_prompt()

        keyword_text = (
            ", ".join(keywords)
            if keywords
            else (
                "solar, "
                "wind, "
                "renewable energy, "
                "BESS, "
                "power transmission, "
                "substation"
            )
        )
        scope_text = research_scope or "Search broadly across relevant Indian renewable-energy sources."

        return f"""
{prompt}

============================================================
RUNTIME RESEARCH PARAMETERS
============================================================

Target organization:

Rays Power Infra

Research scope:

{scope_text}

Geographic scope:

{location}

Search keywords / areas:

{keyword_text}

============================================================
RUNTIME INSTRUCTIONS
============================================================

Perform live web research.

Use multiple search queries and multiple relevant sources.


Follow the research scope above.

Focus the research on the specified organizations and domain.

Do not fall back to unrelated organizations merely because they have more searchable results.

Discover relevant candidate tenders.

Do not discard candidates merely because information is missing.

Extract only information that can be established from the sources.

Use null when information cannot be established.

Do not fabricate identifiers, values, dates, URLs, or other information.

Preserve additional source-specific information in raw_data.

Prefer authoritative sources whenever available.

Return the structured result using the provided schema.
"""

    def discover(self, keywords=None, location="India", research_scope=None) -> TenderDiscoveryResult:
        """
        Discover tender opportunities using:

        Azure OpenAI
        +
        Responses API
        +
        Web Search
        +
        Structured Pydantic output

        The result is returned without applying business
        relevance or eligibility filters.
        """

        try:
            input_text = self._build_input(
                keywords=keywords,
                location=location,
                research_scope=research_scope,
            )
            response = self.client.responses.parse(
                model=self.model,
                input=input_text,
                tools=[
                    {
                        "type": "web_search",
                    }
                ],
                text_format=TenderDiscoveryResult,
            )

            result = response.output_parsed
            if result is None:
                raise ValueError(
                    "Azure OpenAI returned no structured "
                    "tender discovery result."
                )

            print(
                "\n========== RAW PARSED RESULT =========="
            )

            print(
                result.model_dump_json(
                    indent=2
                )
            )

            print(
                "=======================================\n"
            )

            # -------------------------------------------------
            # 5. Return discovery result
            # -------------------------------------------------

            return result

        except Exception as exc:
            raise RuntimeError(
                f"Tender discovery failed: {str(exc)}"
            ) from exc