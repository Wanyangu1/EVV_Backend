# evv/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from .models import Employee

User = get_user_model()

@receiver(post_save, sender=Employee)
def create_user_for_employee(sender, instance, created, **kwargs):
    """
    Automatically create a User when an Employee is created.
    """
    if created and not instance.user:
        # Generate a temporary password
        temp_password = get_random_string(12)
        
        # Create user with employee email
        user = User.objects.create_user(
            email=instance.email,
            name=f"{instance.first_name} {instance.last_name}",
            password=temp_password,  # Users can reset this later
            # Set role based on position if needed
            role='caregiver' if instance.position.lower() == 'caregiver' else instance.position.lower()
        )
        
        # Link the user to the employee
        instance.user = user
        instance.save(update_fields=['user'])
        
        # Optional: Send welcome email with temp password
        # send_welcome_email(instance.email, temp_password)

@receiver(post_save, sender=Employee)
def update_user_from_employee(sender, instance, **kwargs):
    """
    Update User details when Employee details are updated.
    """
    if instance.user:
        # Sync name changes
        if instance.user.name != f"{instance.first_name} {instance.last_name}":
            instance.user.name = f"{instance.first_name} {instance.last_name}"
            instance.user.save(update_fields=['name'])
        
        # Sync email changes
        if instance.user.email != instance.email:
            instance.user.email = instance.email
            instance.user.save(update_fields=['email'])