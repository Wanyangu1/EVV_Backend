from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


class UserModelTest(TestCase):

    def setUp(self):
        return super().setUp()

    def test_user_creation(self):
        data = self.get_data()
        user = User.objects.create_user(**data)

        self.assertEqual(user.name, data["name"])
        self.assertEqual(user.email, data["email"])
        self.assertTrue(user.check_password(data["password"]))

    def test_email_uniqueness(self):
        data = self.get_data()
        User.objects.create_user(**data)
        with self.assertRaises(ValidationError):
            user = User(**data)
            user.full_clean()
            user.save()

    def test_str_method(self):
        data = self.get_data()
        user = User.objects.create_user(**data)
        self.assertEqual(str(user), data["name"])

    def test_required_fields(self):
        incomplete_data = {"email": "newuser@example.com", "password": "newpassword123"}
        with self.assertRaises(TypeError):
            User.objects.create_user(**incomplete_data)

    def get_data(self):
        return {"name": "John Doe", "email": "jdoe@gmail.com", "password": "pa$$w0rd!"}
