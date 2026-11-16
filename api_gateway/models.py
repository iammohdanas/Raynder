from datetime import date
import os
import random
from django.db import models

from django.conf import settings
from api_gateway.utils.utils import tender_document_upload_path


class Tender(models.Model):
    
    tender_id = models.CharField(max_length=20, unique=True, editable=False, null=True, blank=True)
    source=models.CharField(max_length=100)
    source_tender_id = models.CharField(max_length=100)
    tender_ref_no = models.CharField(max_length=255, blank=True, null=True)
    tcno = models.CharField(max_length=100, blank=True, null=True)
    tenderprocid = models.CharField(max_length=100, blank=True, null=True)
    title = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    company_name = models.CharField(max_length=500, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    tender_value = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    earnest_money = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    tender_date = models.DateField(blank=True, null=True)
    opening_date = models.DateField(blank=True, null=True)
    closing_date = models.DateField(blank=True, null=True)
    description_url = models.URLField(blank=True, null=True)
    original_source = models.URLField(blank=True, null=True)
    document_available = models.BooleanField(default=False)
    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ai_summary = models.JSONField(default=dict, blank=True)
    summary_meta = models.JSONField( default=dict, blank=True,)

    

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_tender_id"],
                name="unique_tender_source_id",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.tender_id:
            today = date.today().strftime("%d%m%y")
            while True:
                candidate_id = f"{today}-{random.randint(1000, 9999)}"
                if not Tender.objects.filter(tender_id=candidate_id).exists():
                    self.tender_id = candidate_id
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tender_id} - {self.title or 'Untitled Tender'}"
    
    
class TenderPriority(models.Model):

    tender = models.OneToOneField(
        Tender,
        on_delete=models.CASCADE,
        related_name="priority",
    )

    capacity_mw = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    amount_crore = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )
    def __str__(self):
        return f"{self.tender.tender_id} - {self.tender.title}"



class TenderDocument(models.Model):
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name="documents",)
    file = models.FileField(
        upload_to=tender_document_upload_path
    )
    original_filename = models.CharField(
        max_length=255,
        blank=True,
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.tender.tender_id} - {self.original_filename}"

class DocumentChunk(models.Model):
    document=models.ForeignKey(
        TenderDocument,
        on_delete=models.CASCADE,
        related_name="chunks"
    )
    chunk_index=models.PositiveIntegerField()
    content=models.TextField()
    page_number=models.PositiveIntegerField(null=True,blank=True)
    section=models.CharField(max_length=255,blank=True,null=True)
    metadata=models.JSONField(default=dict,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints=[
            models.UniqueConstraint(
                fields=["document","chunk_index"],
                name="unique_document_chunk"
            )
        ]

class MyTender(models.Model):
    class Status(models.TextChoices):
        GO_APPROVED = "GO_APPROVED", "Go Approved"
        DOCUMENT_REVIEW = "DOCUMENT_REVIEW", "Document Review"
        PRE_BID = "PRE_BID", "Pre-Bid"
        BID_PREPARATION = "BID_PREPARATION", "Bid Preparation"
        PRICING = "PRICING", "Pricing"
        APPROVAL = "APPROVAL", "Approval"
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_EVALUATION = "UNDER_EVALUATION", "Under Evaluation"
        WON = "WON", "Won"
        LOST = "LOST", "Lost"
        CLOSED = "CLOSED", "Closed"

    tender = models.OneToOneField(Tender, on_delete=models.PROTECT, related_name="my_tender")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.GO_APPROVED)
    remarks = models.TextField(blank=True, null=True)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.tender.tender_id} - {self.status}"


class TenderDecision(models.Model):

    class Decision(models.TextChoices):
        GO = "GO", "Go"
        NO_GO = "NO_GO", "No Go"
        HOLD = "HOLD", "Hold"

    tender = models.ForeignKey(Tender,on_delete=models.CASCADE,related_name="decisions")
    decision = models.CharField(max_length=10,choices=Decision.choices)
    remarks = models.TextField(blank=True, null=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-decided_at"]
    def __str__(self):
        return f"{self.tender.tender_id} - {self.decision}"