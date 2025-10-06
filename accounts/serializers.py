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

        # Add token type
        data["token_type"] = "Bearer"

        # Calculate the expiration time for the access token in seconds
        data["expires_in"] = int(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds())

        return data


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ["name", "email", "password"]

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data["email"],
            name=validated_data["name"],
            password=validated_data["password"],
        )
        return user

    def to_representation(self, instance):

        refresh = RefreshToken.for_user(instance)
        data = super().to_representation(instance)
        data["access_token"] = str(refresh.access_token)
        data["refresh_token"] = str(refresh)
        data["token_type"] = "Bearer"
        return data


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email"]

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email", "phone"]

class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer()

    class Meta:
        model = User
        fields = ["id", "name", "email", "profile"]

class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
