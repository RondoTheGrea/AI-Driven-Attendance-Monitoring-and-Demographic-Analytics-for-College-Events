from django.shortcuts import render

def home(request):
    return render(request, 'main/index.html')

def org_login(request):
    return render(request, 'main/org-page.html')

def student_login(request):
    return render(request, 'main/student-page.html')
