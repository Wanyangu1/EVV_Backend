from django.db import models
from django.core.validators import RegexValidator
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
import json
import re

User = get_user_model()

# -----------------------
# EMPLOYEE MODEL (UPDATED WITH DEFAULTS)
# -----------------------
class Employee(models.Model):
    user = models.OneToOneField(
        User, 
        on_delete=models.SET_NULL,  # or CASCADE if you want to delete user when employee is deleted
        null=True,
        blank=True,
        related_name='employee_profile'
    )
    # Basic Information
    employee_id = models.CharField(max_length=50, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    
    # SSN with validation
    ssn = models.CharField(
        max_length=9, 
        unique=True,
        validators=[RegexValidator(r'^\d{9}$', 'SSN must be exactly 9 digits')]
    )
    
    # Personal Information
    date_of_birth = models.DateField(default='2000-01-01')  # Temporary default
    
    # Contact Information
    address_line1 = models.CharField(max_length=255, default='Temporary Address')
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, default="Phoenix")
    state = models.CharField(max_length=2, default="AZ")
    zip_code = models.CharField(
        max_length=10,
        default="85001",
        validators=[RegexValidator(r'^\d{5}(-\d{4})?$', 'Invalid ZIP code format')]
    )
    
    phone_regex = RegexValidator(
        regex=r'^\d{10}$',
        message="Phone number must be 10 digits without spaces or special characters"
    )
    phone = models.CharField(max_length=10, default="0000000000", validators=[phone_regex])
    
    email = models.EmailField(default='temp@example.com')
    
    # Employment Information
    hire_date = models.DateField(default='2024-01-01')  # Temporary default
    position = models.CharField(max_length=100, default='Caregiver')
    department = models.CharField(max_length=100, blank=True, null=True)
    
    PAY_TYPE_CHOICES = [
        ('hourly', 'Hourly'),
        ('salary', 'Salary'),
    ]
    pay_type = models.CharField(max_length=10, choices=PAY_TYPE_CHOICES, default='hourly')
    
    pay_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    EMPLOYMENT_TYPE_CHOICES = [
        ('full-time', 'Full-Time'),
        ('part-time', 'Part-Time'),
        ('contract', 'Contract'),
        ('temporary', 'Temporary'),
    ]
    employment_type = models.CharField(
        max_length=20, 
        choices=EMPLOYMENT_TYPE_CHOICES, 
        default='full-time'
    )
    
    # Emergency Contact
    emergency_contact_name = models.CharField(max_length=200, default='Temp Contact')
    emergency_contact_phone = models.CharField(
        max_length=10, 
        default="0000000000",
        validators=[phone_regex]
    )
    emergency_contact_relation = models.CharField(max_length=100, blank=True, null=True)
    
    # Status and Metadata
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('on_leave', 'On Leave'),
        ('terminated', 'Terminated'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Use timezone.now as callable for default
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # EVV Specific Fields
    evv_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    last_evv_sync = models.DateTimeField(blank=True, null=True)
    evv_status = models.CharField(
        max_length=20,
        choices=[
            ('not_synced', 'Not Synced'),
            ('synced', 'Synced'),
            ('pending', 'Pending'),
            ('error', 'Error'),
        ],
        default='not_synced'
    )

    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['status']),
            models.Index(fields=['evv_status']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_id})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def formatted_phone(self):
        if self.phone and len(self.phone) == 10:
            return f"({self.phone[:3]}) {self.phone[3:6]}-{self.phone[6:]}"
        return self.phone
    
    @property
    def formatted_ssn(self):
        if self.ssn and len(self.ssn) == 9:
            return f"***-**-{self.ssn[5:]}"
        return "***-**-****"
    
    @property
    def is_evv_ready(self):
        """Check if employee has all required fields for EVV submission"""
        required_fields = [
            self.ssn, self.first_name, self.last_name
        ]
        return all(required_fields) and len(self.ssn) == 9

# -----------------------
# CLIENT MODEL (Keep as is)
# -----------------------
class Client(models.Model):
    # Basic Information
    client_id = models.CharField(max_length=50, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    dob = models.DateField()
    
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    ]
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True)

    # Contact Information
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Address Information
    address_line1 = models.CharField(max_length=255, blank=True, null=True)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=2, default="AZ")
    zip_code = models.CharField(max_length=10, blank=True, null=True)
    county = models.CharField(max_length=100, blank=True, null=True)

    # AHCCCS Medicaid ID format A12345678
    medicaid_id = models.CharField(max_length=9, blank=True, null=True)

    # Insurance Information
    PAYOR_CHOICES = [
        ('Medicaid', 'Medicaid'),
        ('Medicare', 'Medicare'),
        ('Private', 'Private Insurance'),
        ('Self Pay', 'Self Pay'),
        ('Other', 'Other'),
    ]
    payor = models.CharField(max_length=20, choices=PAYOR_CHOICES, default='Medicaid')
    insurance_id = models.CharField(max_length=50, blank=True, null=True)

    # Medical Information
    primary_diagnosis = models.CharField(max_length=255, blank=True, null=True)
    secondary_diagnosis = models.CharField(max_length=255, blank=True, null=True)
    physician_name = models.CharField(max_length=255, blank=True, null=True)
    physician_phone = models.CharField(max_length=20, blank=True, null=True)

    # Case Management
    case_manager_name = models.CharField(max_length=255, blank=True, null=True)
    case_manager_phone = models.CharField(max_length=20, blank=True, null=True)

    # Emergency Contact
    emergency_contact_name = models.CharField(max_length=255, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True, null=True)
    emergency_contact_relation = models.CharField(max_length=100, blank=True, null=True)

    # Service Information
    SERVICE_LOCATION_CHOICES = [
        ('home', 'Home'),
        ('facility', 'Facility'),
        ('community', 'Community'),
        ('work', 'Work'),
        ('school', 'School'),
    ]
    service_location = models.CharField(
        max_length=20, 
        choices=SERVICE_LOCATION_CHOICES, 
        default='home'
    )
    
    # GPS Location
    location_latitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6, 
        blank=True, 
        null=True,
        help_text="Latitude coordinate for service location"
    )
    location_longitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6, 
        blank=True, 
        null=True,
        help_text="Longitude coordinate for service location"
    )
    
    service_start_date = models.DateField(blank=True, null=True)
    service_end_date = models.DateField(blank=True, null=True)
    authorized_hours_weekly = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        blank=True, 
        null=True,
        help_text="Authorized service hours per week"
    )

    # Required by AHCCCS EVV — default correct for Arizona
    timezone = models.CharField(max_length=64, default="America/Phoenix")

    # Required value: must be Yes or No
    assent_plan = models.CharField(
        max_length=3,
        choices=[("Yes", "Yes"), ("No", "No")],
        default="Yes"
    )

    # Additional Preferences
    LANGUAGE_CHOICES = [
        ('English', 'English'),
        ('Spanish', 'Spanish'),
        ('Other', 'Other'),
    ]
    language_preference = models.CharField(
        max_length=20, 
        choices=LANGUAGE_CHOICES, 
        default='English'
    )
    mobility_requirements = models.TextField(blank=True, null=True)
    special_instructions = models.TextField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.client_id})"

    class Meta:
        db_table = 'evv_clients'
        verbose_name = 'Client'
        verbose_name_plural = 'Clients'
        ordering = ['last_name', 'first_name']


# -----------------------
# CLIENT ↔ EMPLOYEE RELATIONSHIP (Keep as is)
# -----------------------
# models.py - UPDATED Xref model
from django.db import models
from django.core.validators import RegexValidator
import datetime

class ClientEmployeeXref(models.Model):
    """EVV-compliant Xref model for live-in caregiver relationships"""
    
    # Basic identifiers
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    
    # EVV-required fields
    xref_other_id = models.CharField(
        max_length=50, 
        unique=True,
        help_text="Unique identifier in external system"
    )
    sequence_id = models.IntegerField(
        default=1,
        help_text="Incremented for each update"
    )
    
    # Dates
    start_date = models.DateField(
        default=datetime.date.today,
        help_text="Date when relationship began"
    )
    end_date = models.DateField(
        null=True, blank=True,
        help_text="Date when relationship ended (NULL for ongoing)"
    )
    
    # Payer/Program info
    payer_id = models.CharField(
        max_length=10,
        choices=[
            ('AZACH', 'AZACH'),
            ('AZBUFC', 'AZBUFC'),
            ('AZCCCS', 'AZCCCS'),
            ('AZCDMP', 'AZCDMP'),
            ('AZDDD', 'AZDDD'),
            ('AZMCC', 'AZMCC'),
            ('AZMYC', 'AZMYC'),
            ('AZSHC', 'AZSHC'),
            ('AZUCP', 'AZUCP'),
        ],
        default='AZDDD'
    )
    payer_program = models.CharField(
        max_length=20,
        default='AHCCCS',
        help_text="Must be 'AHCCCS' per spec"
    )
    
    # Procedure/HCPCS code
    procedure_code = models.CharField(
        max_length=10,
        help_text="HCPCS code (see Section 10.10 of spec)"
    )
    
    # Modifiers (optional)
    modifier1 = models.CharField(max_length=2, null=True, blank=True)
    modifier2 = models.CharField(max_length=2, null=True, blank=True)
    modifier3 = models.CharField(max_length=2, null=True, blank=True)
    modifier4 = models.CharField(max_length=2, null=True, blank=True)
    
    # Relationship info
    live_in = models.CharField(
        max_length=10,
        choices=[('Yes', 'Yes'), ('No', 'No')],
        default='No'
    )
    
    # CORRECTED RELATIONSHIP VALUES from spec (Section 10.10 and Xref table)
    relationship = models.CharField(
        max_length=64,
        choices=[
            ('Spouse', 'Spouse'),
            ('Adult children/Stepchildren', 'Adult children/Stepchildren'),
            ('Son-in-law/Daughter-in-law', 'Son-in-law/Daughter-in-law'),
            ('Grandchildren', 'Grandchildren'),
            ('Siblings/Step siblings', 'Siblings/Step siblings'),
            ('Parents/Adoptive Parents/Legal Guardians', 'Parents/Adoptive Parents/Legal Guardians'),
            ('Stepparents', 'Stepparents'),
            ('Grandparents', 'Grandparents'),
            ('Mother-in-law/Father-in-law', 'Mother-in-law/Father-in-law'),
            ('Brother-in-law/Sister-in-law', 'Brother-in-law/Sister-in-law'),
            ('Other', 'Other'),
        ],
        default='Other'
    )
    
    # EVV status
    submitted_to_evv = models.BooleanField(default=False)
    evv_submission_id = models.CharField(max_length=100, null=True, blank=True)
    evv_submission_date = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-generate xref_other_id if not provided
        if not self.xref_other_id:
            self.xref_other_id = f"XREF_{self.client_id}_{self.employee_id}_{int(datetime.datetime.now().timestamp())}"
        
        # Auto-increment sequence for updates
        if self.pk:
            existing = ClientEmployeeXref.objects.get(pk=self.pk)
            if any([
                self.start_date != existing.start_date,
                self.end_date != existing.end_date,
                self.live_in != existing.live_in,
                self.relationship != existing.relationship,
            ]):
                self.sequence_id = existing.sequence_id + 1
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"XREF: {self.client} - {self.employee} ({self.relationship})"
    
    class Meta:
        unique_together = ['client', 'employee']
        verbose_name = "Client-Employee Relationship"
        verbose_name_plural = "Client-Employee Relationships"

# -----------------------
# VISITS (Keep as is)
# -----------------------
class Visit(models.Model):
    # Basic Visit Information
    client = models.ForeignKey('Client', on_delete=models.CASCADE, related_name='visits')
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='visits')
    
    # EVV Identifiers
    visit_other_id = models.CharField(
        max_length=100, 
        unique=True,
        help_text="Unique visit identifier for EVV (generated automatically)"
    )
    sequence_id = models.CharField(
        max_length=16,
        help_text="EVV Sequence ID (YYYYMMDDHHMMSS format)"
    )
    
    # Visit Type
    VISIT_TYPE_CHOICES = [
        ('scheduled', 'Scheduled (No Calls)'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]
    visit_type = models.CharField(
        max_length=20,
        choices=VISIT_TYPE_CHOICES,
        default='scheduled'
    )
    
    # Schedule Information (for both scheduled and completed visits)
    schedule_start_time = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Scheduled start time (UTC)"
    )
    schedule_end_time = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Scheduled end time (UTC)"
    )
    
    # Actual Visit Times (for completed visits)
    actual_start_time = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Actual check-in time (UTC)"
    )
    actual_end_time = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Actual check-out time (UTC)"
    )
    
    # Location Data
    start_latitude = models.DecimalField(
        max_digits=10, 
        decimal_places=7,
        null=True, 
        blank=True,
        help_text="Check-in latitude"
    )
    start_longitude = models.DecimalField(
        max_digits=10, 
        decimal_places=7,
        null=True, 
        blank=True,
        help_text="Check-in longitude"
    )
    end_latitude = models.DecimalField(
        max_digits=10, 
        decimal_places=7,
        null=True, 
        blank=True,
        help_text="Check-out latitude"
    )
    end_longitude = models.DecimalField(
        max_digits=10, 
        decimal_places=7,
        null=True, 
        blank=True,
        help_text="Check-out longitude"
    )
    
    # Location Verification
    location_verified = models.BooleanField(default=False)
    location_distance_miles = models.DecimalField(
        max_digits=6, 
        decimal_places=2,
        null=True, 
        blank=True,
        help_text="Distance from client location in miles"
    )
    
    # EVV Required Fields
    payer_id = models.CharField(
        max_length=10,
        default='AZDDD',
        help_text="EVV Payer ID"
    )
    procedure_code = models.CharField(
        max_length=10,
        default='T1019',
        help_text="EVV procedure code"
    )
    visit_time_zone = models.CharField(
        max_length=50,
        default='US/Arizona',
        help_text="Timezone for visit"
    )
    
    # Client Verification (EVV Required)
    client_verified_times = models.BooleanField(default=False)
    client_verified_tasks = models.BooleanField(default=False)
    client_verified_service = models.BooleanField(default=False)
    client_signature_available = models.BooleanField(default=False)
    client_voice_recording = models.BooleanField(default=False)
    
    # Billable Information
    bill_visit = models.BooleanField(default=True)
    hours_to_bill = models.DecimalField(
        max_digits=10, 
        decimal_places=3,
        default=0.000,
        validators=[MinValueValidator(0)]
    )
    hours_to_pay = models.DecimalField(
        max_digits=10, 
        decimal_places=3,
        default=0.000,
        validators=[MinValueValidator(0)]
    )
    
    # Services and Tasks
    tasks_completed = models.JSONField(
        default=list,
        help_text="List of completed task IDs"
    )
    tasks_refused = models.JSONField(
        default=list,
        help_text="List of refused task IDs"
    )
    
    # Calls Data (EVV Required)
    calls = models.JSONField(
        default=list,
        help_text="EVV call records with timestamps and GPS"
    )
    
    # Visit Changes (EVV Required for adjustments)
    visit_changes = models.JSONField(
        default=list,
        help_text="EVV visit change records"
    )
    
    # Visit Details
    memo = models.TextField(blank=True, help_text="Free text notes about visit")
    contingency_plan = models.CharField(
        max_length=5,
        blank=True,
        help_text="CP01-CP05 or empty"
    )
    
    # EVV Submission Status
    submitted_to_evv = models.BooleanField(default=False)
    evv_submission_id = models.CharField(max_length=100, blank=True)
    evv_submission_date = models.DateTimeField(null=True, blank=True)
    evv_response = models.JSONField(
        null=True, 
        blank=True,
        help_text="Raw response from EVV system"
    )
    evv_errors = models.JSONField(
        default=list,
        help_text="List of EVV submission errors if any"
    )
    
    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'Employee', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='created_visits'
    )
    
    class Meta:
        db_table = 'evv_visits'
        verbose_name = 'EVV Visit'
        verbose_name_plural = 'EVV Visits'
        ordering = ['-schedule_start_time']
        indexes = [
            models.Index(fields=['client', 'schedule_start_time']),
            models.Index(fields=['employee', 'schedule_start_time']),
            models.Index(fields=['visit_type']),
            models.Index(fields=['submitted_to_evv']),
            models.Index(fields=['visit_other_id']),
        ]
    
    def __str__(self):
        return f"Visit {self.visit_other_id}: {self.client} by {self.employee}"
    
    # In your Visit model
    def save(self, *args, **kwargs):
        import time
        from django.db import transaction
        
        # Ensure unique visit_other_id
        if not self.visit_other_id:
            with transaction.atomic():
                # Try to generate a unique ID
                for attempt in range(3):
                    timestamp = int(timezone.now().timestamp() * 1000)  # Use milliseconds
                    self.visit_other_id = f"VISIT{timestamp}"
                    
                    # Check if this ID already exists
                    if self.pk:
                        # For updates, exclude current instance
                        exists = Visit.objects.filter(
                            visit_other_id=self.visit_other_id
                        ).exclude(pk=self.pk).exists()
                    else:
                        # For creates
                        exists = Visit.objects.filter(visit_other_id=self.visit_other_id).exists()
                    
                    if not exists:
                        break
                    
                    # Wait a bit and try again with different timestamp
                    if attempt < 2:
                        time.sleep(0.001)  # 1ms delay
        
        # Generate sequence_id if not provided
        if not self.sequence_id:
            self.sequence_id = timezone.now().strftime("%Y%m%d%H%M%S")
        
        super().save(*args, **kwargs)
        
    @property
    def duration_hours(self):
        """Calculate actual duration in hours"""
        if self.actual_start_time and self.actual_end_time:
            duration = self.actual_end_time - self.actual_start_time
            return round(duration.total_seconds() / 3600, 3)
        return 0.0
    
    @property
    def is_scheduled(self):
        """Check if visit is scheduled (no calls yet)"""
        return self.visit_type == 'scheduled'
    
    @property
    def is_active(self):
        """Check if visit is currently in progress"""
        return self.visit_type == 'in_progress'
    
    @property
    def is_completed(self):
        """Check if visit is completed"""
        return self.visit_type == 'completed'
    
    @property
    def can_submit_to_evv(self):
        """Check if visit can be submitted to EVV"""
        if self.is_completed:
            # For completed visits, need calls and proper data
            return (len(self.calls) >= 2 and 
                    self.actual_start_time and 
                    self.actual_end_time and 
                    not self.submitted_to_evv)
        elif self.is_scheduled:
            # For schedules, just need basic info
            return (self.schedule_start_time and 
                    self.schedule_end_time and 
                    not self.submitted_to_evv)
        return False
    
    def add_call(self, call_type, assignment, latitude=None, longitude=None):
        """Add a call record to the visit"""
        call_data = {
            'call_external_id': f"CALL{int(timezone.now().timestamp())}",
            'call_date_time': timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            'call_assignment': assignment,  # 'Time In' or 'Time Out'
            'call_type': call_type,  # 'Mobile', 'Telephony', etc.
            'procedure_code': self.procedure_code,
            'client_identifier_on_call': self.client.medicaid_id,
            'mobile_login': self.employee.email if hasattr(self.employee, 'email') else '',
            'call_latitude': float(latitude) if latitude else None,
            'call_longitude': float(longitude) if longitude else None,
            'location': self.client.address_line1 if hasattr(self.client, 'address_line1') else '',
            'visit_location_type': '1'  # 1=Home, 2=Community
        }
        
        if not self.calls:
            self.calls = []
        
        self.calls.append(call_data)
        
        # Update visit type based on calls
        if assignment == 'Time In':
            self.actual_start_time = timezone.now()
            self.start_latitude = latitude
            self.start_longitude = longitude
            self.visit_type = 'in_progress'
        elif assignment == 'Time Out':
            self.actual_end_time = timezone.now()
            self.end_latitude = latitude
            self.end_longitude = longitude
            self.visit_type = 'completed'
            self.hours_to_bill = self.duration_hours
            self.hours_to_pay = self.duration_hours
        
        self.save()
    
    def add_visit_change(self, change_made_by, reason_code, memo=''):
        """Add a visit change record (for manual adjustments)"""
        change_data = {
            'sequence_id': timezone.now().strftime("%Y%m%d%H%M%S"),
            'change_made_by': change_made_by,
            'change_date_time': timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            'reason_code': reason_code,
            'change_reason_memo': memo
        }
        
        if not self.visit_changes:
            self.visit_changes = []
        
        self.visit_changes.append(change_data)
        self.save()
    
    def mark_submitted_to_evv(self, submission_id, response_data=None):
        """Mark visit as submitted to EVV"""
        self.submitted_to_evv = True
        self.evv_submission_id = submission_id
        self.evv_submission_date = timezone.now()
        if response_data:
            self.evv_response = response_data
        self.save()
    
    def add_evv_error(self, error_message):
        """Add EVV submission error"""
        error_record = {
            'timestamp': timezone.now().isoformat(),
            'message': error_message
        }
        
        if not self.evv_errors:
            self.evv_errors = []
        
        self.evv_errors.append(error_record)
        self.save()
    
    def validate_for_evv(self):
        """Validate if visit can be submitted to EVV"""
        errors = []
        
        # Common validations
        if not self.visit_other_id:
            errors.append("VisitOtherID is required")
        
        if not self.sequence_id or len(self.sequence_id) != 14:
            errors.append("SequenceID must be 14 digits (YYYYMMDDHHMMSS)")
        
        if not self.client.medicaid_id:
            errors.append("Client Medicaid ID is required")
        elif not re.match(r'^A\d{8}$', str(self.client.medicaid_id)):
            errors.append("Client Medicaid ID must be in format A12345678")
        
        if not self.employee.ssn:
            errors.append("Employee SSN is required")
        elif not re.match(r'^\d{9}$', str(self.employee.ssn)):
            errors.append("Employee SSN must be 9 digits")
        
        # Type-specific validations
        if self.is_scheduled:
            if not self.schedule_start_time or not self.schedule_end_time:
                errors.append("Schedule times are required for scheduled visits")
        
        elif self.is_completed:
            if not self.actual_start_time or not self.actual_end_time:
                errors.append("Actual visit times are required for completed visits")
            
            if len(self.calls) < 2:
                errors.append("At least 2 calls (in and out) are required for completed visits")
            
            if not self.client_verified_times or not self.client_verified_service:
                errors.append("Client verification is required for completed visits")
        
        return errors
# -----------------------
# CLAIM MODEL (Keep as is)
# -----------------------
class Claim(models.Model):
    claim_id = models.CharField(max_length=50, unique=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    service_date = models.DateField()
    service_code = models.CharField(max_length=20)
    billing_code = models.CharField(max_length=20)
    units = models.DecimalField(max_digits=10, decimal_places=2)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Add these required fields for EVV
    payer_id = models.CharField(max_length=20, default="AZDDD", choices=[
        ("AZDDD", "AZDDD"), ("AZCCCS", "AZCCCS"), ("AZACH", "AZACH")
    ])
    payer_program = models.CharField(max_length=20, default="AHCCCS")
    
    # Optional modifiers
    modifier1 = models.CharField(max_length=4, blank=True, null=True)
    modifier2 = models.CharField(max_length=4, blank=True, null=True)
    modifier3 = models.CharField(max_length=4, blank=True, null=True)
    modifier4 = models.CharField(max_length=4, blank=True, null=True)
    
    STATUS_CHOICES = [
        ('Submitted', 'Submitted'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Pending', 'Pending'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Submitted')
    
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Claim {self.claim_id} - {self.client} - {self.service_date}"

    def validate_for_evv(self):
        """Validate if claim can be submitted to EVV"""
        errors = []
        
        if self.status != 'Submitted':
            errors.append("Claim must be in Submitted status")
        
        if not self.service_date:
            errors.append("Service date is required")
        
        if not self.service_code:
            errors.append("Service code is required")
        
        if not self.units or float(self.units) <= 0:
            errors.append("Valid units are required")
        
        if not self.total_amount or float(self.total_amount) <= 0:
            errors.append("Valid total amount is required")
        
        if not self.client.medicaid_id:
            errors.append("Client Medicaid ID is required")
        
        if not self.employee.ssn:
            errors.append("Employee SSN is required")
        
        if not re.match(r'^A\d{8}$', str(self.client.medicaid_id)):
            errors.append("Client Medicaid ID must be in format A12345678")
        
        if not re.match(r'^\d{9}$', str(self.employee.ssn)):
            errors.append("Employee SSN must be 9 digits")
        
        return errors

    def mark_submitted_to_evv(self, submission_id, response_data=None):
        """Mark claim as submitted to EVV"""
        self.status = 'Pending'  # Change to Pending while EVV processes
        self.evv_submission_id = submission_id
        self.evv_submission_date = timezone.now()
        if response_data:
            self.evv_response = response_data
        self.save()

    def mark_evv_processed(self, status="Approved"):
        """Mark claim as fully processed by EVV"""
        self.status = status
        self.evv_processed_date = timezone.now()
        self.save()