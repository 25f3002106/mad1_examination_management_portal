"""
Batch 3 — Examiner Module Tests
Covers: dashboard access, assigned exam access control, slot CRUD with
all validations, booked-student visibility, evaluation submission and
validation, evaluation history, and unauthorized-access prevention.
"""
import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from database.db import db
from database.init_db import init_db
from models.user import User, Student, Examiner
from models.course import Course
from models.examination import Examination, RubricCriterion
from models.slot import Slot
from models.booking import Booking
from models.evaluation import Evaluation, CriterionScore


# ---------------------------------------------------------------------------
# Base helper
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _dt(**kwargs):
    """Return a UTC datetime offset from now."""
    return _now() + timedelta(**kwargs)


class ExaminerTestBase(unittest.TestCase):

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            init_db(self.app)
            self._seed()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # ------------------------------------------------------------------
    # Seed helpers
    # ------------------------------------------------------------------

    def _seed(self):
        """Create two examiners, a course, an examination with rubrics,
        a student, and a confirmed booking."""
        # Approved examiner
        u1 = User(name='Examiner One', email='ex1@test.com', role='examiner', account_status='active')
        u1.set_password('Password123!')
        db.session.add(u1)
        db.session.flush()
        self.ex1_user_id = u1.id
        e1 = Examiner(user_id=u1.id, department='CS', contact_information='111', approval_status='approved')
        db.session.add(e1)
        db.session.flush()
        self.examiner1_id = e1.id

        # Pending examiner
        u2 = User(name='Examiner Two', email='ex2@test.com', role='examiner', account_status='active')
        u2.set_password('Password123!')
        db.session.add(u2)
        db.session.flush()
        self.ex2_user_id = u2.id
        e2 = Examiner(user_id=u2.id, department='EE', contact_information='222', approval_status='pending')
        db.session.add(e2)
        db.session.flush()
        self.examiner2_id = e2.id

        # Approved examiner NOT assigned to exam
        u3 = User(name='Examiner Three', email='ex3@test.com', role='examiner', account_status='active')
        u3.set_password('Password123!')
        db.session.add(u3)
        db.session.flush()
        self.ex3_user_id = u3.id
        e3 = Examiner(user_id=u3.id, department='ME', contact_information='333', approval_status='approved')
        db.session.add(e3)
        db.session.flush()
        self.examiner3_id = e3.id

        # Course
        course = Course(code='CS101', name='Algorithms', description='', status='active')
        db.session.add(course)
        db.session.flush()
        self.course_id = course.id

        # Examination in Slot Creation status with future window
        exam = Examination(
            course_id=course.id,
            name='Final Viva',
            exam_type='Viva',
            duration=30,
            max_marks=100,
            slot_creation_start_date=_dt(hours=-1),
            slot_creation_end_date=_dt(days=5),
            slot_booking_start_date=_dt(days=6),
            slot_booking_end_date=_dt(days=10),
            status='Slot Creation',
        )
        db.session.add(exam)
        db.session.flush()
        self.exam_id = exam.id

        # Assign only e1 to exam
        exam.examiners.append(e1)
        db.session.flush()

        # Rubric criteria
        r1 = RubricCriterion(examination_id=exam.id, criterion_name='Communication', max_marks=50)
        r2 = RubricCriterion(examination_id=exam.id, criterion_name='Technical', max_marks=50)
        db.session.add_all([r1, r2])
        db.session.flush()
        self.rubric1_id = r1.id
        self.rubric2_id = r2.id

        # Student
        us = User(name='Student Alpha', email='stu@test.com', role='student', account_status='active')
        us.set_password('Password123!')
        db.session.add(us)
        db.session.flush()
        self.student_user_id = us.id
        stu = Student(user_id=us.id, roll_number='21F1000001', program='BS Data Science')
        db.session.add(stu)
        db.session.flush()
        self.student_id = stu.id

        db.session.commit()

    def _login(self, email, password='Password123!'):
        return self.client.post('/auth/login', data={'email': email, 'password': password},
                                follow_redirects=True)

    def _logout(self):
        return self.client.get('/auth/logout', follow_redirects=True)

    def _add_slot(self, examiner_id, start_offset_hours=48, duration_hours=1, status='Available'):
        """Insert a slot directly into the DB for examiner_id."""
        with self.app.app_context():
            start = _dt(hours=start_offset_hours)
            end = start + timedelta(hours=duration_hours)
            slot = Slot(
                examination_id=self.exam_id,
                examiner_id=examiner_id,
                start_time=start,
                end_time=end,
                capacity=5,
                status=status,
            )
            db.session.add(slot)
            db.session.commit()
            return slot.id

    def _add_confirmed_booking(self, slot_id):
        """Insert a confirmed booking for the seeded student into slot_id."""
        with self.app.app_context():
            booking = Booking(
                student_id=self.student_id,
                slot_id=slot_id,
                status='confirmed',
            )
            db.session.add(booking)
            db.session.commit()
            return booking.id


# ---------------------------------------------------------------------------
# Dashboard Access
# ---------------------------------------------------------------------------

class TestDashboardAccess(ExaminerTestBase):

    def test_pending_examiner_cannot_access_dashboard(self):
        self._login('ex2@test.com')
        resp = self.client.get('/examiner/dashboard', follow_redirects=False)
        # Should redirect away (to pending approval page)
        self.assertIn(resp.status_code, (302, 200))
        if resp.status_code == 200:
            self.assertIn(b'pending', resp.data.lower())
        else:
            self.assertIn('/auth', resp.headers['Location'])

    def test_approved_examiner_can_access_dashboard(self):
        self._login('ex1@test.com')
        resp = self.client.get('/examiner/dashboard')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Dashboard', resp.data)

    def test_unauthenticated_redirected_from_dashboard(self):
        resp = self.client.get('/examiner/dashboard', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)


# ---------------------------------------------------------------------------
# Assigned Examinations Access Control
# ---------------------------------------------------------------------------

class TestExaminationAccess(ExaminerTestBase):

    def test_examiner_can_see_assigned_exam(self):
        self._login('ex1@test.com')
        resp = self.client.get(f'/examiner/examinations/{self.exam_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Final Viva', resp.data)

    def test_unassigned_examiner_cannot_see_exam(self):
        """Examiner3 is approved but NOT assigned to the exam."""
        self._login('ex3@test.com')
        resp = self.client.get(f'/examiner/examinations/{self.exam_id}',
                               follow_redirects=True)
        self.assertIn(b'do not have access', resp.data)

    def test_examiner_list_shows_only_assigned(self):
        self._login('ex3@test.com')
        resp = self.client.get('/examiner/examinations')
        self.assertEqual(resp.status_code, 200)
        # ex3 is not assigned, so "Final Viva" should not appear in their list
        self.assertNotIn(b'Final Viva', resp.data)


# ---------------------------------------------------------------------------
# Slot Creation
# ---------------------------------------------------------------------------

class TestSlotCreation(ExaminerTestBase):

    def _post_slot(self, start_offset_hours=48, duration_hours=1, capacity=5, **extra):
        start = _dt(hours=start_offset_hours)
        end = start + timedelta(hours=duration_hours)
        data = {
            'date': start.strftime('%Y-%m-%d'),
            'start_time': start.strftime('%H:%M'),
            'end_time': end.strftime('%H:%M'),
            'capacity': capacity,
            'room_or_link': '',
        }
        data.update(extra)
        return self.client.post(
            f'/examiner/examinations/{self.exam_id}/slots/create',
            data=data,
            follow_redirects=True,
        )

    def test_valid_slot_creation(self):
        self._login('ex1@test.com')
        resp = self._post_slot()
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Slot created successfully', resp.data)
        with self.app.app_context():
            count = Slot.query.filter_by(examination_id=self.exam_id, examiner_id=self.examiner1_id).count()
            self.assertEqual(count, 1)

    def test_unassigned_examiner_cannot_create_slot(self):
        self._login('ex3@test.com')
        resp = self._post_slot()
        self.assertIn(b'do not have access', resp.data)
        with self.app.app_context():
            count = Slot.query.filter_by(examiner_id=self.examiner3_id).count()
            self.assertEqual(count, 0)

    def test_past_start_time_rejected(self):
        self._login('ex1@test.com')
        resp = self._post_slot(start_offset_hours=-5, duration_hours=1)
        self.assertIn(b'future', resp.data.lower())
        with self.app.app_context():
            self.assertEqual(Slot.query.count(), 0)

    def test_start_after_end_rejected(self):
        self._login('ex1@test.com')
        start = _dt(hours=48)
        # end is same as start
        data = {
            'date': start.strftime('%Y-%m-%d'),
            'start_time': start.strftime('%H:%M'),
            'end_time': start.strftime('%H:%M'),
            'capacity': 5,
        }
        resp = self.client.post(
            f'/examiner/examinations/{self.exam_id}/slots/create',
            data=data, follow_redirects=True,
        )
        self.assertIn(b'before end time', resp.data)

    def test_zero_capacity_rejected(self):
        self._login('ex1@test.com')
        resp = self._post_slot(capacity=0)
        self.assertIn(b'greater than zero', resp.data)

    def test_slot_duration_less_than_exam_duration_rejected(self):
        """Exam duration is 30 min; create a 10-min slot."""
        self._login('ex1@test.com')
        start = _dt(hours=48)
        end = start + timedelta(minutes=10)
        data = {
            'date': start.strftime('%Y-%m-%d'),
            'start_time': start.strftime('%H:%M'),
            'end_time': end.strftime('%H:%M'),
            'capacity': 5,
        }
        resp = self.client.post(
            f'/examiner/examinations/{self.exam_id}/slots/create',
            data=data, follow_redirects=True,
        )
        self.assertIn(b'duration', resp.data.lower())

    def test_overlapping_slot_rejected(self):
        self._login('ex1@test.com')
        # Create first slot
        self._post_slot(start_offset_hours=48, duration_hours=1)
        # Overlapping second slot
        resp = self._post_slot(start_offset_hours=48, duration_hours=2)
        self.assertIn(b'overlaps', resp.data.lower())
        with self.app.app_context():
            self.assertEqual(Slot.query.count(), 1)


# ---------------------------------------------------------------------------
# Slot Editing and Cancellation
# ---------------------------------------------------------------------------

class TestSlotEditCancel(ExaminerTestBase):

    def _switch_exam_to_booking_open(self):
        with self.app.app_context():
            exam = db.session.get(Examination, self.exam_id)
            exam.status = 'Booking Open'
            db.session.commit()

    def test_slot_edit_blocked_after_booking_starts(self):
        slot_id = self._add_slot(self.examiner1_id)
        self._switch_exam_to_booking_open()
        self._login('ex1@test.com')
        start = _dt(hours=72)
        end = start + timedelta(hours=1)
        data = {
            'date': start.strftime('%Y-%m-%d'),
            'start_time': start.strftime('%H:%M'),
            'end_time': end.strftime('%H:%M'),
            'capacity': 10,
        }
        resp = self.client.post(f'/examiner/slots/{slot_id}/edit',
                                data=data, follow_redirects=True)
        self.assertIn(b'cannot be edited', resp.data)

    def test_slot_cancel_blocked_after_booking_starts(self):
        slot_id = self._add_slot(self.examiner1_id)
        self._switch_exam_to_booking_open()
        self._login('ex1@test.com')
        resp = self.client.post(f'/examiner/slots/{slot_id}/cancel',
                                follow_redirects=True)
        self.assertIn(b'cannot be cancelled', resp.data)
        with self.app.app_context():
            slot = db.session.get(Slot, slot_id)
            self.assertNotEqual(slot.status, 'Cancelled')

    def test_slot_cancel_before_booking_succeeds(self):
        slot_id = self._add_slot(self.examiner1_id)
        self._login('ex1@test.com')
        resp = self.client.post(f'/examiner/slots/{slot_id}/cancel',
                                follow_redirects=True)
        self.assertIn(b'cancelled successfully', resp.data)
        with self.app.app_context():
            slot = db.session.get(Slot, slot_id)
            self.assertEqual(slot.status, 'Cancelled')

    def test_other_examiner_cannot_cancel_slot(self):
        slot_id = self._add_slot(self.examiner1_id)
        self._login('ex3@test.com')
        resp = self.client.post(f'/examiner/slots/{slot_id}/cancel',
                                follow_redirects=True)
        self.assertIn(b'own slots', resp.data)
        with self.app.app_context():
            slot = db.session.get(Slot, slot_id)
            self.assertNotEqual(slot.status, 'Cancelled')


# ---------------------------------------------------------------------------
# Student Visibility
# ---------------------------------------------------------------------------

class TestStudentVisibility(ExaminerTestBase):

    def test_examiner_sees_own_students(self):
        slot_id = self._add_slot(self.examiner1_id)
        booking_id = self._add_confirmed_booking(slot_id)
        self._login('ex1@test.com')
        resp = self.client.get('/examiner/students')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Student Alpha', resp.data)

    def test_examiner_cannot_see_other_examiners_students(self):
        """Examiner3 has their own slot with a student; Examiner1 should not see that student."""
        # Give ex3 an exam assignment and slot with a booking
        with self.app.app_context():
            exam = db.session.get(Examination, self.exam_id)
            e3 = db.session.get(Examiner, self.examiner3_id)
            exam.examiners.append(e3)
            db.session.commit()
        slot_id_e3 = self._add_slot(self.examiner3_id, start_offset_hours=72)
        booking_id = self._add_confirmed_booking(slot_id_e3)

        self._login('ex1@test.com')
        resp = self.client.get('/examiner/students')
        self.assertEqual(resp.status_code, 200)
        # ex1 has no slots, so Student Alpha should not appear for ex1
        self.assertNotIn(b'Student Alpha', resp.data)

    def test_slot_students_visibility_blocked_for_other_examiner(self):
        slot_id = self._add_slot(self.examiner1_id)
        self._login('ex3@test.com')
        resp = self.client.get(f'/examiner/slots/{slot_id}/students',
                               follow_redirects=True)
        self.assertIn(b'own slots', resp.data)


# ---------------------------------------------------------------------------
# Evaluation Submission
# ---------------------------------------------------------------------------

class TestEvaluation(ExaminerTestBase):

    def test_evaluation_submission_success(self):
        slot_id = self._add_slot(self.examiner1_id)
        booking_id = self._add_confirmed_booking(slot_id)
        self._login('ex1@test.com')
        resp = self.client.post(
            f'/examiner/evaluate/{booking_id}',
            data={
                f'criterion_{self.rubric1_id}': '40',
                f'criterion_{self.rubric2_id}': '45',
                'remarks': 'Well done',
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Evaluation submitted successfully', resp.data)
        with self.app.app_context():
            booking = db.session.get(Booking, booking_id)
            self.assertEqual(booking.score, 85.0)
            self.assertEqual(booking.attendance, 'present')
            self.assertIsNotNone(booking.evaluation)
            self.assertEqual(booking.evaluation.status, 'submitted')
            self.assertEqual(len(booking.evaluation.criterion_scores), 2)

    def test_criterion_marks_exceeding_max_rejected(self):
        slot_id = self._add_slot(self.examiner1_id)
        booking_id = self._add_confirmed_booking(slot_id)
        self._login('ex1@test.com')
        resp = self.client.post(
            f'/examiner/evaluate/{booking_id}',
            data={
                f'criterion_{self.rubric1_id}': '60',   # max is 50
                f'criterion_{self.rubric2_id}': '45',
                'remarks': '',
            },
            follow_redirects=True,
        )
        self.assertIn(b'Communication', resp.data)  # error message contains criterion name
        with self.app.app_context():
            booking = db.session.get(Booking, booking_id)
            self.assertIsNone(booking.evaluation)

    def test_unauthorized_evaluation_prevented(self):
        """Examiner3 tries to evaluate a student in Examiner1's slot."""
        slot_id = self._add_slot(self.examiner1_id)
        booking_id = self._add_confirmed_booking(slot_id)
        self._login('ex3@test.com')
        resp = self.client.post(
            f'/examiner/evaluate/{booking_id}',
            data={
                f'criterion_{self.rubric1_id}': '40',
                f'criterion_{self.rubric2_id}': '40',
                'remarks': '',
            },
            follow_redirects=True,
        )
        self.assertIn(b'own slots', resp.data)
        with self.app.app_context():
            booking = db.session.get(Booking, booking_id)
            self.assertIsNone(booking.evaluation)

    def test_evaluation_history_shows_submitted(self):
        slot_id = self._add_slot(self.examiner1_id)
        booking_id = self._add_confirmed_booking(slot_id)
        self._login('ex1@test.com')
        # Submit evaluation first
        self.client.post(
            f'/examiner/evaluate/{booking_id}',
            data={
                f'criterion_{self.rubric1_id}': '30',
                f'criterion_{self.rubric2_id}': '30',
                'remarks': '',
            },
            follow_redirects=True,
        )
        resp = self.client.get('/examiner/evaluations')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Student Alpha', resp.data)
        self.assertIn(b'60', resp.data)  # total marks

    def test_evaluation_update_allowed(self):
        """Re-submitting an evaluation updates existing record."""
        slot_id = self._add_slot(self.examiner1_id)
        booking_id = self._add_confirmed_booking(slot_id)
        self._login('ex1@test.com')
        # First submission
        self.client.post(
            f'/examiner/evaluate/{booking_id}',
            data={
                f'criterion_{self.rubric1_id}': '30',
                f'criterion_{self.rubric2_id}': '30',
                'remarks': 'First',
            },
            follow_redirects=True,
        )
        # Second submission (update)
        resp = self.client.post(
            f'/examiner/evaluate/{booking_id}',
            data={
                f'criterion_{self.rubric1_id}': '45',
                f'criterion_{self.rubric2_id}': '45',
                'remarks': 'Updated',
            },
            follow_redirects=True,
        )
        self.assertIn(b'Evaluation submitted successfully', resp.data)
        with self.app.app_context():
            booking = db.session.get(Booking, booking_id)
            self.assertEqual(booking.score, 90.0)
            # Only one evaluation record
            self.assertEqual(
                Evaluation.query.filter_by(booking_id=booking_id).count(), 1
            )


if __name__ == '__main__':
    unittest.main()
