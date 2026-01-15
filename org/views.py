from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from datetime import datetime
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
        
        payload = {
            'message': user_message,
            'sessionId': session_id,  # For n8n memory
            'organization_id': organization.id,
            'organization_name': organization.organization_name,
            'user_id': request.user.id,
            'conversation_history': conversation_history,  # Send history for better context
        }
        
        # Send request to n8n webhook
        try:
            response = requests.post(
                N8N_WEBHOOK_URL,
                json=payload,
                headers=headers,
                timeout=30  # 30 second timeout
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
            
            # Handle different response formats
            bot_reply = 'I received your message but could not generate a response.'
            
            if isinstance(n8n_data, dict):
                # If it's a dict, look for 'reply' key
                bot_reply = n8n_data.get('reply', n8n_data.get('output', str(n8n_data)))
            elif isinstance(n8n_data, list) and len(n8n_data) > 0:
                # If it's a list, get the first item
                first_item = n8n_data[0]
                if isinstance(first_item, dict):
                    bot_reply = first_item.get('reply', first_item.get('output', str(first_item)))
                else:
                    bot_reply = str(first_item)
            else:
                # If it's just a string
                bot_reply = str(n8n_data)
            
            # Save bot reply to database
            ChatMessage.objects.create(
                user=request.user,
                organization=organization,
                message=bot_reply,
                is_user_message=False,
                session_id=session_id
            )
            
            return JsonResponse({
                'reply': bot_reply,
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
