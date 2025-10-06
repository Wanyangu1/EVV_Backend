from django.urls import path
from .views import LogoutView, LoginView, RegisterView, UserProfileListView, UserProfileDetailView, ChangePasswordView, UserProfileView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("login/", LoginView.as_view(), name="login"),
    path("profile/", UserProfileView.as_view(), name="user-profile-list"),  # List all profiles
    path("profile/<int:pk>/", UserProfileDetailView.as_view(), name="user-profile-detail"), 
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
]
