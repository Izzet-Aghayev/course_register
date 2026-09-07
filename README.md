# CourseReg - Django Course Registration System

A complete, production-ready Django Course Registration Management System built with Django's classic MVT (Model-View-Template) architecture, MySQL, and Bootstrap 5.

## Tech Stack

- **Django 4.2+** - Classic MVT architecture (NO Django REST Framework)
- **MySQL** - Primary database (replacing default SQLite)
- **Bootstrap 5.3** - Responsive UI with 6 breakpoints (xs, sm, md, lg, xl, xxl)
- **Crispy Forms + Bootstrap 5** - Beautiful, responsive forms

## Features

### Role-Based Access Control

| Feature | Admin | Teacher |
|---------|-------|---------|
| Dashboard access | ✓ | ✓ |
| Manage Teachers (CRUD) | ✓ | ✗ |
| Manage ALL Classes (CRUD) | ✓ | ✗ |
| Manage OWN Classes only (CRUD) | ✗ | ✓ |
| View ALL Student data | ✓ | ✗ |
| View OWN Class Students only | ✗ | ✓ |
| Class detail page + enrolled students | ✓ | ✓ (own classes) |

### Models

1. **User** (extends Django AbstractUser)
   - `staff` (Integer, choices: 1=Teacher/Staff, 0=Regular/Other) **Required**
   - `subject` (CharField, max 60) **Required**
   - `class_assigned` (ForeignKey to Class, nullable)

2. **Class**
   - `name` (CharField, max 150) **Required**
   - `teacher` (ForeignKey to User) **Required**

3. **Student**
   - `full_name` (CharField, max 150) **Required**
   - `current_class` (ForeignKey to Class) **Required**
   - `participants` (CharField, choices: 'i/e', 'q/b', 'ü/z') **Required**

### Responsive Breakpoints (6 sizes)

The UI is fully responsive and tested at:

| Breakpoint | Size | Device |
|-----------|------|--------|
| xs | < 576px | Portrait phones |
| sm | ≥ 576px | Landscape phones |
| md | ≥ 768px | Tablets |
| lg | ≥ 992px | Laptops / Desktops |
| xl | ≥ 1200px | Large Desktops |
| xxl | ≥ 1400px | Ultra-wide monitors |

---

## Quick Start

### 1. Prerequisites

- **Python 3.10+** installed
- **MySQL Server 5.7+** or **MariaDB 10.3+** running locally
- **MySQL client libraries** installed on your system:
  - **Windows (MySQL Installer):** Install "MySQL Connector/C" or "MySQL Client" via MySQL Installer
  - **Alternative for Windows (no MySQL installed):** Use `pymysql` instead of `mysqlclient` — see troubleshooting below
  - **macOS:** `brew install mysql-client pkg-config`
  - **Ubuntu/Debian:** `sudo apt install python3-dev default-libmysqlclient-dev build-essential pkg-config`

### 2. Clone/Setup Project

```bash
cd c:\Users\İzzet\Documents\trae_projects\course_register
```

### 3. Create Virtual Environment (Recommended)

```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **If `mysqlclient` fails to install on Windows:**
> ```bash
> # Option A: Install pre-built wheel (recommended)
> pip install mysqlclient
>
> # Option B: Use PyMySQL instead (simpler, no compiler needed)
> pip uninstall mysqlclient
> pip install pymysql
> ```
> Then add these two lines **at the top** of `course_register/__init__.py`:
> ```python
> import pymysql
> pymysql.install_as_MySQLdb()
> ```

### 5. Create MySQL Database

Open your MySQL shell or GUI (MySQL Workbench, DBeaver, phpMyAdmin, etc.) and run:

```sql
CREATE DATABASE course_register_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'course_user'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON course_register_db.* TO 'course_user'@'localhost';
FLUSH PRIVILEGES;
```

### 6. Configure Database

Open `course_register/settings.py` and update the `DATABASES` configuration:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'course_register_db',          # ← Your database name
        'USER': 'course_user',                  # ← Your MySQL username
        'PASSWORD': 'your_secure_password',     # ← Your MySQL password
        'HOST': 'localhost',                    # ← Database host
        'PORT': '3306',                         # ← Default MySQL port
    }
}
```

### 7. Apply Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 8. Seed Demo Data (Optional but Recommended)

This creates a default admin, 2 teachers, sample classes, and students:

```bash
python manage.py seed_data
```

**Default accounts created:**

| Username | Password | Role | Subject |
|----------|----------|------|---------|
| `admin` | `admin12345` | **Administrator** | Administration |
| `teacher1` | `teacher12345` | **Teacher** | Mathematics |
| `teacher2` | `teacher12345` | **Teacher** | Science |

### 9. OR: Create Superuser Manually

If you skip the seed command, create your own admin account:

```bash
python manage.py createsuperuser
```

### 10. Run Development Server

```bash
python manage.py runserver
```

Then visit: **http://127.0.0.1:8000/**

---

## Project Structure

```
course_register/
├── manage.py
├── requirements.txt
├── course_register/              # Project config package
│   ├── __init__.py
│   ├── asgi.py
│   ├── wsgi.py
│   ├── settings.py               # ← MySQL DATABASES config here
│   └── urls.py
├── core/                          # Main application
│   ├── __init__.py
│   ├── admin.py                  # Django admin registration
│   ├── apps.py
│   ├── forms.py                  # All Django forms (crispy-bootstrap5)
│   ├── models.py                 # User, Class, Student models
│   ├── urls.py                   # App routing
│   ├── views.py                  # Role-based view logic
│   ├── management/
│   │   └── commands/
│   │       └── seed_data.py      # Demo data seeder command
│   └── migrations/
├── templates/                     # All Bootstrap 5 templates
│   ├── base.html                 # Master layout + sidebar + nav
│   ├── auth/
│   │   └── login.html
│   ├── dashboard.html
│   ├── teachers/
│   │   ├── list.html
│   │   ├── form.html
│   │   └── delete.html
│   ├── classes/
│   │   ├── list.html
│   │   ├── form.html
│   │   ├── detail.html           # Class info + enrolled students
│   │   └── delete.html
│   └── students/
│       ├── list.html
│       ├── form.html
│       └── delete.html
└── static/                        # Static assets
    ├── css/custom.css
    └── js/custom.js
```

---

## Permissions & Business Logic Summary

- **Admin (superuser)** has full CRUD over everything via custom frontend dashboard templates (not just Django admin).
- **Class assignment:** When an Admin creates a Class, they *must* explicitly assign it to a Teacher (Class.teacher FK). The class belongs to that teacher, not the admin.
- **Teacher isolation:** A Teacher can **only** see, edit, or delete Classes where `class.teacher == request.user`, and **only** Students enrolled in those classes. They are completely restricted from other teachers' data via QuerySet filtering in every view.
- **Class Details page:** Clicking a class opens its full detail view, showing class info, a participant-type breakdown, and the full student roster — still respecting the admin/teacher separation.

---

## Common Troubleshooting

### mysqlclient won't install on Windows
**Best fix:** Use `pymysql`:
```bash
pip install pymysql
```
Then add to `course_register/__init__.py`:
```python
import pymysql
pymysql.install_as_MySQLdb()
```

### Django can't connect to MySQL
1. Confirm MySQL server is running.
2. Double-check credentials in `settings.py` → `DATABASES`.
3. Test the connection with your MySQL client using the same user/password.
4. Ensure the database name exists (run the `CREATE DATABASE` command).

### Auth errors on login
Make sure you ran either `python manage.py seed_data` or `python manage.py createsuperuser`.

---

## Production Deployment Checklist

Before deploying to production:

1. Set `DEBUG = False` in `settings.py`
2. Change `SECRET_KEY` to a long random string
3. Set `ALLOWED_HOSTS` to your actual domain(s)
4. Run: `python manage.py collectstatic`
5. Use a proper web server (Gunicorn + Nginx, or similar)
6. Enable HTTPS
7. Use environment variables or `.env` for DB credentials

---

## License

Internal project.
