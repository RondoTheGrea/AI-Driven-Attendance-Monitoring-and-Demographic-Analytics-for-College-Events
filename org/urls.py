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
    path('dashboard/insights/', views.org_dashboard_insights, name='org-dashboard-insights'),
    path('dashboard/settings/', views.org_dashboard_settings, name='org-dashboard-settings'),
    
    # SSE endpoint for real-time attendance updates
    path('api/attendance-stream/<int:event_id>/', views.attendance_stream, name='attendance-stream'),
]
