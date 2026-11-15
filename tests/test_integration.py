"""
Batch 5 — Final Integration and Advanced Features Tests
Covers:
- 18-Step Full End-to-End Workflow across Admin, Examiner, and Student roles
- Admin Examination Slot Overview (searching & filtering)
- Admin Booking Management & Overview (multi-field search & filtering)
- Admin Rescheduling of Student Bookings (capacity sync, validation, audit trail)
- Admin Examiner Reassignment (slot reassignment, approval validation, exam association)
- Historical Data Store and Audit Trail Access
- Role-based security and permission enforcement
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


class IntegrationTestCase(unittest.TestCase):

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            init_db(self.app)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _login(self, email, password):
        return self.client.post('/auth/login', data={'email': email, 'password': password}, follow_redirects=True)

    def _logout(self):
        return self.client.get('/auth/logout', follow_redirects=True)

    # =========================================================================
    # 1. 18-STEP END-TO-END WORKFLOW INTEGRATION TEST
    # =========================================================================
    def test_full_18_step_end_to_end_workflow(self):
        """
        Execute and verify the full 18-step portal lifecycle:
        1. Admin logs in.
        2. Admin creates a course.
        3. Admin creates an examination.
        4. Admin creates examination rubrics.
        5. Examiner registers.
        6. Admin approves the examiner.
        7. Admin assigns the examination to the examiner.
        8. Admin opens slot creation.
        9. Examiner creates examination slots.
        10. Admin opens student booking.
        11. Student registers and logs in.
        12. Student searches for the examination.
        13. Student books a slot.
        14. Examiner views the booked student.
        15. Examiner submits rubric-based marks and remarks.
        16. Admin reviews the examination and booking records.
        17. Result is published.
        18. Student views the result and feedback.
        """
        # Step 1: Admin logs in
        resp = self._login('admin@emp.iitm.ac.in', 'AdminPassword123!')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Administrator Dashboard', resp.data)

        # Step 2: Admin creates a course
        resp = self.client.post('/admin/courses/create', data={
            'code': 'CS3001',
            'name': 'Software Engineering Capstone',
            'description': 'Advanced software development course',
            'department': 'Computer Science',
            'credits': 4,
            'status': 'Active'
        }, follow_redirects=True)
        self.assertIn(b'created successfully', resp.data)

        with self.app.app_context():
            course = Course.query.filter_by(code='CS3001').first()
            self.assertIsNotNone(course)
            course_id = course.id

        # Step 3: Admin creates an examination
        slot_cr_start = _dt(days=-2).strftime('%Y-%m-%d')
        slot_cr_end = _dt(days=5).strftime('%Y-%m-%d')
        slot_bk_start = _dt(days=6).strftime('%Y-%m-%d')
        slot_bk_end = _dt(days=12).strftime('%Y-%m-%d')

        resp = self.client.post('/admin/examinations/create', data={
            'course_id': course_id,
            'name': 'Capstone Final Demo & Viva',
            'exam_type': 'Project Demo',
            'duration': 45,
            'max_marks': 100,
            'status': 'Draft',
            'slot_creation_start_date': slot_cr_start,
            'slot_creation_end_date': slot_cr_end,
            'slot_booking_start_date': slot_bk_start,
            'slot_booking_end_date': slot_bk_end,
        }, follow_redirects=True)
        self.assertIn(b'created successfully', resp.data)

        with self.app.app_context():
            exam = Examination.query.filter_by(name='Capstone Final Demo & Viva').first()
            self.assertIsNotNone(exam)
            exam_id = exam.id

        # Step 4: Admin creates examination rubrics
        resp = self.client.post(f'/admin/examinations/{exam_id}/rubrics/add', data={
            'criterion_name': 'System Architecture & Implementation',
            'max_marks': 60,
            'weightage': 1.0,
            'description': 'Code structure and completeness'
        }, follow_redirects=True)
        self.assertIn(b'added successfully', resp.data)

        resp = self.client.post(f'/admin/examinations/{exam_id}/rubrics/add', data={
            'criterion_name': 'Defense & Technical Q&A',
            'max_marks': 40,
            'weightage': 1.0,
            'description': 'Viva oral defense'
        }, follow_redirects=True)
        self.assertIn(b'added successfully', resp.data)

        with self.app.app_context():
            rubrics = RubricCriterion.query.filter_by(examination_id=exam_id).all()
            self.assertEqual(len(rubrics), 2)
            r1_id = rubrics[0].id
            r2_id = rubrics[1].id

        self._logout()

        # Step 5: Examiner registers
        resp = self.client.post('/auth/register/examiner', data={
            'name': 'Prof. Grace Hopper',
            'email': 'grace.hopper@emp.iitm.ac.in',
            'password': 'GracePassword123!',
            'confirm_password': 'GracePassword123!',
            'department': 'Computer Science',
            'contact_information': '+91 9444123456'
        }, follow_redirects=True)
        self.assertIn(b'Registration submitted', resp.data)

        with self.app.app_context():
            examiner_user = User.query.filter_by(email='grace.hopper@emp.iitm.ac.in').first()
            self.assertIsNotNone(examiner_user)
            examiner = examiner_user.examiner_profile
            self.assertEqual(examiner.approval_status, 'pending')
            examiner_id = examiner.id

        # Step 6: Admin approves the examiner
        self._login('admin@emp.iitm.ac.in', 'AdminPassword123!')
        resp = self.client.post(f'/admin/examiner/{examiner_id}/approve', follow_redirects=True)
        self.assertIn(b'approved', resp.data)

        # Step 7: Admin assigns the examination to the examiner
        resp = self.client.post(f'/admin/examinations/{exam_id}/assign-examiners', data={
            'examiner_ids': [examiner_id]
        }, follow_redirects=True)
        self.assertIn(b'Assigned examiners updated', resp.data)

        # Step 8: Admin opens slot creation (updates status and window)
        resp = self.client.post(f'/admin/examinations/{exam_id}/status/Slot Creation', follow_redirects=True)
        self.assertIn(b'Slot Creation', resp.data)

        with self.app.app_context():
            ex_obj = db.session.get(Examination, exam_id)
            ex_obj.slot_creation_start_date = _dt(days=-1)
            ex_obj.slot_creation_end_date = _dt(days=5)
            db.session.commit()

        self._logout()

        # Step 9: Examiner creates examination slots
        self._login('grace.hopper@emp.iitm.ac.in', 'GracePassword123!')
        slot_date = _dt(days=3).strftime('%Y-%m-%d')
        resp = self.client.post(f'/examiner/examinations/{exam_id}/slots/create', data={
            'date': slot_date,
            'start_time': '10:00',
            'end_time': '11:00',
            'capacity': 2,
            'room_or_link': 'CS Lab 301'
        }, follow_redirects=True)
        self.assertIn(b'Slot created successfully', resp.data)

        with self.app.app_context():
            slot = Slot.query.filter_by(examination_id=exam_id, examiner_id=examiner_id).first()
            self.assertIsNotNone(slot)
            slot_id = slot.id

        self._logout()

        # Step 10: Admin opens student booking
        self._login('admin@emp.iitm.ac.in', 'AdminPassword123!')
        self.client.post(f'/admin/examinations/{exam_id}/status/Booking Open', follow_redirects=True)

        with self.app.app_context():
            ex_obj = db.session.get(Examination, exam_id)
            ex_obj.slot_booking_start_date = _dt(days=-1)
            ex_obj.slot_booking_end_date = _dt(days=5)
            db.session.commit()

        self._logout()

        # Step 11: Student registers and logs in
        resp = self.client.post('/auth/register/student', data={
            'name': 'Ada Lovelace',
            'email': 'ada@student.iitm.ac.in',
            'password': 'AdaPassword123!',
            'confirm_password': 'AdaPassword123!',
            'roll_number': '21CS9001',
            'program': 'B.Tech Computer Science',
            'department': 'CSE',
            'contact_number': '+91 9888877777'
        }, follow_redirects=True)
        self.assertIn(b'Registration successful', resp.data)

        # Step 12: Student searches for the examination
        resp = self.client.get('/student/examinations?q=Capstone')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Capstone Final Demo &amp; Viva', resp.data)

        # Step 13: Student books a slot
        resp = self.client.post(f'/student/slots/{slot_id}/book', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Slot booked successfully', resp.data)

        with self.app.app_context():
            booking = Booking.query.filter_by(slot_id=slot_id).first()
            self.assertIsNotNone(booking)
            booking_id = booking.id

        self._logout()

        # Step 14: Examiner views the booked student
        self._login('grace.hopper@emp.iitm.ac.in', 'GracePassword123!')
        resp = self.client.get('/examiner/students')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Ada Lovelace', resp.data)
        self.assertIn(b'21CS9001', resp.data)

        # Step 15: Examiner submits rubric-based marks and remarks
        resp = self.client.post(f'/examiner/evaluate/{booking_id}', data={
            f'criterion_{r1_id}': '55',
            f'criterion_{r2_id}': '38',
            'remarks': 'Exceptional engineering prowess and clear analytical defense.'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Evaluation submitted successfully', resp.data)

        with self.app.app_context():
            ev = Evaluation.query.filter_by(booking_id=booking_id).first()
            self.assertIsNotNone(ev)
            self.assertEqual(ev.total_marks, 93.0)
            self.assertFalse(ev.is_published)

        self._logout()

        # Step 16: Admin reviews the examination and booking records
        self._login('admin@emp.iitm.ac.in', 'AdminPassword123!')
        resp = self.client.get(f'/admin/bookings/{booking_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Ada Lovelace', resp.data)
        self.assertIn(b'93.0', resp.data)

        # Step 17: Result is published (via Admin endpoint)
        resp = self.client.post(f'/admin/examinations/{exam_id}/publish-results', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'have been published to students', resp.data)

        with self.app.app_context():
            ev = Evaluation.query.filter_by(booking_id=booking_id).first()
            self.assertTrue(ev.is_published)

        self._logout()

        # Step 18: Student views the published result and feedback
        self._login('ada@student.iitm.ac.in', 'AdaPassword123!')
        resp = self.client.get('/student/results')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Capstone Final Demo &amp; Viva', resp.data)
        self.assertIn(b'93.0', resp.data)

        resp_detail = self.client.get(f'/student/results/{booking_id}')
        self.assertEqual(resp_detail.status_code, 200)
        self.assertIn(b'System Architecture &amp; Implementation', resp_detail.data)
        self.assertIn(b'55.0', resp_detail.data)
        self.assertIn(b'Defense &amp; Technical Q&amp;A', resp_detail.data)
        self.assertIn(b'38.0', resp_detail.data)
        self.assertIn(b'Exceptional engineering prowess', resp_detail.data)
        self.assertIn(b'Published', resp_detail.data)

    # =========================================================================
    # 2. ADMIN EXAMINATION SLOTS OVERVIEW & FILTERING TESTS
    # =========================================================================
    def test_admin_slots_overview_and_filters(self):
        """Test Admin slots listing, search, and filters."""
        with self.app.app_context():
            course = Course(code='CS401', name='Cloud Architecture', status='Active')
            db.session.add(course)
            db.session.flush()

            u_ex = User(name='Dr. Knuth', email='knuth@emp.iitm.ac.in', role='examiner', account_status='active')
            u_ex.set_password('KnuthPass123!')
            db.session.add(u_ex)
            db.session.flush()
            examiner = Examiner(user_id=u_ex.id, department='CS', contact_information='knuth@office.ac.in', approval_status='approved')
            db.session.add(examiner)
            db.session.flush()

            exam = Examination(course_id=course.id, name='Cloud Systems Viva', status='Booking Open')
            db.session.add(exam)
            db.session.flush()

            s1 = Slot(examination_id=exam.id, examiner_id=examiner.id, start_time=_dt(days=2), end_time=_dt(days=2, hours=1), capacity=5, room_or_link='Lab 404', status='Available')
            s2 = Slot(examination_id=exam.id, examiner_id=examiner.id, start_time=_dt(days=3), end_time=_dt(days=3, hours=1), capacity=2, room_or_link='Online Link', status='Full')
            db.session.add_all([s1, s2])
            db.session.commit()
            s1_id = s1.id

        self._login('admin@emp.iitm.ac.in', 'AdminPassword123!')

        # View all slots
        resp = self.client.get('/admin/slots')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Cloud Systems Viva', resp.data)
        self.assertIn(b'Dr. Knuth', resp.data)
        self.assertIn(b'Lab 404', resp.data)

        # Search by room
        resp_q = self.client.get('/admin/slots?q=Lab+404')
        self.assertEqual(resp_q.status_code, 200)
        self.assertIn(b'Lab 404', resp_q.data)

        # Filter by status
        resp_f = self.client.get('/admin/slots?status=Full')
        self.assertEqual(resp_f.status_code, 200)
        self.assertIn(b'Online Link', resp_f.data)

    # =========================================================================
    # 3. ADMIN BOOKING MANAGEMENT & RESCHEDULING TESTS
    # =========================================================================
    def test_admin_booking_rescheduling_and_audit_trail(self):
        """Test Admin can reschedule a booking to an alternative available slot, updating capacity and saving audit log."""
        with self.app.app_context():
            course = Course(code='MA201', name='Linear Algebra', status='Active')
            db.session.add(course)
            db.session.flush()

            exam = Examination(course_id=course.id, name='LA Viva', status='Booking Open')
            db.session.add(exam)
            db.session.flush()

            u_stu = User(name='Carl Gauss', email='gauss@student.iitm.ac.in', role='student', account_status='active')
            u_stu.set_password('GaussPass123!')
            db.session.add(u_stu)
            db.session.flush()
            student = Student(user_id=u_stu.id, roll_number='21MA1001', program='B.S. Math')
            db.session.add(student)
            db.session.flush()

            # Slot A (Capacity 1, currently booked by Gauss)
            slot_a = Slot(examination_id=exam.id, start_time=_dt(days=2), end_time=_dt(days=2, hours=1), capacity=1, status='Full')
            # Slot B (Capacity 2, Available)
            slot_b = Slot(examination_id=exam.id, start_time=_dt(days=3), end_time=_dt(days=3, hours=1), capacity=2, status='Available')
            db.session.add_all([slot_a, slot_b])
            db.session.flush()

            booking = Booking(student_id=student.id, slot_id=slot_a.id, status='Booked')
            db.session.add(booking)
            db.session.commit()

            booking_id = booking.id
            slot_a_id = slot_a.id
            slot_b_id = slot_b.id

        self._login('admin@emp.iitm.ac.in', 'AdminPassword123!')

        # 1. View reschedule page
        resp_get = self.client.get(f'/admin/bookings/{booking_id}/reschedule')
        self.assertEqual(resp_get.status_code, 200)
        self.assertIn(b'Reschedule Student Booking', resp_get.data)
        self.assertIn(b'Carl Gauss', resp_get.data)

        # 2. Perform reschedule to slot_b
        resp_post = self.client.post(f'/admin/bookings/{booking_id}/reschedule', data={
            'new_slot_id': slot_b_id,
            'reason': 'Academic symposium schedule clash'
        }, follow_redirects=True)
        self.assertEqual(resp_post.status_code, 200)
        self.assertIn(b'successfully rescheduled', resp_post.data)

        # 3. Verify database state
        with self.app.app_context():
            updated_booking = db.session.get(Booking, booking_id)
            self.assertEqual(updated_booking.slot_id, slot_b_id)
            self.assertEqual(updated_booking.original_slot_id, slot_a_id)
            self.assertIsNotNone(updated_booking.rescheduled_at)
            self.assertIn('Academic symposium schedule clash', updated_booking.history_notes)

            # Slot A capacity restored
            slot_a = db.session.get(Slot, slot_a_id)
            self.assertEqual(slot_a.available_seats, 1)
            self.assertEqual(slot_a.status, 'Available')

            # Slot B capacity deducted
            slot_b = db.session.get(Slot, slot_b_id)
            self.assertEqual(slot_b.available_seats, 1)

    # =========================================================================
    # 4. ADMIN EXAMINER REASSIGNMENT TESTS
    # =========================================================================
    def test_admin_examiner_reassignment_on_slot(self):
        """Test Admin can reassign an approved examiner to an existing examination slot."""
        with self.app.app_context():
            course = Course(code='EE201', name='Circuits', status='Active')
            db.session.add(course)
            db.session.flush()

            u1 = User(name='Dr. Ohm', email='ohm@emp.iitm.ac.in', role='examiner', account_status='active')
            u1.set_password('OhmPass123!')
            db.session.add(u1)
            db.session.flush()
            ex1 = Examiner(user_id=u1.id, department='EE', contact_information='ohm@ee.iitm.ac.in', approval_status='approved')
            db.session.add(ex1)
            db.session.flush()

            u2 = User(name='Dr. Ampere', email='ampere@emp.iitm.ac.in', role='examiner', account_status='active')
            u2.set_password('AmperePass123!')
            db.session.add(u2)
            db.session.flush()
            ex2 = Examiner(user_id=u2.id, department='EE', contact_information='ampere@ee.iitm.ac.in', approval_status='approved')
            db.session.add(ex2)
            db.session.flush()

            exam = Examination(course_id=course.id, name='Circuit Lab Viva', status='Slot Creation')
            exam.examiners.append(ex1)
            db.session.add(exam)
            db.session.flush()

            slot = Slot(examination_id=exam.id, examiner_id=ex1.id, start_time=_dt(days=2), end_time=_dt(days=2, hours=1), capacity=5, status='Available')
            db.session.add(slot)
            db.session.commit()

            slot_id = slot.id
            ex2_id = ex2.id

        self._login('admin@emp.iitm.ac.in', 'AdminPassword123!')

        # Reassign to Dr. Ampere
        resp = self.client.post(f'/admin/slots/{slot_id}/reassign-examiner', data={
            'examiner_id': ex2_id
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'reassigned from Dr. Ohm to Dr. Ampere', resp.data)

        with self.app.app_context():
            updated_slot = db.session.get(Slot, slot_id)
            self.assertEqual(updated_slot.examiner_id, ex2_id)
            # Ensure ex2 is now in exam.examiners
            self.assertIn(ex2_id, [e.id for e in updated_slot.examination.examiners])

    # =========================================================================
    # 5. HISTORICAL DATA STORE ACCESS
    # =========================================================================
    def test_historical_overview_access(self):
        """Test Admin can access the complete historical data repository."""
        self._login('admin@emp.iitm.ac.in', 'AdminPassword123!')
        resp = self.client.get('/admin/history')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Historical Examination Records &amp; Audit Trail', resp.data)
        self.assertIn(b'Completed Examinations', resp.data)
        self.assertIn(b'Past Slots', resp.data)
        self.assertIn(b'Historical Bookings', resp.data)
        self.assertIn(b'Evaluations &amp; Results', resp.data)

    # =========================================================================
    # 6. ADMIN BOOKINGS SEARCH & ADVANCED RESCHEDULING VALIDATIONS
    # =========================================================================
    def test_admin_bookings_search_and_filters(self):
        """Test Admin bookings multi-attribute search and filtering."""
        with self.app.app_context():
            course = Course(code='CS501', name='Machine Learning', status='Active')
            db.session.add(course)
            db.session.flush()

            exam = Examination(course_id=course.id, name='ML Final Project', status='Booking Open')
            db.session.add(exam)
            db.session.flush()

            u_stu = User(name='Alan Turing', email='alan@student.iitm.ac.in', role='student', account_status='active')
            u_stu.set_password('AlanPass123!')
            db.session.add(u_stu)
            db.session.flush()
            student = Student(user_id=u_stu.id, roll_number='21CS9999', program='BS DS')
            db.session.add(student)
            db.session.flush()

            slot = Slot(examination_id=exam.id, start_time=_dt(days=2), end_time=_dt(days=2, hours=1), capacity=3, status='Available')
            db.session.add(slot)
            db.session.flush()

            booking = Booking(student_id=student.id, slot_id=slot.id, status='Booked')
            db.session.add(booking)
            db.session.commit()
            booking_id = booking.id

        self._login('admin@emp.iitm.ac.in', 'AdminPassword123!')

        # 1. Search by student name
        resp = self.client.get('/admin/bookings?q=Alan+Turing')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Alan Turing', resp.data)
        self.assertIn(b'21CS9999', resp.data)

        # 2. Search by roll number
        resp = self.client.get('/admin/bookings?q=21CS9999')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Alan Turing', resp.data)

        # 3. Search by exam name
        resp = self.client.get('/admin/bookings?q=Machine+Learning')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'ML Final Project', resp.data)

        # 4. Search by booking ID
        resp = self.client.get(f'/admin/bookings?q={booking_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Alan Turing', resp.data)

    def test_admin_rescheduling_invalid_cases_blocked(self):
        """Test rescheduling validation: different exam, full slot, same slot."""
        with self.app.app_context():
            course = Course(code='PH101', name='Physics', status='Active')
            db.session.add(course)
            db.session.flush()

            exam1 = Examination(course_id=course.id, name='Physics Viva 1', status='Booking Open')
            exam2 = Examination(course_id=course.id, name='Physics Viva 2', status='Booking Open')
            db.session.add_all([exam1, exam2])
            db.session.flush()

            u_stu = User(name='Isaac Newton', email='newton@student.iitm.ac.in', role='student', account_status='active')
            u_stu.set_password('NewtonPass123!')
            db.session.add(u_stu)
            db.session.flush()
            student = Student(user_id=u_stu.id, roll_number='21PH1001', program='B.S. Physics')
            db.session.add(student)
            db.session.flush()

            slot_cur = Slot(examination_id=exam1.id, start_time=_dt(days=2), end_time=_dt(days=2, hours=1), capacity=2, status='Available')
            slot_diff_exam = Slot(examination_id=exam2.id, start_time=_dt(days=2), end_time=_dt(days=2, hours=1), capacity=2, status='Available')
            slot_full = Slot(examination_id=exam1.id, start_time=_dt(days=3), end_time=_dt(days=3, hours=1), capacity=1, status='Full')
            db.session.add_all([slot_cur, slot_diff_exam, slot_full])
            db.session.flush()

            # Fill slot_full with a dummy booking
            u_dummy = User(name='Dummy Student', email='dummy@student.iitm.ac.in', role='student', account_status='active')
            u_dummy.set_password('DummyPass123!')
            db.session.add(u_dummy)
            db.session.flush()
            s_dummy = Student(user_id=u_dummy.id, roll_number='21PH9999', program='B.S. Physics')
            db.session.add(s_dummy)
            db.session.flush()
            b_dummy = Booking(student_id=s_dummy.id, slot_id=slot_full.id, status='Booked')
            db.session.add(b_dummy)

            booking = Booking(student_id=student.id, slot_id=slot_cur.id, status='Booked')
            db.session.add(booking)
            db.session.commit()

            b_id = booking.id
            slot_cur_id = slot_cur.id
            slot_diff_id = slot_diff_exam.id
            slot_full_id = slot_full.id

        self._login('admin@emp.iitm.ac.in', 'AdminPassword123!')

        # 1. Rescheduling to a slot in a different exam must be rejected
        resp1 = self.client.post(f'/admin/bookings/{b_id}/reschedule', data={
            'new_slot_id': slot_diff_id
        }, follow_redirects=True)
        self.assertIn(b'different examination', resp1.data)

        # 2. Rescheduling to the same slot must be rejected
        resp2 = self.client.post(f'/admin/bookings/{b_id}/reschedule', data={
            'new_slot_id': slot_cur_id
        }, follow_redirects=True)
        self.assertIn(b'already assigned', resp2.data)

        # 3. Rescheduling to a full slot must be rejected
        resp3 = self.client.post(f'/admin/bookings/{b_id}/reschedule', data={
            'new_slot_id': slot_full_id
        }, follow_redirects=True)
        self.assertIn(b'full or unavailable', resp3.data)

    def test_admin_examiner_reassignment_validation(self):
        """Test examiner reassignment rejects non-existent or pending examiners."""
        with self.app.app_context():
            course = Course(code='CH101', name='Chemistry', status='Active')
            db.session.add(course)
            db.session.flush()

            u_pending = User(name='Dr. Pending', email='pending@emp.iitm.ac.in', role='examiner', account_status='active')
            u_pending.set_password('PendingPass123!')
            db.session.add(u_pending)
            db.session.flush()
            ex_pending = Examiner(user_id=u_pending.id, department='Chem', contact_information='chem@iitm.ac.in', approval_status='pending')
            db.session.add(ex_pending)
            db.session.flush()

            exam = Examination(course_id=course.id, name='Chemistry Viva', status='Slot Creation')
            db.session.add(exam)
            db.session.flush()

            slot = Slot(examination_id=exam.id, start_time=_dt(days=2), end_time=_dt(days=2, hours=1), capacity=3, status='Available')
            db.session.add(slot)
            db.session.commit()

            slot_id = slot.id
            pending_id = ex_pending.id

        self._login('admin@emp.iitm.ac.in', 'AdminPassword123!')

        # Reassign to pending examiner must be rejected
        resp = self.client.post(f'/admin/slots/{slot_id}/reassign-examiner', data={
            'examiner_id': pending_id
        }, follow_redirects=True)
        self.assertIn(b'Only approved examiners can be assigned', resp.data)

    def test_security_cross_role_access_prevented(self):
        """Test non-admin users cannot access admin management endpoints."""
        # 1. Unauthenticated access
        resp = self.client.get('/admin/slots')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login', resp.headers['Location'])

        # 2. Student access
        with self.app.app_context():
            u_stu = User(name='Eve Student', email='eve@student.iitm.ac.in', role='student', account_status='active')
            u_stu.set_password('EvePass123!')
            db.session.add(u_stu)
            db.session.flush()
            stu = Student(user_id=u_stu.id, roll_number='21CS0000', program='B.S.')
            db.session.add(stu)
            db.session.commit()

        self._login('eve@student.iitm.ac.in', 'EvePass123!')
        resp_slots = self.client.get('/admin/slots')
        self.assertEqual(resp_slots.status_code, 403)

        resp_bookings = self.client.get('/admin/bookings')
        self.assertEqual(resp_bookings.status_code, 403)

        resp_history = self.client.get('/admin/history')
        self.assertEqual(resp_history.status_code, 403)


if __name__ == '__main__':
    unittest.main()
