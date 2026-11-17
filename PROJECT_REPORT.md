# IIT Madras — Modern Application Development 1 (MAD-1)
## Project Report: Examination Management Portal (EMP)

---

### Candidate & Project Identification
- **Project Title**: Examination Management Portal (EMP)
- **Course**: Modern Application Development 1 (MAD-1)
- **Academic Degree**: IIT Madras BS in Data Science and Applications
- **Student Full Name**: Shreya Pal
- **Student Roll Number**: 25F3002106
- **Student Email Address**: 25f3002106@student.onlinedegree.iitm.ac.in / jeonsamikshita@gmail.com
- **Date of Submission**: November 17, 2026
- **Video Presentation / Demonstration Link**: [Watch the Project Demo on Google Drive](https://drive.google.com/file/d/1KCQ8O46NbcouLB5uCalOvUGKzvFOgWRU/view?usp=drive_link)

---

### Academic Integrity & AI / LLM Usage Declaration
> **Declaration**:
> - **AI Tools Utilized**: Google Antigravity
> - **Nature of Assistance**: Assisted with initial project structure scaffolding, test case formulation, edge-case debugging (timezone conversions, slot capacity accounting), and documentation refinement.
> - **Originality Confirmation**: I hereby affirm that all application logic, database schemas, security controls, server-side validation rules, and implementations strictly comply with the IIT Madras Academic Honor Code. I have thoroughly understood, manually tested, and verified every route, model, and workflow in this codebase and take full personal ownership of this submission.

---

## 1. Why I Built This (The Honest Problem Statement)

If you've ever had to give an online viva or project demo in a massive program like IIT Madras BS, you already know the specific kind of chaos I'm talking about.

Picture this: It's Saturday night. There are 2,000 students enrolled in a course. A single Google Spreadsheet link gets dropped in an announcement channel. Within thirty seconds, fifty anonymous cursors are frantically fighting over Row 142. Someone accidentally hits backspace and deletes three hours of time slots. Two students book the exact same 10:15 AM slot with the same faculty. Meanwhile, an examiner sits in a Google Meet lobby wondering why nobody showed up, while a student waits in a different lobby having an existential crisis.

And when you finally finish your viva? You wait two weeks only to receive a single, mysterious aggregate number like "18/25" on your dashboard with zero feedback on whether your code was bad, your presentation was rushed, or your viva answers were wrong.

This isn't an exaggeration—it's what happens when you try to run academic assessments across an entire university using ad-hoc tools. 

The **Examination Management Portal (EMP)** exists to kill that spreadsheet nightmare once and for all. The goal wasn't just to build another CRUD app to tick off a rubric; it was to build a clean, reliable, collision-free system where:
1. Students can pick their own time slots without conflicting with jobs, classes, or life.
2. Examiners can manage their capacity, record criterion-by-criterion marks, and give real feedback without acting as impromptu tech support.
3. Admins have a single "control room" to supervise schedules, reassign examiners if someone falls sick, and publish results with one click when everything is ready.

---

## 2. The Three Worlds: How the System Actually Works

Rather than building one generic dashboard with a hundred confusing buttons, EMP cleanly separates the universe into three distinct roles, each with its own workflow and rules.

### 2.1 The Student Experience (Keeping It Stress-Free)
For students, simplicity is peace of mind. When a student logs into EMP:
- **Course & Exam Discovery**: They see only the examinations for courses they are enrolled in. Exams display clear badges indicating whether booking is currently open, closed, or upcoming.
- **Collision-Free Booking**: The system automatically checks whether a slot has available seats. If a slot has a capacity of 1, once booked, it instantly locks out others. If a student tries to book two different slots for the same exam, the backend firmly rejects it.
- **Reservation Voucher & Receipts**: Once a slot is booked, students get an instant confirmation voucher with the exact date, time, venue/meeting link, and examiner details.
- **Self-Service Cancellation**: If an emergency arises, students can cancel their booking before the deadline. The system immediately restores the slot's capacity back to the pool for someone else to claim.
- **Transparent Scorecards**: Once results are officially published by the Admin, the student doesn't just see a total score. They get a full breakdown showing exactly how many marks they earned on each rubric criterion (e.g., Code Quality, System Architecture, Viva Q&A) along with the examiner's personalized qualitative feedback.

### 2.2 The Examiner Experience (Focused on Grading, Not Logistics)
Faculty and TAs shouldn't have to manage calendar invites or juggle spreadsheets:
- **Admin Vetting**: Examiners sign up, but their accounts stay in `Pending Approval` until verified by an Administrator, preventing unauthorized individuals from grading students.
- **Flexible Slot Creation**: Once assigned to an exam by Admin, examiners can create time slots tailored to their availability (e.g., four 15-minute viva slots on Wednesday morning) with custom capacity limits and Google Meet/classroom links.
- **Real-Time Candidate Rosters**: Examiners see an organized roster of every student booked into their slots, complete with roll numbers and contact details.
- **Interactive Evaluation Pad**: During or after the viva, the examiner opens an evaluation form pre-populated with the exam's rubric criteria. The form enforces maximum mark limits on each criterion so an evaluator can't accidentally type "50" on a 20-mark criterion. They leave general feedback, submit, and the booking automatically records attendance as `Present`.

### 2.3 The Administrator Experience (The Command Center)
Administrators are the orchestrators who ensure academic integrity across the board:
- **Course & Examination Management**: Admins create courses and configure examinations, including duration, maximum marks, and strict timeline windows (when examiners can create slots vs. when students can book them).
- **Rubric Builder**: Admins define multi-criteria rubrics with weightages and maximum marks. The system dynamically validates that the sum of rubric criteria equals the examination's total marks.
- **Timeline State Machine**: Examinations progress through a strict lifecycle:
  $$\text{Draft} \longrightarrow \text{Slot Creation} \longrightarrow \text{Booking Open} \longrightarrow \text{Closed} \longrightarrow \text{Completed} \longrightarrow \text{Results Published}$$
- **Emergency Rescheduling & Examiner Reassignment**: If an examiner is indisposed or a student faces an emergency, Admins can reassign slots to another approved faculty member or reschedule a candidate to another available slot, with a detailed audit trail timestamped and saved in the booking history.
- **Bulk Results Publication**: Evaluations submitted by examiners stay gated as `Evaluated (Pending Publication)` until the Admin formally reviews the batch and clicks **Publish Results**, pushing scorecards to all student profiles simultaneously.

---

## 3. Technology Stack & Architectural Decisions

I adhered 100% strictly to the IITM MAD-1 project specifications:

| Layer | Technology Used | Why This Choice? |
|---|---|---|
| **Language** | Python 3.11 | Clean syntax, rock-solid datetime handling, and expressive object-oriented patterns. |
| **Web Framework** | Flask 3.x | Lightweight, unopinionated WSGI micro-framework. It doesn't hide magic from you—you control every route, session, and redirect. |
| **Architecture** | Flask Blueprints | Modularized into 4 clean domain packages: `auth`, `admin`, `examiner`, and `student`. |
| **ORM & Database** | Flask-SQLAlchemy / SQLite 3 | Relational database with foreign key cascades and transactions. Zero external database servers required. |
| **Templating** | Jinja2 | Clean server-side HTML rendering with auto-escaping to kill XSS vulnerabilities. |
| **Frontend Styling** | Bootstrap 5.3 + Custom CSS | Responsive, accessible UI that looks professional on both desktop monitors and phones. |
| **Password Security**| Werkzeug Security | Salted PBKDF2:SHA256 password hashing. Raw passwords never touch the database. |
| **Disallowed Stacks**| Strict Compliance | **Zero** React, Angular, Vue, Node.js, MongoDB, or PostgreSQL. Zero core business logic delegated to client-side JS. |

---

## 4. The War Stories: Battles Fought & Bugs Slain

Building software that looks simple on the surface requires solving a lot of nasty edge cases underneath. Here are four real challenges I ran into during development and manual testing that taught me more than any tutorial ever could:

### War Story 1: The Timezone Trap (IST vs. UTC)
During manual testing on macOS, I set up an examination with slot creation starting at 5:58 PM. At 6:11 PM IST, I logged in as an examiner to create slots, only to be greeted with:
> *"Slot creation is not currently open."*

I checked the system clock—it was 6:11 PM! Why was it locked?
**The root cause:** HTML `<input type="datetime-local">` submits naive string timestamps (e.g., `2026-11-16T17:58`). In the backend, comparisons were being done against UTC-aware timestamps (`datetime.now(timezone.utc)`). At 6:11 PM IST (which is 12:41 PM UTC), the backend had blindly tagged `17:58` as UTC, meaning the portal thought the start window was still five hours in the future!
**The fix:** I standardized timestamp conversions across the application using Python's standard `timezone.utc` normalization helper (`_to_utc()`), ensuring wall-clock comparisons always align consistently.

### War Story 2: The "Pending Publication" Ghost Button
After examiners evaluated candidates, students checked their history page and saw their status stuck on `Evaluated (Pending Publication)`. When I logged into the Admin portal to publish the grades, there was no button to publish!
Upon digging into `routes/admin.py`, I found that the backend route `POST /admin/examinations/<exam_id>/publish-results` was already completely written, tested, and working. But in the Jinja2 template (`view.html`), the button was simply missing!
Adding the CSRF-protected "Publish Results" form button with a Javascript confirmation modal completed the circuit. Now, publishing flips both `exam.results_published` and each candidate's `evaluation.is_published` to `True`, unlocking detailed scorecards for students immediately.

### War Story 3: Ghost Capacity & Zombie Rescheduling
Here was a subtle logic bug: when a candidate finishes an exam and their booking status updates to `Completed`, what happens to the slot capacity?
Initially, `Slot.booked_count` was calculated as:
```python
len([b for b in self.bookings if b.status in ('confirmed', 'Booked')])
```
As soon as a student was marked `Completed`, `booked_count` dropped by 1! If a slot had capacity 2 and both students completed their viva, the slot suddenly showed "2 seats available," allowing new students to book into a finished slot!
I updated `booked_count` to count `('confirmed', 'Booked', 'Completed')`. Furthermore, I locked down the Admin rescheduling route so that completed bookings, published examinations, or evaluated candidates cannot be accidentally rescheduled via direct URL manipulation.

### War Story 4: Premature Examination Completion
What if an administrator accidentally clicks "Mark Completed" on Monday morning when candidate slots are still scheduled for Tuesday afternoon?
To prevent accidental premature completion, I implemented an active future-slot validator:
```python
def has_active_future_slots(self, check_time=None) -> bool:
    for slot in self.slots:
        if slot.status != 'Cancelled' and slot.end_time > now:
            return True
    return False
```
If any non-cancelled slot still concludes in the future, the Admin route strictly rejects completion with a clear alert:
> *"Cannot mark examination as Completed while future examination slots are still scheduled. All examination slots must conclude or be cancelled first."*

---

## 5. Verification & Testing: Does It Actually Hold Up?

Writing code without tests is like walking on a tightrope without a net. To ensure EMP doesn't break when edge cases collide, I wrote a comprehensive automated test suite covering all four user roles and integration workflows.

### Test Suite Summary
- **Test Framework**: Python standard `unittest` library (zero third-party test dependencies required).
- **Test Database**: In-memory SQLite (`sqlite:///:memory:`) initialized fresh per test case for complete isolation.
- **Total Test Cases**: **77 Automated Tests**
- **Test Execution Time**: **38.0 seconds**
- **Pass Rate**: **100% (77 passed, 0 failures, 0 errors)**

```text
Ran 77 tests in 38.066s

OK
```

### Key Behaviors Verified by Tests
1. **Role-Based Access Control**: Students cannot access admin routes; unapproved examiners are stopped by decorators; unauthenticated visitors are redirected to login.
2. **Capacity Concurrency & Seat Locking**: Verified that when a slot reaches capacity, status transitions to `Full` and excess booking attempts are safely rejected.
3. **Double Booking Rejection**: A student with an active booking cannot book a second slot in the same exam.
4. **Rubric Arithmetic**: Total marks must equal the sum of rubric criteria; criteria marks entered by examiners cannot exceed individual maximums.
5. **Lifecycle State Integrity**: Results cannot be published prematurely; exams with active future slots cannot be marked `Completed`.

---

## 6. What I Learned & Final Reflection

Before starting this project, web development felt mostly like making forms and styling cards with CSS. Building EMP taught me that real software development is about **state machines, concurrency, and defending against edge cases**.

What happens when an examiner doesn't show up? What happens when two students click "Book" at the exact same millisecond? What happens when a slot starts in IST but the server runs in UTC? What happens when a completed booking frees up capacity by accident?

Thinking through these questions forced me to write cleaner Python, design tighter relational schemas, and appreciate the power of server-side validation. There is zero client-side JavaScript trickery here—everything is verified where it belongs: on the server, backed by database transactions.

EMP started as an academic submission for IIT Madras MAD-1, but seeing it run smoothly with realistic data, role transitions, and scorecards makes me genuinely proud. It solves a real problem that every online student has experienced, and it does so reliably.

---

### Links & Submission Resources
- **Project Repository**: [GitHub Repository](https://github.com/25f3002106/mad1_examination_management_portal.git)
- **Demo Video Walkthrough**: [Google Drive Video Presentation](https://drive.google.com/file/d/1KCQ8O46NbcouLB5uCalOvUGKzvFOgWRU/view?usp=drive_link)
- **Submission ZIP Archive**: `examination_management_portal.zip` (clean single root folder without `.git` or caches)
