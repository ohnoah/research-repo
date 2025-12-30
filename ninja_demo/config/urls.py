from django.contrib import admin
from django.urls import path
from api.api import api
from api.api_fixed import api_fixed

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("api-fixed/", api_fixed.urls),
]
