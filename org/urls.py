# org/urls.py
from django.urls import path
from . import views  # Imports the views from the org folder

urlpatterns = [
    path('login/', views.org_login, name='org-login'),        # /org/login/
    path('dashboard/', views.org_page, name='org-page'),
    path('logout/', views.org_logout, name='org-logout'),     # /org/logout/
    
    # HTMX endpoints for dashboard tabs
    path('dashboard/overview/', views.org_dashboard_overview, name='org-dashboard-overview'),
    path('dashboard/events/', views.org_dashboard_events, name='org-dashboard-events'),
    path('dashboard/events/create/', views.org_dashboard_events_create, name='org-dashboard-events-create'),
    path('dashboard/events/<int:event_id>/report/', views.org_dashboard_event_report, name='org-dashboard-event-report'),
    path('dashboard/insights/', views.org_dashboard_insights, name='org-dashboard-insights'),
    path('dashboard/settings/', views.org_dashboard_settings, name='org-dashboard-settings'),
    
    # SSE endpoint for real-time attendance updates
    path('api/attendance-stream/<int:event_id>/', views.attendance_stream, name='attendance-stream'),
    
    # Chat endpoint for AI insights
    path('api/chat/', views.chat_message, name='chat-message'),
    
    # Context selector API endpoints
    path('api/context/events/', views.api_get_events_for_context, name='api-context-events'),
    path('api/context/students/', views.api_get_students_for_context, name='api-context-students'),
    
    # API endpoints for n8n integration
    path('api/event/<int:event_id>/attendance/', views.api_get_event_attendance, name='api-event-attendance'),
    path('api/organization/<int:org_id>/events/', views.api_get_organization_events, name='api-org-events'),
    path('api/student/<str:student_id>/attendance/', views.api_get_student_attendance, name='api-student-attendance'),
]
