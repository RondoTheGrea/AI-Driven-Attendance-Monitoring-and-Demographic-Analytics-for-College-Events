from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.contrib import messages
from main.models import Organization, Student

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

def org_logout(request):
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('home')
