# views.py
import re
import logging
from datetime import date, datetime
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse

import requests
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Client, Employee, Visit, ClientEmployeeXref
from .serializers import (
    ClientSerializer,
    EmployeeSerializer,
    VisitSerializer,
    XrefSerializer,
    EVVVisitSerializer,
    EVVXrefSerializer
)
from .services.evv_service import EVVService

logger = logging.getLogger(__name__)
evv = EVVService()

# Validation regexes
NAME_RE = re.compile(r"^[A-Za-z \-']+$")             
MEDICAID_RE = re.compile(r"^[A-Z][0-9]{8}$")       
# Helpers
def build_test_medicaid_id_from_pk(pk: int) -> str:
    return f"A{str(pk).zfill(8)}"[:9]

def format_date_mmddyyyy(d: date) -> str:
    # Accept either date or datetime; return MM/DD/YYYY
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%m/%d/%Y")

def safe_str(val):
    return (val or "").strip()

def evv_health_check(request):
    return JsonResponse({"status": "ok", "service": "EVV backend running"})

def get_user_employee(user):
    """
    Helper to get employee associated with a user
    Returns employee object or None
    """
    if not user.is_authenticated:
        return None
    
    try:
        return user.employee_profile
    except (AttributeError, Employee.DoesNotExist):
        return None

def filter_visits_by_user(queryset, user):
    """
    Helper to filter visits by user's employee profile
    """
    employee = get_user_employee(user)
    if employee:
        return queryset.filter(employee=employee)
    return queryset.none()

class ClientView(APIView):
    def get(self, request):
        try:
            clients = Client.objects.all()
            serializer = ClientSerializer(clients, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.exception("Error fetching clients")
            return Response({"error": "Failed to fetch clients"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            serializer = ClientSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Error creating client")
            return Response({"error": "Failed to create client"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CheckClientStatus(APIView):
    """Check overall client status in EVV system"""
    
    def get(self, request):
        try:
            result = evv.get_status("clients")
            return Response({
                "entity": "clients",
                "status_result": result
            })
        except Exception as e:
            logger.exception("Error checking client status")
            return Response({
                "error": "Failed to check client status",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

User = get_user_model()

class EmployeeView(generics.ListCreateAPIView):
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Get employees with their user relationships"""
        queryset = Employee.objects.all().select_related('user')
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by role if provided (through user)
        role_filter = self.request.query_params.get('role')
        if role_filter:
            queryset = queryset.filter(user__role=role_filter)
        
        # Filter employees with/without user accounts
        has_user = self.request.query_params.get('has_user')
        if has_user == 'true':
            queryset = queryset.filter(user__isnull=False)
        elif has_user == 'false':
            queryset = queryset.filter(user__isnull=True)
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        """Create employee (user will be created via signal)"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Check if email is already in use by a user
        email = serializer.validated_data.get('email')
        existing_user = User.objects.filter(email=email).first()
        
        if existing_user and not hasattr(existing_user, 'employee_profile'):
            # User exists but isn't linked to an employee
            # We could link them, but for safety we'll return an error
            return Response({
                'error': f'User with email {email} already exists. Please use a different email.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create employee (signal will handle user creation)
        employee = serializer.save()
        
        # Refresh to get the user relationship
        employee.refresh_from_db()
        
        headers = self.get_success_headers(serializer.data)
        return Response(
            EmployeeSerializer(employee).data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )


# Optional: Create a view to manually create users for existing employees
class CreateUserForEmployeeView(generics.GenericAPIView):
    """API endpoint to manually create user for an existing employee"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, employee_id):
        try:
            employee = Employee.objects.get(id=employee_id)
            
            # Check if user already exists
            if employee.user:
                return Response({
                    'error': f'User already exists for employee {employee.full_name}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Import your signal function to create user
            from .signals import create_user_for_employee
            create_user_for_employee(sender=Employee, instance=employee, created=False)
            
            # Refresh employee to get user
            employee.refresh_from_db()
            
            return Response({
                'message': f'User created for employee {employee.full_name}',
                'employee': EmployeeSerializer(employee).data
            }, status=status.HTTP_201_CREATED)
            
        except Employee.DoesNotExist:
            return Response({
                'error': 'Employee not found'
            }, status=status.HTTP_404_NOT_FOUND)

class VisitView(APIView):
    """
    Handle all visit operations:
    - GET: List all visits (filter by type, date, etc.)
    - POST: Create new visit (schedule or completed)
    """
    
    def get(self, request):
        try:
            # Get query parameters for filtering
            visit_type = request.query_params.get('type')
            schedule_only = request.query_params.get('schedule_only', 'false').lower() == 'true'
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            
            # DEBUG: Log the request
            logger.info(f"[VisitView GET] User: {request.user.username} (staff: {request.user.is_staff}), "
                       f"Params: type={visit_type}, schedule_only={schedule_only}, "
                       f"date_from={date_from}, date_to={date_to}")
            
            # Start with all visits - include related data using prefetch_related
            visits = Visit.objects.select_related('client', 'employee').all()
            
            # =============== MODIFIED FILTER LOGIC WITH DEBUGGING ===============
            if request.user.is_authenticated:
                if not request.user.is_staff:  # Only apply filter for non-staff users
                    try:
                        employee = request.user.employee_profile
                        logger.info(f"[VisitView GET] Filtering for employee: {employee.id} - {employee.first_name} {employee.last_name}")
                        
                        # Get total count before filtering
                        total_before = visits.count()
                        
                        # Filter visits to only those assigned to this employee
                        visits = visits.filter(employee=employee)
                        
                        # DEBUG: Log filtering results
                        total_after = visits.count()
                        logger.info(f"[VisitView GET] Filtered from {total_before} to {total_after} visits for employee {employee.id}")
                        
                    except AttributeError as e:
                        logger.warning(f"[VisitView GET] User {request.user.username} has no employee_profile attribute: {str(e)}")
                        visits = visits.none()
                    except Employee.DoesNotExist:
                        logger.warning(f"[VisitView GET] User {request.user.username} has no associated employee")
                        visits = visits.none()
                else:
                    logger.info(f"[VisitView GET] Staff user {request.user.username} sees ALL visits")
            else:
                logger.warning("[VisitView GET] Unauthenticated user access attempt")
                visits = visits.none()
            # =============== END OF MODIFIED FILTER ===============
            
            # Apply existing filters - WITH DEBUGGING
            if visit_type:
                logger.info(f"[VisitView GET] Filtering by visit_type: {visit_type}")
                if ',' in visit_type:
                    types = visit_type.split(',')
                    visits = visits.filter(visit_type__in=types)
                else:
                    visits = visits.filter(visit_type=visit_type)
                logger.info(f"[VisitView GET] After visit_type filter: {visits.count()} visits")
            
            if schedule_only:
                logger.info(f"[VisitView GET] Filtering schedule_only=True")
                visits = visits.filter(visit_type='scheduled')
                logger.info(f"[VisitView GET] After schedule_only filter: {visits.count()} visits")
            
            if date_from:
                logger.info(f"[VisitView GET] Filtering date_from: {date_from}")
                visits = visits.filter(schedule_start_time__date__gte=date_from)
                logger.info(f"[VisitView GET] After date_from filter: {visits.count()} visits")
            
            if date_to:
                logger.info(f"[VisitView GET] Filtering date_to: {date_to}")
                visits = visits.filter(schedule_start_time__date__lte=date_to)
                logger.info(f"[VisitView GET] After date_to filter: {visits.count()} visits")
            
            # Order by schedule time (most recent first)
            visits = visits.order_by('-schedule_start_time')
            
            # DEBUG: Log final results
            final_count = visits.count()
            logger.info(f"[VisitView GET] Final result: {final_count} visits for user {request.user.username}")
            
            if final_count > 0:
                # Log first few visits for debugging
                for i, visit in enumerate(visits[:3]):
                    logger.info(f"[VisitView GET] Visit {i+1}: ID={visit.id}, "
                               f"Type={visit.visit_type}, Employee={visit.employee.id if visit.employee else None}, "
                               f"Start={visit.schedule_start_time}")
            
            # Create a custom response with nested client/employee data
            data = []
            for visit in visits:
                visit_data = VisitSerializer(visit).data
                
                # Add client details
                if visit.client:
                    visit_data['client_details'] = {
                        'id': visit.client.id,
                        'first_name': getattr(visit.client, 'first_name', ''),
                        'last_name': getattr(visit.client, 'last_name', ''),
                        'medicaid_id': getattr(visit.client, 'medicaid_id', ''),
                        'address_line1': getattr(visit.client, 'address_line1', ''),
                        'city': getattr(visit.client, 'city', ''),
                        'state': getattr(visit.client, 'state', ''),
                        'latitude': float(visit.client.latitude) if hasattr(visit.client, 'latitude') and visit.client.latitude else None,
                        'longitude': float(visit.client.longitude) if hasattr(visit.client, 'longitude') and visit.client.longitude else None
                    }
                else:
                    visit_data['client_details'] = None
                
                # Add employee details
                if visit.employee:
                    visit_data['employee_details'] = {
                        'id': visit.employee.id,
                        'first_name': getattr(visit.employee, 'first_name', ''),
                        'last_name': getattr(visit.employee, 'last_name', ''),
                        'ssn': getattr(visit.employee, 'ssn', ''),
                        'email': getattr(visit.employee, 'email', '')
                    }
                else:
                    visit_data['employee_details'] = None
                
                # Add service_date for backward compatibility
                if visit.schedule_start_time:
                    visit_data['service_date'] = visit.schedule_start_time.date()
                elif visit.actual_start_time:
                    visit_data['service_date'] = visit.actual_start_time.date()
                
                data.append(visit_data)
            
            return Response(data)
            
        except Exception as e:
            logger.exception("Error fetching visits")
            return Response({"error": "Failed to fetch visits", "details": str(e)}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            # Check if this is a schedule or completed visit
            visit_type = request.data.get('visit_type', 'scheduled')
            logger.info(f"Creating visit of type: {visit_type}")
            
            serializer = VisitSerializer(data=request.data, context={'request': request})
            
            if serializer.is_valid():
                visit = serializer.save()
                
                # If this is a completed visit with calls, handle them
                if visit_type == 'completed' and 'calls' in request.data:
                    visit.calls = request.data['calls']
                    visit.save()
                
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.exception("Error creating visit")
            return Response({"error": "Failed to create visit", "details": str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VisitDetailView(APIView):
    """
    Handle individual visit operations:
    - GET: Get visit details
    - PATCH: Update visit (e.g., check-in, check-out, add calls)
    - DELETE: Cancel visit
    """
    
    def get_object(self, pk, user):
        """
        Helper method to get visit object with user permission check
        """
        try:
            visit = Visit.objects.get(pk=pk)
            
            # =============== ADD THIS CHECK ===============
            # Check if visit belongs to logged-in user's employee
            if user.is_authenticated:
                try:
                    employee = user.employee_profile
                    if visit.employee != employee:
                        # User doesn't own this visit
                        return None
                except (AttributeError, Employee.DoesNotExist):
                    # User doesn't have an employee profile
                    return None
            # =============== END OF ADDED CHECK ===============
            
            return visit
        except Visit.DoesNotExist:
            return None
    
    def get(self, request, pk):
        try:
            visit = self.get_object(pk, request.user)
            if not visit:
                return Response({"error": "Visit not found or access denied"}, 
                              status=status.HTTP_404_NOT_FOUND)
            
            serializer = VisitSerializer(visit)
            return Response(serializer.data)
        except Exception as e:
            logger.exception(f"Error fetching visit {pk}")
            return Response({"error": "Failed to fetch visit", "details": str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def patch(self, request, pk):
        try:
            visit = self.get_object(pk, request.user)
            if not visit:
                return Response({"error": "Visit not found or access denied"}, 
                              status=status.HTTP_404_NOT_FOUND)
            
            # ACTUALLY INCLUDE THE PATCH LOGIC HERE:
            # Handle check-in
            if 'check_in' in request.data:
                checkin_data = request.data['check_in']
                latitude = checkin_data.get('latitude')
                longitude = checkin_data.get('longitude')
                
                visit.add_call(
                    call_type='Mobile',
                    assignment='Time In',
                    latitude=latitude,
                    longitude=longitude
                )
                
                visit.location_verified = checkin_data.get('location_verified', False)
                visit.location_distance_miles = checkin_data.get('distance_miles')
                
                if 'services_rendered' in checkin_data:
                    visit.tasks_completed = checkin_data['services_rendered']
                
                visit.save()
                
            # Handle check-out
            elif 'check_out' in request.data:
                checkout_data = request.data['check_out']
                latitude = checkout_data.get('latitude')
                longitude = checkout_data.get('longitude')
                
                visit.add_call(
                    call_type='Mobile',
                    assignment='Time Out',
                    latitude=latitude,
                    longitude=longitude
                )
                
                # Update client verification
                if 'client_verified_times' in checkout_data:
                    visit.client_verified_times = checkout_data['client_verified_times']
                if 'client_verified_tasks' in checkout_data:
                    visit.client_verified_tasks = checkout_data['client_verified_tasks']
                if 'client_verified_service' in checkout_data:
                    visit.client_verified_service = checkout_data['client_verified_service']
                if 'client_signature_available' in checkout_data:
                    visit.client_signature_available = checkout_data['client_signature_available']
                
                # Add visit change record for check-out
                visit.add_visit_change(
                    change_made_by=checkout_data.get('changed_by', 'Caregiver App'),
                    reason_code='9',  # 'Other'
                    memo='Visit completed via mobile app'
                )
                
                visit.memo = checkout_data.get('visit_notes', '')
                visit.save()
                
                # Auto-submit to EVV if configured
                if checkout_data.get('auto_submit_to_evv', False):
                    self._submit_visit_to_evv(visit)
            
            # Handle general updates
            else:
                serializer = VisitSerializer(visit, data=request.data, partial=True)
                if serializer.is_valid():
                    serializer.save()
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            # Return updated visit
            serializer = VisitSerializer(visit)
            return Response(serializer.data)
            
        except Exception as e:
            logger.exception(f"Error updating visit {pk}")
            return Response({"error": "Failed to update visit", "details": str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def delete(self, request, pk):
        try:
            visit = self.get_object(pk, request.user)
            if not visit:
                return Response({"error": "Visit not found or access denied"}, 
                              status=status.HTTP_404_NOT_FOUND)
            
            # Don't delete, just mark as cancelled
            if not visit.is_completed:
                visit.visit_type = 'cancelled'
                visit.save()
                return Response({"message": "Visit cancelled successfully"})
            else:
                return Response({"error": "Cannot delete completed visit"}, 
                              status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.exception(f"Error cancelling visit {pk}")
            return Response({"error": "Failed to cancel visit", "details": str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _submit_visit_to_evv(self, visit):
        """Helper to submit individual visit to EVV"""
        try:
            # Convert to EVV format
            evv_serializer = EVVVisitSerializer(visit)
            evv_payload = [evv_serializer.data]
            
            # Send to EVV
            result = evv.upload_visits(evv_payload)
            
            if result.get('status_code') == 200:
                visit.mark_submitted_to_evv(
                    submission_id=result.get('response', {}).get('id'),
                    response_data=result
                )
                return True
            else:
                visit.add_evv_error(f"EVV upload failed: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error submitting visit {visit.id} to EVV: {str(e)}")
            visit.add_evv_error(f"EVV submission error: {str(e)}")
            return False

class EVVUploadClients(APIView):
    """Upload clients to AHCCCS EVV (raw payload forwarder)"""
    def post(self, request):
        try:
            payload = request.data
            # Expect either list or {"Clients": [...]} — EVVService handles both
            logger.info("EVVUploadClients called")
            result = evv.upload_clients(payload)
            return Response(result)
        except Exception as e:
            logger.exception("Error uploading clients to EVV")
            return Response({"error": "Failed to upload clients to EVV", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SendEmployeesToEVV(APIView):
    """
    Debug version to see exact payload being sent
    """

    def post(self, request):
        try:
            employees_qs = Employee.objects.all()[:1]  # Just first employee for testing
            if not employees_qs.exists():
                return Response({"error": "No employees found"}, status=status.HTTP_404_NOT_FOUND)

            payload = []
            emp = employees_qs.first()
            
            first = safe_str(emp.first_name)
            last = safe_str(emp.last_name)
            employee_id = safe_str(getattr(emp, "employee_id", None))

            # Build exact same structure as clients
            record = {
                "ProviderIdentification": {
                    "ProviderQualifier": "MedicaidID",
                    "ProviderID": "211108"
                },
                "EmployeeOtherID": employee_id,
                "SequenceID": 1,
                "EmployeeInformation": {
                    "EmployeeID": employee_id,
                    "EmployeeIdentifier": employee_id,
                    "EmployeeFirstName": first,
                    "EmployeeLastName": last,
                    "EmployeeActiveIndicator": "Yes"
                }
            }

            payload.append(record)

            # Debug: show exact payload
            import json
            debug_payload = json.dumps(payload, indent=2)
            logger.info(f"Employee payload being sent: {debug_payload}")

            # Send to EVV
            result = evv.upload_employees(payload)

            return Response({
                "debug_payload": payload,
                "evv_response": result
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Error in employee debug")
            return Response({"error": "Internal server error", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# views.py - ALTERNATIVE SIMPLIFIED VIEW
class XrefView(APIView):
    def get(self, request):
        try:
            xrefs = ClientEmployeeXref.objects.select_related('client', 'employee').all()
            
            # Format response for frontend
            response_data = []
            for xref in xrefs:
                response_data.append({
                    'id': xref.id,
                    'client_medicaid_id': xref.client.medicaid_id if xref.client else None,
                    'employee_ssn': xref.employee.ssn if xref.employee else None,
                    'xref_other_id': xref.xref_other_id,
                    'start_date': xref.start_date,
                    'end_date': xref.end_date,
                    'payer_id': xref.payer_id,
                    'payer_program': xref.payer_program,
                    'procedure_code': xref.procedure_code,
                    'live_in': xref.live_in,
                    'relationship': xref.relationship,
                    'modifier1': xref.modifier1,
                    'modifier2': xref.modifier2,
                    'modifier3': xref.modifier3,
                    'modifier4': xref.modifier4,
                    'status': 'Active' if not xref.end_date or xref.end_date > timezone.now().date() else 'Inactive',
                    'created_at': xref.created_at,
                    'updated_at': xref.updated_at
                })
            
            return Response(response_data)
            
        except Exception as e:
            logger.exception("Error fetching xrefs")
            return Response({"error": "Failed to fetch xrefs"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            data = request.data.copy()
            
            # Log incoming data
            logger.info(f"Creating xref with data: {data}")
            
            # Validate required fields
            required_fields = ['client_medicaid_id', 'employee_ssn', 'start_date']
            for field in required_fields:
                if not data.get(field):
                    return Response(
                        {"error": f"Missing required field: {field}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Find client
            try:
                client = Client.objects.get(medicaid_id=data['client_medicaid_id'])
            except Client.DoesNotExist:
                return Response(
                    {"error": f"Client with Medicaid ID {data['client_medicaid_id']} not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Find employee
            try:
                employee = Employee.objects.get(ssn=data['employee_ssn'])
            except Employee.DoesNotExist:
                return Response(
                    {"error": f"Employee with SSN {data['employee_ssn']} not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check if exists
            existing_xref = ClientEmployeeXref.objects.filter(
                client=client,
                employee=employee
            ).first()
            
            if existing_xref:
                # Update
                existing_xref.start_date = data.get('start_date', existing_xref.start_date)
                existing_xref.end_date = data.get('end_date', existing_xref.end_date)
                existing_xref.payer_id = data.get('payer_id', existing_xref.payer_id)
                existing_xref.payer_program = data.get('payer_program', 'AHCCCS')
                existing_xref.procedure_code = data.get('procedure_code', existing_xref.procedure_code)
                existing_xref.live_in = data.get('live_in', 'No')
                existing_xref.relationship = data.get('relationship', 'Other')
                existing_xref.modifier1 = data.get('modifier1', existing_xref.modifier1)
                existing_xref.modifier2 = data.get('modifier2', existing_xref.modifier2)
                existing_xref.modifier3 = data.get('modifier3', existing_xref.modifier3)
                existing_xref.modifier4 = data.get('modifier4', existing_xref.modifier4)
                existing_xref.sequence_id += 1
                existing_xref.save()
                
                xref = existing_xref
                message = "Xref updated"
                status_code = status.HTTP_200_OK
            else:
                # Create new
                xref = ClientEmployeeXref.objects.create(
                    client=client,
                    employee=employee,
                    xref_other_id=f"XREF_{client.id}_{employee.id}_{int(timezone.now().timestamp())}",
                    sequence_id=1,
                    start_date=data['start_date'],
                    end_date=data.get('end_date'),
                    payer_id=data.get('payer_id', 'AZDDD'),
                    payer_program=data.get('payer_program', 'AHCCCS'),
                    procedure_code=data.get('procedure_code', 'T1019'),
                    live_in=data.get('live_in', 'No'),
                    relationship=data.get('relationship', 'Other'),
                    modifier1=data.get('modifier1'),
                    modifier2=data.get('modifier2'),
                    modifier3=data.get('modifier3'),
                    modifier4=data.get('modifier4')
                )
                message = "Xref created"
                status_code = status.HTTP_201_CREATED
            
            # Return response
            return Response({
                "message": message,
                "xref": {
                    'id': xref.id,
                    'client_medicaid_id': client.medicaid_id,
                    'employee_ssn': employee.ssn,
                    'xref_other_id': xref.xref_other_id,
                    'start_date': xref.start_date,
                    'end_date': xref.end_date,
                    'payer_id': xref.payer_id,
                    'payer_program': xref.payer_program,
                    'procedure_code': xref.procedure_code,
                    'live_in': xref.live_in,
                    'relationship': xref.relationship,
                    'status': 'Active' if not xref.end_date or xref.end_date > timezone.now().date() else 'Inactive'
                }
            }, status=status_code)
            
        except Exception as e:
            logger.exception(f"Error creating xref: {str(e)}")
            return Response(
                {"error": f"Failed to create xref: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class SendXrefsToEVV(APIView):
    """
    Build EVV-compliant Xref payloads from local ClientEmployeeXref model and send to EVV
    """
    
    def post(self, request):
        try:
            # Get all active xrefs (without end date or end date in future)
            xrefs_qs = ClientEmployeeXref.objects.select_related('client', 'employee').filter(
                end_date__isnull=True
            ) | ClientEmployeeXref.objects.select_related('client', 'employee').filter(
                end_date__gte=date.today()
            )
            
            if not xrefs_qs.exists():
                return Response({"message": "No active client-employee relationships found"}, 
                               status=status.HTTP_200_OK)

            payload = []
            invalid_records = []
            processed_count = 0

            # Provider config from settings
            provider_id = getattr(settings, "EVV_PROVIDER_ID", "211108")  # Default from your example
            provider_qualifier = "MedicaidID"

            # Allowed procedure codes for live-in (from spec Section 10.10)
            allowed_procedure_codes = [
                'S5125', 'T2017', 'T1021', 'S5130', 'T1019', 'S5150', 'S5151'
            ]

            for xref in xrefs_qs:
                errors = []
                
                # Get client and employee data
                client = xref.client
                employee = xref.employee

                # Validate client Medicaid ID format (A + 8 digits)
                client_medicaid = getattr(client, "medicaid_id", "")
                if not client_medicaid or not re.match(r'^A\d{8}$', client_medicaid):
                    errors.append(f"Client {getattr(client, 'client_id', 'Unknown')}: Invalid Medicaid ID format. Must be A followed by 8 digits")
                
                # Validate employee SSN format (9 digits)
                employee_ssn = getattr(employee, "ssn", "")
                if not employee_ssn or not re.match(r'^\d{9}$', employee_ssn):
                    errors.append(f"Employee {getattr(employee, 'employee_id', 'Unknown')}: Invalid SSN format. Must be 9 digits")
                
                # Validate procedure code
                if xref.procedure_code not in allowed_procedure_codes:
                    errors.append(f"Procedure code {xref.procedure_code} not allowed for live-in caregiver. Must be one of: {', '.join(allowed_procedure_codes)}")
                
                # Validate payer program is AHCCCS
                if xref.payer_program != "AHCCCS":
                    errors.append(f"Payer Program must be 'AHCCCS', got '{xref.payer_program}'")
                
                # Validate relationship is from allowed list
                allowed_relationships = [
                    'Spouse', 'Adult children/Stepchildren', 'Son-in-law/Daughter-in-law',
                    'Grandchildren', 'Siblings/Step siblings', 'Parents/Adoptive Parents/Legal Guardians',
                    'Stepparents', 'Grandparents', 'Mother-in-law/Father-in-law',
                    'Brother-in-law/Sister-in-law', 'Other'
                ]
                if xref.relationship not in allowed_relationships:
                    errors.append(f"Relationship '{xref.relationship}' not in allowed list")

                if errors:
                    invalid_records.append({
                        "xref_id": xref.xref_other_id,
                        "client_id": getattr(client, 'client_id', 'Unknown'),
                        "employee_id": getattr(employee, 'employee_id', 'Unknown'),
                        "errors": errors
                    })
                    continue

                # Build the complete EVV Xref record
                record = {
                    "ProviderIdentification": {
                        "ProviderQualifier": provider_qualifier,
                        "ProviderID": str(provider_id)
                    },
                    "ClientIDQualifier": "ClientMedicaidID",
                    "ClientIdentifier": client_medicaid,
                    "EmployeeQualifier": "EmployeeSSN",
                    "EmployeeIdentifier": employee_ssn,
                    "XRefStartDate": xref.start_date.isoformat() if xref.start_date else date.today().isoformat(),
                    "XRefEndDate": xref.end_date.isoformat() if xref.end_date else None,
                    "PayerID": xref.payer_id,
                    "PayerProgram": "AHCCCS",  # REQUIRED per spec
                    "ProcedureCode": xref.procedure_code,
                    "Modifier1": xref.modifier1,
                    "Modifier2": xref.modifier2,
                    "Modifier3": xref.modifier3,
                    "Modifier4": xref.modifier4,
                    "LiveIn": xref.live_in,  # "Yes" or "No" as string
                    "Relationship": xref.relationship
                }

                payload.append(record)
                processed_count += 1

            if not payload:
                return Response({
                    "message": "No valid Xrefs to send",
                    "invalid_records": invalid_records
                }, status=status.HTTP_400_BAD_REQUEST)

            # Send to EVV
            logger.info(f"Sending {len(payload)} Xref records to EVV")
            evv_service = EVVService()
            result = evv_service.upload_xrefs(payload)

            # Update submission status for successful records
            if result.get("status_code") in [200, 201]:
                for xref in xrefs_qs:
                    if not any(err["xref_id"] == xref.xref_other_id for err in invalid_records):
                        xref.submitted_to_evv = True
                        xref.evv_submission_id = result.get("response", {}).get("transactionId")
                        xref.evv_submission_date = datetime.now()
                        xref.save()

            return Response({
                "message": "Xrefs sent to EVV",
                "count_sent": len(payload),
                "invalid_count": len(invalid_records),
                "invalid_records": invalid_records,
                "evv_response": result
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Error sending Xrefs to EVV")
            return Response({
                "error": "Internal server error", 
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CreateXrefAndSend(APIView):
    """Create new Xref and immediately send to EVV"""
    
    def post(self, request):
        try:
            # Validate incoming data
            required_fields = ['client_id', 'employee_id', 'procedure_code']
            for field in required_fields:
                if field not in request.data:
                    return Response({"error": f"Missing required field: {field}"}, 
                                   status=status.HTTP_400_BAD_REQUEST)
            
            # Get client and employee
            try:
                client = Client.objects.get(client_id=request.data['client_id'])
                employee = Employee.objects.get(employee_id=request.data['employee_id'])
            except (Client.DoesNotExist, Employee.DoesNotExist) as e:
                return Response({"error": f"Client or Employee not found: {str(e)}"}, 
                               status=status.HTTP_404_NOT_FOUND)
            
            # Create Xref
            xref_data = {
                'client': client.id,
                'employee': employee.id,
                'payer_id': request.data.get('payer_id', 'AZDDD'),
                'payer_program': 'AHCCCS',
                'procedure_code': request.data['procedure_code'],
                'live_in': request.data.get('live_in', 'No'),
                'relationship': request.data.get('relationship', 'Other'),
                'start_date': request.data.get('start_date', date.today()),
                'end_date': request.data.get('end_date', None),
                'created_by': request.user.id if request.user.is_authenticated else None
            }
            
            serializer = XrefSerializer(data=xref_data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            xref = serializer.save()
            
            # Immediately send to EVV
            evv_xref_serializer = EVVXrefSerializer(xref)
            evv_payload = [evv_xref_serializer.data]
            
            evv_service = EVVService()
            result = evv_service.upload_xrefs(evv_payload)
            
            # Update status
            if result.get("status_code") in [200, 201]:
                xref.submitted_to_evv = True
                xref.evv_submission_id = result.get("response", {}).get("transactionId")
                xref.evv_submission_date = datetime.now()
                xref.save()
            
            return Response({
                "message": "Xref created and sent to EVV",
                "xref": serializer.data,
                "evv_response": result
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.exception("Error creating and sending Xref")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UpdateXrefRelationship(APIView):
    """Update an existing Xref (end date or other changes)"""
    
    def put(self, request, xref_id):
        try:
            xref = ClientEmployeeXref.objects.get(xref_other_id=xref_id)
            
            # Check if we're ending the relationship
            if 'end_date' in request.data:
                xref.end_date = request.data['end_date']
                xref.save()
                
                # Send update to EVV
                evv_xref_serializer = EVVXrefSerializer(xref)
                evv_payload = [evv_xref_serializer.data]
                
                evv_service = EVVService()
                result = evv_service.upload_xrefs(evv_payload)
                
                return Response({
                    "message": "Relationship updated and sent to EVV",
                    "result": result
                })
            
            return Response({"error": "Only end_date updates currently supported"}, 
                           status=status.HTTP_400_BAD_REQUEST)
            
        except ClientEmployeeXref.DoesNotExist:
            return Response({"error": "Xref not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.exception("Error updating Xref")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SendClientsToEVV(APIView):
    """
    Build EVV-compliant client payloads from local Client model, validate,
    and send only valid records to AHCCCS / EVV vendor.
    """

    def post(self, request):
        try:
            clients_qs = Client.objects.all()
            if not clients_qs.exists():
                return Response({"error": "No clients found"}, status=status.HTTP_404_NOT_FOUND)

            payload = []             # list of clients to send
            invalid_records = []     # diagnostics for records we won't send
            seq = 1

            # provider config from settings
            provider_id = getattr(settings, "EVV_PROVIDER_ID", None)
            provider_qualifier = getattr(settings, "EVV_PROVIDER_QUALIFIER", "MedicaidID")
            default_timezone = getattr(settings, "EVV_DEFAULT_TIMEZONE", "America/Phoenix")
            default_assent = getattr(settings, "EVV_DEFAULT_ASSENT", "Yes")

            for c in clients_qs:
                errors = []

                # Safe string values
                first = safe_str(getattr(c, "first_name", None))
                last = safe_str(getattr(c, "last_name", None))
                tz = safe_str(getattr(c, "timezone", None)) or default_timezone
                assent = safe_str(getattr(c, "assent_plan", None)) or default_assent
                medicaid = safe_str(getattr(c, "medicaid_id", None))

                # Validate required fields
                if not first:
                    errors.append("First name is required")
                elif len(first) > 30 or not NAME_RE.match(first):
                    errors.append("First name must be ≤30 chars and contain only letters, spaces, hyphen, apostrophe")

                if not last:
                    errors.append("Last name is required")
                elif len(last) > 30 or not NAME_RE.match(last):
                    errors.append("Last name must be ≤30 chars and contain only letters, spaces, hyphen, apostrophe")

                # DOB
                dob_val = getattr(c, "dob", None)
                try:
                    dob_str = format_date_mmddyyyy(dob_val) if dob_val else None
                except Exception:
                    errors.append("Invalid DOB (must be a date)")

                # Medicaid ID - CRITICAL: Must be uppercase letter + 8 digits
                if medicaid:
                    if not MEDICAID_RE.match(medicaid):
                        errors.append("medicaid_id must be uppercase letter + 8 digits (e.g. A12345678)")
                else:
                    # fallback generator for test use only
                    medicaid = build_test_medicaid_id_from_pk(c.pk)

                # ClientCustomID and ClientQualifier must follow specific format
                client_custom_id = medicaid  # This should be the Medicaid ID format
                client_qualifier = "ClientCustomID"  # Fixed value as per error message
                client_identifier = medicaid  # Should be same as Medicaid ID format

                # Validate field lengths
                if client_custom_id and len(client_custom_id) > 20:
                    errors.append("ClientCustomID must be ≤20 characters")

                # Timezone validation
                if not tz or len(tz) > 64:
                    errors.append("timezone is required and must be ≤64 characters")

                # Assent plan validation
                if assent not in ("Yes", "No"):
                    errors.append("assent_plan must be 'Yes' or 'No'")

                # MissingMedicaidID must be "True" or "False" (capital T/F)
                missing_medicaid = "False" if medicaid else "True"

                # If any validation failed, skip and log
                if errors:
                    invalid_records.append({
                        "client_id": getattr(c, "client_id", None),
                        "pk": c.pk,
                        "errors": errors
                    })
                    continue

                # Build EVV-compliant record - FLAT STRUCTURE
                record = {
                    "ProviderIdentification": {
                        "ProviderQualifier": provider_qualifier,
                        "ProviderID": str(provider_id) if provider_id else None
                    },
                    "ClientOtherID": getattr(c, "client_id", None) or f"CL{str(c.pk).zfill(6)}",
                    "SequenceID": seq,
                    # CRITICAL: These fields must be at root level, not nested
                    "ClientID": getattr(c, "client_id", None) or f"CL{str(c.pk).zfill(6)}",
                    "ClientCustomID": client_custom_id,
                    "ClientQualifier": client_qualifier,  # Must be "ClientCustomID"
                    "ClientFirstName": first,
                    "ClientLastName": last,
                    "ClientMedicaidID": medicaid,
                    "ClientIdentifier": client_identifier,
                    "ClientTimezone": tz,
                    "ProviderAssentContPlan": assent,
                    "MissingMedicaidID": missing_medicaid,  # MUST be "True" or "False"
                    "ClientActiveIndicator": "Yes",
                    # Person information if needed
                    "Person": {
                        "PersonName": {
                            "PersonFirstName": first,
                            "PersonLastName": last
                        },
                        "PersonDateOfBirth": dob_str
                    } if dob_str else None
                }

                # Remove None values to avoid sending null fields
                record = {k: v for k, v in record.items() if v is not None}

                payload.append(record)
                seq += 1

            # if nothing valid to send, return diagnostics
            if not payload:
                return Response({
                    "message": "No valid clients to send",
                    "invalid_records": invalid_records
                }, status=status.HTTP_400_BAD_REQUEST)

            # Send to EVV
            logger.info(f"Sending {len(payload)} client records to EVV")
            result = evv.upload_clients(payload)

            return Response({
                "message": "Clients sent to EVV",
                "count_sent": len(payload),
                "invalid_count": len(invalid_records),
                "invalid_records": invalid_records,
                "evv_response": result
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Error sending clients to EVV")
            return Response({"error": "Internal server error", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# views.py - UPDATED SendVisitsToEVV
class SendVisitsToEVV(APIView):
    """
    Build EVV-compliant visit payloads and send to EVV.
    Supports sending schedules-only or completed visits.
    """
    
    def post(self, request):
        try:
            send_type = request.data.get('send_type', 'completed_visits')  # 'schedules_only' or 'completed_visits'
            visit_ids = request.data.get('visit_ids', [])  # Optional specific IDs
            
            logger.info(f"Sending visits to EVV - Type: {send_type}, IDs: {visit_ids}")
            
            # Query based on type
            if send_type == 'schedules_only':
                visits_qs = Visit.objects.select_related('client', 'employee').filter(
                    visit_type='scheduled',
                    submitted_to_evv=False
                )
                message_prefix = "schedules"
            else:  # completed_visits
                visits_qs = Visit.objects.select_related('client', 'employee').filter(
                    visit_type='completed',
                    submitted_to_evv=False
                )
                message_prefix = "completed visits"
            
            # Filter by specific IDs if provided
            if visit_ids:
                visits_qs = visits_qs.filter(id__in=visit_ids)
            
            if not visits_qs.exists():
                return Response({
                    "message": f"No {message_prefix} found to send to EVV",
                    "count_sent": 0,
                    "invalid_count": 0,
                    "invalid_records": []
                }, status=status.HTTP_200_OK)
            
            # Process visits
            payload = []
            invalid_records = []
            
            for visit in visits_qs:
                # Validate visit
                validation_errors = visit.validate_for_evv()
                
                if validation_errors:
                    invalid_records.append({
                        "visit_id": visit.id,
                        "visit_other_id": visit.visit_other_id,
                        "client_id": visit.client.id,
                        "employee_id": visit.employee.id,
                        "errors": validation_errors
                    })
                    continue
                
                # Convert to EVV format
                evv_serializer = EVVVisitSerializer(visit)
                payload.append(evv_serializer.data)
            
            # Check if we have valid records
            if not payload:
                return Response({
                    "message": f"No valid {message_prefix} to send after validation",
                    "invalid_count": len(invalid_records),
                    "invalid_records": invalid_records
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Send to EVV
            logger.info(f"Sending {len(payload)} {message_prefix} to EVV")
            result = evv.upload_visits(payload)
            
            # Mark visits as submitted if successful
            if result.get('status_code') in [200, 202]:
                submitted_count = 0
                for visit in visits_qs:
                    if any(rec.get('VisitOtherID') == visit.visit_other_id for rec in payload):
                        visit.mark_submitted_to_evv(
                            submission_id=result.get('response', {}).get('id'),
                            response_data=result
                        )
                        submitted_count += 1
                
                response_message = f"{submitted_count} {message_prefix} sent to EVV successfully"
            else:
                response_message = f"Failed to send {message_prefix} to EVV"
            
            return Response({
                "message": response_message,
                "count_sent": len(payload),
                "invalid_count": len(invalid_records),
                "invalid_records": invalid_records,
                "evv_response": result
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.exception("Error sending visits to EVV")
            return Response({
                "error": "Internal server error", 
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class CaregiverOperationsView(APIView):
    """
    Specialized endpoints for caregiver mobile app operations.
    """
    
    def get(self, request):
        """Get today's schedules for logged-in caregiver"""
        try:
            # =============== ENHANCED CHECK ===============
            if not request.user.is_authenticated:
                return Response({"error": "Authentication required"}, 
                              status=status.HTTP_401_UNAUTHORIZED)
            
            # Get employee profile for logged-in user
            try:
                employee = request.user.employee_profile
            except AttributeError:
                return Response({"error": "User is not associated with an employee profile"}, 
                              status=status.HTTP_403_FORBIDDEN)
            # =============== END OF ENHANCED CHECK ===============
            
            today = timezone.now().date()
            
            # Get today's schedules for this caregiver
            visits = Visit.objects.select_related('client').filter(
                employee=employee,  # Already filtered by employee
                schedule_start_time__date=today,
                visit_type='scheduled'
            ).order_by('schedule_start_time')
            
            # Format response for mobile app
            schedules = []
            for visit in visits:
                schedules.append({
                    'id': visit.id,
                    'visit_other_id': visit.visit_other_id,
                    'client': {
                        'id': visit.client.id,
                        'first_name': visit.client.first_name,
                        'last_name': visit.client.last_name,
                        'medicaid_id': visit.client.medicaid_id,
                        'address_line1': visit.client.address_line1,
                        'city': visit.client.city,
                        'state': visit.client.state,
                        'zip_code': visit.client.zip_code,
                        'latitude': visit.client.latitude,
                        'longitude': visit.client.longitude
                    },
                    'schedule_start_time': visit.schedule_start_time,
                    'schedule_end_time': visit.schedule_end_time,
                    'procedure_code': visit.procedure_code,
                    'visit_time_zone': visit.visit_time_zone,
                    'is_active': visit.is_active
                })
            
            return Response({
                'date': today.isoformat(),
                'schedules': schedules,
                'count': len(schedules)
            })
            
        except Exception as e:
            logger.exception("Error fetching caregiver schedules")
            return Response({"error": "Failed to fetch schedules", "details": str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request):
        """Handle check-in or check-out operations"""
        try:
            # =============== ENHANCED CHECK ===============
            if not request.user.is_authenticated:
                return Response({"error": "Authentication required"}, 
                              status=status.HTTP_401_UNAUTHORIZED)
            
            # Get employee profile for logged-in user
            try:
                employee = request.user.employee_profile
            except AttributeError:
                return Response({"error": "User is not associated with an employee profile"}, 
                              status=status.HTTP_403_FORBIDDEN)
            # =============== END OF ENHANCED CHECK ===============
            
            operation = request.data.get('operation')  # 'check_in' or 'check_out'
            visit_id = request.data.get('visit_id')
            latitude = request.data.get('latitude')
            longitude = request.data.get('longitude')
            services = request.data.get('services', [])
            
            if not operation or not visit_id:
                return Response({"error": "Operation and visit_id are required"}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            # Get visit and verify ownership
            try:
                visit = Visit.objects.get(id=visit_id, employee=employee)
            except Visit.DoesNotExist:
                return Response({"error": "Visit not found or access denied"}, 
                              status=status.HTTP_404_NOT_FOUND)
            
            # Rest of the POST method remains the same...
            # [Keep all your existing POST logic here]
            
            if operation == 'check_in':
                # Verify location
                location_verified = self._verify_location(visit, latitude, longitude)
                
                # Add call record
                visit.add_call(
                    call_type='Mobile',
                    assignment='Time In',
                    latitude=latitude,
                    longitude=longitude
                )
                
                # Update services if provided
                if services:
                    visit.tasks_completed = services
                
                # Update location verification status
                visit.location_verified = location_verified
                visit.save()
                
                return Response({
                    'message': 'Successfully checked in',
                    'visit_id': visit.id,
                    'location_verified': location_verified,
                    'check_in_time': visit.actual_start_time
                })
            
            elif operation == 'check_out':
                # Verify location again
                location_verified = self._verify_location(visit, latitude, longitude)
                
                # Add call record
                visit.add_call(
                    call_type='Mobile',
                    assignment='Time Out',
                    latitude=latitude,
                    longitude=longitude
                )
                
                # Get client verification data
                client_verified_times = request.data.get('client_verified_times', False)
                client_verified_tasks = request.data.get('client_verified_tasks', False)
                client_verified_service = request.data.get('client_verified_service', False)
                client_signature_available = request.data.get('client_signature_available', False)
                visit_notes = request.data.get('visit_notes', '')
                
                # Update visit
                visit.client_verified_times = client_verified_times
                visit.client_verified_tasks = client_verified_tasks
                visit.client_verified_service = client_verified_service
                visit.client_signature_available = client_signature_available
                visit.location_verified = location_verified
                visit.memo = visit_notes
                
                # Add visit change record
                visit.add_visit_change(
                    change_made_by='Caregiver Mobile App',
                    reason_code='9',  # 'Other'
                    memo='Visit completed via mobile app with client verification'
                )
                
                visit.save()
                
                # Auto-submit to EVV if configured
                auto_submit = request.data.get('auto_submit_to_evv', True)
                evv_result = None
                if auto_submit:
                    evv_serializer = EVVVisitSerializer(visit)
                    evv_payload = [evv_serializer.data]
                    evv_result = evv.upload_visits(evv_payload)
                    
                    if evv_result.get('status_code') in [200, 202]:
                        visit.mark_submitted_to_evv(
                            submission_id=evv_result.get('response', {}).get('id'),
                            response_data=evv_result
                        )
                
                return Response({
                    'message': 'Successfully checked out',
                    'visit_id': visit.id,
                    'duration_hours': visit.duration_hours,
                    'location_verified': location_verified,
                    'check_out_time': visit.actual_end_time,
                    'submitted_to_evv': auto_submit,
                    'evv_result': evv_result if evv_result else None
                })
            
            else:
                return Response({"error": "Invalid operation"}, 
                              status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.exception("Error in caregiver operation")
            return Response({"error": "Operation failed", "details": str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _verify_location(self, visit, latitude, longitude):
        """Verify caregiver is at client location"""
        try:
            if not latitude or not longitude:
                return False
            
            # Get client location from visit
            client = visit.client
            if not client.latitude or not client.longitude:
                return True  # No client location set, assume OK
            
            # Calculate distance (simplified - use proper haversine in production)
            # This is a simplified calculation
            lat_diff = abs(float(latitude) - float(client.latitude))
            lng_diff = abs(float(longitude) - float(client.longitude))
            distance = (lat_diff + lng_diff) * 69  # Rough miles conversion
            
            # EVV allows up to 1.24 miles (2km) radius
            visit.location_distance_miles = round(distance, 2)
            return distance <= 1.24
            
        except Exception as e:
            logger.error(f"Location verification error: {str(e)}")
            return False
        
class EVVUploadEmployees(APIView):
    """Raw forwarder for employees"""
    def post(self, request):
        try:
            payload = request.data
            logger.info("EVVUploadEmployees called")
            result = evv.upload_employees(payload)
            return Response(result)
        except Exception as e:
            logger.exception("Error uploading employees to EVV")
            return Response({"error": "Failed to upload employees to EVV", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CheckUploadStatus(APIView):
    """Check the status of a previous upload using transaction ID"""
    
    def get(self, request, transaction_id):
        try:
            result = evv.get_upload_status(transaction_id)
            return Response({
                "transaction_id": transaction_id,
                "status_check_result": result
            })
        except Exception as e:
            logger.exception(f"Error checking status for transaction {transaction_id}")
            return Response({
                "error": "Failed to check upload status",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        """Check status from POST data"""
        try:
            transaction_id = request.data.get('transaction_id')
            if not transaction_id:
                return Response({"error": "transaction_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            
            result = evv.get_upload_status(transaction_id)
            return Response({
                "transaction_id": transaction_id,
                "status_check_result": result
            })
        except Exception as e:
            logger.exception(f"Error checking status for transaction {transaction_id}")
            return Response({
                "error": "Failed to check upload status",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EVVUploadXrefs(APIView):
    """Raw forwarder for xrefs"""
    def post(self, request):
        try:
            payload = request.data
            logger.info("EVVUploadXrefs called")
            result = evv.upload_xrefs(payload)
            return Response(result)
        except Exception as e:
            logger.exception("Error uploading xrefs to EVV")
            return Response({"error": "Failed to upload xrefs to EVV", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EVVUploadVisits(APIView):
    """Raw forwarder for visits"""
    def post(self, request):
        try:
            payload = request.data
            logger.info("EVVUploadVisits called")
            result = evv.upload_visits(payload)
            return Response(result)
        except Exception as e:
            logger.exception("Error uploading visits to EVV")
            return Response({"error": "Failed to upload visits to EVV", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EVVEntityStatus(APIView):
    """Check status of clients, visits, employees, claims, etc."""
    def get(self, request, entity):
        try:
            result = evv.get_status(entity)
            return Response(result)
        except Exception as e:
            logger.exception(f"Error getting EVV status for {entity}")
            return Response({"error": f"Failed to get status for {entity}", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EVVGetAccountInfo(APIView):
    """Get account information using current settings"""
    def get(self, request):
        try:
            # reuse EVVService's get_account
            result = evv.get_account()
            return Response(result)
        except Exception as e:
            logger.exception("Failed to get EVV account info")
            return Response({
                "error": "Failed to get account info",
                "details": str(e),
                "required_format": "Account header must be a valid GUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)