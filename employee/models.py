from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from decimal import Decimal

User = get_user_model()


class UserWorkProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='work_profile')
    rate_per_hour = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    biweekly_total_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Payment Profile"


class TimeRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='time_records')
    date = models.DateField()
    check_in = models.DateTimeField()
    check_in_time = models.TimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    hours_worked = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ('user', 'date')
        ordering = ['-date', '-check_in']

    def clean(self):
        if self.check_out and self.check_out <= self.check_in:
            raise ValidationError("Check-out time must be after check-in time")
        if not self.pk and TimeRecord.objects.filter(user=self.user, date=self.date).exists():
            raise ValidationError("Only one time record per day allowed")

    def save(self, *args, **kwargs):
        if self.check_out:
            total_seconds_worked = (self.check_out - self.check_in).total_seconds()
            self.hours_worked = round(Decimal(total_seconds_worked) / Decimal(3600), 2)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.date}: {self.hours_worked} hours"


# Auto create user profile
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_work_profile(sender, instance, created, **kwargs):
    if created and not hasattr(instance, 'work_profile'):
        UserWorkProfile.objects.create(user=instance)
