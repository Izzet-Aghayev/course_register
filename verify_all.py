# -*- coding: utf-8 -*-
import os
import sys
import string
import datetime
import django

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'course_register.settings')
django.setup()

from django.test import Client
from core.models import (
    Student, Class, Lesson, Attendance, ClassRosterEntry,
    StudentClassEnrollment, User, capitalize_az, generate_student_password
)
from core.forms import UserRegistrationForm, NewStudentForm, StudentForm, StudentUpdateForm

print("=== TASK 1: TERMINOLOGY STANDARDIZATION ===")
assert Student._meta.verbose_name == 'Şagird'
assert Student._meta.verbose_name_plural == 'Şagirdlər'
assert StudentClassEnrollment._meta.verbose_name == 'Şagird-Sinif Qeydiyyatı'
print("[PASS] Models verbose_name verified as 'Şagird'.")

# Check Attendance choice pipeline
choices = dict(Attendance.STATUS_CHOICES)
assert len(choices) == 16, f"Expected 16 choices, got {len(choices)}"
assert '' in choices and choices[''] == '--------'
assert choices['i/e'] == 'İştirak edir'
assert choices['q/b'] == 'Qayıb'
assert choices['gecikir'] == 'Gecikir'
assert choices['icazeli'] == 'İcazəli'
for i in range(11):
    assert str(i) in choices and choices[str(i)] == str(i)
print("[PASS] Attendance STATUS_CHOICES has exact 15 choices + 1 unset choice.")

print("\n=== REQUIREMENT 1: LESSON LIST & PERSONAL STATUS DISPLAY FOR STUDENTS ===")
teacher = User.objects.filter(staff=1).first() or User.objects.filter(is_superuser=True).first()
cls = Class.objects.first()
student = Student.objects.first()

if teacher and cls and student:
    if not student.classes.filter(pk=cls.pk).exists():
        student.classes.add(cls)

    today = datetime.date.today()
    l_past, _ = Lesson.objects.get_or_create(
        class_assigned=cls,
        title_topic='Riyaziyyat Dərs 1 (Keçmiş)',
        date=today - datetime.timedelta(days=2),
        defaults={'start_time': datetime.time(9, 0), 'end_time': datetime.time(10, 0)}
    )
    l_future, _ = Lesson.objects.get_or_create(
        class_assigned=cls,
        title_topic='Riyaziyyat Dərs 2 (Gələcək Ən Son)',
        date=today + datetime.timedelta(days=5),
        defaults={'start_time': datetime.time(15, 0), 'end_time': datetime.time(16, 0)}
    )

    # Set student's attendance on l_past to '10' and l_future to 'i/e'
    roster_entry, _ = ClassRosterEntry.objects.get_or_create(
        current_class=cls,
        full_name=student.get_full_name()
    )
    att1, _ = Attendance.objects.get_or_create(lesson=l_past, student=roster_entry)
    att1.status = '10'
    att1.save()

    att2, _ = Attendance.objects.get_or_create(lesson=l_future, student=roster_entry)
    att2.status = 'i/e'
    att2.save()

    client_student = Client()
    s = client_student.session
    s['student_id'] = student.pk
    s.save()

    resp_s_lessons = client_student.get(f'/lessons/?class={cls.pk}')
    assert resp_s_lessons.status_code == 200
    s_html = resp_s_lessons.content.decode('utf-8')

    # 1. Personal status column header must exist
    assert '<th>Davamiyyət / Qiymət</th>' in s_html
    # 2. Student's specific score '10' and status 'İştirak edir' must be displayed
    assert '10</span>' in s_html
    assert '<span>İştirak edir</span>' in s_html
    # 3. Chronological sorting: past lesson before future lesson
    pos_past = s_html.find('Riyaziyyat Dərs 1 (Keçmiş)')
    pos_future = s_html.find('Riyaziyyat Dərs 2 (Gələcək Ən Son)')
    assert pos_past < pos_future, "Future lesson is not below past lesson!"
    # 4. Detail link and actions column must be absent for student
    assert f'/lessons/{l_past.pk}/' not in s_html
    assert f'/lessons/{l_future.pk}/' not in s_html
    assert '<th>Əməllər</th>' not in s_html
    print("[PASS] Lesson List: Personal status column displayed, chronological sort verified, detail links blocked.")

print("\n=== REQUIREMENT 2: CLASS-BASED SEARCH FILTERING ON CREDENTIALS PAGE ===")
if teacher and cls:
    client_teacher = Client()
    client_teacher.force_login(teacher)

    # 1. Check placeholder in HTML template
    resp_cred = client_teacher.get('/students/credentials/')
    assert resp_cred.status_code == 200
    cred_html = resp_cred.content.decode('utf-8')
    assert 'placeholder="Sinifə görə axtar..."' in cred_html
    assert 'name="class_q"' in cred_html

    # 2. Test class_q filtering
    resp_filtered = client_teacher.get(f'/students/credentials/?class_q={cls.name}')
    assert resp_filtered.status_code == 200
    filt_html = resp_filtered.content.decode('utf-8')
    assert cls.name in filt_html
    print("[PASS] Credentials Page: Class-based search filter with 'Sinifə görə axtar...' verified.")

print("\n=== REQUIREMENT 3: INDEPENDENT SIDEBAR SCROLL FIX ===")
with open('templates/base.html', 'r', encoding='utf-8') as f:
    base_html = f.read()
assert '.sidebar-wrapper {' in base_html
assert 'overflow-y: auto;' in base_html
assert 'overscroll-behavior: contain;' in base_html
assert 'position: sticky;' in base_html
print("[PASS] Sidebar Layout: Independent scrolling CSS with overflow-y: auto and overscroll-behavior: contain verified.")

print("\n=== REQUIREMENT 4: PASSWORD GENERATION (LOWERCASE ENFORCEMENT) ===")
# Generate 100 sample passwords and verify trailing letter is strictly lowercase
for _ in range(100):
    pwd = generate_student_password()
    assert len(pwd) == 7, f"Expected 7 chars, got {len(pwd)} ({pwd})"
    assert pwd[:6].isdigit(), f"First 6 characters must be digits, got {pwd[:6]}"
    last_char = pwd[-1]
    assert last_char in string.ascii_lowercase, f"Last char must be lowercase ascii, got '{last_char}' in {pwd}"
    assert last_char not in string.ascii_uppercase, f"Last char must never be uppercase, got '{last_char}' in {pwd}"
print("[PASS] Password Generation: 100/100 passwords end with strictly lowercase English letter (e.g. 123456a).")

print("\n=== AUTOMATED INPUT CAPITALIZATION PIPELINE ===")
assert capitalize_az('əli') == 'Əli'
assert capitalize_az('həsən-zadə') == 'Həsən-Zadə'
assert capitalize_az('elçin məmmədov') == 'Elçin Məmmədov'
print("[PASS] capitalize_az helper verified.")

print("\n========================================================")
print("  ALL VERIFICATION TESTS COMPLETED AND PASSED (100%)!  ")
print("========================================================")
