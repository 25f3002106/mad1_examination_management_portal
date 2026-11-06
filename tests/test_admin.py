import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from database.db import db
from database.init_db import init_db
from models.user import User, Student, Examiner
from models.course import Course
from models.examination import Examination, RubricCriterion
from models.slot import Slot
from models.booking import Booking


class AdminModuleTestCase(unittest.TestCase):
    """Automated test suite for Batch 2 Admin Module functionality."""

    def setUp(self):
        """Set up in-memory SQLite database and authenticated admin client."""
        self.app = create_app('testing')
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            init_db(self.app)

        # Authenticate as default Admin
        self.client.post('/auth/login', data={
            'email': 'admin@emp.iitm.ac.in',
            'password': 'AdminPassword123!'
        }, follow_redirects=True)

    def tearDown(self):
        """Clean up database tables."""
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_admin_dashboard_real_statistics(self):
        """Test dashboard calculates and displays all 6 database-backed statistics."""
        with self.app.app_context():
            # Seed 1 course, 1 exam, 1 student, 1 examiner, 1 slot, 1 booking
            course = Course(code='CS101', name='Intro to CS', credits=4, status='Active')
            db.session.add(course)
            db.session.flush()

            exam = Examination(
                course_id=course.id,
                name='Quiz 1',
                exam_type='Assessment',
                duration=45,
                max_marks=50,
                status='Draft'
            )
            db.session.add(exam)
            db.session.flush()

            # Student
            stu_user = User(name='Test Student', email='student1@test.com', role='student', account_status='active')
            stu_user.set_password('Pass123')
            db.session.add(stu_user)
            db.session.flush()
            student = Student(user_id=stu_user.id, roll_number='21F1001', program='BS DS')
            db.session.add(student)

            # Examiner
            ex_user = User(name='Test Examiner', email='examiner1@test.com', role='examiner', account_status='active')
            ex_user.set_password('Pass123')
            db.session.add(ex_user)
            db.session.flush()
            examiner = Examiner(user_id=ex_user.id, department='CS', contact_information='Cabin 1', approval_status='approved')
            db.session.add(examiner)

            # Slot & Booking
            now = datetime.now(timezone.utc)
            slot = Slot(examination_id=exam.id, start_time=now, end_time=now + timedelta(hours=1), capacity=20)
            db.session.add(slot)
            db.session.flush()

            booking = Booking(student_id=student.id, slot_id=slot.id, status='confirmed')
            db.session.add(booking)
            db.session.commit()

        # Request dashboard
        response = self.client.get('/admin/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'COURSES', response.data)
        self.assertIn(b'EXAMINATIONS', response.data)
        self.assertIn(b'EXAMINERS', response.data)
        self.assertIn(b'STUDENTS', response.data)
        self.assertIn(b'EXAM SLOTS', response.data)
        self.assertIn(b'BOOKINGS', response.data)

    def test_course_crud_and_deletion_guard(self):
        """Test full course CRUD and prevention of deletion when exams depend on it."""
        # 1. Create Course
        create_resp = self.client.post('/admin/courses/create', data={
            'code': 'CS2001',
            'name': 'Data Structures and Algorithms',
            'department': 'Computer Science',
            'credits': '4',
            'status': 'Active',
            'description': 'Core DSA course'
        }, follow_redirects=True)
        self.assertEqual(create_resp.status_code, 200)
        self.assertIn(b'created successfully', create_resp.data)
        self.assertIn(b'CS2001', create_resp.data)

        with self.app.app_context():
            course = Course.query.filter_by(code='CS2001').first()
            self.assertIsNotNone(course)
            course_id = course.id

        # 2. Search / List Course
        search_resp = self.client.get('/admin/courses?q=Structures')
        self.assertIn(b'CS2001', search_resp.data)

        # 3. Edit Course
        edit_resp = self.client.post(f'/admin/courses/{course_id}/edit', data={
            'code': 'CS2001',
            'name': 'Advanced Data Structures and Algorithms',
            'department': 'CSE',
            'credits': '4',
            'status': 'Active',
            'description': 'Updated description'
        }, follow_redirects=True)
        self.assertIn(b'updated successfully', edit_resp.data)
        self.assertIn(b'Advanced Data Structures', edit_resp.data)

        # 4. Toggle Course Status
        toggle_resp = self.client.post(f'/admin/courses/{course_id}/toggle-status', follow_redirects=True)
        self.assertIn(b'status set to Inactive', toggle_resp.data)

        # 5. Guard against deletion when linked examination exists
        with self.app.app_context():
            exam = Examination(course_id=course_id, name='DSA Midterm', exam_type='Practical', duration=60, max_marks=50)
            db.session.add(exam)
            db.session.commit()

        delete_blocked = self.client.post(f'/admin/courses/{course_id}/delete', follow_redirects=True)
        self.assertIn(b'Cannot delete course', delete_blocked.data)

        # Verify course still exists
        with self.app.app_context():
            course_check = db.session.get(Course, course_id)
            self.assertIsNotNone(course_check)

            # Remove exam manually and re-attempt delete
            db.session.delete(exam)
            db.session.commit()

        # 6. Delete Course successfully now that no exams depend on it
        delete_success = self.client.post(f'/admin/courses/{course_id}/delete', follow_redirects=True)
        self.assertIn(b'removed successfully', delete_success.data)

    def test_examination_crud_and_validation(self):
        """Test examination creation, date validation, and editing."""
        with self.app.app_context():
            course = Course(code='MA101', name='Calculus I', credits=4, status='Active')
            db.session.add(course)
            db.session.commit()
            course_id = course.id

        # Test date validation: start > end should fail
        invalid_dates_resp = self.client.post('/admin/examinations/create', data={
            'course_id': str(course_id),
            'name': 'Calculus Viva',
            'exam_type': 'Viva',
            'duration': '30',
            'max_marks': '25',
            'slot_creation_start_date': '2026-11-20T10:00',
            'slot_creation_end_date': '2026-11-15T10:00',  # Earlier than start!
            'status': 'Draft'
        }, follow_redirects=True)
        self.assertIn(b'must be earlier than or equal to End Date', invalid_dates_resp.data)

        # Valid examination creation
        valid_resp = self.client.post('/admin/examinations/create', data={
            'course_id': str(course_id),
            'name': 'Calculus Viva 1',
            'exam_type': 'Viva',
            'duration': '30',
            'max_marks': '25',
            'slot_creation_start_date': '2026-11-10T10:00',
            'slot_creation_end_date': '2026-11-20T10:00',
            'slot_booking_start_date': '2026-11-21T10:00',
            'slot_booking_end_date': '2026-11-25T10:00',
            'status': 'Draft'
        }, follow_redirects=True)
        self.assertEqual(valid_resp.status_code, 200)
        self.assertIn(b'created successfully', valid_resp.data)
        self.assertIn(b'Calculus Viva 1', valid_resp.data)

        with self.app.app_context():
            exam = Examination.query.filter_by(name='Calculus Viva 1').first()
            self.assertIsNotNone(exam)
            exam_id = exam.id

        # Edit examination
        edit_resp = self.client.post(f'/admin/examinations/{exam_id}/edit', data={
            'course_id': str(course_id),
            'name': 'Calculus Final Viva',
            'exam_type': 'Viva',
            'duration': '40',
            'max_marks': '30',
            'status': 'Draft'
        }, follow_redirects=True)
        self.assertIn(b'updated successfully', edit_resp.data)

    def test_rubric_criteria_management_and_mark_limit(self):
        """Test rubric creation, total mark limit validation, and evaluation locking."""
        with self.app.app_context():
            course = Course(code='CS301', name='Web App Dev', credits=4, status='Active')
            db.session.add(course)
            db.session.flush()
            exam = Examination(course_id=course.id, name='Web Project Demo', exam_type='Project Demo', duration=30, max_marks=20)
            db.session.add(exam)
            db.session.commit()
            exam_id = exam.id

        # 1. Add valid criterion 1 (10 marks)
        r1_resp = self.client.post(f'/admin/examinations/{exam_id}/rubrics/add', data={
            'criterion_name': 'Backend API Architecture',
            'max_marks': '10',
            'weightage': '1.0',
            'description': 'REST design and database modeling'
        }, follow_redirects=True)
        self.assertIn(b'added successfully', r1_resp.data)

        # 2. Add criterion exceeding examination max marks (20 marks total exam, 10 allocated, trying to add 15 -> 25 > 20)
        exceed_resp = self.client.post(f'/admin/examinations/{exam_id}/rubrics/add', data={
            'criterion_name': 'UI/UX Design',
            'max_marks': '15',
            'weightage': '1.0'
        }, follow_redirects=True)
        self.assertIn(b'would exceed', exceed_resp.data)

        # 3. Add criterion fitting within remaining marks (10 marks)
        r2_resp = self.client.post(f'/admin/examinations/{exam_id}/rubrics/add', data={
            'criterion_name': 'Frontend UI Design',
            'max_marks': '10',
            'weightage': '1.0'
        }, follow_redirects=True)
        self.assertIn(b'added successfully', r2_resp.data)

        # Verify total allocated is 20 / 20
        with self.app.app_context():
            exam = db.session.get(Examination, exam_id)
            self.assertEqual(exam.total_rubric_marks, 20.0)
            self.assertEqual(exam.rubric_marks_remaining, 0.0)

            # 4. Simulate a student evaluation being recorded
            now = datetime.now(timezone.utc)
            slot = Slot(examination_id=exam_id, start_time=now, end_time=now + timedelta(hours=1), capacity=10)
            db.session.add(slot)
            db.session.flush()

            stu_user = User(name='Student Evaluated', email='ev@test.com', role='student')
            stu_user.set_password('Pass123')
            db.session.add(stu_user)
            db.session.flush()
            student = Student(user_id=stu_user.id, roll_number='21F9999', program='BS DS')
            db.session.add(student)
            db.session.flush()

            booking = Booking(student_id=student.id, slot_id=slot.id, status='confirmed', attendance='present', score=18.5)
            db.session.add(booking)
            db.session.commit()

            rubric_id = exam.rubrics[0].id

        # 5. Attempting to add or delete rubrics after evaluations must be rejected
        blocked_delete = self.client.post(f'/admin/examinations/{exam_id}/rubrics/{rubric_id}/delete', follow_redirects=True)
        self.assertIn(b'evaluations have been recorded', blocked_delete.data)

        blocked_add = self.client.post(f'/admin/examinations/{exam_id}/rubrics/add', data={
            'criterion_name': 'Post evaluation',
            'max_marks': '2'
        }, follow_redirects=True)
        self.assertIn(b'evaluations have already been recorded', blocked_add.data)

    def test_examiner_management_lifecycle(self):
        """Test examiner approval, search, deactivation, and reactivation."""
        # Register an examiner
        with self.app.app_context():
            ex_user = User(name='Dr. APJ Kalam', email='kalam@dept.iitm.ac.in', role='examiner', account_status='pending')
            ex_user.set_password('KalamPass123')
            db.session.add(ex_user)
            db.session.flush()
            examiner = Examiner(user_id=ex_user.id, department='Aerospace & Computing', contact_information='+91 9900011122', approval_status='pending')
            db.session.add(examiner)
            db.session.commit()
            examiner_id = examiner.id

        # 1. Search examiner by name
        search_resp = self.client.get('/admin/examiners?q=Kalam')
        self.assertIn(b'Dr. APJ Kalam', search_resp.data)

        # 2. Approve examiner
        approve_resp = self.client.post(f'/admin/examiner/{examiner_id}/approve', follow_redirects=True)
        self.assertIn(b'has been approved', approve_resp.data)

        with self.app.app_context():
            ex = db.session.get(Examiner, examiner_id)
            self.assertEqual(ex.approval_status, 'approved')
            self.assertEqual(ex.user.account_status, 'active')

        # 3. Deactivate examiner
        deact_resp = self.client.post(f'/admin/examiner/{examiner_id}/deactivate', follow_redirects=True)
        self.assertIn(b'has been deactivated', deact_resp.data)

        with self.app.app_context():
            ex = db.session.get(Examiner, examiner_id)
            self.assertEqual(ex.approval_status, 'deactivated')

        # 4. Reactivate examiner
        react_resp = self.client.post(f'/admin/examiners/{examiner_id}/reactivate', follow_redirects=True)
        self.assertIn(b'has been reactivated', react_resp.data)

        with self.app.app_context():
            ex = db.session.get(Examiner, examiner_id)
            self.assertEqual(ex.approval_status, 'approved')

    def test_student_management_and_search(self):
        """Test viewing and searching students and their profile details."""
        with self.app.app_context():
            stu_user = User(name='Priya Sundaram', email='priya@study.iitm.ac.in', role='student', account_status='active')
            stu_user.set_password('Priya123!')
            db.session.add(stu_user)
            db.session.flush()
            student = Student(user_id=stu_user.id, roll_number='21F2000555', program='Diploma in Programming', department='CSE')
            db.session.add(student)
            db.session.commit()
            student_id = student.id

        # 1. Search student by roll number
        search_resp = self.client.get('/admin/students?q=21F2000555')
        self.assertIn(b'Priya Sundaram', search_resp.data)
        self.assertIn(b'21F2000555', search_resp.data)

        # 2. View student profile
        view_resp = self.client.get(f'/admin/students/{student_id}')
        self.assertEqual(view_resp.status_code, 200)
        self.assertIn(b'Diploma in Programming', view_resp.data)
        self.assertIn(b'Priya Sundaram', view_resp.data)

    def test_timeline_transition_controls_and_methods(self):
        """Test examination status transitions and timeline date boundary checks."""
        with self.app.app_context():
            course = Course(code='CS401', name='Cloud Systems', credits=4, status='Active')
            db.session.add(course)
            db.session.flush()

            now = datetime.now(timezone.utc)
            exam = Examination(
                course_id=course.id,
                name='Cloud Final Exam',
                exam_type='Assessment',
                duration=60,
                max_marks=100,
                status='Draft',
                slot_creation_start_date=now - timedelta(days=2),
                slot_creation_end_date=now + timedelta(days=2),
                slot_booking_start_date=now + timedelta(days=3),
                slot_booking_end_date=now + timedelta(days=5)
            )
            db.session.add(exam)
            db.session.commit()
            exam_id = exam.id

            # In Draft status, slot creation and booking should be false
            self.assertFalse(exam.can_create_slots())
            self.assertFalse(exam.can_book_slots())

        # 1. Admin transitions status to 'Slot Creation'
        status_resp = self.client.post(f'/admin/examinations/{exam_id}/status/Slot Creation', follow_redirects=True)
        self.assertIn(b'status updated', status_resp.data)
        self.assertIn(b'Slot Creation', status_resp.data)

        with self.app.app_context():
            exam = db.session.get(Examination, exam_id)
            self.assertEqual(exam.status, 'Slot Creation')
            # Currently within slot creation window
            self.assertTrue(exam.can_create_slots())
            # Outside creation window test
            future_check = datetime.now(timezone.utc) + timedelta(days=10)
            self.assertFalse(exam.can_create_slots(check_time=future_check))

        # 2. Transition status to 'Booking Open'
        self.client.post(f'/admin/examinations/{exam_id}/status/Booking Open', follow_redirects=True)

        with self.app.app_context():
            exam = db.session.get(Examination, exam_id)
            self.assertEqual(exam.status, 'Booking Open')
            # Check during booking window
            booking_check_time = datetime.now(timezone.utc) + timedelta(days=4)
            self.assertTrue(exam.can_book_slots(check_time=booking_check_time))


if __name__ == '__main__':
    unittest.main()
