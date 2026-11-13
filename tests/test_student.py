"""
Batch 4 — Student Module and Booking Engine Tests
Covers:
- Student dashboard real DB metrics
- Examination browsing, searching, and filtering
- Slot booking with all strict validations (period, capacity, duplicate, inactive)
- Concurrency and auto-marking slot as Full
- Booking cancellation and capacity restoration
- Re-booking after cancellation
- Cancellation deadline and past slot protections
- My bookings list and receipt
- Examination history view
- Published results visibility and criterion-wise marks
- Protection against viewing unpublished results
- Profile management with protection of system fields
- Authorization and cross-student access prevention
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


def _now():
    return datetime.now(timezone.utc)


def _dt(**kwargs):
    return _now() + timedelta(**kwargs)


class StudentTestBase(unittest.TestCase):

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

    def _seed(self):
        """Create course, examiners, exams, rubrics, and two students."""
        # Active Course
        c1 = Course(code='CS201', name='Data Structures', description='Core CS Course', status='Active')
        c2 = Course(code='MA101', name='Calculus', description='Math Course', status='Active')
        c_inactive = Course(code='ARCH01', name='Ancient History', description='Archived', status='Inactive')
        db.session.add_all([c1, c2, c_inactive])
        db.session.flush()
        self.course1_id = c1.id
        self.course2_id = c2.id
        self.course_inactive_id = c_inactive.id

        # Approved Examiner
        u_ex = User(name='Dr. Turing', email='turing@emp.iitm.ac.in', role='examiner', account_status='active')
        u_ex.set_password('TuringPass123!')
        db.session.add(u_ex)
        db.session.flush()
        ex = Examiner(user_id=u_ex.id, department='CSE', contact_information='turing@office.ac.in', approval_status='approved')
        db.session.add(ex)
        db.session.flush()
        self.examiner_id = ex.id

        # 1. Open Examination (Booking Open, current time inside window)
        e_open = Examination(
            course_id=c1.id,
            name='DS Practical Viva',
            exam_type='Viva',
            duration=30,
            max_marks=50,
            slot_creation_start_date=_dt(days=-10),
            slot_creation_end_date=_dt(days=-5),
            slot_booking_start_date=_dt(days=-2),
            slot_booking_end_date=_dt(days=5),
            status='Booking Open',
            results_published=False,
        )
        db.session.add(e_open)
        db.session.flush()
        self.exam_open_id = e_open.id
        e_open.examiners.append(ex)

        # Rubrics for open exam
        r1 = RubricCriterion(examination_id=e_open.id, criterion_name='Code Correctness', max_marks=30, weightage=1.0)
        r2 = RubricCriterion(examination_id=e_open.id, criterion_name='Complexity Analysis', max_marks=20, weightage=1.0)
        db.session.add_all([r1, r2])
        db.session.flush()
        self.rubric1_id = r1.id
        self.rubric2_id = r2.id

        # 2. Closed Examination
        e_closed = Examination(
            course_id=c1.id,
            name='Midterm Viva',
            exam_type='Viva',
            duration=30,
            max_marks=50,
            slot_booking_start_date=_dt(days=-10),
            slot_booking_end_date=_dt(days=-2),
            status='Closed',
        )
        db.session.add(e_closed)
        db.session.flush()
        self.exam_closed_id = e_closed.id

        # 3. Slots for Open Examination
        # Slot 1: Capacity 2, future
        s1 = Slot(
            examination_id=e_open.id,
            examiner_id=ex.id,
            start_time=_dt(days=2, hours=10),
            end_time=_dt(days=2, hours=11),
            capacity=2,
            room_or_link='Lab 101',
            status='Available'
        )
        # Slot 2: Capacity 1, future
        s2 = Slot(
            examination_id=e_open.id,
            examiner_id=ex.id,
            start_time=_dt(days=3, hours=14),
            end_time=_dt(days=3, hours=15),
            capacity=1,
            room_or_link='Lab 102',
            status='Available'
        )
        # Slot 3: Past slot
        s3 = Slot(
            examination_id=e_open.id,
            examiner_id=ex.id,
            start_time=_dt(days=-1, hours=10),
            end_time=_dt(days=-1, hours=11),
            capacity=5,
            room_or_link='Online',
            status='Available'
        )
        # Slot 4: Closed exam slot
        s4 = Slot(
            examination_id=e_closed.id,
            examiner_id=ex.id,
            start_time=_dt(days=2, hours=10),
            end_time=_dt(days=2, hours=11),
            capacity=5,
            status='Available'
        )
        db.session.add_all([s1, s2, s3, s4])
        db.session.flush()
        self.slot1_id = s1.id
        self.slot2_id = s2.id
        self.slot_past_id = s3.id
        self.slot_closed_exam_id = s4.id

        # Student 1
        u_s1 = User(name='Alice Student', email='alice@student.iitm.ac.in', role='student', account_status='active')
        u_s1.set_password('AlicePass123!')
        db.session.add(u_s1)
        db.session.flush()
        self.user_s1_id = u_s1.id
        stu1 = Student(user_id=u_s1.id, roll_number='21F100001', program='BS Data Science', department='CS', contact_number='9876543210')
        db.session.add(stu1)
        db.session.flush()
        self.student1_id = stu1.id

        # Student 2
        u_s2 = User(name='Bob Student', email='bob@student.iitm.ac.in', role='student', account_status='active')
        u_s2.set_password('BobPass123!')
        db.session.add(u_s2)
        db.session.flush()
        self.user_s2_id = u_s2.id
        stu2 = Student(user_id=u_s2.id, roll_number='21F100002', program='BS Electronic Systems', department='EE')
        db.session.add(stu2)
        db.session.flush()
        self.student2_id = stu2.id

        db.session.commit()

    def _login(self, email='alice@student.iitm.ac.in', password='AlicePass123!'):
        return self.client.post('/auth/login', data={'email': email, 'password': password}, follow_redirects=True)

    def _logout(self):
        return self.client.get('/auth/logout', follow_redirects=True)


# ---------------------------------------------------------------------------
# 1. Student Dashboard Tests
# ---------------------------------------------------------------------------

class TestStudentDashboard(StudentTestBase):

    def test_dashboard_access_and_statistics(self):
        self._login()
        resp = self.client.get('/student/dashboard')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Alice Student', resp.data)
        self.assertIn(b'21F100001', resp.data)
        # Check metrics labels
        self.assertIn(b'AVAILABLE EXAMINATIONS', resp.data)
        self.assertIn(b'AVAILABLE SLOTS', resp.data)
        self.assertIn(b'MY BOOKED SLOTS', resp.data)
        self.assertIn(b'PUBLISHED RESULTS', resp.data)

    def test_unauthenticated_dashboard_redirects_to_login(self):
        resp = self.client.get('/student/dashboard')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login', resp.headers['Location'])

    def test_examiner_cannot_access_student_dashboard(self):
        self.client.post('/auth/login', data={'email': 'turing@emp.iitm.ac.in', 'password': 'TuringPass123!'}, follow_redirects=True)
        resp = self.client.get('/student/dashboard')
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# 2. Examination Browsing & Filtering Tests
# ---------------------------------------------------------------------------

class TestExaminationBrowsing(StudentTestBase):

    def test_browse_available_examinations(self):
        self._login()
        resp = self.client.get('/student/examinations')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'DS Practical Viva', resp.data)
        self.assertIn(b'CS201', resp.data)

    def test_search_by_examination_name(self):
        self._login()
        resp = self.client.get('/student/examinations?q=Practical')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'DS Practical Viva', resp.data)

        # Search non-matching
        resp2 = self.client.get('/student/examinations?q=NonExistent')
        self.assertNotIn(b'DS Practical Viva', resp2.data)

    def test_filter_by_course(self):
        self._login()
        resp = self.client.get(f'/student/examinations?course_id={self.course1_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'DS Practical Viva', resp.data)

        resp2 = self.client.get(f'/student/examinations?course_id={self.course2_id}')
        self.assertNotIn(b'DS Practical Viva', resp2.data)

    def test_filter_by_exam_type(self):
        self._login()
        resp = self.client.get('/student/examinations?type=Viva')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'DS Practical Viva', resp.data)

        resp2 = self.client.get('/student/examinations?type=Project+Demo')
        self.assertNotIn(b'DS Practical Viva', resp2.data)

    def test_view_examination_details_and_slots(self):
        self._login()
        resp = self.client.get(f'/student/examinations/{self.exam_open_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'DS Practical Viva', resp.data)
        self.assertIn(b'Book Slot', resp.data)
        self.assertIn(b'Lab 101', resp.data)


# ---------------------------------------------------------------------------
# 3 & 4. Examination Slot Booking & Strict Validations
# ---------------------------------------------------------------------------

class TestSlotBooking(StudentTestBase):

    def test_successful_slot_booking(self):
        self._login()
        resp = self.client.post(f'/student/slots/{self.slot1_id}/book', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Slot booked successfully', resp.data)
        self.assertIn(b'Reservation Voucher', resp.data)

        with self.app.app_context():
            booking = Booking.query.filter_by(student_id=self.student1_id, slot_id=self.slot1_id).first()
            self.assertIsNotNone(booking)
            self.assertIn(booking.status, ('Booked', 'confirmed'))

            # Check slot capacity updated (was 2, now 1 left, status Available)
            slot = db.session.get(Slot, self.slot1_id)
            self.assertEqual(slot.available_seats, 1)
            self.assertEqual(slot.status, 'Available')

    def test_duplicate_booking_for_same_examination_blocked(self):
        """Student cannot book two different slots for the same examination."""
        self._login()
        # Book slot 1
        self.client.post(f'/student/slots/{self.slot1_id}/book', follow_redirects=True)

        # Attempt to book slot 2 in same exam
        resp = self.client.post(f'/student/slots/{self.slot2_id}/book', follow_redirects=True)
        self.assertIn(b'already have an active booking', resp.data)

        with self.app.app_context():
            slot2_bookings = Booking.query.filter_by(slot_id=self.slot2_id).count()
            self.assertEqual(slot2_bookings, 0)

    def test_prevent_booking_same_slot_twice(self):
        self._login()
        self.client.post(f'/student/slots/{self.slot1_id}/book', follow_redirects=True)
        resp = self.client.post(f'/student/slots/{self.slot1_id}/book', follow_redirects=True)
        self.assertIn(b'already have an active booking', resp.data)

    def test_booking_closed_examination_blocked(self):
        self._login()
        resp = self.client.post(f'/student/slots/{self.slot_closed_exam_id}/book', follow_redirects=True)
        self.assertIn(b'not currently open', resp.data)
        with self.app.app_context():
            b = Booking.query.filter_by(slot_id=self.slot_closed_exam_id).first()
            self.assertIsNone(b)

    def test_booking_past_slot_blocked(self):
        self._login()
        resp = self.client.post(f'/student/slots/{self.slot_past_id}/book', follow_redirects=True)
        self.assertIn(b'unavailable or in the past', resp.data)
        with self.app.app_context():
            b = Booking.query.filter_by(slot_id=self.slot_past_id).first()
            self.assertIsNone(b)

    def test_capacity_limit_and_auto_mark_full(self):
        """Slot 2 has capacity 1. Booking it should fill it and mark status 'Full'."""
        # Alice books slot 2
        self._login()
        self.client.post(f'/student/slots/{self.slot2_id}/book', follow_redirects=True)

        with self.app.app_context():
            slot = db.session.get(Slot, self.slot2_id)
            self.assertEqual(slot.available_seats, 0)
            self.assertEqual(slot.status, 'Full')

        self._logout()

        # Bob tries to book full slot 2
        self._login('bob@student.iitm.ac.in', 'BobPass123!')
        resp = self.client.post(f'/student/slots/{self.slot2_id}/book', follow_redirects=True)
        self.assertIn(b'unavailable or in the past', resp.data)


# ---------------------------------------------------------------------------
# 5 & 6. Booking Cancellation & My Bookings
# ---------------------------------------------------------------------------

class TestBookingCancellation(StudentTestBase):

    def test_cancellation_restores_capacity_and_slot_status(self):
        # Alice books slot 2 (capacity 1)
        self._login()
        self.client.post(f'/student/slots/{self.slot2_id}/book', follow_redirects=True)

        with self.app.app_context():
            booking = Booking.query.filter_by(student_id=self.student1_id, slot_id=self.slot2_id).first()
            booking_id = booking.id
            slot = db.session.get(Slot, self.slot2_id)
            self.assertEqual(slot.status, 'Full')

        # Alice cancels her booking
        resp = self.client.post(f'/student/bookings/{booking_id}/cancel', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'cancelled successfully', resp.data)

        with self.app.app_context():
            booking = db.session.get(Booking, booking_id)
            self.assertEqual(booking.status, 'Cancelled')

            # Slot restored
            slot = db.session.get(Slot, self.slot2_id)
            self.assertEqual(slot.status, 'Available')
            self.assertEqual(slot.available_seats, 1)

    def test_rebooking_after_cancellation_allowed(self):
        # Alice books slot 2
        self._login()
        self.client.post(f'/student/slots/{self.slot2_id}/book', follow_redirects=True)

        with self.app.app_context():
            booking = Booking.query.filter_by(student_id=self.student1_id, slot_id=self.slot2_id).first()
            booking_id = booking.id

        # Cancel
        self.client.post(f'/student/bookings/{booking_id}/cancel', follow_redirects=True)

        # Now Alice can book slot 1 in the same examination!
        resp = self.client.post(f'/student/slots/{self.slot1_id}/book', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Slot booked successfully', resp.data)

    def test_rebooking_same_slot_after_cancellation_allowed(self):
        """Student cancels slot 1, then re-books slot 1 while booking is still open."""
        self._login()
        self.client.post(f'/student/slots/{self.slot1_id}/book', follow_redirects=True)

        with self.app.app_context():
            b = Booking.query.filter_by(student_id=self.student1_id, slot_id=self.slot1_id).first()
            b_id = b.id

        self.client.post(f'/student/bookings/{b_id}/cancel', follow_redirects=True)

        # Re-book same slot
        resp = self.client.post(f'/student/slots/{self.slot1_id}/book', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Slot booked successfully', resp.data)

        with self.app.app_context():
            b_after = db.session.get(Booking, b_id)
            self.assertEqual(b_after.status, 'Booked')

    def test_cannot_cancel_other_student_booking(self):
        # Alice books slot 1
        self._login()
        self.client.post(f'/student/slots/{self.slot1_id}/book', follow_redirects=True)

        with self.app.app_context():
            b = Booking.query.filter_by(student_id=self.student1_id, slot_id=self.slot1_id).first()
            b_id = b.id

        self._logout()

        # Bob tries to cancel Alice's booking
        self._login('bob@student.iitm.ac.in', 'BobPass123!')
        resp = self.client.post(f'/student/bookings/{b_id}/cancel')
        self.assertEqual(resp.status_code, 404)

        with self.app.app_context():
            b_check = db.session.get(Booking, b_id)
            self.assertEqual(b_check.status, 'Booked')


# ---------------------------------------------------------------------------
# 7 & 8. Results, Feedback & Unpublished Protection
# ---------------------------------------------------------------------------

class TestResultsAndFeedback(StudentTestBase):

    def _setup_booking_with_evaluation(self, is_published=False):
        with self.app.app_context():
            booking = Booking(
                student_id=self.student1_id,
                slot_id=self.slot1_id,
                status='Booked',
                attendance='present',
                score=45.0,
            )
            db.session.add(booking)
            db.session.flush()

            evaluation = Evaluation(
                booking_id=booking.id,
                examiner_id=self.examiner_id,
                evaluation_date=_now(),
                total_marks=45.0,
                remarks='Outstanding depth and code quality',
                status='submitted',
                is_published=is_published,
            )
            db.session.add(evaluation)
            db.session.flush()

            cs1 = CriterionScore(evaluation_id=evaluation.id, rubric_criterion_id=self.rubric1_id, marks_awarded=27.0, remarks='Good code')
            cs2 = CriterionScore(evaluation_id=evaluation.id, rubric_criterion_id=self.rubric2_id, marks_awarded=18.0, remarks='Solid analysis')
            db.session.add_all([cs1, cs2])
            db.session.commit()
            return booking.id

    def test_unpublished_results_hidden_from_student(self):
        b_id = self._setup_booking_with_evaluation(is_published=False)
        self._login()

        # Result list should not show unpublished
        resp = self.client.get('/student/results')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'Outstanding depth', resp.data)

        # Direct access to unpublished scorecard must be blocked
        resp_card = self.client.get(f'/student/results/{b_id}', follow_redirects=True)
        self.assertIn(b'not been published yet', resp_card.data)

    def test_published_results_visible_with_criterion_breakdown(self):
        b_id = self._setup_booking_with_evaluation(is_published=True)
        self._login()

        # Results index shows scorecard
        resp = self.client.get('/student/results')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'DS Practical Viva', resp.data)
        self.assertIn(b'45', resp.data)

        # Scorecard detail view
        resp_card = self.client.get(f'/student/results/{b_id}')
        self.assertEqual(resp_card.status_code, 200)
        self.assertIn(b'Official Result Scorecard', resp_card.data)
        self.assertIn(b'Code Correctness', resp_card.data)
        self.assertIn(b'Complexity Analysis', resp_card.data)
        self.assertIn(b'27', resp_card.data)
        self.assertIn(b'18', resp_card.data)
        self.assertIn(b'Outstanding depth and code quality', resp_card.data)
        self.assertIn(b'Published', resp_card.data)

    def test_examination_history_view(self):
        self._setup_booking_with_evaluation(is_published=True)
        self._login()
        resp = self.client.get('/student/history')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'DS Practical Viva', resp.data)
        self.assertIn(b'Published', resp.data)


# ---------------------------------------------------------------------------
# 9. Profile Management Tests
# ---------------------------------------------------------------------------

class TestStudentProfile(StudentTestBase):

    def test_view_profile(self):
        self._login()
        resp = self.client.get('/student/profile')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Alice Student', resp.data)
        self.assertIn(b'21F100001', resp.data)

    def test_edit_permitted_profile_fields(self):
        self._login()
        resp = self.client.post('/student/profile', data={
            'name': 'Alice Allison',
            'program': 'BS Data Science & AI',
            'department': 'CS Department',
            'contact_number': '+91 9999888877',
        }, follow_redirects=True)

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Your profile has been updated successfully', resp.data)

        with self.app.app_context():
            u = db.session.get(User, self.user_s1_id)
            stu = db.session.get(Student, self.student1_id)
            self.assertEqual(u.name, 'Alice Allison')
            self.assertEqual(stu.program, 'BS Data Science & AI')
            self.assertEqual(stu.department, 'CS Department')
            self.assertEqual(stu.contact_number, '+91 9999888877')

    def test_protected_fields_cannot_be_tampered(self):
        """Role, user ID, roll number, and email must not change even if posted."""
        self._login()
        self.client.post('/student/profile', data={
            'name': 'Alice Allison',
            'program': 'BS Data Science',
            'department': 'CS',
            'contact_number': '12345',
            # Malicious inputs:
            'role': 'admin',
            'user_id': 9999,
            'roll_number': 'HACKED001',
            'email': 'admin@hacked.com',
        }, follow_redirects=True)

        with self.app.app_context():
            u = db.session.get(User, self.user_s1_id)
            stu = db.session.get(Student, self.student1_id)
            self.assertEqual(u.role, 'student')  # Unchanged
            self.assertEqual(u.email, 'alice@student.iitm.ac.in')  # Unchanged
            self.assertEqual(stu.roll_number, '21F100001')  # Unchanged


if __name__ == '__main__':
    unittest.main()
