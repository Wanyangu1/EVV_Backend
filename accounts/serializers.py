from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, UserProfile


User = get_user_model()


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)

        data["access_token"] = data.pop("access")
        data["refresh_token"] = data.pop("refresh")
        # Add user role to login response
        data["role"] = self.user.role
        data["name"] = self.user.name
        data["email"] = self.user.email

        # Add token type
        data["token_type"] = "Bearer"

        # Calculate the expiration time for the access token in seconds
        data["expires_in"] = int(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds())

        return data


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, required=False, default='caregiver')

    class Meta:
        model = User
        fields = ["name", "email", "password", "role", "phone"]

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data["email"],
            name=validated_data["name"],
            phone=validated_data.get("phone", ""),
            password=validated_data["password"],
            role=validated_data.get("role", "caregiver")
        )
        return user

    def to_representation(self, instance):
        refresh = RefreshToken.for_user(instance)
        data = super().to_representation(instance)
        data["access_token"] = str(refresh.access_token)
        data["refresh_token"] = str(refresh)
        data["token_type"] = "Bearer"
        data["role"] = instance.role
        return data


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email", "role"]


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email", "phone", "role"]


class UserWithProfileSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer()

    class Meta:
        model = User
        fields = ["id", "name", "email", "role", "profile"]


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)


class UpdateUserRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["role"]
        extra_kwargs = {
            'role': {'required': True}
        }


class UserInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email", "role", "phone"]