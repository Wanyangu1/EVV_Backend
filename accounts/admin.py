from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from accounts.models import User, UserProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Columns displayed in the User list
    list_display = [
        "name",
        "email",
        "phone",
        "role",  # Added role to list display
        "is_staff",
        "is_superuser",
        "is_active",
    ]

    list_filter = [
        "role",  # Added role to filters
        "is_staff",
        "is_superuser",
        "is_active",
    ]

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('name', 'phone', 'role')}),  # Added role to fields
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'phone', 'role', 'password1', 'password2'),  # Added role to add form
        }),
    )

    search_fields = ('email', 'name')
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions')