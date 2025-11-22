from django.contrib import admin
from django.utils.html import format_html
from .models import Client, Service, Assignment, VisitLog


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0
    autocomplete_fields = ('caregiver',)
    show_change_link = True


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        'first_name',
        'last_name',
        'phone',
        'email',
        'visits_per_week',
        'colored_updated_at',
        'assigned_caregivers',
    )
    inlines = [AssignmentInline]
    search_fields = ('first_name', 'last_name', 'phone', 'email')
    list_filter = ('visits_per_week', 'updated_at')
    ordering = ('last_name', 'first_name')
    list_per_page = 20
    date_hierarchy = 'updated_at'

    def colored_updated_at(self, obj):
        """Highlight recent updates."""
        return format_html(
            '<span style="color: {};">{}</span>',
            "green" if obj.updated_at else "red",
            obj.updated_at.strftime("%Y-%m-%d %H:%M"),
        )
    colored_updated_at.short_description = "Last Updated"

    def assigned_caregivers(self, obj):
        """Show caregivers linked to the client."""
        caregivers = obj.assignment_set.select_related("caregiver").all()
        return ", ".join([a.caregiver.username for a in caregivers]) or "—"
    assigned_caregivers.short_description = "Caregivers"


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_description')
    search_fields = ('name',)
    ordering = ('name',)

    def short_description(self, obj):
        """Trim long service descriptions for cleaner view."""
        return (obj.description[:50] + "…") if obj.description and len(obj.description) > 50 else obj.description
    short_description.short_description = "Description"


@admin.register(VisitLog)
class VisitLogAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'client',
        'caregiver',
        'check_in_time',
        'check_out_time',
        'hours_worked',
        'colored_status',
        'created_at',
    )
    list_filter = (
        'status',
        'client',
        'caregiver',
        'created_at',
    )
    search_fields = (
        'client__first_name',
        'client__last_name',
        'caregiver__username',
    )
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    list_per_page = 25

    def colored_status(self, obj):
        """Color-coded status for quick visual distinction."""
        color_map = {
            "Completed": "green",
            "Pending": "orange",
            "Missed": "red",
        }
        return format_html(
            '<b><span style="color: {};">{}</span></b>',
            color_map.get(obj.status, "black"),
            obj.status,
        )
    colored_status.short_description = "Status"
