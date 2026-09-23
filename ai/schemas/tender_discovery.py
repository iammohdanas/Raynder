from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TenderRawData(BaseModel):
    """
    Additional source-specific tender information.

    These fields preserve information that does not belong
    directly in the normalized Tender model.
    """

    model_config = ConfigDict(extra="forbid")

    # Source / procurement identification
    nit_number: Optional[str] = None
    rfs_number: Optional[str] = None
    rfp_number: Optional[str] = None
    bid_number: Optional[str] = None
    notice_number: Optional[str] = None
    package_number: Optional[str] = None

    # Tender classification
    tender_type: Optional[str] = None
    procurement_type: Optional[str] = None
    work_type: Optional[str] = None
    tender_category: Optional[str] = None

    # Project information
    project_name: Optional[str] = None
    project_location: Optional[str] = None
    technology: Optional[str] = None

    # Capacity details
    ac_capacity_mw: Optional[float] = None
    dc_capacity_mw: Optional[float] = None
    bess_capacity_mw: Optional[float] = None
    bess_energy_mwh: Optional[float] = None
    storage_duration_hours: Optional[float] = None

    # Electrical / transmission
    evacuation_voltage_kv: Optional[float] = None
    substation_details: Optional[str] = None
    transmission_details: Optional[str] = None
    power_evacuation_details: Optional[str] = None

    # Commercial information
    document_fee: Optional[float] = None
    estimated_project_cost: Optional[float] = None
    project_investment: Optional[float] = None
    ppa_value: Optional[float] = None
    tariff: Optional[float] = None

    # Schedule
    bid_submission_start: Optional[str] = None
    bid_submission_end: Optional[str] = None
    pre_bid_meeting_date: Optional[str] = None
    pre_bid_meeting_location: Optional[str] = None
    technical_bid_opening_date: Optional[str] = None
    financial_bid_opening_date: Optional[str] = None
    bid_validity_days: Optional[int] = None
    project_completion_period: Optional[str] = None
    commissioning_deadline: Optional[str] = None

    # Eligibility
    minimum_turnover_crore: Optional[float] = None
    minimum_net_worth_crore: Optional[float] = None
    experience_requirement: Optional[str] = None
    technical_qualification: Optional[str] = None
    financial_qualification: Optional[str] = None
    consortium_requirements: Optional[str] = None

    # Contract / security
    performance_security: Optional[str] = None
    payment_terms: Optional[str] = None
    warranty_period: Optional[str] = None
    o_and_m_period: Optional[str] = None

    # Land / connectivity
    land_requirement: Optional[str] = None
    connectivity_requirement: Optional[str] = None

    # Additional source information
    scope_of_work: Optional[str] = None
    corrigendum_information: Optional[str] = None
    amendment_information: Optional[str] = None
    source_page_title: Optional[str] = None
    source_snippet: Optional[str] = None


class TenderEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    value: str
    source_url: Optional[str] = None
    source_type: Optional[str] = None


class DiscoveredTender(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # ---------------------------------------------------------
    # Core identification
    # ---------------------------------------------------------

    source: Optional[str] = None
    source_tender_id: Optional[str] = None
    tender_ref_no: Optional[str] = None
    tcno: Optional[str] = None
    tenderprocid: Optional[str] = None

    # ---------------------------------------------------------
    # Basic information
    # ---------------------------------------------------------

    title: Optional[str] = None
    description: Optional[str] = None

    company_name: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None

    # ---------------------------------------------------------
    # Commercial information
    # ---------------------------------------------------------

    tender_value: Optional[float] = None
    amount_crore: Optional[float] = None
    earnest_money: Optional[float] = None

    # ---------------------------------------------------------
    # Technical information
    # ---------------------------------------------------------

    capacity_mw: Optional[float] = None

    # ---------------------------------------------------------
    # Dates
    # ---------------------------------------------------------

    tender_date: Optional[str] = None
    opening_date: Optional[str] = None
    closing_date: Optional[str] = None

    # ---------------------------------------------------------
    # URLs
    # ---------------------------------------------------------

    description_url: Optional[str] = None
    original_source: Optional[str] = None
    official_tender_url: Optional[str] = None
    tender_document_url: Optional[str] = None

    # ---------------------------------------------------------
    # Status
    # ---------------------------------------------------------

    document_available: Optional[bool] = None
    live_status: Optional[bool] = None
    status_text: Optional[str] = None

    # ---------------------------------------------------------
    # Evidence
    # ---------------------------------------------------------

    evidence: list[TenderEvidence] = Field(
        default_factory=list
    )

    # ---------------------------------------------------------
    # Additional source-specific information
    # ---------------------------------------------------------

    raw_data: TenderRawData = Field(
        default_factory=TenderRawData
    )


class TenderDiscoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenders: list[DiscoveredTender] = Field(
        default_factory=list
    )