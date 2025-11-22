from django.urls import path
from .views import CheckInView, CheckOutView, TimeHistoryView, TodayStatusView

urlpatterns = [
    path('checkin/', CheckInView.as_view(), name='checkin'),
    path('checkout/', CheckOutView.as_view(), name='checkout'),
    path('history/', TimeHistoryView.as_view(), name='time-history'),
    path('today/', TodayStatusView.as_view(), name='today-status'),
]
