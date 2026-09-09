from rest_framework import serializers

from api_gateway.models import Tender


class TenderSerializer(serializers.ModelSerializer):

    class Meta:
        model = Tender
        fields = "__all__"