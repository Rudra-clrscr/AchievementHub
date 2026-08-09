# AchievementHub — Synopsis Reference

Source material for writing the project synopsis. Everything under "Implemented Features" and "System Workflow" describes what is **actually built and working** in the codebase as of 2026-08-09 — safe to present as delivered functionality. The "Future Scope" section is explicitly separated out; do not present those as completed work.

---

## 1. Title

**AchievementHub — A Centralized Digital Repository for Academic and Professional Achievement Management**

## 2. Problem Statement

Educational institutions track student and faculty achievements (certificates, publications, patents, internships, event participation, and more) through fragmented, manual processes — physical documents, scattered spreadsheets, or department-specific systems with no central verification workflow. This makes it difficult to:

- Verify the authenticity of a claimed achievement.
- Get an institution-wide view of student/faculty accomplishments.
- Showcase verified achievements publicly (to recruiters, parents, accreditation visits) without manually compiling records.
- Manage the storage of supporting proof documents (certificates, scanned pages, presentations) without accumulating unmanageable file sizes.

## 3. Objectives

1. Provide a single platform where students (and faculty) can submit achievements with supporting proof documents.
2. Implement a role-based, multi-tier verification workflow so submissions are checked before being considered official.
3. Automatically and intelligently compress uploaded proof files — of *any* type or size — so storage stays efficient without manual intervention or rejecting large files.
4. Offer a public-facing feed showcasing verified achievements, browsable without login.
5. Give administrators tools to manage the student roster and verification assignments.

## 4. Scope

Covers: student self-registration, achievement submission (any category, any file type), a two-tier verification workflow (faculty coordinator → department admin), a public achievement feed with search/filter, a student/faculty profile view, and automatic file compression at upload time.

Out of scope for the current build (see Future Scope): analytics/accreditation reporting, gamification/leaderboards, OCR-based certificate verification, third-party integrations (DigiLocker, institutional ERPs).

## 5. Implemented Features

### 5.1 Authentication & Roles
- JWT-based authentication (`python-jose`), bcrypt password hashing (`passlib`).
- **Student**: self-service registration (name, email, password, in-house/out-house type, optional department).
- **Faculty Coordinator**: verifies achievements only for their specifically assigned students.
- **Admin (HOD / Clerk)**: verifies achievements for every student in their department, and manages department roster + coordinator assignments.
- **Principal**: role exists in the schema, reserved for future institution-wide reporting (not wired to a UI yet).
- Faculty/Admin/Principal accounts are institution-provisioned (seeded), not self-registered — verification authority isn't something a user can grant themselves.

### 5.2 Achievement Submission
- A single, flexible achievement model covers all categories — not five rigid forms. A student or faculty member picks a category from a predefined taxonomy and fills in title, sub-category, and any category-specific details, then attaches one proof file.
- **Student categories:** Academic Achievements, Research & Publications, Intellectual Property, Internship & Industrial Training, Certifications, Technical Competitions, Project Achievements, Event Participation, Leadership & Club Activities, Sports, Cultural Activities, Placement & Career, Community Service, Awards & Recognition.
- **Faculty categories:** Academic Achievements, Research Publications, Intellectual Property, Grants & Funding, Teaching & Learning, Faculty Development, Professional Memberships, Administrative Responsibilities, Student Mentorship, Consultancy & Industry Collaboration, Invited Talks, Awards & Recognition, Editorial & Review Activities, Event Organization.
- Every submission starts in **pending** status and is invisible to the public feed until verified.

### 5.3 Verification Workflow
1. Student/faculty submits → status = `pending`.
2. It appears in the queue of whoever has jurisdiction: the student's assigned faculty coordinator, or any admin in their department.
3. The verifier approves or rejects, optionally attaching a remark (e.g. reason for rejection) — stored alongside the record.
4. On approval, `verified_by` and `verified_at` are stamped, and the record becomes visible on the public feed.
5. Admins additionally manage which faculty coordinator each student is assigned to, scoped to their own department.

### 5.4 Automatic File Compression — a core technical feature
This is the project's most distinctive engineering component and worth featuring prominently in the synopsis: **any file, of any type or size, can be uploaded** — the system compresses it automatically rather than rejecting oversized files or leaving storage bloated.

- **Images** (JPEG/PNG/etc.): classified as photo, graphic, or near-text-scan content, then routed to the best-fitting codec — continuous-tone photos to JPEG, flat-color graphics/screenshots and scanned text to WebP (lossy or lossless as appropriate) — rather than one-size-fits-all compression, to avoid visible artifacts on content that's sensitive to them.
- **PDFs**: every embedded image is decoded and recompressed individually against a size budget; non-content "editor round-trip" data some design tools embed (e.g. an entire native source file bundled in for re-editing) is stripped, since it's never rendered by a PDF viewer.
- **Office documents** (.docx/.pptx/.xlsx): embedded media is recompressed in place without altering the document structure, so the file still opens normally.
- **Safety guarantee**: compression never makes a file larger than what was uploaded — if a compression attempt doesn't help, the original bytes are kept instead, checked at both the whole-file and per-embedded-image level.
- Target: proof files land around 250KB without visible quality loss for the typical case (a single certificate/photo); multi-image documents are allowed to land higher rather than being crushed to the point of illegibility.
- Only the resulting file's URL is stored in the database — actual bytes live in object storage (Supabase Storage), keeping the database itself lightweight.

### 5.5 Public Achievement Feed
- No login required — browsable by anyone (prospective employers, parents, visitors).
- "Latest Achievements" grid (thumbnail-first, YouTube-style layout) and a "Top Achievements" marquee for records an admin has marked as featured.
- Search by title, filter by category and by owner type (student/faculty).
- Each entry opens a detail page rendering the actual proof document (PDF viewer, image, or download link) alongside submitter name, category, and verification date.

### 5.6 Profile Page
- Shows the logged-in user's name, email, and a breakdown of their own achievement count per category.
- Reachable from any authenticated page; a persistent link is also provided back to the public feed.

## 6. Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy ORM, Alembic (migrations) |
| Database | PostgreSQL (hosted on Supabase) |
| File storage | Supabase Storage (object storage — only URLs persisted in the DB) |
| Image/PDF processing | Pillow, PyMuPDF |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Frontend | React, TypeScript, Vite |
| Backend hosting | Render |
| Frontend hosting | Vercel |

## 7. System Architecture (brief)

Three-tier: React SPA frontend ↔ FastAPI REST backend ↔ PostgreSQL + object storage. The backend exposes REST endpoints under `/auth`, `/achievements`, `/students`, `/departments`, `/feed`, and `/uploads`. All achievement types share one database table with a flexible metadata column, driven by a shared submit → pending → verify pipeline rather than duplicated logic per category.

## 8. Database Design (core entities)

- **Student** — profile, department, assigned coordinator.
- **Employee** — profile, role (principal / admin_hod / admin_clerk / faculty_coordinator), department.
- **Department**.
- **Achievement** — title, category, sub-category, flexible metadata (JSON, for category-specific fields like patent number or publication venue), owner (student or employee), file URL, thumbnail URL, status (pending/approved/rejected), submission and verification timestamps, verifier reference, featured flag.

## 9. Future Scope

Presented in the original project pitch and worth listing as roadmap items, but **not yet implemented** — do not describe these as current functionality:
- Leaderboards / gamification (points, badges) for recognition.
- Analytics dashboards and automated reports for accreditation bodies (NAAC, NBA, NIRF).
- OCR-based automatic certificate verification.
- Integration with DigiLocker, National Academic Depository, or institutional ERPs.
- Mobile application.
- Principal-level institution-wide monitoring dashboard (role exists, UI doesn't yet).
