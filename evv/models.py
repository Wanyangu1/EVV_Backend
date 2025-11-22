from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()


class Service(models.Model):
    """Types of services a caregiver can provide (e.g. personal care, therapy)."""
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Client(models.Model):
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    date_of_birth = models.DateField(null=True, blank=True)
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    socials = models.JSONField(blank=True, null=True)
    next_of_kin_name = models.CharField(max_length=200, blank=True)
    next_of_kin_phone = models.CharField(max_length=100, blank=True)
    ssn = models.CharField(max_length=50, blank=True)
    medical_history = models.TextField(blank=True)
    visits_per_week = models.PositiveSmallIntegerField(default=0)
    visit_times = models.JSONField(blank=True, null=True)
    services_needed = models.ManyToManyField(Service, blank=True, related_name='clients')
    address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    notes = models.TextField(blank=True)

    # Caregiver assignments
    assigned_caregivers = models.ManyToManyField(
        User,
        through='Assignment',
        through_fields=('client', 'caregiver'),
        related_name='assigned_clients'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('last_name', 'first_name')

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Assignment(models.Model):
    """Link between caregiver and client, tracking who assigned and status."""
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='assignments')
    caregiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='caregiver_assignments')
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments_made'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('client', 'caregiver')

    def __str__(self):
        return f"{self.caregiver} -> {self.client}"


class VisitLog(models.Model):
    """Logs each visit a caregiver makes to a client."""
    STATUS_CHOICES = [
        ("checked_in", "Checked In"),
        ("completed", "Completed"),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='visits')
    caregiver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='visits')

    services = models.ManyToManyField(Service, blank=True, related_name='visit_logs')

    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)

    check_in_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_in_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_out_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_out_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # signatures stored as images (Base64 -> Image via serializer)
    client_signature = models.ImageField(upload_to='signatures/%Y/%m/%d/', null=True, blank=True)
    caregiver_signature = models.ImageField(upload_to='signatures/%Y/%m/%d/', null=True, blank=True)

    visit_notes = models.TextField(blank=True)
    hours_worked = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="checked_in")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def save(self, *args, **kwargs):
        """Automatically calculate hours worked when both check-in and check-out exist."""
        if self.check_in_time and self.check_out_time:
            delta_seconds = (self.check_out_time - self.check_in_time).total_seconds()
            # protect against negative durations
            if delta_seconds < 0:
                self.hours_worked = None
            else:
                self.hours_worked = round(delta_seconds / 3600.0, 2)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Visit {self.id} - {self.client} by {self.caregiver}"
