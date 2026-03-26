<div align="center">
  <h1>Kodehax Academy</h1>
  <p>A comprehensive Learning Management System built with Django.</p>
  
  <p>
    <img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=green" alt="Django" />
    <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
    <img src="https://img.shields.io/badge/Gemini_AI-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Gemini AI" />
  </p>
</div>

<br />

## About The Project

Kodehax Academy is a modern, feature-rich Learning Management System (LMS) designed to facilitate seamless interaction between students, teachers, and administrators. It comes bundled with advanced capabilities like AI-integrated skill assessments, daily coding challenges, and real-time chat.

## Key Features

*   **Student Portal**: View courses, attempt quizzes, participate in daily challenges, and track learning progress.
*   **Teacher Dashboard**: Manage courses, grade assignments, and monitor student performance.
*   **Skill Assessment**: AI-powered (Google Gemini) grading and skill evaluation for students.
*   **Daily Challenges**: Automated coding challenges published daily based on configurable timezones.
*   **Real-Time Chat**: Integrated chat application for student-teacher communication.
*   **Robust Administration**: Comprehensive admin panel for user and content management.

## Technology Stack

*   **Backend Framework**: Django 5.2.5
*   **Database**: SQLite (Development) / PostgreSQL (Production)
*   **AI Integration**: Google GenAI
*   **Static & Media Handling**: WhiteNoise & Cloudinary Storage
*   **Authentication**: Django Rest Framework SimpleJWT

## Installation & Setup

Follow these steps to set up the project locally:

### Prerequisites

*   Python 3.10+
*   pip & virtualenv
*   Git

### Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/DhruvarajK/kodehax_academy.git
    cd kodehax_academy
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    # On Windows:
    venv\Scripts\activate
    # On Unix or MacOS:
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure environment variables:**
    *   Rename `.env.example` to `.env` or create a new `.env` file in the root directory.
    *   Fill in the required variables (e.g., `SECRET_KEY`, `GEMINI_API_KEY`, Database credentials).

5.  **Apply database migrations:**
    ```bash
    python manage.py migrate
    ```

6.  **Create a superuser:**
    ```bash
    python manage.py createsuperuser
    ```

7.  **Run the development server:**
    ```bash
    python manage.py runserver
    ```

The application will be available at ``.

## Environment Variables

Refer to `.env.example` for the required configuration. Key variables include:

*   `SECRET_KEY`: Django secret key
*   `DEBUG`: `True` for development, `False` for production
*   `ALLOWED_HOSTS`: Domain names expected to serve the application
*   `DB_URL`: Database connection URL for production
*   `GEMINI_API_KEY`: API key for Google GenAI features
*   `DAILY_CHALLENGE_TIMEZONE`: e.g., `Asia/Kolkata`

<br />
<div align="center">
  <img src="https://img.shields.io/badge/Made%20with-Django-092E20?style=for-the-badge&logo=django" alt="Made with Django" />
</div>
