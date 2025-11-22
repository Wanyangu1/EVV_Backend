from rest_framework import serializers
from .models import TimeRecord
from django.contrib.auth import get_user_model

User = get_user_model()


class TimeRecordSerializer(serializers.ModelSerializer):
    date = serializers.DateField(format='%m/%d/%Y')
    check_in = serializers.DateTimeField(format='%I:%M %p')
    check_out = serializers.DateTimeField(format='%I:%M %p', required=False, allow_null=True)
    rate_per_hour = serializers.SerializerMethodField()
    biweekly_total_hours = serializers.SerializerMethodField()

    class Meta:
        model = TimeRecord
        fields = [
            'id',
            'user',
            'date',
            'check_in',
            'check_out',
            'hours_worked',
            'rate_per_hour',
            'biweekly_total_hours',
        ]
        read_only_fields = [
            'id',
            'hours_worked',
            'rate_per_hour',
            'biweekly_total_hours',
        ]

    def get_rate_per_hour(self, obj):
        return getattr(obj.user.work_profile, 'rate_per_hour', None)

    def get_biweekly_total_hours(self, obj):
        return getattr(obj.user.work_profile, 'biweekly_total_hours', None)


class UserTimeRecordSerializer(serializers.ModelSerializer):
    time_records = TimeRecordSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'time_records']
