from rest_framework import serializers
from drf_extra_fields.fields import Base64ImageField
from .models import Client, Service, VisitLog, Assignment
from django.contrib.auth import get_user_model

User = get_user_model()


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ['id', 'name', 'description']


class ClientSerializer(serializers.ModelSerializer):
    services_needed = ServiceSerializer(many=True, read_only=True)
    assigned_caregivers = serializers.StringRelatedField(many=True, read_only=True)

    class Meta:
        model = Client
        fields = [
            'id', 'first_name', 'last_name', 'date_of_birth', 'age',
            'phone', 'email', 'socials', 'next_of_kin_name',
            'next_of_kin_phone', 'ssn', 'medical_history',
            'visits_per_week', 'visit_times', 'services_needed',
            'address', 'latitude', 'longitude', 'assigned_caregivers', 'notes'
        ]


class VisitLogSerializer(serializers.ModelSerializer):
    client_signature = Base64ImageField(required=False)
    caregiver_signature = Base64ImageField(required=False)
    services = ServiceSerializer(many=True, read_only=True)

    class Meta:
        model = VisitLog
        read_only_fields = [
            'caregiver', 'hours_worked', 'created_at', 'status',
            'check_in_time', 'check_out_time'
        ]
        fields = [
            'id', 'client', 'caregiver',
            'services', 'check_in_time', 'check_out_time',
            'check_in_lat', 'check_in_lng',
            'check_out_lat', 'check_out_lng',
            'client_signature', 'caregiver_signature',
            'visit_notes', 'hours_worked', 'status', 'created_at'
        ]

    def create(self, validated_data):
        """Attach caregiver automatically from request.user."""
        caregiver = self.context['request'].user
        validated_data['caregiver'] = caregiver
        return super().create(validated_data)
