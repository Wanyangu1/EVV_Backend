from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import date
import pytz
import ipaddress
from .models import TimeRecord
from .serializers import TimeRecordSerializer

# Set timezone
ARIZONA_TZ = pytz.timezone('US/Arizona')

# Allowed IPs
ALLOWED_IPS = ['*']


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR', '')
    return ip.strip()


def is_allowed_ip(request):
    ip = get_client_ip(request)
    return ip in ALLOWED_IPS or '*' in ALLOWED_IPS


class CheckInView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_allowed_ip(request):
            return Response({'error': 'Check-in is only allowed from authorized IP.'}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now().astimezone(ARIZONA_TZ)
        today = now.date()

        if TimeRecord.objects.filter(user=request.user, date=today).exists():
            return Response({'error': 'You have already checked in today'}, status=status.HTTP_400_BAD_REQUEST)

        time_record = TimeRecord(user=request.user, date=today, check_in=now)
        time_record.full_clean()
        time_record.save()
        serializer = TimeRecordSerializer(time_record)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CheckOutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_allowed_ip(request):
            return Response({'error': 'Check-out is only allowed from authorized IP.'}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now().astimezone(ARIZONA_TZ)
        today = now.date()

        try:
            record = TimeRecord.objects.get(user=request.user, date=today, check_out__isnull=True)
            record.check_out = now
            record.save()
            serializer = TimeRecordSerializer(record)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except TimeRecord.DoesNotExist:
            return Response({'error': 'No active check-in found for today or already checked out'}, status=status.HTTP_400_BAD_REQUEST)


class TimeHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        records = TimeRecord.objects.filter(user=request.user).order_by('-date', '-check_in')
        serializer = TimeRecordSerializer(records, many=True)
        return Response(serializer.data)


class TodayStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().astimezone(ARIZONA_TZ).date()
        try:
            record = TimeRecord.objects.get(user=request.user, date=today)
            serializer = TimeRecordSerializer(record)
            return Response(serializer.data)
        except TimeRecord.DoesNotExist:
            return Response({'status': 'Not checked in today'})
