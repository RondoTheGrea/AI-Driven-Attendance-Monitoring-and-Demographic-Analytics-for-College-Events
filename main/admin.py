from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from django.db import transaction
from django.utils import timezone
import secrets
import string

from .models import Organization, Student


class StudentAccountCreationAdmin(admin.ModelAdmin):
    """
    Custom admin interface for Student model with account creation functionality
    """
    list_display = ('student_id', 'first_name', 'last_name', 'email', 'course', 'organization', 'get_username', 'account_status')
    list_filter = ('account_created', 'year_level', 'course', 'organization')
    search_fields = ('student_id', 'first_name', 'last_name', 'email')
    readonly_fields = ('rfid_uid', 'created_at', 'updated_at', 'account_created_date')
    
    fieldsets = (
        ('RFID & Profile Information', {
            'fields': ('rfid_uid', 'student_id', 'first_name', 'last_name', 'email', 'course', 'year_level', 'organization')
        }),
        ('User Account', {
            'fields': ('user', 'account_created', 'account_created_date'),
            'description': 'Link to login account. Create using the "Create login accounts for selected students" action below.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['create_accounts_for_selected']
    
    def account_status(self, obj):
        """Display account status with color"""
        if obj.account_created and obj.user:
            return mark_safe(
                '<span style="color: green; font-weight: bold;">✓ Active</span>'
            )
        return mark_safe(
            '<span style="color: orange; font-weight: bold;">✗ No Account</span>'
        )
    account_status.short_description = 'Account Status'
    
    def get_username(self, obj):
        """Display the linked username"""
        if obj.user:
            return obj.user.username
        return mark_safe('<span style="color: gray;">—</span>')
    get_username.short_description = 'Username'
    
    @transaction.atomic
    def create_accounts_for_selected(self, request, queryset):
        """
        Batch action to create accounts for selected students
        """
        created_count = 0
        failed_list = []
        credentials_log = []  # Collect generated credentials to show once
        
        for student in queryset:
            if not student.account_created or not student.user:
                try:
                    # Generate temporary password
                    temp_password = self._generate_temporary_password()
                    
                    # Create Django User
                    username = self._generate_username(student)
                    user = User.objects.create_user(
                        username=username,
                        email=student.email,
                        password=temp_password,
                        first_name=student.first_name,
                        last_name=student.last_name
                    )
                    
                    # Link user to student
                    student.user = user
                    student.account_created = True
                    student.account_created_date = timezone.now()
                    student.save()
                    
                    # Keep a record of credentials to display to admin once
                    credentials_log.append(f"{student.student_id} | {username} | {temp_password}")

                    created_count += 1
                    
                except Exception as e:
                    failed_list.append(f"{student.student_id}: {str(e)}")
        
        # Display success message
        if created_count > 0:
            # Show credentials only once so admin can hand them off securely
            creds_text = "\n".join(credentials_log)
            self.message_user(
                request,
                f"Successfully created {created_count} account(s).\n" +
                "Credentials (Student ID | Username | Temp Password):\n" +
                creds_text,
                messages.SUCCESS
            )
        
        if failed_list:
            error_msg = 'Failed to create accounts for: ' + '; '.join(failed_list)
            self.message_user(request, error_msg, messages.ERROR)
    
    create_accounts_for_selected.short_description = '✓ Create login accounts for selected students'
    
    @staticmethod
    def _generate_username(student):
        """Generate a unique username based on student_id"""
        base_username = student.student_id.lower().replace(' ', '')
        username = base_username
        counter = 1
        
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        return username
    
    @staticmethod
    def _generate_temporary_password(length=12):
        """Generate a secure temporary password"""
        characters = string.ascii_letters + string.digits + string.punctuation
        # Avoid problematic characters
        characters = characters.replace('"', '').replace("'", '').replace('\\', '')
        return ''.join(secrets.choice(characters) for _ in range(length))


class OrganizationAdmin(admin.ModelAdmin):
    """Admin interface for Organization model"""
    list_display = ('organization_name', 'get_username', 'contact_number', 'created_at')
    search_fields = ('organization_name', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    
    def get_username(self, obj):
        return obj.user.username
    get_username.short_description = 'Username'


# Register models with custom admin
admin.site.register(Student, StudentAccountCreationAdmin)
admin.site.register(Organization, OrganizationAdmin)