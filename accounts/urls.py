from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (LogoutView, LoginView, RegisterView, 
                    UserProfileListView, UserProfileDetailView, 
                    ChangePasswordView, UserProfileView, UserInfoView,
                    UpdateUserRoleView, UserViewSet)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("login/", LoginView.as_view(), name="login"),
    path("profile/", UserProfileView.as_view(), name="user-profile"),
    path("profiles/", UserProfileListView.as_view(), name="user-profile-list"),
    path("profiles/<int:pk>/", UserProfileDetailView.as_view(), name="user-profile-detail"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("user-info/", UserInfoView.as_view(), name="user-info"),
    path("update-role/<int:pk>/", UpdateUserRoleView.as_view(), name="update-role"),
    path("", include(router.urls)),
]