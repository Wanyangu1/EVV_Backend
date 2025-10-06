from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):

    def create_user(self, email, name, password=None, **kwargs):
        email = self.normalize_email(email)
        new_user = self.model(email=email, name=name, **kwargs)
        new_user.set_password(password)
        new_user.save(using=self._db)

        return new_user

    def create_superuser(self, email, name, password=None, **kwargs):
        kwargs.setdefault("is_staff", True)
        kwargs.setdefault("is_superuser", True)
        kwargs.setdefault("is_active", True)
        return self.create_user(email, name, password, **kwargs)
