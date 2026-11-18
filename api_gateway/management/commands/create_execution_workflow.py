
from django.core.management.base import BaseCommand
from api_gateway.models import ExecutionWorkflowTemplate


WORKFLOW_DATA = {
    "phases": [
        {
            "code": "TENDER_ONBOARDING",
            "name": "Tender Onboarding & Internal Alignment",
            "sequence": 1,
            "tasks": [
                {
                    "code": "DOWNLOAD_DOCUMENTS",
                    "title": "Download Tender Documents",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": [],
                },
                {
                    "code": "PURCHASE_DOCUMENTS",
                    "title": "Purchase Tender Documents",
                    "department": "BD",
                    "priority": "MEDIUM",
                    "optional": True,
                    "condition": "IF_REQUIRED",
                    "dependencies": ["DOWNLOAD_DOCUMENTS"],
                },
                {
                    "code": "REVIEW_REQUIREMENTS",
                    "title": "Review Tender Requirements",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": ["DOWNLOAD_DOCUMENTS"],
                },
                {
                    "code": "TEAM_ALIGNMENT",
                    "title": "Align BD and Technical Managers",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": ["REVIEW_REQUIREMENTS"],
                },
                {
                    "code": "SHARE_TECHNICAL_DOCUMENTS",
                    "title": "Share Documents with Engineering Team",
                    "department": "Engineering",
                    "priority": "HIGH",
                    "dependencies": ["TEAM_ALIGNMENT"],
                },
                {
                    "code": "SHARE_COMMERCIAL_DOCUMENTS",
                    "title": "Share Documents with BD Team",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": ["TEAM_ALIGNMENT"],
                },
            ],
        },
        {
            "code": "PRE_BID",
            "name": "Pre-Bid & Corrigendum Management",
            "sequence": 2,
            "tasks": [
                {
                    "code": "TECHNICAL_QUERIES",
                    "title": "Prepare Technical Queries",
                    "department": "Engineering",
                    "priority": "HIGH",
                    "dependencies": ["SHARE_TECHNICAL_DOCUMENTS"],
                },
                {
                    "code": "COMMERCIAL_QUERIES",
                    "title": "Prepare Commercial Queries",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": ["SHARE_COMMERCIAL_DOCUMENTS"],
                },
                {
                    "code": "CONTRACTUAL_QUERIES",
                    "title": "Prepare Contractual Queries",
                    "department": "Legal",
                    "priority": "MEDIUM",
                    "optional": True,
                    "condition": "IF_REQUIRED",
                    "dependencies": ["SHARE_COMMERCIAL_DOCUMENTS"],
                },
                {
                    "code": "COMPILE_PRE_BID_QUERIES",
                    "title": "Compile Pre-Bid Queries",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": [
                        "TECHNICAL_QUERIES",
                        "COMMERCIAL_QUERIES",
                        "CONTRACTUAL_QUERIES",
                    ],
                },
                {
                    "code": "SUBMIT_PRE_BID_QUERIES",
                    "title": "Submit Pre-Bid Queries",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": ["COMPILE_PRE_BID_QUERIES"],
                },
                {
                    "code": "ATTEND_PRE_BID_MEETING",
                    "title": "Attend Pre-Bid Meeting",
                    "department": "BD",
                    "priority": "HIGH",
                    "optional": True,
                    "condition": "IF_REQUIRED",
                    "dependencies": ["SUBMIT_PRE_BID_QUERIES"],
                },
                {
                    "code": "UPLOAD_PRE_BID_RESPONSES",
                    "title": "Upload Pre-Bid Responses",
                    "department": "BD",
                    "priority": "MEDIUM",
                    "optional": True,
                    "condition": "IF_AVAILABLE",
                    "dependencies": ["SUBMIT_PRE_BID_QUERIES"],
                },
                {
                    "code": "UPLOAD_CORRIGENDUM",
                    "title": "Upload Corrigendums / Amendments",
                    "department": "BD",
                    "priority": "HIGH",
                    "optional": True,
                    "condition": "IF_AVAILABLE",
                    "dependencies": ["SUBMIT_PRE_BID_QUERIES"],
                },
                {
                    "code": "AI_CORRIGENDUM_REVIEW",
                    "title": "AI Corrigendum Review & Risk Assessment",
                    "department": "BD",
                    "priority": "HIGH",
                    "optional": True,
                    "condition": "IF_AVAILABLE",
                    "dependencies": ["UPLOAD_CORRIGENDUM"],
                },
                {
                    "code": "UPDATE_TENDER_SUMMARY",
                    "title": "Update Tender Summary",
                    "department": "BD",
                    "priority": "MEDIUM",
                    "optional": True,
                    "condition": "IF_AVAILABLE",
                    "dependencies": ["AI_CORRIGENDUM_REVIEW"],
                },
            ],
        },
        {
            "code": "BID_PLANNING",
            "name": "Bid Planning & Department Coordination",
            "sequence": 3,
            "tasks": [
                {
                    "code": "PREPARE_CHECKLIST",
                    "title": "Prepare Bid Checklist",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": [],
                },
                {
                    "code": "COORDINATE_FINANCE",
                    "title": "Coordinate with Finance",
                    "department": "Finance",
                    "priority": "MEDIUM",
                    "dependencies": ["PREPARE_CHECKLIST"],
                },
                {
                    "code": "COORDINATE_PROJECT",
                    "title": "Coordinate with Project Department",
                    "department": "Project",
                    "priority": "MEDIUM",
                    "dependencies": ["PREPARE_CHECKLIST"],
                },
                {
                    "code": "COORDINATE_ENGINEERING",
                    "title": "Coordinate with Engineering",
                    "department": "Engineering",
                    "priority": "HIGH",
                    "dependencies": ["PREPARE_CHECKLIST"],
                },
                {
                    "code": "COORDINATE_LEGAL",
                    "title": "Coordinate with Legal",
                    "department": "Legal",
                    "priority": "MEDIUM",
                    "optional": True,
                    "condition": "IF_REQUIRED",
                    "dependencies": ["PREPARE_CHECKLIST"],
                },
                {
                    "code": "COORDINATE_EXTERNAL_AGENCIES",
                    "title": "Coordinate with External Agencies",
                    "department": "BD",
                    "priority": "MEDIUM",
                    "optional": True,
                    "condition": "IF_REQUIRED",
                    "dependencies": ["PREPARE_CHECKLIST"],
                },
                {
                    "code": "ARRANGE_EMD",
                    "title": "Arrange EMD / Bid Security",
                    "department": "Finance",
                    "priority": "HIGH",
                    "optional": True,
                    "condition": "IF_REQUIRED",
                    "dependencies": ["COORDINATE_FINANCE"],
                },
            ],
        },
        {
            "code": "TECHNICAL_DOCUMENTATION",
            "name": "Technical & Documentation Preparation",
            "sequence": 4,
            "tasks": [
                {
                    "code": "PREPARE_TECHNICAL_PROPOSAL",
                    "title": "Prepare Technical Proposal (SLD, Layout, GTP)",
                    "department": "Engineering",
                    "priority": "CRITICAL",
                    "dependencies": ["COORDINATE_ENGINEERING"],
                },
                {
                    "code": "PREPARE_BID_DOCUMENTATION",
                    "title": "Prepare Bid Documentation & Experience",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": ["PREPARE_CHECKLIST"],
                },
            ],
        },
        {
            "code": "COMMERCIAL_COSTING",
            "name": "Commercial Costing & Pricing",
            "sequence": 5,
            "tasks": [
                {
                    "code": "SCM_COSTING",
                    "title": "Prepare Costing by SCM",
                    "department": "SCM",
                    "priority": "CRITICAL",
                    "dependencies": [],
                },
                {
                    "code": "BD_COSTING",
                    "title": "Prepare Other Commercial Costing",
                    "department": "BD",
                    "priority": "CRITICAL",
                    "dependencies": [],
                },
                {
                    "code": "CONSOLIDATE_COSTING",
                    "title": "Consolidate Commercial Costing",
                    "department": "BD",
                    "priority": "CRITICAL",
                    "dependencies": ["SCM_COSTING", "BD_COSTING"],
                },
            ],
        },
        {
            "code": "PRICING_APPROVAL",
            "name": "Pricing Finalization & Approval",
            "sequence": 6,
            "tasks": [
                {
                    "code": "PREPARE_PRICING_SHEET",
                    "title": "Prepare Final Pricing Sheet",
                    "department": "BD",
                    "priority": "CRITICAL",
                    "dependencies": ["CONSOLIDATE_COSTING"],
                },
                {
                    "code": "HOD_PRICING_REVIEW",
                    "title": "HOD Pricing Review",
                    "department": "Management",
                    "priority": "CRITICAL",
                    "dependencies": ["PREPARE_PRICING_SHEET"],
                },
                {
                    "code": "MANAGEMENT_PRICE_APPROVAL",
                    "title": "Management Approval of Final Price",
                    "department": "Management",
                    "priority": "CRITICAL",
                    "approval_required": True,
                    "dependencies": ["HOD_PRICING_REVIEW"],
                },
            ],
        },
        {
            "code": "BID_SUBMISSION",
            "name": "Bid Compilation & Submission",
            "sequence": 7,
            "tasks": [
                {
                    "code": "COMPILE_BID_DOCUMENTS",
                    "title": "Compile Bid Documents & Price Sheet",
                    "department": "BD",
                    "priority": "CRITICAL",
                    "dependencies": [
                        "PREPARE_TECHNICAL_PROPOSAL",
                        "PREPARE_BID_DOCUMENTATION",
                        "MANAGEMENT_PRICE_APPROVAL",
                    ],
                },
                {
                    "code": "INTERNAL_COMPLIANCE",
                    "title": "Internal Compliance Check",
                    "department": "BD",
                    "priority": "CRITICAL",
                    "dependencies": ["COMPILE_BID_DOCUMENTS"],
                },
                {
                    "code": "RESOLVE_COMPLIANCE_GAPS",
                    "title": "Resolve Compliance Gaps",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": ["INTERNAL_COMPLIANCE"],
                },
                {
                    "code": "SUBMIT_BID",
                    "title": "Submit Bid (Online / Physical)",
                    "department": "BD",
                    "priority": "CRITICAL",
                    "dependencies": ["RESOLVE_COMPLIANCE_GAPS"],
                },
                {
                    "code": "UPLOAD_ACKNOWLEDGEMENT",
                    "title": "Upload Submission Acknowledgement",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": ["SUBMIT_BID"],
                },
            ],
        },
        {
            "code": "POST_SUBMISSION",
            "name": "Post-Submission Evaluation",
            "sequence": 8,
            "tasks": [
                {
                    "code": "BID_OPENING",
                    "title": "Track Bid Opening",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": ["SUBMIT_BID"],
                },
                {
                    "code": "HANDLE_CLARIFICATIONS",
                    "title": "Handle Bid Clarifications",
                    "department": "BD",
                    "priority": "HIGH",
                    "optional": True,
                    "condition": "IF_REQUIRED",
                    "dependencies": ["BID_OPENING"],
                },
                {
                    "code": "REVERSE_AUCTION",
                    "title": "Participate in Reverse Auction",
                    "department": "BD",
                    "priority": "HIGH",
                    "optional": True,
                    "condition": "IF_APPLICABLE",
                    "dependencies": ["BID_OPENING"],
                },
                {
                    "code": "TRACK_LOA",
                    "title": "Track Letter of Award",
                    "department": "BD",
                    "priority": "HIGH",
                    "dependencies": ["BID_OPENING"],
                },
            ],
        },
        {
            "code": "AWARD_HANDOVER",
            "name": "Award & Project Handover",
            "sequence": 9,
            "tasks": [
                {
                    "code": "RECORD_BID_OUTCOME",
                    "title": "Record Final Bid Outcome",
                    "department": "BD",
                    "priority": "CRITICAL",
                    "dependencies": ["TRACK_LOA"],
                },
                {
                    "code": "UPDATE_LOST_RESULT",
                    "title": "Update Lost Result in BD Tracker",
                    "department": "BD",
                    "priority": "HIGH",
                    "optional": True,
                    "condition": "IF_LOST",
                    "dependencies": ["RECORD_BID_OUTCOME"],
                },
                {
                    "code": "ARRANGE_PBG",
                    "title": "Arrange Performance Bank Guarantee",
                    "department": "Finance",
                    "priority": "CRITICAL",
                    "optional": True,
                    "condition": "IF_WON",
                    "dependencies": ["RECORD_BID_OUTCOME"],
                },
                {
                    "code": "SIGN_CONTRACT",
                    "title": "Sign Contract Agreement",
                    "department": "Legal",
                    "priority": "CRITICAL",
                    "optional": True,
                    "condition": "IF_WON",
                    "dependencies": ["ARRANGE_PBG"],
                },
                {
                    "code": "PROJECT_KICKOFF",
                    "title": "Conduct Project Kickoff Meeting",
                    "department": "Project",
                    "priority": "HIGH",
                    "optional": True,
                    "condition": "IF_WON",
                    "dependencies": ["SIGN_CONTRACT"],
                },
                {
                    "code": "PROJECT_HANDOVER",
                    "title": "Handover to Project Team",
                    "department": "Project",
                    "priority": "HIGH",
                    "optional": True,
                    "condition": "IF_WON",
                    "dependencies": ["PROJECT_KICKOFF"],
                },
            ],
        },
    ]
}


class Command(BaseCommand):
    help = "Create the default Raynder tender execution workflow"

    def handle(self, *args, **options):

        template, created = ExecutionWorkflowTemplate.objects.get_or_create(
            name="Raynder Standard Tender Execution",
            version=1,
            defaults={
                "description": (
                    "Standard execution workflow after management GO approval."
                ),
                "workflow_data": WORKFLOW_DATA,
                "is_active": True,
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Workflow template created successfully. ID: {template.id}"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Workflow template already exists. No changes made."
                )
            )
