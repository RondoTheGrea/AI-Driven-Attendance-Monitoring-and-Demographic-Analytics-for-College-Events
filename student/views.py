from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.utils import timezone
from main.models import Organization, Student, Event, Attendance

def student_login(request):
    # If already logged in, redirect to appropriate dashboard
    if request.user.is_authenticated:
        try:
            request.user.student
            return redirect('student-page')
        except Student.DoesNotExist:
            try:
                request.user.organization
                return redirect('org-page')
            except Organization.DoesNotExist:
                pass
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            # Verify the user actually has a Student profile
            try:
                student = user.student
                login(request, user)
                return redirect('student-page')
            except Student.DoesNotExist:
                messages.error(request, 'This account is not associated with a student profile. Please use the organization login.')
                return redirect('home')

        messages.error(request, 'Invalid student credentials.')
        return redirect('home')

    return redirect('home')


def student_page(request):
    # Verify user is actually a student (security check)
    if not request.user.is_authenticated:
        messages.error(request, 'Please login to access the student dashboard.')
        return redirect('home')
    
    try:
        student = request.user.student
    except Student.DoesNotExist:
        messages.error(request, 'You do not have permission to access the student dashboard.')
        return redirect('home')

    # Determine which events to show based on the student's organization
    org = student.organization
    today = timezone.localdate()

    events_qs = Event.objects.all().order_by('-event_date', '-start_time')
    if org is not None:
        events_qs = events_qs.filter(organization=org)

    # Upcoming events (today and future)
    upcoming_events = (
        events_qs
        .filter(event_date__gte=today)
        .order_by('event_date', 'start_time')[:5]
    )

    # Recent past events (for attendance history)
    recent_events = (
        events_qs
        .filter(event_date__lt=today)
        .order_by('-event_date', '-start_time')[:10]
    )

    # Map event -> attended?
    attended_ids = set(
        Attendance.objects
        .filter(student=student, event__in=recent_events)
        .values_list('event_id', flat=True)
    )

    recent_events_with_status = []
    for ev in recent_events:
        attended = ev.id in attended_ids
        status = 'Attended' if attended else 'No check-in recorded'
        recent_events_with_status.append({
            'event': ev,
            'attended': attended,
            'status': status,
        })

    context = {
        'student': student,
        'upcoming_events': upcoming_events,
        'recent_events_with_status': recent_events_with_status,
    }

    return render(request, 'student/dashboard.html', context)

def student_logout(request):
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('home')