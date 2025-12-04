from rest_framework import status, permissions, viewsets, generics
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from accounts.serializers import (RegisterSerializer, LoginSerializer, 
                                  UserProfileSerializer, UpdateUserRoleSerializer,
                                  UserInfoSerializer)
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import get_user_model
from rest_framework.decorators import action

User = get_user_model()


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer


class RegisterView(generics.CreateAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LogoutView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {"detail": "Successfully logged out."},
                status=status.HTTP_205_RESET_CONTENT,
            )
        except Exception:
            return Response(
                {"detail": "Invalid refresh token."}, status=status.HTTP_400_BAD_REQUEST
            )


class UserProfileView(generics.RetrieveUpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        current_password = request.data.get("current_password")
        new_password = request.data.get("new_password")

        if not user.check_password(current_password):
            return Response({"detail": "Current password is incorrect"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(new_password, user)
            user.set_password(new_password)
            user.save()
            update_session_auth_hash(request, user)
            return Response({"detail": "Password updated successfully"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UserProfileListView(generics.ListAPIView):
    """
    Handles GET requests for listing all users' profiles.
    """
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Only admin/superuser can see all users
        user = self.request.user
        if user.is_admin():
            return User.objects.all()
        else:
            # Non-admin users can only see their own profile
            return User.objects.filter(id=user.id)


class UserProfileDetailView(generics.RetrieveAPIView):
    """
    Handles GET requests for retrieving a specific user's profile.
    """
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Only admin/superuser can see all users
        user = self.request.user
        if user.is_admin():
            return User.objects.all()
        else:
            # Non-admin users can only see their own profile
            return User.objects.filter(id=user.id)


class UserInfoView(APIView):
    """
    Returns basic user info including role for frontend
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        serializer = UserInfoSerializer(user)
        return Response(serializer.data)


class UpdateUserRoleView(generics.UpdateAPIView):
    """
    Admin-only endpoint to update user roles
    """
    queryset = User.objects.all()
    serializer_class = UpdateUserRoleSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        # Only admin/superuser can update roles
        return [permission() for permission in [IsAuthenticated] if self.request.user.is_admin()]
    
    def update(self, request, *args, **kwargs):
        user_to_update = self.get_object()
        requesting_user = request.user
        
        # Check permissions
        if not requesting_user.is_admin():
            return Response(
                {"detail": "You do not have permission to update roles."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Superuser cannot change their own role or other superusers
        if user_to_update == requesting_user:
            return Response(
                {"detail": "You cannot change your own role."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = self.get_serializer(user_to_update, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response({
            "detail": "User role updated successfully.",
            "user": UserProfileSerializer(user_to_update).data
        })


class UserViewSet(viewsets.ModelViewSet):
    """
    Comprehensive user management for admin users
    """
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        # Only admin/superuser can access this viewset
        if self.action in ['list', 'retrieve', 'update', 'partial_update', 'destroy', 'update_role']:
            return [permission() for permission in [IsAuthenticated] if self.request.user.is_admin()]
        return super().get_permissions()
    
    @action(detail=True, methods=['put'])
    def update_role(self, request, pk=None):
        """Update user role (admin only)"""
        user = self.get_object()
        serializer = UpdateUserRoleSerializer(user, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'detail': 'Role updated successfully',
                'user': UserProfileSerializer(user).data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)