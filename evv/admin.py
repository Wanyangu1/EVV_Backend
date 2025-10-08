from django.contrib import admin
from .models import Client, Service, Assignment, VisitLog


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0
    autocomplete_fields = ('caregiver',)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        'first_name',
        'last_name',
        'phone',
        'email',
        'visits_per_week',
        'updated_at',
    )
    inlines = [AssignmentInline]
    search_fields = ('first_name', 'last_name', 'phone', 'email')
    list_filter = ('visits_per_week',)
    ordering = ('last_name', 'first_name')


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)


@admin.register(VisitLog)
class VisitLogAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'client',
        'caregiver',
        'check_in_time',
        'check_out_time',
        'hours_worked',
        'status',
        'created_at',
    )
    list_filter = (
        'status',
        'client',
        'caregiver',
    )
    search_fields = (
        'client__first_name',
        'client__last_name',
        'caregiver__username',
    )
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
