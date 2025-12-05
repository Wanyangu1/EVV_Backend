# urls.py - UPDATED
from django.urls import path
from .views import (
    ClientView,
    EmployeeView,
    VisitView,
    VisitDetailView,
    XrefView,
    
    # EVV Upload
    EVVUploadClients,
    EVVUploadEmployees,
    EVVUploadXrefs,
    EVVUploadVisits,
    
    # EVV Send Operations
    SendClientsToEVV,
    SendEmployeesToEVV,
    SendXrefsToEVV,
    SendVisitsToEVV,
    
    # Status and Info
    EVVEntityStatus,
    EVVGetAccountInfo,
    CheckUploadStatus,
    CheckClientStatus,
    
    # NEW: Caregiver Operations
    CaregiverOperationsView,
    # Xref Management
    CreateXrefAndSend,
    UpdateXrefRelationship,
    CreateUserForEmployeeView,
)

urlpatterns = [
    # ------------------------
    # LOCAL CRUD ENDPOINTS
    # ------------------------
    path("clients/", ClientView.as_view(), name="clients"),
    path("employees/", EmployeeView.as_view(), name="employees"),
    path("visits/", VisitView.as_view(), name="visits"),
    path("visits/<int:pk>/", VisitDetailView.as_view(), name="visit-detail"), 
    path("xrefs/", XrefView.as_view(), name="xrefs"),
    path("employees/<int:employee_id>/create-user/", CreateUserForEmployeeView.as_view(), name="create-user-for-employee"),
    
    # ------------------------
    # CAREGIVER MOBILE ENDPOINTS
    # ------------------------
    path("caregiver/operations/", CaregiverOperationsView.as_view(), name="caregiver-operations"),
    
    # ------------------------
    # EVV API ENDPOINTS
    # ------------------------
    path("evv/account/", EVVGetAccountInfo.as_view(), name="evv-account"),   
    path("evv/clients/send/", SendClientsToEVV.as_view(), name="send-clients-to-evv"),
    path("evv/clients/upload/", EVVUploadClients.as_view(), name="evv-upload-clients"),
    path("evv/employees/upload/", EVVUploadEmployees.as_view(), name="evv-upload-employees"),
    path("evv/xrefs/upload/", EVVUploadXrefs.as_view(), name="evv-upload-xrefs"),
    path("evv/visits/upload/", EVVUploadVisits.as_view(), name="evv-upload-visits"),
    path("evv/employees/send/", SendEmployeesToEVV.as_view(), name="send-employees-to-evv"),
    path("evv/visits/send/", SendVisitsToEVV.as_view(), name="send-visits-to-evv"),
    path("evv/xrefs/send/", SendXrefsToEVV.as_view(), name="send-xrefs-to-evv"),
    
    # Status endpoints
    path("evv/status/<str:entity>/", EVVEntityStatus.as_view(), name="evv-status"),
    path("evv/check-upload-status/<str:transaction_id>/", CheckUploadStatus.as_view(), name="check-upload-status"),
    path("evv/check-upload-status/", CheckUploadStatus.as_view(), name="check-upload-status-post"),
    path("evv/clients/status/", CheckClientStatus.as_view(), name="evv-clients-status"),
    
    # Test and connection endpoints
    path('evv/account-info/', EVVGetAccountInfo.as_view(), name='evv-account-info'),
    # Xref management
    path("xrefs/create-and-send/", CreateXrefAndSend.as_view(), name="create-xref-and-send"),
    path("xrefs/update/<str:xref_id>/", UpdateXrefRelationship.as_view(), name="update-xref"),
    path("xrefs/batch-send/", SendXrefsToEVV.as_view(), name="send-xrefs-batch"),
]