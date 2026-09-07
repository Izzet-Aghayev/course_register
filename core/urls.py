from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('student/login/', views.student_login_view, name='student_login'),
    path('student/logout/', views.student_logout_view, name='student_logout'),
    path('', views.landing_page, name='landing_page'),
    path('dashboard/', views.dashboard, name='dashboard'),

    path('teachers/', views.teacher_list, name='teacher_list'),
    path('teachers/create/', views.teacher_create, name='teacher_create'),
    path('teachers/<int:pk>/update/', views.teacher_update, name='teacher_update'),
    path('teachers/<int:pk>/delete/', views.teacher_delete, name='teacher_delete'),

    path('classes/', views.class_list, name='class_list'),
    path('classes/create/', views.class_create, name='class_create'),
    path('classes/<int:pk>/update/', views.class_update, name='class_update'),
    path('classes/<int:pk>/delete/', views.class_delete, name='class_delete'),
    path('classes/<int:pk>/', views.class_detail, name='class_detail'),

    path('roster/', views.roster_list, name='roster_list'),
    path('roster/create/', views.roster_create, name='roster_create'),
    path('roster/<int:pk>/update/', views.roster_update, name='roster_update'),
    path('roster/<int:pk>/delete/', views.roster_delete, name='roster_delete'),

    path('students/', views.student_list, name='student_list'),
    path('students/credentials/', views.student_account_list, name='student_account_list'),
    path('students/credentials-list/', views.student_account_list, name='credentials_list'),
    path('students/new/', views.new_student_create, name='new_student_create'),
    path('students/enroll/', views.student_enroll, name='student_enroll'),
    path('students/<int:student_id>/enroll/', views.student_direct_enroll, name='student_direct_enroll'),
    path('students/<int:student_id>/assign-class/', views.student_assign_class, name='student_assign_class'),
    path('students/<int:pk>/update/', views.student_update, name='student_update'),
    path('students/<int:pk>/delete/', views.student_delete, name='student_delete'),

    path('lessons/', views.lesson_list, name='lesson_list'),
    path('lessons/create/', views.lesson_create, name='lesson_create'),
    path('lessons/<int:pk>/', views.lesson_detail, name='lesson_detail'),
    path('lessons/<int:pk>/update/', views.lesson_update, name='lesson_update'),
    path('lessons/<int:pk>/delete/', views.lesson_delete, name='lesson_delete'),
    path('lessons/<int:pk>/attendance/', views.lesson_attendance, name='lesson_attendance'),
    path('lessons/<int:pk>/activate/', views.lesson_activate, name='lesson_activate'),
    path('lessons/<int:pk>/deactivate/', views.lesson_deactivate, name='lesson_deactivate'),

    path('reklamlar/', views.reklam_list, name='reklam_list'),
    path('reklamlar/create/', views.reklam_create, name='reklam_create'),
    path('reklamlar/<int:pk>/', views.reklam_detail_public, name='reklam_detail'),
    path('reklamlar/<int:pk>/admin/', views.reklam_detail, name='reklam_detail_admin'),
    path('reklamlar/<int:pk>/update/', views.reklam_update, name='reklam_update'),
    path('reklamlar/<int:pk>/delete/', views.reklam_delete, name='reklam_delete'),

    path('teacher-application/submit/', views.teacher_application_submit, name='teacher_application_submit'),
    path('feedback/submit/', views.feedback_submit, name='feedback_submit'),
]
