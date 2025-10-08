from rest_framework import routers
from .views import ClientViewSet, ServiceViewSet, VisitLogViewSet

router = routers.DefaultRouter()
router.register(r'clients', ClientViewSet, basename='client')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'visits', VisitLogViewSet, basename='visit')

urlpatterns = router.urls
