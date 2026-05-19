# Implementation Plan - User Courses & Certificates

Extend the LMS system to allow users to contribute courses and enable admins to issue certificates.

## User Review Required

> [!IMPORTANT]
> - Users will now be able to create courses. These courses will be visible in the catalog.
> - Certificates will be issued manually by admins once they verify a user has completed 100% of a course.

## Proposed Changes

### Database Schema

#### [MODIFY] [app.py](file:///c:/Users/acer/OneDrive%20-%20ELCOT/Desktop/project%201/app.py)
- Update `courses` table in `init_db()`:
    - Add `creator_id` (INTEGER)
    - Add `creator_type` (TEXT: 'admin' or 'user')
- [NEW] Create `certificates` table:
    - `id`, `user_id`, `course_id`, `issued_at`, `certificate_code`

### User Course Creation

#### [NEW] [user_courses.html](file:///c:/Users/acer/OneDrive%20-%20ELCOT/Desktop/project%201/templates/user_courses.html)
- Page for users to manage courses they have created.

#### [MODIFY] [app.py](file:///c:/Users/acer/OneDrive%20-%20ELCOT/Desktop/project%201/app.py)
- Add routes:
    - `/my_created_courses` (GET)
    - `/course/create` (GET, POST)
    - `/my_course/<course_id>/lessons` (GET, POST) - Users can manage lessons for their own courses.

### Certificates

#### [NEW] [admin_certificates.html](file:///c:/Users/acer/OneDrive%20-%20ELCOT/Desktop/project%201/templates/admin_certificates.html)
- Admin interface to see course completions and issue certificates.

#### [NEW] [certificate_template.html](file:///c:/Users/acer/OneDrive%20-%20ELCOT/Desktop/project%201/templates/certificate_view.html)
- A beautiful certificate view that users can print or share.

#### [MODIFY] [app.py](file:///c:/Users/acer/OneDrive%20-%20ELCOT/Desktop/project%201/app.py)
- Add routes:
    - `/admin/certificates` (GET) - Overview of completions.
    - `/admin/issue_certificate/<user_id>/<course_id>` (POST).
    - `/my_certificates` (GET) - User view of their certificates.
    - `/certificate/view/<certificate_code>` (GET).

## Verification Plan

### Manual Verification
1. Log in as a user and create a new course.
2. Add lessons to the course as a user.
3. Log in as another user and enroll in that course.
4. Complete all lessons.
5. Log in as admin and verify the completion shows up.
6. Issue a certificate as admin.
7. Log in as the student and view/verify the certificate.
