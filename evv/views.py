from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from math import radians, cos, sin, asin, sqrt

from .models import Client, Service, VisitLog, Assignment
from .serializers import (
    ClientSerializer, ServiceSerializer,
    VisitLogSerializer, CheckInSerializer, CheckOutSerializer
)


def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on Earth (in meters).
    """
    try:
        lat1 = float(lat1); lon1 = float(lon1)
        lat2 = float(lat2); lon2 = float(lon2)
    except (TypeError, ValueError):
        return float('inf')

    R = 6371000  # Radius of Earth in meters
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
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

    # -----------------------------------------
    # CUSTOM ACTIONS
    # -----------------------------------------

    @action(detail=False, methods=['post'])
    def checkin(self, request):
        """
        Allows caregiver to check in within 0.9 miles (≈1450 meters) radius from client's coordinates.
        """
        serializer = CheckInSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        client = get_object_or_404(Client, pk=request.data.get('client'))
        caregiver = request.user

        # Ensure caregiver is assigned to client
        if not client.assigned_caregivers.filter(id=caregiver.id).exists():
            return Response({"error": "You are not assigned to this client."}, status=status.HTTP_403_FORBIDDEN)

        # Validate caregiver location proximity
        start_lat = request.data.get('start_lat')
        start_lng = request.data.get('start_lng')
        if client.latitude and client.longitude and start_lat and start_lng:
            distance = haversine(start_lat, start_lng, client.latitude, client.longitude)
            if distance > 1450:  # 0.9 miles = ~1450 meters
                return Response({
                    "error": "Location mismatch. You must be within 0.9 miles (≈1.45 km) of the client's location."
                }, status=status.HTTP_400_BAD_REQUEST)

        # Create visit log
        visit = serializer.save()
        return Response(VisitLogSerializer(visit).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post', 'patch'])
    def checkout(self, request, pk=None):
        """
        Allows caregiver to check out within 0.9 miles (≈1450 meters) radius from client's coordinates.
        """
        visit = get_object_or_404(VisitLog, pk=pk)
        caregiver = request.user

        if visit.caregiver != caregiver:
            return Response({"error": "You are not authorized for this visit."}, status=status.HTTP_403_FORBIDDEN)

        if visit.status != "checked_in":
            return Response({"error": "Visit already checked out or invalid state."}, status=status.HTTP_400_BAD_REQUEST)

        # Retrieve end coordinates from request
        end_lat = request.data.get('end_lat') or request.data.get('check_out_lat')
        end_lng = request.data.get('end_lng') or request.data.get('check_out_lng')

        # Validate location proximity for checkout
        if visit.client.latitude and visit.client.longitude and end_lat and end_lng:
            distance = haversine(end_lat, end_lng, visit.client.latitude, visit.client.longitude)
            if distance > 1450:  # 0.9 miles
                return Response({
                    "error": "Location mismatch. You must be within 0.9 miles (≈1.45 km) of the client's location."
                }, status=status.HTTP_400_BAD_REQUEST)

        # Validate and update visit via serializer
        ser = CheckOutSerializer(visit, data=request.data, partial=True, context={'request': request})
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        # Update geocoordinates and checkout time
        if end_lat:
            visit.check_out_lat = end_lat
        if end_lng:
            visit.check_out_lng = end_lng

        visit.check_out_time = ser.validated_data.get('check_out_time', timezone.now())
        visit = ser.save()

        return Response({
            "message": "Check-out successful",
            "visit_id": visit.id,
            "hours_worked": visit.hours_worked,
            "services": [s.name for s in visit.services.all()]
        }, status=status.HTTP_200_OK)
