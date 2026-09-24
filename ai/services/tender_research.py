from ai.services.tender_discovery import TenderDiscoveryService
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor,as_completed

KEYWORDS = [
    "solar","wind","BESS","Green Hydrogen",
    "33 KV","66 KV","132 KV","110 KV",
    "765 KV","800 KV","220 KV","400 KV",
    "765/400 KV","Substations","Transmission Lines","VRFB"
]

RESEARCH_TRACKS = [
    {
        "name": "central_renewable",
        "organizations": [
            "SECI","MNRE","IREDA","NTPC","NTPC Renewable Energy",
            "NHPC","SJVN","NLC India","THDC India"
        ]
    },
    {
        "name": "transmission_grid",
        "organizations": [
            "POWERGRID","PGCIL","CTUIL","CEA",
            "REC PDCL","state transmission utilities"
        ]
    },
    {
        "name": "state_renewable",
        "organizations": [
            "UPNEDA","RRECL","MEDA","KREDL","GUVNL",
            "RVUNL","MSEDCL","TANGEDCO","KSEB"
        ]
    },
    {
        "name": "private_energy",
        "organizations": [
            "Adani Green Energy","ReNew","JSW Energy",
            "Tata Power","Greenko","Avaada","ACME","AM Green"
        ]
    },
    {
        "name": "industrial_renewable",
        "organizations": [
            "GAIL","IOCL","BPCL","HPCL",
            "ONGC","Coal India","NMDC"
        ]
    }
]

class TenderResearchService:
    def __init__(self):
        self.discovery = TenderDiscoveryService()

    # def research(self, location="India"):
    #     all_tenders = []

    #     for track in RESEARCH_TRACKS:
    #         scope = (
    #             f"Research specifically these organizations: "
    #             f"{', '.join(track['organizations'])}. "
    #             f"Search for tender opportunities matching these Raynder "
    #             f"keywords: {', '.join(KEYWORDS)}. "
    #             "Use multiple targeted web searches across the organizations "
    #             "and keywords. Look for actual tender opportunities and "
    #             "official or reliable source evidence."
    #         )

    #         result = self.discovery.discover(
    #             keywords=KEYWORDS + track["organizations"],
    #             location=location,
    #             research_scope=scope,
    #         )

    #         print(f"[{track['name']}] discovered: {len(result.tenders)}")
    #         all_tenders.extend(result.tenders)

    #     print(f"RAW TOTAL: {len(all_tenders)}")
    #     unique = self._deduplicate(all_tenders)
    #     print(f"UNIQUE AFTER DEDUPLICATION: {len(unique)}")
    #     return unique

    def research(self,location="India"):
        all_tenders=[]

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures=[
                executor.submit(self._research_track,track,location)
                for track in RESEARCH_TRACKS
            ]

            for future in as_completed(futures):
                try:
                    result=future.result()
                    print(f"[AI Track] discovered: {len(result.tenders)}")
                    all_tenders.extend(result.tenders)
                except Exception as e:
                    print(f"[AI Track] failed: {e}")

        print(f"RAW TOTAL: {len(all_tenders)}")

        unique=self._deduplicate(all_tenders)

        print(f"UNIQUE AFTER DEDUPLICATION: {len(unique)}")
        return unique

    def _research_track(self,track,location):
        scope=(
            f"Research specifically these organizations: "
            f"{', '.join(track['organizations'])}. "
            f"Search for tender opportunities matching these Raynder "
            f"keywords: {', '.join(KEYWORDS)}. "
            "Use multiple targeted web searches across the organizations "
            "and keywords. Look for actual tender opportunities and "
            "official or reliable source evidence."
        )

        result=self.discovery.discover(
            keywords=KEYWORDS+track["organizations"],
            location=location,
            research_scope=scope,
        )
        print(f"[{track['name']}] discovered: {len(result.tenders)}")
        return result

    def _deduplicate(self, tenders):
        unique = []
        seen = {}

        for tender in tenders:
            key = self._get_exact_key(tender)

            if key and key in seen:
                self._merge(seen[key], tender)
                continue

            match = self._find_similar(tender, unique)

            if match:
                self._merge(match, tender)
                continue

            unique.append(tender)

            if key:
                seen[key] = tender

        return unique

    def _get_exact_key(self, tender):
        for field in ["source_tender_id","tenderprocid","tcno","tender_ref_no"]:
            value = getattr(tender, field, None)
            if value:
                return f"{field}:{self._normalize(value)}"
        return None

    def _normalize(self, value):
        return " ".join(str(value).lower().strip().split())

    def _normalize_url(self, url):
        if not url:
            return None
        parsed = urlparse(url.lower().strip())
        return f"{parsed.netloc}{parsed.path}".rstrip("/")

    def _find_similar(self, tender, tenders):
        title = self._normalize(tender.title)
        company = self._normalize(tender.company_name)

        for existing in tenders:
            if self._same_url(tender, existing):
                return existing

            if (
                title and company
                and title == self._normalize(existing.title)
                and company == self._normalize(existing.company_name)
            ):
                return existing

        return None

    def _same_url(self, a, b):
        urls_a = {
            self._normalize_url(a.official_tender_url),
            self._normalize_url(a.tender_document_url),
            self._normalize_url(a.description_url),
            self._normalize_url(a.original_source),
        }
        urls_b = {
            self._normalize_url(b.official_tender_url),
            self._normalize_url(b.tender_document_url),
            self._normalize_url(b.description_url),
            self._normalize_url(b.original_source),
        }
        return bool((urls_a & urls_b) - {None})

    def _merge(self, target, source):
        for field in type(target).model_fields:
            old = getattr(target, field, None)
            new = getattr(source, field, None)

            if old is None and new is not None:
                setattr(target, field, new)

        self._merge_raw_data(target, source)
        self._merge_evidence(target, source)

    def _merge_raw_data(self, target, source):
        for field in type(target.raw_data).model_fields:
            old = getattr(target.raw_data, field, None)
            new = getattr(source.raw_data, field, None)

            if old is None and new is not None:
                setattr(target.raw_data, field, new)

    def _merge_evidence(self, target, source):
        existing = {
            (e.field,e.value,e.source_url)
            for e in target.evidence
        }

        for evidence in source.evidence:
            key = (evidence.field,evidence.value,evidence.source_url)

            if key not in existing:
                target.evidence.append(evidence)
                existing.add(key)