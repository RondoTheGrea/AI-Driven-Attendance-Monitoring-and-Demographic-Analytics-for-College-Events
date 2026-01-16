from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import models
from datetime import datetime, timedelta
import time
import json
import requests
from main.models import Organization, Student, Event, Attendance, ChatMessage

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

    # --- Risk breakdown for Graph 2 ---
    # We classify students based on their attendance across ALL past events
    # for this organization using the legend shown in the UI:
    #   High-risk       = attendance < 70%
    #   Emerging-risk   = 2+ absences in the last 10 days
    #   Low-risk        = everyone else (occasional or no absences)

    # Instead of relying on Student.organization (which may be null in fixtures),
    # we infer the student set from attendance records tied to this organization.
    students = Student.objects.filter(history__event__organization=organization).distinct()
    total_students = students.count()

    # Consider only events that have already happened (up to today)
    today = now.date()
    completed_events = Event.objects.filter(
        organization=organization,
        event_date__lte=today
    ).order_by('event_date')

    total_events = completed_events.count()

    # Fallback: if this organization has no attendance data yet,
    # use all events with logs so the graph still shows something
    # for demo/testing accounts.
    if total_students == 0 or total_events == 0:
        completed_events = Event.objects.filter(logs__isnull=False).order_by('event_date').distinct()
        total_events = completed_events.count()
        students = Student.objects.filter(history__event__in=completed_events).distinct()
        total_students = students.count()

    high_risk = 0
    emerging_risk = 0
    low_risk = 0

    if total_students:
        # Events in the last 10 days window (including today)
        window_start = today - timedelta(days=9)
        recent_events = completed_events.filter(event_date__gte=window_start)

        all_event_ids = list(completed_events.values_list('id', flat=True))
        recent_event_ids = list(recent_events.values_list('id', flat=True))

        for student in students:
            attended_all = Attendance.objects.filter(
                student=student,
                event_id__in=all_event_ids
            ).count()

            attendance_rate = (attended_all * 100.0 / total_events) if total_events else 0.0

            # Absences in the last 10 days
            if recent_event_ids:
                attended_recent = Attendance.objects.filter(
                    student=student,
                    event_id__in=recent_event_ids
                ).count()
                absences_recent = len(recent_event_ids) - attended_recent
            else:
                absences_recent = 0

            if attendance_rate < 70.0:
                high_risk += 1
            elif absences_recent >= 2:
                emerging_risk += 1
            else:
                # Everyone else is considered low-risk (either
                # perfect or occasional absences)
                low_risk += 1

    # Percentages for the graph (avoid division by zero)
    if total_students:
        high_pct = round(high_risk * 100.0 / total_students)
        emerging_pct = round(emerging_risk * 100.0 / total_students)
        low_pct = round(low_risk * 100.0 / total_students)
    else:
        high_pct = emerging_pct = low_pct = 0

    # --- Arrival pattern for Graph 1 (AI Summary box) ---
    arrival_event = None
    arrival_stats = {
        'total': 0,
        'early': 0,
        'on_time': 0,
        'late': 0,
        'early_percent': 0,
        'on_time_percent': 0,
        'late_percent': 0,
        'median_label': 'No data yet',
    }

    # Prefer an event for this organization with attendance logs; if none,
    # fall back to any event that has logs so demo data still shows something.
    arrival_events_qs = Event.objects.filter(
        organization=organization,
        logs__isnull=False
    ).order_by('-event_date', '-start_time').distinct()

    if not arrival_events_qs.exists():
        arrival_events_qs = Event.objects.filter(
            logs__isnull=False
        ).order_by('-event_date', '-start_time').distinct()

    if arrival_events_qs.exists():
        arrival_event = arrival_events_qs.first()

        start_dt = datetime.combine(arrival_event.event_date, arrival_event.start_time)
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt, tz)

        attendance_qs = Attendance.objects.filter(event=arrival_event).order_by('timestamp')

        offsets = []  # minutes relative to event start
        for record in attendance_qs:
            ts = record.timestamp
            if timezone.is_naive(ts):
                ts = timezone.make_aware(ts, tz)
            diff_minutes = (ts - start_dt).total_seconds() / 60.0
            offsets.append(diff_minutes)

        total_arrivals = len(offsets)
        if total_arrivals:
            early_count = sum(1 for m in offsets if m <= -5)
            on_time_count = sum(1 for m in offsets if -5 < m <= 10)
            late_count = sum(1 for m in offsets if m > 10)

            early_pct = round(early_count * 100.0 / total_arrivals)
            on_time_pct = round(on_time_count * 100.0 / total_arrivals)
            late_pct = round(late_count * 100.0 / total_arrivals)

            # Median arrival offset in minutes
            offsets_sorted = sorted(offsets)
            n = total_arrivals
            if n % 2 == 1:
                median_val = offsets_sorted[n // 2]
            else:
                median_val = (offsets_sorted[n // 2 - 1] + offsets_sorted[n // 2]) / 2.0

            median_minutes = int(round(median_val))
            if median_minutes <= -1:
                median_label = f"{abs(median_minutes)} min before start"
            elif median_minutes >= 1:
                median_label = f"{median_minutes} min after start"
            else:
                median_label = "right at start"

            arrival_stats = {
                'total': total_arrivals,
                'early': early_count,
                'on_time': on_time_count,
                'late': late_count,
                'early_percent': early_pct,
                'on_time_percent': on_time_pct,
                'late_percent': late_pct,
                'median_label': median_label,
            }

    # --- Student List with AI Flags ---
    # Load all students for this organization and compute their risk flags
    search_query = request.GET.get('search', '').strip()
    
    # Get students linked to this org's events
    students_list = Student.objects.filter(
        history__event__organization=organization
    ).distinct().order_by('last_name', 'first_name')
    
    # If no students found, fall back to all students with attendance records
    if not students_list.exists():
        students_list = Student.objects.filter(
            history__isnull=False
        ).distinct().order_by('last_name', 'first_name')
    
    # Apply search filter
    if search_query:
        students_list = students_list.filter(
            models.Q(first_name__icontains=search_query) |
            models.Q(last_name__icontains=search_query) |
            models.Q(student_id__icontains=search_query)
        )
    
    # Compute AI flags for each student
    students_with_flags = []
    for student in students_list:
        attended_all = Attendance.objects.filter(
            student=student,
            event_id__in=all_event_ids
        ).count() if total_events else 0
        
        attendance_rate = (attended_all * 100.0 / total_events) if total_events else 100.0
        
        # Absences in the last 10 days
        if recent_event_ids:
            attended_recent = Attendance.objects.filter(
                student=student,
                event_id__in=recent_event_ids
            ).count()
            absences_recent = len(recent_event_ids) - attended_recent
        else:
            absences_recent = 0
        
        # Determine AI flag based on predefined rules:
        # - High-risk (Chronic): attendance < 70%
        # - Emerging-risk (At-Risk): 2+ absences in last 10 days
        # - Low-risk (Good Standing): everyone else
        if attendance_rate < 70.0:
            flag = 'high-risk'
            flag_label = 'Chronic Risk'
        elif absences_recent >= 2:
            flag = 'emerging-risk'
            flag_label = 'At-Risk'
        else:
            flag = 'low-risk'
            flag_label = 'Good Standing'
        
        students_with_flags.append({
            'student': student,
            'flag': flag,
            'flag_label': flag_label,
            'attendance_rate': round(attendance_rate, 1),
        })
    
    context = {
        'active_event': active_event,
        'recent_logs': recent_logs,
        'arrival_event': arrival_event,
        'arrival_stats': arrival_stats,
        'risk_counts': {
            'high': high_risk,
            'emerging': emerging_risk,
            'low': low_risk,
            'high_percent': high_pct,
            'emerging_percent': emerging_pct,
            'low_percent': low_pct,
            'total_students': total_students,
            'total_events': total_events,
        },
        'students_with_flags': students_with_flags,
        'search_query': search_query,
    }

    # If this is an HTMX request with a search parameter, return just the student list
    if request.headers.get('HX-Request') and 'search' in request.GET:
        return render(request, 'org/overview/_student_list.html', context)

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
def org_dashboard_event_report(request, event_id):
    """HTMX endpoint showing an attendance report for a single event."""
    try:
        organization = request.user.organization
    except Organization.DoesNotExist:
        return redirect('home')

    # Only allow access to events owned by this organization
    try:
        event = Event.objects.get(id=event_id, organization=organization)
    except Event.DoesNotExist:
        return redirect('home')

    tz = timezone.get_current_timezone()

    # All attendance records for this event
    attendances = (
        Attendance.objects
        .filter(event=event)
        .select_related('student')
        .order_by('timestamp')
    )

    total_attendees = attendances.count()

    # Compute arrival offsets relative to start time
    start_dt = datetime.combine(event.event_date, event.start_time)
    if timezone.is_naive(start_dt):
        start_dt = timezone.make_aware(start_dt, tz)

    offsets = []
    attendee_rows = []

    for record in attendances:
        ts = record.timestamp
        if timezone.is_naive(ts):
            ts = timezone.make_aware(ts, tz)
        diff_minutes = (ts - start_dt).total_seconds() / 60.0
        offsets.append(diff_minutes)

        if diff_minutes <= -5:
            arrival_bucket = 'Early'
        elif -5 < diff_minutes <= 10:
            arrival_bucket = 'On-time'
        else:
            arrival_bucket = 'Late'

        attendee_rows.append({
            'student_name': f"{record.student.first_name} {record.student.last_name}",
            'student_id': record.student.student_id,
            'timestamp': ts,
            'arrival_bucket': arrival_bucket,
        })

    early_count = on_time_count = late_count = 0
    if offsets:
        early_count = sum(1 for m in offsets if m <= -5)
        on_time_count = sum(1 for m in offsets if -5 < m <= 10)
        late_count = sum(1 for m in offsets if m > 10)

    if total_attendees:
        early_pct = round(early_count * 100.0 / total_attendees)
        on_time_pct = round(on_time_count * 100.0 / total_attendees)
        late_pct = round(late_count * 100.0 / total_attendees)
    else:
        early_pct = on_time_pct = late_pct = 0

    median_label = 'No data yet'
    if offsets:
        offsets_sorted = sorted(offsets)
        n = len(offsets_sorted)
        if n % 2 == 1:
            median_val = offsets_sorted[n // 2]
        else:
            median_val = (offsets_sorted[n // 2 - 1] + offsets_sorted[n // 2]) / 2.0

        median_minutes = int(round(median_val))
        if median_minutes <= -1:
            median_label = f"{abs(median_minutes)} min before start"
        elif median_minutes >= 1:
            median_label = f"{median_minutes} min after start"
        else:
            median_label = "right at start"

    context = {
        'event': event,
        'attendee_rows': attendee_rows,
        'total_attendees': total_attendees,
        'early_count': early_count,
        'on_time_count': on_time_count,
        'late_count': late_count,
        'early_percent': early_pct,
        'on_time_percent': on_time_pct,
        'late_percent': late_pct,
        'median_label': median_label,
    }

    return render(request, 'org/events/report.html', context)

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


@login_required(login_url='home')
@require_http_methods(["POST"])
def chat_message(request):
    """Handle chat messages and forward to n8n workflow"""
    try:
        organization = request.user.organization
    except Organization.DoesNotExist:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)
        
        # Generate or retrieve session ID for this user
        # This allows n8n to maintain conversation memory per user
        if 'chat_session_id' not in request.session:
            import uuid
            request.session['chat_session_id'] = str(uuid.uuid4())
        
        session_id = request.session['chat_session_id']
        
        # n8n webhook configuration
        # TODO: Replace with your actual n8n webhook URL
        N8N_WEBHOOK_URL = 'http://4.194.202.144/webhook/c2d477ca-e66b-46f5-9b07-7044d621d0d1'
        
        # TODO: If you set up Header Auth in n8n, uncomment and add your API key
        # N8N_API_KEY = 'your-api-key-here'
        
        # Prepare the request to n8n
        headers = {
            'Content-Type': 'application/json',
            # Uncomment if using API key authentication
            # 'X-API-KEY': N8N_API_KEY,
        }
        
        # Get recent chat history for context (last 10 messages)
        recent_messages = ChatMessage.objects.filter(
            user=request.user,
            session_id=session_id
        ).order_by('-created_at')[:10]
        
        # Build conversation history for n8n
        conversation_history = []
        for msg in reversed(recent_messages):  # Reverse to get chronological order
            conversation_history.append({
                'role': 'user' if msg.is_user_message else 'assistant',
                'content': msg.message
            })
        
        # Add current message to history
        conversation_history.append({
            'role': 'user',
            'content': user_message
        })
        
        # Get context data if provided (default to empty arrays)
        context_data = data.get('context', {})
        if not isinstance(context_data, dict):
            context_data = {}
        
        # Ensure context has events and students arrays
        context_payload = {
            'events': context_data.get('events', []),
            'students': context_data.get('students', [])
        }
        
        payload = {
            'message': user_message,
            'sessionId': session_id,  # For n8n memory
            'organization_id': organization.id,
            'organization_name': organization.organization_name,
            'user_id': request.user.id,
            'conversation_history': conversation_history,  # Send history for better context
            'context': context_payload,  # Selected events/students for context
        }
        
        # Send request to n8n webhook
        try:
            response = requests.post(
                N8N_WEBHOOK_URL,
                json=payload,
                headers=headers,
                timeout=60  # 60 second timeout
            )
            response.raise_for_status()
            
            # Save user message to database
            ChatMessage.objects.create(
                user=request.user,
                organization=organization,
                message=user_message,
                is_user_message=True,
                session_id=session_id
            )
            
            # Parse n8n response
            n8n_data = response.json()
            
            # Handle different response formats (supporting optional chart_url)
            bot_reply = 'I received your message but could not generate a response.'
            chart_url = None

            if isinstance(n8n_data, dict):
                bot_reply = n8n_data.get('reply') or n8n_data.get('text') or n8n_data.get('output', str(n8n_data))
                chart_url = n8n_data.get('chart_url') or n8n_data.get('chartUrl')
            elif isinstance(n8n_data, list) and len(n8n_data) > 0:
                first_item = n8n_data[0]
                if isinstance(first_item, dict):
                    bot_reply = first_item.get('reply') or first_item.get('text') or first_item.get('output', str(first_item))
                    chart_url = first_item.get('chart_url') or first_item.get('chartUrl')
                else:
                    bot_reply = str(first_item)
            else:
                bot_reply = str(n8n_data)
            
            # Save bot reply to database (text only; charts are displayed client-side)
            ChatMessage.objects.create(
                user=request.user,
                organization=organization,
                message=bot_reply,
                is_user_message=False,
                session_id=session_id
            )
            
            return JsonResponse({
                'reply': bot_reply,
                'chart_url': chart_url,
                'status': 'success'
            })
            
        except requests.exceptions.Timeout:
            return JsonResponse({
                'error': 'Request timed out. Please try again.',
                'status': 'error'
            }, status=504)
            
        except requests.exceptions.RequestException as e:
            # Log the error for debugging
            import sys
            print(f"n8n request error: {str(e)}", file=sys.stderr, flush=True)
            
            return JsonResponse({
                'error': 'Failed to connect to AI service. Please try again later.',
                'status': 'error'
            }, status=503)
    
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    except Exception as e:
        import sys
        print(f"Chat error: {str(e)}", file=sys.stderr, flush=True)
        return JsonResponse({'error': 'An unexpected error occurred'}, status=500)


# ============================================================================
# API Endpoints for n8n Integration
# ============================================================================

@csrf_exempt
@require_http_methods(["GET"])
def api_get_event_attendance(request, event_id):
    """
    API endpoint for n8n to get attendance data for a specific event
    GET /org/api/event/<event_id>/attendance/
    
    Returns:
    - Event details
    - List of students who attended with timestamps
    - Attendance statistics
    """
    try:
        event = Event.objects.get(id=event_id)
        
        # Get all attendance records for this event
        attendances = Attendance.objects.filter(event=event).select_related('student')
        
        # Build attendance list
        attendance_list = []
        for att in attendances:
            attendance_list.append({
                'student_id': att.student.student_id,
                'name': f"{att.student.first_name} {att.student.last_name}",
                'email': att.student.email,
                'course': att.student.course,
                'year_level': att.student.year_level,
                'timestamp': att.timestamp.isoformat(),
                'time_difference': calculate_time_difference(event, att.timestamp)
            })
        
        # Calculate statistics
        total_attended = len(attendance_list)
        on_time = sum(1 for a in attendance_list if a['time_difference'] <= 0)
        late = total_attended - on_time
        
        return JsonResponse({
            'event': {
                'id': event.id,
                'title': event.title,
                'description': event.description,
                'date': event.event_date.isoformat(),
                'start_time': event.start_time.isoformat(),
                'end_time': event.end_time.isoformat(),
                'is_active': event.is_active,
            },
            'attendance': attendance_list,
            'statistics': {
                'total_attended': total_attended,
                'on_time': on_time,
                'late': late,
                'attendance_rate': f"{(total_attended / max(1, total_attended)) * 100:.1f}%"
            },
            'status': 'success'
        })
        
    except Event.DoesNotExist:
        return JsonResponse({'error': 'Event not found', 'status': 'error'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e), 'status': 'error'}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_get_organization_events(request, org_id):
    """
    API endpoint for n8n to get all events for an organization
    GET /org/api/organization/<org_id>/events/
    """
    try:
        organization = Organization.objects.get(id=org_id)
        events = Event.objects.filter(organization=organization).order_by('-event_date')
        
        events_list = []
        for event in events:
            attendance_count = Attendance.objects.filter(event=event).count()
            events_list.append({
                'id': event.id,
                'title': event.title,
                'description': event.description,
                'date': event.event_date.isoformat(),
                'start_time': event.start_time.isoformat(),
                'end_time': event.end_time.isoformat(),
                'is_active': event.is_active,
                'total_attendees': attendance_count
            })
        
        return JsonResponse({
            'organization': {
                'id': organization.id,
                'name': organization.organization_name,
            },
            'events': events_list,
            'total_events': len(events_list),
            'status': 'success'
        })
        
    except Organization.DoesNotExist:
        return JsonResponse({'error': 'Organization not found', 'status': 'error'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e), 'status': 'error'}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_get_student_attendance(request, student_id):
    """
    API endpoint for n8n to get attendance history for a specific student
    GET /org/api/student/<student_id>/attendance/
    """
    try:
        student = Student.objects.get(student_id=student_id)
        attendances = Attendance.objects.filter(student=student).select_related('event').order_by('-timestamp')
        
        attendance_list = []
        for att in attendances:
            attendance_list.append({
                'event_id': att.event.id,
                'event_title': att.event.title,
                'event_date': att.event.event_date.isoformat(),
                'timestamp': att.timestamp.isoformat(),
                'time_difference': calculate_time_difference(att.event, att.timestamp)
            })
        
        return JsonResponse({
            'student': {
                'student_id': student.student_id,
                'name': f"{student.first_name} {student.last_name}",
                'email': student.email,
                'course': student.course,
                'year_level': student.year_level,
            },
            'attendance_history': attendance_list,
            'total_events_attended': len(attendance_list),
            'status': 'success'
        })
        
    except Student.DoesNotExist:
        return JsonResponse({'error': 'Student not found', 'status': 'error'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e), 'status': 'error'}, status=500)


def calculate_time_difference(event, timestamp):
    """
    Calculate minutes difference between attendance timestamp and event start time
    Negative = early, Positive = late
    """
    from datetime import datetime, timedelta
    
    # Combine event date and start time
    event_start = datetime.combine(event.event_date, event.start_time)
    
    # Make timezone aware if needed
    if timezone.is_naive(event_start):
        event_start = timezone.make_aware(event_start)
    
    # Calculate difference in minutes
    diff = (timestamp - event_start).total_seconds() / 60
    return int(diff)


@login_required(login_url='home')
@require_http_methods(["GET"])
def api_get_events_for_context(request):
    """
    API endpoint to get all events for context selector
    Returns simplified event list for chat context
    Note: Does not filter by organization since organization field is optional
    """
    try:
        # Verify user is authenticated (required for login_required)
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Unauthorized'}, status=401)
    except Exception:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        # Get search query parameter
        search_query = request.GET.get('search', '').strip()
        
        # Get all events (organization is optional, so we don't filter by it)
        events = Event.objects.all()
        
        # Apply search filter if provided (search by title only)
        if search_query:
            events = events.filter(title__icontains=search_query)
        
        # Sort by date and time (chronological: earliest first)
        events = events.order_by('event_date', 'start_time')
        
        events_list = []
        for event in events:
            attendance_count = Attendance.objects.filter(event=event).count()
            events_list.append({
                'id': event.id,
                'title': event.title,
                'description': event.description or '',
                'date': event.event_date.isoformat(),
                'start_time': event.start_time.isoformat(),
                'end_time': event.end_time.isoformat(),
                'is_active': event.is_active,
                'total_attendees': attendance_count
            })
        
        return JsonResponse({
            'events': events_list,
            'status': 'success'
        })
    except Exception as e:
        import sys
        print(f"Error fetching events: {str(e)}", file=sys.stderr, flush=True)
        return JsonResponse({'error': str(e), 'status': 'error'}, status=500)


@login_required(login_url='home')
@require_http_methods(["GET"])
def api_get_students_for_context(request):
    """
    API endpoint to get all students for context selector
    Returns simplified student list for chat context
    Note: Does not filter by organization since organization field is optional
    """
    try:
        # Verify user is authenticated (required for login_required)
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Unauthorized'}, status=401)
    except Exception:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        # Get search query parameter
        search_query = request.GET.get('search', '').strip()
        
        # Get all students (organization is optional, so we don't filter by it)
        # Sort alphabetically by first name, then last name
        # Handle NULL values by using Coalesce to treat NULL as empty string for sorting
        from django.db.models import F, Value, CharField, Q
        from django.db.models.functions import Coalesce, Lower
        
        students = Student.objects.all()
        
        # Apply search filter if provided
        if search_query:
            students = students.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(student_id__icontains=search_query) |
                Q(email__icontains=search_query)
            )
        
        students = students.annotate(
            first_name_sort=Coalesce('first_name', Value(''), output_field=CharField()),
            last_name_sort=Coalesce('last_name', Value(''), output_field=CharField())
        ).order_by(
            Lower('first_name_sort'),
            Lower('last_name_sort')
        )
        
        students_list = []
        for student in students:
            students_list.append({
                'id': student.id,
                'student_id': student.student_id,
                'first_name': student.first_name or '',
                'last_name': student.last_name or '',
                'middle_name': student.middle_name or '',
                'email': student.email,
                'course': student.course,
                'year_level': student.year_level
            })
        
        return JsonResponse({
            'students': students_list,
            'status': 'success'
        })
    except Exception as e:
        import sys
        print(f"Error fetching students: {str(e)}", file=sys.stderr, flush=True)
        return JsonResponse({'error': str(e), 'status': 'error'}, status=500)
