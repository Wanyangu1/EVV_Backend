from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Client, Service, VisitLog
from .serializers import ClientSerializer, ServiceSerializer, VisitLogSerializer
from django.shortcuts import get_object_or_404
from django.utils import timezone
from math import radians, cos, sin, asin, sqrt


def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on the Earth (in meters).
    """
    R = 6371000  # Radius of Earth in meters
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon/2)**2
    c = 2 * asin(sqrt(a))
    return R * c


class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return request.user and request.user.is_staff


class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Client.objects.all().order_by('-updated_at')
        return Client.objects.filter(assigned_caregivers=user).order_by('-updated_at')


class ServiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]


class VisitLogViewSet(viewsets.ModelViewSet):
    serializer_class = VisitLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return VisitLog.objects.all().order_by('-created_at')
        return VisitLog.objects.filter(caregiver=user).order_by('-created_at')

    # ------------------------
    # CUSTOM ACTIONS
    # ------------------------

    @action(detail=True, methods=['post'])
    def checkin(self, request, pk=None):
        client = get_object_or_404(Client, pk=pk)
        caregiver = request.user

        lat = float(request.data.get("latitude"))
        lng = float(request.data.get("longitude"))

        # Verify caregiver is assigned to this client
        if not client.assigned_caregivers.filter(id=caregiver.id).exists():
            return Response({"error": "You are not assigned to this client."}, status=403)

        # Location validation (within 100m radius)
        distance = haversine(lat, lng, client.latitude, client.longitude)
        if distance > 100:
            return Response({"error": "Location mismatch. You must be near the client."}, status=400)

        # Create VisitLog
        visit = VisitLog.objects.create(
            client=client,
            caregiver=caregiver,
            check_in_time=timezone.now(),
            check_in_lat=lat,
            check_in_lng=lng,
            status="checked_in"
        )

        return Response({
            "message": "Check-in successful",
            "visit_id": visit.id,
            "timestamp": visit.check_in_time
        }, status=201)

    @action(detail=True, methods=['post'])
    def checkout(self, request, pk=None):
        visit = get_object_or_404(VisitLog, pk=pk)
        caregiver = request.user

        if visit.caregiver != caregiver:
            return Response({"error": "You are not authorized for this visit."}, status=403)

        if visit.status != "checked_in":
            return Response({"error": "Visit already checked out or invalid state."}, status=400)

        lat = float(request.data.get("latitude"))
        lng = float(request.data.get("longitude"))

        # Location validation again
        distance = haversine(lat, lng, visit.client.latitude, visit.client.longitude)
        if distance > 100:
            return Response({"error": "Location mismatch. You must be near the client."}, status=400)

        # Collect additional info
        services = request.data.get("services", [])  # list of service IDs
        notes = request.data.get("visit_notes", "")
        caregiver_signature = request.data.get("caregiver_signature")
        client_signature = request.data.get("client_signature")

        # Update visit log
        visit.check_out_time = timezone.now()
        visit.check_out_lat = lat
        visit.check_out_lng = lng
        visit.visit_notes = notes
        visit.caregiver_signature = caregiver_signature
        visit.client_signature = client_signature
        visit.status = "completed"

        # Attach services
        if services:
            visit.services.set(Service.objects.filter(id__in=services))

        # Calculate hours worked
        duration = visit.check_out_time - visit.check_in_time
        visit.hours_worked = round(duration.total_seconds() / 3600, 2)
        visit.save()

        return Response({
            "message": "Check-out successful",
            "visit_id": visit.id,
            "hours_worked": visit.hours_worked,
            "services": [s.name for s in visit.services.all()]
        }, status=200)
