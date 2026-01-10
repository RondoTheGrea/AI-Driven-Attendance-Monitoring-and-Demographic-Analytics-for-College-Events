from django.db import models
from django.contrib.auth.models import User

# Student Model
class Student(models.Model):
    # RFID Information (Phase 1 - Required immediately)
    rfid_uid = models.CharField(max_length=50, unique=True)  # The RFID card UID
    
    # Basic Profile (Phase 1 - Required immediately)
    student_id = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField()
    course = models.CharField(max_length=100)
    year_level = models.IntegerField()

    # Owning organization (flexible: optional, many students per organization)
    organization = models.ForeignKey(
        'Organization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students'
    )
    
    # User Account (Phase 2 - Created later, optional at first)
    user = models.OneToOneField(
        User, 
        on_delete=models.SET_NULL,  # Keep student profile even if User is deleted
        null=True,  # Can be empty initially
        blank=True  # Can be left empty in forms
    )
    
    # Account Status
    account_created = models.BooleanField(default=False)  # Track if login account exists
    account_created_date = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    

    # Display at admin panel
    def __str__(self):
        return f"{self.student_id} - {self.first_name} {self.last_name}"
    
    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = "Student"
        verbose_name_plural = "Students"
    

# Organization Model(like CES, CECS and etc)
class Organization(models.Model):

    # The organization's user account
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    
    # Organization details
    organization_name = models.CharField(max_length=200)
    contact_number = models.CharField(max_length=15)
    
    # Optional: Additional information
    description = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Display at admin panel
    def __str__(self):
        return f"{self.organization_name} ({self.user.username})"
    
    class Meta:
        ordering = ['organization_name']
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"

# Event Model
class Event(models.Model):
    # Link to the Organization hosting the event
    organization = models.ForeignKey(
        'Organization', 
        on_delete=models.CASCADE, 
        related_name='events'
    )
    
    # Basic Information
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Date and Time
    event_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    # Tracking
    is_active = models.BooleanField(default=True) # Turn off to stop RFID scans
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-event_date', '-start_time'] # Newest first

    # Display at admin panel
    def __str__(self):
        return f"{self.title} - {self.event_date}"

# Attendance Log Model    
class Attendance(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='logs')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='history')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'student')

# AI Response Model
class AIInsight(models.Model):
    # The Link (allows many insights per event)
    event = models.ForeignKey('Event', on_delete=models.CASCADE, related_name='ai_insights')
    
    # Categorization of the insight types
    INSIGHT_TYPES = [
        ('prediction', 'Future Prediction'),
        ('attendance', 'Attendance Analysis'),
        ('engagement', 'Engagement Pattern'),
        ('anomaly', 'Anomaly Detection'),
    ]
    type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    
    # The Data
    title = models.CharField(max_length=200) # e.g., "Peak Hour Identified"
    content = models.TextField()           # The actual AI explanation
    score = models.FloatField(null=True)   # A numerical value for charts (0.0 - 100.0)
    
    # Timing
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type} for {self.event.title}"