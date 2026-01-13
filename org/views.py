from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import StreamingHttpResponse
from datetime import datetime
import time
import json
from main.models import Organization, Student, Event, Attendance

def org_login(request):
    # If already logged in, redirect to appropriate dashboard
    if request.user.is_authenticated:
        try:
            request.user.organization
            return redirect('org-page')
        except Organization.DoesNotExist:
            try:
                request.user.student
                return redirect('student-page')
            except Student.DoesNotExist:
                pass
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            # Verify the user actually has an Organizer profile
            try:
                organization = user.organization
                login(request, user)
                return redirect('org-page')
            except Organization.DoesNotExist:
                messages.error(request, 'This account is not associated with an organization. Please use the student login.')
                return redirect('home')

        messages.error(request, 'Invalid organization credentials.')
        return redirect('home')

    # Non-POST should just show the login page
    return redirect('home')

def org_page(request):
    # Verify user is actually an organizer (security check)
    if not request.user.is_authenticated:
        messages.error(request, 'Please login to access the organization dashboard.')
        return redirect('home')
    
    try:
        organization = request.user.organization
    except Organization.DoesNotExist:
        messages.error(request, 'You do not have permission to access the organization dashboard.')
        return redirect('home')
    
    return render(request, 'org/dashboard.html')


def _get_event_context(organization):
    """Return categorized events for an organization."""
    events = Event.objects.filter(organization=organization).order_by('-event_date', '-start_time')

    now = timezone.now()
    tz = timezone.get_current_timezone()

    ongoing_events = []
    future_events = []
    recent_events = []

    for event in events:
        start_dt = datetime.combine(event.event_date, event.start_time)
        end_dt = datetime.combine(event.event_date, event.end_time)

        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt, tz)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt, tz)

        if start_dt <= now <= end_dt:
            ongoing_events.append(event)
        elif start_dt > now:
            future_events.append(event)
        else:
            recent_events.append(event)

    return {
        'ongoing_events': ongoing_events,
        'future_events': future_events,
        'recent_events': recent_events,
    }

@login_required(login_url='home')
def org_dashboard_overview(request):
    """HTMX endpoint for Overview tab"""
    try:
        organization = request.user.organization
    except Organization.DoesNotExist:
        return redirect('home')

    now = timezone.now()
    tz = timezone.get_current_timezone()

    # Find current live event (first ongoing)
    active_event = None
    events = Event.objects.filter(organization=organization).order_by('-event_date', '-start_time')
    for event in events:
        start_dt = datetime.combine(event.event_date, event.start_time)
        end_dt = datetime.combine(event.event_date, event.end_time)

        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt, tz)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt, tz)

        if start_dt <= now <= end_dt:
            active_event = event
            break

    # Pull recent check-ins for the active event
    recent_logs = []
    if active_event:
        recent_logs = (
            Attendance.objects
            .filter(event=active_event)
            .select_related('student')
            .order_by('-timestamp')[:50]
        )

    context = {
        'active_event': active_event,
        'recent_logs': recent_logs,
    }

    return render(request, 'org/overview/overview.html', context)

@login_required(login_url='home')
def org_dashboard_events(request):
    """HTMX endpoint for Events tab"""
    try:
        organization = request.user.organization
    except Organization.DoesNotExist:
        return redirect('home')

    context = _get_event_context(organization)
    return render(request, 'org/events/events.html', context)


@login_required(login_url='home')
def org_dashboard_events_create(request):
    """HTMX endpoint to create a new event and return updated events list."""
    try:
        organization = request.user.organization
    except Organization.DoesNotExist:
        return redirect('home')

    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        description = (request.POST.get('description') or '').strip()
        event_date_raw = (request.POST.get('event_date') or '').strip()
        start_time_raw = (request.POST.get('start_time') or '').strip()
        end_time_raw = (request.POST.get('end_time') or '').strip()

        errors = []

        # Validate required fields
        if not title:
            errors.append('Title is required.')
        if not event_date_raw:
            errors.append('Event date is required.')
        if not start_time_raw:
            errors.append('Start time is required.')
        if not end_time_raw:
            errors.append('End time is required.')

        parsed_date = None
        parsed_start = None
        parsed_end = None

        # Parse date and times
        if event_date_raw:
            try:
                parsed_date = datetime.strptime(event_date_raw, '%Y-%m-%d').date()
            except ValueError:
                errors.append('Invalid date format. Use YYYY-MM-DD.')

        if start_time_raw:
            try:
                parsed_start = datetime.strptime(start_time_raw, '%H:%M').time()
            except ValueError:
                errors.append('Invalid start time format. Use HH:MM (24-hour).')

        if end_time_raw:
            try:
                parsed_end = datetime.strptime(end_time_raw, '%H:%M').time()
            except ValueError:
                errors.append('Invalid end time format. Use HH:MM (24-hour).')

        if parsed_start and parsed_end and parsed_start >= parsed_end:
            errors.append('End time must be after start time.')

        if errors:
            return render(request, 'org/events/create.html', {
                'errors': errors,
                'form_data': {
                    'title': title,
                    'description': description,
                    'event_date': event_date_raw,
                    'start_time': start_time_raw,
                    'end_time': end_time_raw,
                }
            })

        # Create event
        Event.objects.create(
            organization=organization,
            title=title,
            description=description,
            event_date=parsed_date,
            start_time=parsed_start,
            end_time=parsed_end,
            is_active=True,
        )

        context = _get_event_context(organization)
        context['toast'] = 'Event created successfully.'
        return render(request, 'org/events/events.html', context)

    # GET - return form partial
    return render(request, 'org/events/create.html')

@login_required(login_url='home')
def org_dashboard_insights(request):
    """HTMX endpoint for Insights tab"""
    try:
        organization = request.user.organization
    except Organization.DoesNotExist:
        return redirect('home')
    
    return render(request, 'org/insights/insights.html')

@login_required(login_url='home')
def org_dashboard_settings(request):
    """HTMX endpoint for Settings tab"""
    try:
        organization = request.user.organization
    except Organization.DoesNotExist:
        return redirect('home')
    
    return render(request, 'org/settings/settings.html')


@login_required(login_url='home')
def attendance_stream(request, event_id):
    """SSE endpoint for streaming attendance updates for a specific event"""
    try:
        organization = request.user.organization
    except Organization.DoesNotExist:
        return redirect('home')
    
    # Verify event belongs to this organization
    try:
        event = Event.objects.get(id=event_id, organization=organization)
    except Event.DoesNotExist:
        return redirect('home')
    
    def event_stream():
        import sys
        print(f"SSE Stream started for event {event_id}", file=sys.stderr, flush=True)
        
        # Send initial connection message
        yield f"data: {json.dumps({'timestamp': timezone.now().strftime('%H:%M:%S'), 'student_name': 'Connection established'})}\n\n"
        
        last_check = timezone.now()
        iterations = 0
        
        try:
            while True:
                iterations += 1
                
                # Check for new attendance records since last check
                new_records = list(
                    Attendance.objects
                    .filter(event=event, timestamp__gt=last_check)
                    .select_related('student')
                    .order_by('-timestamp')
                )
                
                if new_records:
                    print(f"Found {len(new_records)} new records", file=sys.stderr, flush=True)
                    last_check = new_records[0].timestamp
                    
                    for record in new_records:
                        data = {
                            'timestamp': record.timestamp.strftime('%H:%M:%S'),
                            'student_name': f"{record.student.first_name} {record.student.last_name}",
                        }
                        print(f"Sending: {data}", file=sys.stderr, flush=True)
                        yield f"data: {json.dumps(data)}\n\n"
                
                # Sleep briefly to avoid busy waiting
                time.sleep(0.2)
        except GeneratorExit:
            print("SSE connection closed", file=sys.stderr, flush=True)
    
    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


def org_logout(request):
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('home')
