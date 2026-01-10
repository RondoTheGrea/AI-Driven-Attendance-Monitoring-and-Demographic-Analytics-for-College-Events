from django.db import models
from django.contrib.auth.models import User

class Student(models.Model):
    # RFID Information (Phase 1 - Required immediately)
    rfid_uid = models.CharField(max_length=50, unique=True)  # The RFID card UID
    
    # Basic Profile (Phase 1 - Required immediately)
    student_id = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    course = models.CharField(max_length=100)
    year_level = models.IntegerField()
    
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
    
    def __str__(self):
        return f"{self.student_id} - {self.first_name} {self.last_name}"
    
    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = "Student"
        verbose_name_plural = "Students"
    
# Organization Model(like CCS, CES and etc)
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
    
    def __str__(self):
        return f"{self.organization_name} ({self.user.username})"
    
    class Meta:
        ordering = ['organization_name']
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"