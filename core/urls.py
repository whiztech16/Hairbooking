"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

# Admin URL path is configurable via env var so it's not sitting at the
# well-known /admin/ that every automated scanner tries first. This is
# obscurity, not real security — the actual protection is still the
# superuser password — but it cuts down on brute-force noise significantly.
import os
admin_path = os.environ.get("DJANGO_ADMIN_PATH", "admin/")

urlpatterns = [
    path(admin_path, admin.site.urls),
    path('api/', include('booking.urls')),
]
