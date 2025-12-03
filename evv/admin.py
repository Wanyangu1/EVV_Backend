# admin.py - UPDATED
from django.contrib import admin
from django.utils.html import format_html
from .models import Client, Employee, ClientEmployeeXref, Visit
from django.utils import timezone

# ------------------------------
# CLIENT ADMIN (unchanged)
# ------------------------------
@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        "client_id", 
        "first_name", 
        "last_name", 
        "dob", 
        "medicaid_id", 
        "timezone", 
        "assent_plan"
    )
    search_fields = ("client_id", "first_name", "last_name", "medicaid_id")
    list_filter = ("dob", "timezone", "assent_plan")
    ordering = ("client_id",)


# ------------------------------
# EMPLOYEE ADMIN (unchanged)
# ------------------------------
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "first_name", "last_name", "ssn", "status")
    search_fields = ("employee_id", "first_name", "last_name", "ssn")
    list_filter = ("status", "pay_type", "employment_type")
    ordering = ("employee_id",)


# ------------------------------
# CLIENT ↔ EMPLOYEE XREF ADMIN (unchanged)
# ------------------------------
@admin.register(ClientEmployeeXref)
class ClientEmployeeXrefAdmin(admin.ModelAdmin):
    list_display = ("client", "employee")
    search_fields = (
        "client__client_id", 
        "client__first_name",
        "client__last_name",
        "employee__employee_id",
        "employee__first_name",
        "employee__last_name",
    )
    list_filter = ("client", "employee")


# ------------------------------
# VISIT ADMIN (UPDATED FOR NEW MODEL)
# ------------------------------
@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = (
        "visit_other_id",
        "get_client_name",
        "get_employee_name",
        "visit_type_display",
        "schedule_date",
        "duration_display",
        "get_calls_count",
        "evv_submission_status",
        "created_at_short"
    )
    
    list_filter = (
        "visit_type",
        "payer_id",
        "procedure_code",
        "submitted_to_evv",
        "location_verified",
        ("schedule_start_time", admin.DateFieldListFilter),
        ("created_at", admin.DateFieldListFilter),
    )
    
    search_fields = (
        "visit_other_id",
        "client__first_name",
        "client__last_name",
        "client__medicaid_id",
        "employee__first_name",
        "employee__last_name",
        "employee__ssn",
        "memo",
    )
    
    ordering = ("-schedule_start_time", "-created_at")
    
    readonly_fields = (
        "visit_other_id",
        "sequence_id",
        "created_at",
        "updated_at",
        "duration_hours",
        "is_scheduled",
        "is_active",
        "is_completed",
        "can_submit_to_evv",
        "evv_submission_date",
        "evv_submission_id",
        "formatted_calls",
        "formatted_tasks",
        "formatted_visit_changes",
    )
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'visit_other_id',
                'sequence_id',
                'client',
                'employee',
                'visit_type',
                ('created_at', 'updated_at'),
            )
        }),
        
        ('Schedule Information', {
            'fields': (
                ('schedule_start_time', 'schedule_end_time'),
                ('actual_start_time', 'actual_end_time'),
                'duration_hours',
                'visit_time_zone',
            )
        }),
        
        ('Location Data', {
            'fields': (
                ('start_latitude', 'start_longitude'),
                ('end_latitude', 'end_longitude'),
                'location_verified',
                'location_distance_miles',
            ),
            'classes': ('collapse',)
        }),
        
        ('EVV Configuration', {
            'fields': (
                'payer_id',
                'procedure_code',
                ('bill_visit', 'hours_to_bill', 'hours_to_pay'),
                'contingency_plan',
            )
        }),
        
        ('Client Verification', {
            'fields': (
                ('client_verified_times', 'client_verified_tasks', 'client_verified_service'),
                ('client_signature_available', 'client_voice_recording'),
            ),
            'classes': ('collapse',)
        }),
        
        ('Visit Data', {
            'fields': (
                'memo',
                'formatted_tasks',
                'formatted_calls',
                'formatted_visit_changes',
            ),
            'classes': ('collapse',)
        }),
        
        ('EVV Submission', {
            'fields': (
                'submitted_to_evv',
                'evv_submission_id',
                'evv_submission_date',
                'evv_response',
                'can_submit_to_evv',
            ),
            'classes': ('collapse',)
        }),
        
        ('Audit Information', {
            'fields': ('created_by',),
            'classes': ('collapse',)
        }),
    )
    
    # Custom actions
    actions = ['mark_as_submitted_to_evv', 'reset_evv_submission', 'convert_to_completed']
    
    def mark_as_submitted_to_evv(self, request, queryset):
        """Mark selected visits as submitted to EVV"""
        count = 0
        for visit in queryset:
            if not visit.submitted_to_evv and visit.can_submit_to_evv:
                visit.mark_submitted_to_evv(
                    submission_id=f"ADMIN_{timezone.now().strftime('%Y%m%d%H%M%S')}",
                    response_data={"admin_action": True}
                )
                count += 1
        
        self.message_user(request, f"Marked {count} visits as submitted to EVV.")
    mark_as_submitted_to_evv.short_description = "Mark as submitted to EVV"
    
    def reset_evv_submission(self, request, queryset):
        """Reset EVV submission status for selected visits"""
        count = 0
        for visit in queryset:
            visit.submitted_to_evv = False
            visit.evv_submission_id = ''
            visit.evv_submission_date = None
            visit.evv_response = None
            visit.save()
            count += 1
        
        self.message_user(request, f"Reset EVV submission for {count} visits.")
    reset_evv_submission.short_description = "Reset EVV submission status"
    
    def convert_to_completed(self, request, queryset):
        """Convert scheduled visits to completed (for testing)"""
        count = 0
        for visit in queryset:
            if visit.visit_type == 'scheduled':
                visit.visit_type = 'completed'
                # Add mock call data
                if not visit.calls:
                    visit.calls = [
                        {
                            'call_external_id': f"TEST_IN_{visit.visit_other_id}",
                            'call_date_time': timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                            'call_assignment': 'Time In',
                            'call_type': 'Mobile',
                            'procedure_code': visit.procedure_code,
                            'client_identifier_on_call': str(visit.client.medicaid_id),
                        },
                        {
                            'call_external_id': f"TEST_OUT_{visit.visit_other_id}",
                            'call_date_time': timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                            'call_assignment': 'Time Out',
                            'call_type': 'Mobile',
                            'procedure_code': visit.procedure_code,
                            'client_identifier_on_call': str(visit.client.medicaid_id),
                        }
                    ]
                visit.save()
                count += 1
        
        self.message_user(request, f"Converted {count} scheduled visits to completed.")
    convert_to_completed.short_description = "Convert to completed (test)"
    
    # Custom display methods for list view
    def get_client_name(self, obj):
        return f"{obj.client.first_name} {obj.client.last_name}"
    get_client_name.short_description = 'Client'
    get_client_name.admin_order_field = 'client__last_name'
    
    def get_employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"
    get_employee_name.short_description = 'Employee'
    get_employee_name.admin_order_field = 'employee__last_name'
    
    def visit_type_display(self, obj):
        color_map = {
            'scheduled': 'blue',
            'in_progress': 'orange',
            'completed': 'green',
            'cancelled': 'red',
            'no_show': 'gray',
        }
        color = color_map.get(obj.visit_type, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_visit_type_display()
        )
    visit_type_display.short_description = 'Type'
    
    def schedule_date(self, obj):
        if obj.schedule_start_time:
            return obj.schedule_start_time.strftime("%m/%d %H:%M")
        return "-"
    schedule_date.short_description = 'Schedule'
    
    def duration_display(self, obj):
        if obj.is_completed and obj.duration_hours > 0:
            return f"{obj.duration_hours:.2f}h"
        return "-"
    duration_display.short_description = 'Duration'
    
    def get_calls_count(self, obj):
        if obj.calls and isinstance(obj.calls, list):
            return len(obj.calls)
        return 0
    get_calls_count.short_description = 'Calls'
    
    def evv_submission_status(self, obj):
        if obj.submitted_to_evv:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Submitted</span><br>'
                '<small style="color: gray;">{}</small>',
                obj.evv_submission_date.strftime("%m/%d") if obj.evv_submission_date else ""
            )
        else:
            if obj.can_submit_to_evv:
                return format_html(
                    '<span style="color: orange;">Ready to Submit</span>'
                )
            else:
                return format_html(
                    '<span style="color: gray;">Not Ready</span>'
                )
    evv_submission_status.short_description = 'EVV Status'
    
    def created_at_short(self, obj):
        return obj.created_at.strftime("%m/%d") if obj.created_at else "-"
    created_at_short.short_description = 'Created'
    
    # Custom formatters for readonly fields
    def formatted_calls(self, obj):
        if not obj.calls or not isinstance(obj.calls, list):
            return "No calls recorded"
        
        html = []
        for i, call in enumerate(obj.calls[:5], 1):
            call_time = call.get('call_date_time', 'N/A')
            assignment = call.get('call_assignment', 'Unknown')
            call_type = call.get('call_type', 'Unknown')
            html.append(f"{i}. {assignment} ({call_type}) at {call_time}")
        
        if len(obj.calls) > 5:
            html.append(f"... and {len(obj.calls) - 5} more calls")
        
        return format_html("<br>".join(html))
    formatted_calls.short_description = 'Call Records'
    
    def formatted_tasks(self, obj):
        if not obj.tasks_completed and not obj.tasks_refused:
            return "No tasks recorded"
        
        html = []
        if obj.tasks_completed:
            html.append(f"<strong>Completed:</strong> {', '.join(obj.tasks_completed[:10])}")
            if len(obj.tasks_completed) > 10:
                html[-1] += f" ... ({len(obj.tasks_completed)} total)"
        
        if obj.tasks_refused:
            html.append(f"<strong>Refused:</strong> {', '.join(obj.tasks_refused)}")
        
        return format_html("<br>".join(html))
    formatted_tasks.short_description = 'Tasks'
    
    def formatted_visit_changes(self, obj):
        if not obj.visit_changes or not isinstance(obj.visit_changes, list):
            return "No changes recorded"
        
        html = []
        for i, change in enumerate(obj.visit_changes[:3], 1):
            change_by = change.get('change_made_by', 'Unknown')
            change_time = change.get('change_date_time', 'N/A')
            reason = change.get('reason_code', 'N/A')
            html.append(f"{i}. By {change_by} at {change_time} (Reason: {reason})")
        
        if len(obj.visit_changes) > 3:
            html.append(f"... and {len(obj.visit_changes) - 3} more changes")
        
        return format_html("<br>".join(html))
    formatted_visit_changes.short_description = 'Visit Changes'
    
    # Custom queryset optimization
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related('client', 'employee', 'created_by')
        return queryset