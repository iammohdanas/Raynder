from datetime import date
import os
import random
from django.db import models

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