# Implementation Plan - LMS System

Add a Learning Management System (LMS) to the existing attendance and work assignment application. This will allow admins to create courses and lessons, and users to enroll and track their progress.

## Proposed Changes

### Database Schema

- Update `init_db()` in `app.py` to create new tables:
    - `courses`: `id`, `title`, `description`, `thumbnail_url`, `created_at`
    - `lessons`: `id`, `course_id`, `title`, `content`, `video_url`, `order_index`
    - `enrollments`: `id`, `user_id`, `course_id`, `enrolled_at`
    - `user_lesson_progress`: `id`, `user_id`, `lesson_id`, `completed_at`

### Admin Functionality

- New routes and templates for course and lesson management.
- Integration into the admin dashboard.

### User Functionality

- New routes and templates for course browsing, enrollment, and lesson viewing.
- Progress tracking for lessons.

## Verification Plan

- Manual testing of all new routes and functionality.
