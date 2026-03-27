# <div align="center">Kodehax Academy</div>

<div align="center">
  <p><strong>A premium, role-based learning platform built with Django for students, teachers, and administrators.</strong></p>
  <p>Responsive learning flows, AI-assisted grading, skill assessment, daily coding challenges, classroom management, and mobile-aware rendering in one codebase.</p>
</div>

<div align="center">
  <img src="https://img.shields.io/badge/Django-5.2.5-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django 5.2.5" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/Tailwind_CSS-3.4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white" alt="Tailwind CSS" />
  <img src="https://img.shields.io/badge/MySQL-Development-4479A1?style=for-the-badge&logo=mysql&logoColor=white" alt="MySQL" />
  <img src="https://img.shields.io/badge/SQLite-Test%20Settings-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/Gemini-AI%20Assisted-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Gemini AI" />
</div>

---

## Overview

Kodehax Academy is a multi-role LMS focused on practical technical education. The platform combines classroom workflows with AI-assisted teaching tools, skill tracking, daily coding practice, and device-aware interfaces for mobile and desktop users.

The project is structured as a Django monolith with dedicated apps for authentication, classroom operations, performance management, skill assessment, daily challenges, chat, and admin tooling.

## What This Project Does

| Area | Highlights |
| --- | --- |
| Student experience | Registration, login, dashboard, profile, assignments, quiz attempts, coding submissions, skill assessment, daily challenge workspace, chat |
| Teacher workspace | Classroom creation, assignment authoring, quiz generation, code and file grading, AI support tools, performance views, student progress tracking |
| Admin controls | Platform settings, maintenance mode, analytics-style dashboards, student and teacher management |
| Assessment engine | Self-assessment, MCQs, coding exercises, weighted scoring, skill-level classification, weak-topic tracking |
| Daily practice | Personalized daily coding challenges, hints, point deductions, execution sandboxing, leaderboard-oriented point tracking |
| Device support | Mobile template routing for selected views and role-aware UI rendering |

## Core Features

### 1. Role-Based Learning Platform

- Separate flows for students, teachers, and administrators
- Role-aware authentication and redirect handling
- Dedicated dashboards and templates for each product area

### 2. AI-Assisted Teaching Tools

- Teacher-side quiz generation from natural language topics
- AI-generated lecture notes
- AI-assisted coding assignment generation
- AI-assisted grading for file and code submissions

### 3. Skill Assessment System

- Multi-step student assessment flow
- Default MCQ and coding problem seeding
- Weighted scoring across self-assessment, MCQs, and coding tasks
- Skill level classification from beginner to expert
- Strong-topic and weak-topic summaries

### 4. Daily Coding Challenges

- Daily challenge generation based on student skill state
- Difficulty tiers and progressive level unlocking
- Secure Python execution with restricted imports and blocked calls
- Attempt limits, penalties, hint purchases, and points tracking
- Automatic student skill refresh based on challenge performance

### 5. Classroom and Performance Management

- Create classes and manage enrollments
- Create file, code, and quiz assignments
- Auto-grade quizzes
- Manual and AI-supported evaluation flows
- Student performance records and classroom analytics views

### 6. Responsive, Device-Aware Rendering

- Mobile template mapping for key pages
- Dedicated mobile landing and student flows
- Shared backend rendering with device-based template selection
- Tailwind-backed frontend styling

## Product Architecture

```text
kodehax/
|-- kodehax_academy/        # project settings, middleware, mobile rendering, root urls
|-- accounts/               # account flows, OTP/email-related templates and services
|-- users/                  # custom user model, auth redirects, shared entry views
|-- student/                # student dashboards, submissions, chat memory, APIs
|-- teacher/                # classroom, assignments, grading, AI tools, performance
|-- adminpanel/             # platform management, maintenance mode, admin dashboards
|-- skill_assessment/       # assessment content, scoring, skill profile logic
|-- daily_challenges/       # challenge generation, code runner, points, sessions
|-- chat/                   # Gemini client integration and chat views
|-- templates/              # desktop, mobile, shared, role-specific templates
|-- static/                 # Tailwind source, compiled CSS, images
|-- media/                  # uploaded files and generated user content
|-- manage.py               # Django entry point
```

## Main Apps

| App | Responsibility |
| --- | --- |
| `accounts` | Registration, password reset, verification templates, account services |
| `users` | Custom user model, home page, login/logout, role redirects |
| `student` | Student dashboard, assignment submissions, profile, chat, APIs |
| `teacher` | Classroom workflows, assignments, grading, performance, AI authoring tools |
| `adminpanel` | Admin dashboard, site settings, maintenance mode, user management |
| `skill_assessment` | Assessment questions, coding problems, scoring, skill profiles |
| `daily_challenges` | Daily challenge generation, sandboxed execution, points, sessions |
| `chat` | Gemini client integration and chat endpoints |

## Technology Stack

| Layer | Tools |
| --- | --- |
| Backend | Django, Python |
| Database | MySQL by default, SQLite for test settings, PostgreSQL-ready via `dj-database-url` |
| Frontend | Django Templates, Tailwind CSS, PostCSS, Autoprefixer |
| AI integration | Google Gemini via `google-genai` |
| Static serving | WhiteNoise |
| Media and storage support | Cloudinary and Django Storages dependencies present |
| Process and deployment support | Gunicorn, Docker |

## Local Setup

### Prerequisites

- Python 3.10 or newer
- Node.js and npm
- MySQL for the default local settings
- Git

### 1. Clone the repository

```bash
git clone https://github.com/DhruvarajK/kodehax_academy.git
cd kodehax_academy
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

macOS / Linux:

```bash
source venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install frontend dependencies

```bash
npm install
```

### 5. Configure environment variables

Create a `.env` file in the project root using `.env.example` as the starting point.

Suggested variables:

```env
DEBUG=True
PRODUCTION=False
SECRET_KEY=replace-me
ALLOWED_HOSTS=127.0.0.1,localhost
GEMINI_API_KEY=replace-me
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=True
DAILY_CHALLENGE_TIMEZONE=Asia/Kolkata
DAILY_CHALLENGE_PUBLISH_HOUR=10
DB_URL=
```

### 6. Configure the database

By default, the current settings file expects MySQL in development:

```text
ENGINE: django.db.backends.mysql
NAME: kodehax_academy
USER: root
HOST: localhost
PORT: 3306
```

If you prefer a lightweight local test setup, the project also includes `kodehax_academy.test_settings`, which switches to SQLite.

### 7. Run migrations

```bash
python manage.py migrate
```

### 8. Create a superuser

```bash
python manage.py createsuperuser
```

### 9. Build frontend assets

```bash
npm run tailwind:build
```

For development:

```bash
npm run tailwind:watch
```

### 10. Start the server

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Useful Commands

### Run with SQLite test settings

```bash
python manage.py runserver --settings=kodehax_academy.test_settings
```

### Tailwind commands

```bash
npm run tailwind:build
npm run tailwind:watch
```

### Project utility commands

```bash
python manage.py inspect_quizzes --limit 2
python manage.py export_recent_quiz_answers --limit 10 --output ans_debug.txt
python manage.py regrade_quiz 5 Mubashir114
```

## Environment Notes

- `GEMINI_API_KEY` enables AI-backed quiz generation, notes generation, coding assignment generation, and grading flows.
- `DAILY_CHALLENGE_TIMEZONE` and `DAILY_CHALLENGE_PUBLISH_HOUR` control when daily challenges become active.
- Email settings fall back to the console backend when SMTP credentials are not configured.
- `PRODUCTION=True` activates database parsing through `DB_URL`.

## Notable Implementation Details

### Skill Assessment

- Seeds default assessment questions and coding problems
- Scores self-assessment, MCQs, and coding separately
- Produces a combined final skill score
- Stores weak topics and strong topics for future challenge generation

### Daily Challenges

- Generates question sets from skill level and weak-topic context
- Executes student code in a restricted runner
- Tracks runtime, compilation, timeout, failed tests, penalties, and points
- Refreshes challenge-set summaries and student points automatically

### Teacher AI Tooling

- Builds quizzes from topic prompts
- Produces classroom notes
- Creates coding assignments in a structured format
- Grades code and uploaded files with AI-backed feedback

### Mobile Rendering

- Uses `render_for_device(...)` to map selected desktop templates to mobile-specific templates
- Keeps the backend flow unified while allowing dedicated mobile UX where needed

## Current Repository Notes

- The project contains both desktop and mobile templates under `templates/`
- Root-level compatibility scripts are still present, but utility work has been moved into Django management commands
- The current default local database configuration is MySQL, so `mysqlclient` must be installed for the default settings to boot cleanly

## Roadmap Ideas

- Add automated test coverage for core student and teacher workflows
- Move sensitive development defaults fully into environment variables
- Add richer dashboard analytics and reporting
- Expand mobile-specific coverage for more classroom screens
- Add CI for migrations, linting, and template build validation

## License

This repository does not currently declare a license. Add one before public distribution if you plan to open-source the project.
