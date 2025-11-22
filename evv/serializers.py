from rest_framework import serializers
from drf_extra_fields.fields import Base64ImageField
from .models import Client, Service, VisitLog, Assignment
from django.contrib.auth import get_user_model
from django.utils import timezone

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
    class Meta:
        model = VisitLog
        fields = "__all__"


class CheckInSerializer(serializers.ModelSerializer):
    """Used when creating a check-in. Accepts services as list of IDs (optional)."""
    services = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True)
    check_in = serializers.DateTimeField(source='check_in_time', required=False)
    start_lat = serializers.DecimalField(source='check_in_lat', max_digits=9, decimal_places=6, required=False)
    start_lng = serializers.DecimalField(source='check_in_lng', max_digits=9, decimal_places=6, required=False)

    class Meta:
        model = VisitLog
        fields = ['client', 'check_in', 'start_lat', 'start_lng', 'services']

    def validate_client(self, value):
        # ensure client exists (ModelSerializer ensures that) and caregiver assignment will be checked in view
        return value

    def create(self, validated_data):
        services_ids = validated_data.pop('services', [])
        caregiver = self.context['request'].user

        # Map renamed fields back to model fields are already set by source mapping
        visit = VisitLog.objects.create(
            client=validated_data.get('client'),
            caregiver=caregiver,
            check_in_time=validated_data.get('check_in_time') or timezone.now(),
            check_in_lat=validated_data.get('check_in_lat'),
            check_in_lng=validated_data.get('check_in_lng'),
            status='checked_in'
        )
        if services_ids:
            visit.services.set(Service.objects.filter(id__in=services_ids))
        return visit


class CheckOutSerializer(serializers.ModelSerializer):
    """
    Used to checkout — accepts service ids list as `services_offered` and base64 signatures.
    Supports both array [1,2,3] and comma-separated string "1,2,3".
    """
    services_offered = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True
    )
    check_out = serializers.DateTimeField(source='check_out_time', required=False)
    caregiver_signature = Base64ImageField(required=False, allow_null=True)
    client_signature = Base64ImageField(required=False, allow_null=True)
    notes = serializers.CharField(source='visit_notes', required=False, allow_blank=True)

    class Meta:
        model = VisitLog
        fields = [
            'check_out',
            'caregiver_signature',
            'client_signature',
            'notes',
            'services_offered',
        ]

    def to_internal_value(self, data):
        """
        Make `services_offered` flexible: accept list or comma-separated string.
        """
        services = data.get("services_offered")
        if isinstance(services, str):
            try:
                data["services_offered"] = [
                    int(x.strip()) for x in services.split(",") if x.strip().isdigit()
                ]
            except Exception:
                raise serializers.ValidationError({
                    "services_offered": ["Invalid format. Must be a list or comma-separated string of IDs."]
                })
        return super().to_internal_value(data)

    def update(self, instance, validated_data):
        services_ids = validated_data.pop('services_offered', [])
        
        # mapped fields (source) already provide keys:
        check_out_time = validated_data.get('check_out_time')
        if check_out_time:
            instance.check_out_time = check_out_time

        # signatures and notes (visit_notes)
        if 'caregiver_signature' in validated_data:
            instance.caregiver_signature = validated_data.get('caregiver_signature')
        if 'client_signature' in validated_data:
            instance.client_signature = validated_data.get('client_signature')
        if 'visit_notes' in validated_data:
            instance.visit_notes = validated_data.get('visit_notes')

        # update services if provided
        if services_ids:
            instance.services.set(Service.objects.filter(id__in=services_ids))

        # mark visit as completed
        instance.status = 'completed'

        # save instance (hours worked computed in model save)
        instance.save()
        return instance