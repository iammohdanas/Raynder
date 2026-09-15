from rest_framework import serializers

from api_gateway.models import Tender, TenderDocument


class TenderSerializer(serializers.ModelSerializer):

    class Meta:
        model = Tender
        fields = "__all__"

class TenderDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenderDocument
        fields = [
            "id",
            "file",
            "original_filename",
            "uploaded_at",
        ]
        read_only_fields = [
            "id",
            "original_filename",
            "uploaded_at",
        ]

