<p align="center">
  <img src="assets/kodehax_banner.png" alt="Kodehax Academy Banner" width="100%">
</p>

<h1 align="center">Kodehax Academy</h1>
<h3 align="center">AI-Powered Learning &amp; Developer Education Platform</h3>

<p align="center">
  A production-engineered developer education platform integrating structured classrooms, context-aware AI tutoring, adaptive skill assessments, and daily coding challenges.
</p>

<p align="center">
  <a href="https://www.djangoproject.com/"><img src="https://img.shields.io/badge/Django-5.2.5-092E20?logo=django&logoColor=white&style=for-the-badge" alt="Django"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12.12-3776AB?logo=python&logoColor=white&style=for-the-badge" alt="Python"></a>
  <a href="https://www.mysql.com/"><img src="https://img.shields.io/badge/MySQL-8.0+-4479A1?logo=mysql&logoColor=white&style=for-the-badge" alt="MySQL"></a>
  <a href="https://tailwindcss.com/"><img src="https://img.shields.io/badge/Tailwind-CSS-06B6D4?logo=tailwindcss&logoColor=white&style=for-the-badge" alt="Tailwind CSS"></a>
  <a href="https://groq.com/"><img src="https://img.shields.io/badge/Groq-AI-F55036?logo=groq&logoColor=white&style=for-the-badge" alt="Groq AI"></a>
  <a href="https://www.brevo.com/"><img src="https://img.shields.io/badge/Brevo-Email-0B996F?logo=brevo&logoColor=white&style=for-the-badge" alt="Brevo"></a>
  <a href="https://render.com/"><img src="https://img.shields.io/badge/Render-Deployment-46E3B7?logo=render&logoColor=black&style=for-the-badge" alt="Render"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
</p>

<p align="center">
  <a href="#-product-snapshot">Snapshot</a> •
  <a href="#-product-experience">Experience</a> •
  <a href="#-core-capabilities">Capabilities</a> •
  <a href="#-system-architecture">Architecture</a> •
  <a href="#-technology-stack">Tech Stack</a> •
  <a href="#-engineering-highlights">Engineering</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-deployment">Deployment</a> •
  <a href="#-documentation">Documentation</a>
</p>

<p align="center">
  <em>Learn live. Build for real.</em>
</p>

---

## 🎯 Product Snapshot

<table width="100%">
  <tr>
    <td width="33%" align="center">
      <h4>🎓 Learn</h4>
      <p>Structured classrooms, modular curriculum, and guided assignment delivery.</p>
    </td>
    <td width="33%" align="center">
      <h4>🤖 Build with AI</h4>
      <p>Context-aware Groq tutoring, lecture synthesis, and automated evaluation.</p>
    </td>
    <td width="33%" align="center">
      <h4>💻 Practice</h4>
      <p>Daily coding challenges, remote code-execution workflow, and real-time scoring.</p>
    </td>
  </tr>
  <tr>
    <td width="33%" align="center">
      <h4>📊 Measure</h4>
      <p>Adaptive skill matrices, progress tracking, and diagnostic performance analytics.</p>
    </td>
    <td width="33%" align="center">
      <h4>🧑‍🏫 Mentor</h4>
      <p>Educator consoles, roster administration, and automated test authoring.</p>
    </td>
    <td width="33%" align="center">
      <h4>🔐 Secure</h4>
      <p>Strict role boundaries, configurable 2FA/OTP, and private signed media storage.</p>
    </td>
  </tr>
</table>

---

## ✦ Product Experience

<p align="center">
  A unified, role-aware interface engineered for student focus, teaching velocity, and platform governance.
</p>

<p align="center">
  <img src="assets/dashboards_preview.png" alt="Kodehax Academy Multi-Role Dashboard Preview" width="95%">
</p>

<p align="center">
  <sub>Multi-role workspace preview: Interactive student learning portal, teacher classroom command center, and platform administrative operations.</sub>
</p>

---

## ⚡ Core Capabilities

<table width="100%">
  <tr>
    <td width="50%" valign="top">
      <h3>🎓 Learning Experience</h3>
      <ul>
        <li><strong>Interactive Classrooms</strong> — Course enrollment, modular progression, and student submission tracking.</li>
        <li><strong>Adaptive Skill Profiles</strong> — Weighted skill classification combining self-assessment, quizzes, and tasks.</li>
        <li><strong>Competency Milestones</strong> — Transparent scoring breakdowns and real-time student mastery indicators.</li>
      </ul>
    </td>
    <td width="50%" valign="top">
      <h3>🤖 AI &amp; Coding Workflows</h3>
      <ul>
        <li><strong>Groq-Powered Tutoring</strong> — Low-latency contextual AI assistant for code explanations, debugging, and Q&amp;A.</li>
        <li><strong>Daily Coding Challenges</strong> — Algorithmic problem generation with isolated execution integration and scoring.</li>
        <li><strong>Intelligent Content Aids</strong> — AI-assisted lecture note synthesis and automated quiz drafting.</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>🧑‍🏫 Teaching &amp; Administration</h3>
      <ul>
        <li><strong>Classroom Management</strong> — Roster controls, enrollment verification, and assignment dispatch.</li>
        <li><strong>Automated Assessment</strong> — Fast test authoring with automated grading and feedback delivery.</li>
        <li><strong>Platform Governance</strong> — System metrics, maintenance mode controls, and teacher verification.</li>
      </ul>
    </td>
    <td width="50%" valign="top">
      <h3>🛡️ Platform &amp; Security Guardrails</h3>
      <ul>
        <li><strong>Role-Based Access (RBAC)</strong> — Strict boundary separation across Student, Teacher, and Admin portals.</li>
        <li><strong>Multi-Factor Security</strong> — Configurable 2FA login, OTP verification, and transactional email via Brevo.</li>
        <li><strong>Private Object Storage</strong> — Backblaze B2 S3 storage with short-lived signed URLs for submitted media.</li>
      </ul>
    </td>
  </tr>
</table>

---

## ⚙️ System Architecture

Kodehax Academy is structured as a modular Django monolith with domain-driven applications, explicit separation of concerns, and clean cloud service integrations. Requests traverse security middleware and device-aware routing before interacting with core business logic, persistence layers, and external APIs.

<p align="center">
  <img src="assets/architecture.png" alt="Kodehax Academy System Architecture &amp; Data Pipeline" width="100%">
</p>

```text
Client Traffic → Django Application Core → Domain Services → Persistence & Cloud APIs
```

- **Ingress & Device Routing** — Responsive desktop and smartphone viewports are dynamically routed through device-aware template middleware.
- **Django Monolith Core** — Django 5.2.5 on Gunicorn coordinates root routing, RBAC authentication, and security middleware across 9 modular applications.
- **Domain Services** — Specialized apps encapsulate accounts/security (`accounts`, `users`), role workflows (`student`, `teacher`, `adminpanel`), practical challenges (`daily_challenges`, `skill_assessment`), and AI services (`chat`).
- **Relational Persistence** — Production workloads rely on a dedicated MySQL 8.0+ database connected via PyMySQL; SQLite is reserved exclusively for the isolated test runner.
- **Durable Media & Static** — Static assets are served via WhiteNoise; student uploads are stored in private Backblaze B2 S3 buckets with time-limited signed URLs.
- **Cloud AI & Integrations** — Groq delivers high-throughput inference for tutoring and quiz generation, Brevo sends transactional emails and OTPs, and a remote code-execution workflow evaluates untrusted code.

**[→ Read the full architecture documentation](docs/ARCHITECTURE.md)**

---

## 🛠️ Technology Stack

<table width="100%">
  <thead>
    <tr>
      <th width="33%" align="left">⚙️ Backend Engineering</th>
      <th width="33%" align="left">🎨 Frontend &amp; Interface</th>
      <th width="33%" align="left">💾 Data &amp; Storage</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td valign="top">
        <a href="https://www.djangoproject.com/"><img src="https://img.shields.io/badge/Django_5.2.5-092E20?style=flat-square&logo=django&logoColor=white" alt="Django"></a><br>
        <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python_3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a><br>
        <a href="https://gunicorn.org/"><img src="https://img.shields.io/badge/Gunicorn_WSGI-499848?style=flat-square&logo=gunicorn&logoColor=white" alt="Gunicorn"></a>
      </td>
      <td valign="top">
        <a href="https://tailwindcss.com/"><img src="https://img.shields.io/badge/Tailwind_CSS_3.4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white" alt="Tailwind CSS"></a><br>
        <img src="https://img.shields.io/badge/Django_Templates-092E20?style=flat-square&logo=html5&logoColor=white" alt="Django Templates"><br>
        <img src="https://img.shields.io/badge/JavaScript_ES6+-F7DF1E?style=flat-square&logo=javascript&logoColor=black" alt="JavaScript">
      </td>
      <td valign="top">
        <a href="https://www.mysql.com/"><img src="https://img.shields.io/badge/MySQL_8.0+-4479A1?style=flat-square&logo=mysql&logoColor=white" alt="MySQL"></a><br>
        <a href="https://www.backblaze.com/b2/cloud-storage.html"><img src="https://img.shields.io/badge/Backblaze_B2_S3-E02424?style=flat-square&logo=backblaze&logoColor=white" alt="Backblaze B2"></a><br>
        <img src="https://img.shields.io/badge/PyMySQL_Client-4479A1?style=flat-square&logo=python&logoColor=white" alt="PyMySQL">
      </td>
    </tr>
    <tr>
      <th align="left">🤖 Artificial Intelligence</th>
      <th align="left">📬 Comms &amp; Delivery</th>
      <th align="left">🚀 Infrastructure &amp; Edge</th>
    </tr>
    <tr>
      <td valign="top">
        <a href="https://groq.com/"><img src="https://img.shields.io/badge/Groq_API-F55036?style=flat-square&logo=groq&logoColor=white" alt="Groq AI"></a><br>
        <sub>Groq-hosted text &amp; vision models</sub>
      </td>
      <td valign="top">
        <a href="https://www.brevo.com/"><img src="https://img.shields.io/badge/Brevo_HTTPS_API-0B996F?style=flat-square&logo=brevo&logoColor=white" alt="Brevo"></a><br>
        <sub>Transactional Email &amp; Login OTPs</sub>
      </td>
      <td valign="top">
        <a href="https://render.com/"><img src="https://img.shields.io/badge/Render_PaaS-46E3B7?style=flat-square&logo=render&logoColor=black" alt="Render"></a><br>
        <img src="https://img.shields.io/badge/WhiteNoise_Static-1F2937?style=flat-square&logoColor=white" alt="WhiteNoise">
      </td>
    </tr>
  </tbody>
</table>

---

## 🧠 Engineering Highlights

<table width="100%">
  <tr>
    <td width="50%" valign="top">
      <h4>🔒 Security &amp; Access Controls</h4>
      <ul>
        <li><strong>Configurable Login 2FA</strong> — Optional two-factor authentication enforcing time-sensitive one-time passwords for account defense.</li>
        <li><strong>Brevo API Transactional Email</strong> — Secure HTTPS API integration handling verification links, invitations, and password resets.</li>
        <li><strong>OTP Security Controls</strong> — Rate-limited, bounded-expiry OTP generation guarding against brute-force and token reuse.</li>
        <li><strong>Role-Based Access Architecture</strong> — Strict operational boundaries isolating Student, Teacher, and Admin permissions.</li>
        <li><strong>Private B2 Media Storage</strong> — Durably stored user uploads on S3-compatible Backblaze B2 using short-lived signed URLs.</li>
        <li><strong>Fail-Closed Production Guardrails</strong> — Application startup halts immediately if required security or database secrets are missing.</li>
      </ul>
    </td>
    <td width="50%" valign="top">
      <h4>⚡ Reliability, Performance &amp; Scale</h4>
      <ul>
        <li><strong>Production MySQL Persistence</strong> — Enforced MySQL 8+ backend with PyMySQL compatibility to prevent silent data drifts.</li>
        <li><strong>Groq Service Abstraction</strong> — Resilient AI integration encapsulating prompt engineering, error handling, and rate limits.</li>
        <li><strong>Query-Optimized Dashboards</strong> — Targeted indexing and pre-fetched relationships preventing N+1 query bottlenecks.</li>
        <li><strong>Responsive Device Routing</strong> — Contextual template resolution providing tailored experiences for mobile and desktop viewports.</li>
        <li><strong>Regression &amp; Security Testing</strong> — Dedicated SQLite test harness validating core application flows without altering production data.</li>
        <li><strong>Deployment Health Checks</strong> — Unauthenticated <code>/health/</code> endpoint supporting deployment health monitoring and rollout checks on Render.</li>
      </ul>
    </td>
  </tr>
</table>

---

## 📂 Project Structure

<details open>
<summary><strong>📁 View Repository Architecture &amp; Key Directories</strong></summary>
<br>

```text
kodehax/
├── accounts/          # Authentication lifecycle, OTP verification, and security flows
├── adminpanel/        # System governance, platform metrics, and maintenance controls
├── assets/            # Architecture diagrams, preview media, and brand graphics
├── chat/              # Contextual Groq AI tutoring service and conversation memory
├── daily_challenges/  # Algorithmic problem generation, isolated execution integration, and scoring
├── docs/              # In-depth architectural, deployment, security, and developer guides
├── kodehax_academy/   # Django project root, WSGI/ASGI, middleware, and route dispatch
├── skill_assessment/  # Weighted evaluation engine, skill rubrics, and diagnostic tests
├── static/            # Tailwind CSS source, compiled assets, and platform iconography
├── student/           # Student learning workspace, classroom views, and submission portal
├── teacher/           # Educator dashboard, curriculum authoring, and assessment tools
├── templates/         # Responsive desktop and device-aware mobile template hierarchy
├── users/             # Custom user model, shared permissions, and profile management
├── manage.py          # Django administrative entry point
└── build.sh           # Deployment pipeline build script for Render
```

</details>

---

## 🚀 Quick Start

### Prerequisites

- [Python](https://www.python.org/) 3.10+ (Production target: Python 3.12.12)
- [Node.js](https://nodejs.org/) (for Tailwind CSS asset compilation)
- [MySQL](https://www.mysql.com/) 8.0+ for local MySQL development (or bundled test settings for SQLite)
- [Groq API key](https://console.groq.com/) for AI-assisted tutoring features

### Local setup

```bash
git clone https://github.com/Mubashir-114/kodehax_academy.git
cd kodehax_academy
python -m venv .venv
# On Windows: .venv\Scripts\activate | On macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
npm ci
cp .env.example .env
```

### Run the application

```bash
python manage.py migrate
npm run tailwind:build
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.

> **Note**: The repository test configuration uses SQLite via `--settings=kodehax_academy.test_settings` and is isolated from the primary MySQL runtime setup.

---

## ⚙️ Configuration

Create a local `.env` file from `.env.example` and keep sensitive credentials private:

```env
PRODUCTION=False
DEBUG=False
SECRET_KEY=replace-with-a-secure-random-key
ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=kodehax_academy
DB_USER=root
DB_PASSWORD=your-database-password
DB_HOST=localhost
DB_PORT=3306
GROQ_API_KEY=your-groq-key
GROQ_TEXT_MODEL=openai/gpt-oss-20b
GROQ_VISION_MODEL=qwen/qwen3.8-27b
BREVO_API_KEY=your-brevo-key
BREVO_SENDER_EMAIL=noreply@example.com
BREVO_SENDER_NAME=Kodehax Academy
MEDIA_STORAGE_BUCKET_NAME=
MEDIA_STORAGE_ACCESS_KEY_ID=
MEDIA_STORAGE_SECRET_ACCESS_KEY=
```

For complete development setup options and environment variable specifications, see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) and [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## 🧪 Testing

Execute the comprehensive test suite with the isolated SQLite test settings:

```bash
python manage.py test --settings=kodehax_academy.test_settings
```

This validates authentication, student/teacher interactions, assessment rubrics, and route-level permissions while keeping tests fast, reliable, and isolated from production databases.

---

## 🔐 Security

Kodehax Academy follows defense-in-depth principles:

- **Environment-Managed Secrets** — Strict credential separation preventing hardcoded API tokens or keys in version control.
- **Fail-Closed Runtime Checks** — Production startup aborts immediately if required host, database, AI, or storage credentials are absent.
- **Private S3-Compatible Media** — Backblaze B2 storage configuration with signed, time-limited URL generation for sensitive student submissions.
- **Hardened Cookie & Transport Security** — HTTPS redirects, secure session cookies, CSRF validation, and HSTS headers enforced in production.

For detailed security guidelines, refer to [docs/SECURITY.md](docs/SECURITY.md).

---

## 🚢 Deployment

Render serves as the primary production deployment target. The platform runs as a native Python + Gunicorn service backed by an external managed MySQL instance:

### Deployment summary

| Component | Target / Configuration |
| :--- | :--- |
| **Platform** | Render (Web Service) |
| **Runtime** | Python 3.12.12 + Gunicorn WSGI |
| **Database** | MySQL 8.0+ (PyMySQL adapter with modern auth support) |
| **Static Assets** | Tailwind CSS compiled during build; served via WhiteNoise |
| **Object Storage** | Backblaze B2 (Private S3 bucket with signed URL expiry) |
| **Email Delivery** | Brevo HTTPS API (Transactional verification and OTP) |
| **Health Check** | `/health/` (unauthenticated liveness probe) |
| **Build Script** | `bash build.sh` |

For step-by-step production configuration, TLS certificate setup, and release procedures, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## 📚 Documentation

Detailed technical manuals and historical review documents are maintained in the repository:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — Comprehensive application topology, module boundaries, and request flow
- [docs/SECURITY.md](docs/SECURITY.md) — Production environment safety, authentication policies, and secret handling
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Step-by-step Render setup, MySQL configuration, and pre-deploy migrations
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — Local developer environment setup, dependency management, and workflow tips
- [PROJECT_REPORT.md](PROJECT_REPORT.md) — Platform audit, quality assurance summary, and release sign-off
- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) — Extended platform overview and domain models
- [GROQ_MIGRATION.md](GROQ_MIGRATION.md) — Groq AI integration design and latency benchmarks
- [CODE_EXECUTION.md](CODE_EXECUTION.md) — Remote code execution transport and sandbox safety specs
- [SECURITY_REVIEW.md](SECURITY_REVIEW.md) — Security audit findings, remediations, and threat vectors

---

## 🗺️ Roadmap

- [ ] Expand automated end-to-end integration suites across student and teacher flows
- [ ] Deepen student learning analytics with skill retention heatmaps
- [ ] Broaden dedicated mobile templates for additional classroom and grading views
- [ ] Implement automated release CI pipelines for database migrations and static asset linting

---

## 🤝 Contributing

Contributions are welcome. Please follow our engineering standards:

1. Create a feature branch from the default branch.
2. Ensure all changes adhere to modular Django application conventions.
3. Validate your changes locally with `python manage.py test --settings=kodehax_academy.test_settings`.
4. Submit a clear pull request describing the implementation rationale.

---

## 📄 License

This project is open-source software licensed under the [MIT License](LICENSE).

<p align="center">Made with ❤️ for practical, AI-assisted technical education.</p>
