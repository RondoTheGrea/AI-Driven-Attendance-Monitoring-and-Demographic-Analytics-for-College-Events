from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from main.models import Organization, Student

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
    
    return render(request, 'student/dashboard.html')

def student_logout(request):
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('home')