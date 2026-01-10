import random
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from main.models import Organization, Student, Event, Attendance, AIInsight
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Seeds the database with demo data for the hackathon'

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding data...")

        # 1. Use existing organization or create one
        try:
            # Try to use the existing CES-admin user's organization
            user = User.objects.get(username="CES-admin")
            org = user.organization
        except User.DoesNotExist:
            # Fallback: create a new organization
            user, _ = User.objects.get_or_create(username="ces_admin")
            user.set_password("password123")
            user.save()
            org, _ = Organization.objects.get_or_create(user=user, organization_name="College of Engineering Studies")

        # 2. Create 50 Fake Students
        courses = ['BSCS', 'BSIT', 'BSIS']
        students = []
        for i in range(1, 51):
            student, _ = Student.objects.get_or_create(
                student_id=f"2026-{1000+i}",
                defaults={
                    'rfid_uid': f"UID-{random.randint(10000, 99999)}",
                    'first_name': f"Student_{i}",
                    'last_name': "Test",
                    'course': random.choice(courses),
                    'year_level': random.randint(1, 4),
                    'organization': org
                }
            )
            students.append(student)

        # 3. Create 3 Events (2 Past, 1 Current)
        event1 = Event.objects.create(
            organization=org, title="Python Workshop", 
            event_date=timezone.now().date() - timedelta(days=7),
            start_time="09:00", end_time="12:00", is_active=False
        )
        
        event2 = Event.objects.create(
            organization=org, title="Hackathon Orientation", 
            event_date=timezone.now().date() - timedelta(days=2),
            start_time="13:00", end_time="16:00", is_active=False
        )

        current_event = Event.objects.create(
            organization=org, title="Live Demo Event", 
            event_date=timezone.now().date(),
            start_time="08:00", end_time="17:00", is_active=True
        )

        # 4. Create Random Attendance for Past Events
        for event in [event1, event2]:
            sampled_students = random.sample(students, random.randint(25, 45))
            for s in sampled_students:
                Attendance.objects.get_or_create(event=event, student=s)

        # 5. Create Mock AI Insights
        AIInsight.objects.create(
            event=event1,
            type='attendance',
            title="High Engagement",
            content="BSCS students showed 90% attendance rate for this technical workshop.",
            score=90.0
        )

        self.stdout.write(self.style.SUCCESS('Successfully seeded demo data!'))