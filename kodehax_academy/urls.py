"""
URL configuration for kodehax_academy project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
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
from adminpanel.views import maintenance_page
from student.views import (
    chat_session_clear_api,
    chat_session_detail_api,
    chat_session_message_api,
    chat_session_rename_api,
    chat_sessions_api,
    chat_start_api,
    image_query_api,
)

from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse

def health_check(request):
    return JsonResponse({"status": "healthy"})


urlpatterns = [
    path('health/', health_check, name='health_check'),
    path("maintenance/", maintenance_page, name="maintenance_page"),
    path('admin/', admin.site.urls),
    path('admin-panel/', include('adminpanel.urls')),
    path("api/chat/start/", chat_start_api, name="api_chat_start"),
    path("api/chat/sessions/", chat_sessions_api, name="api_chat_sessions"),
    path("api/chat/<int:session_id>/", chat_session_detail_api, name="api_chat_session_detail"),
    path("api/chat/<int:session_id>/message/", chat_session_message_api, name="api_chat_session_message"),
    path("api/chat/<int:session_id>/rename/", chat_session_rename_api, name="api_chat_session_rename"),
    path("api/chat/<int:session_id>/clear/", chat_session_clear_api, name="api_chat_session_clear"),
    path("api/ai/image-query/", image_query_api, name="api_image_query"),
    path('', include('accounts.urls')),
    path('', include('users.urls')),
    path('student/daily-challenges/', include('daily_challenges.urls')),
    path('student/skill-assessment/', include('skill_assessment.urls')),
    path('student/', include('student.urls')),
    path('teacher/', include('teacher.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
