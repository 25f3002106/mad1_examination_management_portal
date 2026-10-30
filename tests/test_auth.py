import os
import sys
import unittest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from database.db import db
from database.init_db import init_db
from models.user import User, Student, Examiner


class AuthTestCase(unittest.TestCase):
    """Test suite for EMP Authentication, Role-based Access, and Foundation."""

    def setUp(self):
        """Configure test application with in-memory SQLite database."""
        self.app = create_app('testing')
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            init_db(self.app)

    def tearDown(self):
        """Clean up database session and tables."""
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_admin_initialization_and_login(self):
        """Test default admin is seeded and can authenticate successfully."""
        with self.app.app_context():
            admin = User.query.filter_by(role='admin').first()
            self.assertIsNotNone(admin)
            self.assertEqual(admin.email, 'admin@emp.iitm.ac.in')
            self.assertTrue(admin.check_password('AdminPassword123!'))

        # Log in with admin credentials
        response = self.client.post('/auth/login', data={
            'email': 'admin@emp.iitm.ac.in',
            'password': 'AdminPassword123!'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Admin Dashboard', response.data)
        self.assertIn(b'Administrative Overview', response.data)

    def test_invalid_credentials_login(self):
        """Test invalid credentials reject login with flash error."""
        response = self.client.post('/auth/login', data={
            'email': 'admin@emp.iitm.ac.in',
            'password': 'WrongPassword123!'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid email or password', response.data)

        # Non-existent user
        response2 = self.client.post('/auth/login', data={
            'email': 'nobody@emp.iitm.ac.in',
            'password': 'AnyPassword'
        }, follow_redirects=True)
        self.assertIn(b'Invalid email or password', response2.data)

    def test_student_registration_and_login(self):
        """Test student registration and subsequent direct access to student dashboard."""
        response = self.client.post('/auth/register/student', data={
            'name': 'Aarav Sharma',
            'email': 'aarav@study.iitm.ac.in',
            'roll_number': '21F1000999',
            'program': 'BS in Data Science and Applications',
            'department': 'Data Science',
            'contact_number': '+91 9988776655',
            'password': 'StudentSecret123',
            'confirm_password': 'StudentSecret123'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Student Dashboard', response.data)
        self.assertIn(b'21F1000999', response.data)
        self.assertIn(b'Aarav Sharma', response.data)

        # Verify DB entries
        with self.app.app_context():
            user = User.query.filter_by(email='aarav@study.iitm.ac.in').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.role, 'student')
            self.assertIsNotNone(user.student_profile)
            self.assertEqual(user.student_profile.roll_number, '21F1000999')

    def test_duplicate_email_registration(self):
        """Test registration prevents duplicate email across the portal."""
        # First student
        self.client.post('/auth/register/student', data={
            'name': 'Student One',
            'email': 'duplicate@study.iitm.ac.in',
            'roll_number': '21F1000001',
            'program': 'Foundation Level',
            'password': 'SecretPassword123',
            'confirm_password': 'SecretPassword123'
        }, follow_redirects=True)

        # Attempt duplicate student registration
        response = self.client.post('/auth/register/student', data={
            'name': 'Student Two',
            'email': 'duplicate@study.iitm.ac.in',
            'roll_number': '21F1000002',
            'program': 'Diploma in Programming',
            'password': 'SecretPassword123',
            'confirm_password': 'SecretPassword123'
        }, follow_redirects=True)

        self.assertIn(b'already exists', response.data)

        # Attempt examiner registration with same email
        response2 = self.client.post('/auth/register/examiner', data={
            'name': 'Examiner Two',
            'email': 'duplicate@study.iitm.ac.in',
            'department': 'Computer Science',
            'contact_information': 'Office 101',
            'password': 'SecretPassword123',
            'confirm_password': 'SecretPassword123'
        }, follow_redirects=True)

        self.assertIn(b'already exists', response2.data)

    def test_examiner_registration_and_pending_restriction(self):
        """Test examiner registers with pending status and cannot access examiner dashboard."""
        response = self.client.post('/auth/register/examiner', data={
            'name': 'Dr. Ramanujan',
            'email': 'ramanujan@faculty.iitm.ac.in',
            'department': 'Mathematics & Computing',
            'contact_information': '+91 9123456780',
            'password': 'ExaminerPass123',
            'confirm_password': 'ExaminerPass123'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'pending Administrator approval', response.data)

        # Check DB state
        with self.app.app_context():
            examiner_user = User.query.filter_by(email='ramanujan@faculty.iitm.ac.in').first()
            self.assertIsNotNone(examiner_user)
            self.assertEqual(examiner_user.role, 'examiner')
            self.assertEqual(examiner_user.examiner_profile.approval_status, 'pending')

        # Try to access examiner dashboard directly while pending
        dash_response = self.client.get('/examiner/dashboard', follow_redirects=True)
        self.assertIn(b'pending administrator approval', dash_response.data.lower())
        self.assertNotIn(b'Question Papers', dash_response.data)

    def test_admin_approves_examiner_and_examiner_can_access_dashboard(self):
        """Test admin can approve an examiner, granting dashboard access."""
        # 1. Examiner registers
        self.client.post('/auth/register/examiner', data={
            'name': 'Prof. Visvesvaraya',
            'email': 'visvesvaraya@faculty.iitm.ac.in',
            'department': 'Civil & Computational Engineering',
            'contact_information': 'Room 204',
            'password': 'ExaminerPass123',
            'confirm_password': 'ExaminerPass123'
        }, follow_redirects=True)

        # 2. Admin logs in
        self.client.post('/auth/login', data={
            'email': 'admin@emp.iitm.ac.in',
            'password': 'AdminPassword123!'
        }, follow_redirects=True)

        with self.app.app_context():
            examiner = Examiner.query.join(User).filter(User.email == 'visvesvaraya@faculty.iitm.ac.in').first()
            examiner_id = examiner.id

        # Admin approves examiner
        approve_resp = self.client.post(f'/admin/examiner/{examiner_id}/approve', follow_redirects=True)
        self.assertIn(b'has been approved', approve_resp.data)

        # Logout admin
        self.client.get('/auth/logout', follow_redirects=True)

        # 3. Examiner logs in now
        login_resp = self.client.post('/auth/login', data={
            'email': 'visvesvaraya@faculty.iitm.ac.in',
            'password': 'ExaminerPass123'
        }, follow_redirects=True)

        self.assertEqual(login_resp.status_code, 200)
        self.assertIn(b'Examiner Dashboard', login_resp.data)
        self.assertIn(b'Civil &amp; Computational Engineering', login_resp.data)

    def test_unauthorized_role_access(self):
        """Test role-based access control prevents unauthorized route cross-access."""
        # Register and log in as student
        self.client.post('/auth/register/student', data={
            'name': 'Regular Student',
            'email': 'student@study.iitm.ac.in',
            'roll_number': '21F1000055',
            'program': 'Foundation Level',
            'password': 'StudentPass123',
            'confirm_password': 'StudentPass123'
        }, follow_redirects=True)

        # Student tries to access Admin dashboard -> 403 Forbidden
        admin_resp = self.client.get('/admin/dashboard')
        self.assertEqual(admin_resp.status_code, 403)
        self.assertIn(b'403', admin_resp.data)

        # Student tries to access Examiner dashboard -> 403 Forbidden
        examiner_resp = self.client.get('/examiner/dashboard')
        self.assertEqual(examiner_resp.status_code, 403)
        self.assertIn(b'403', examiner_resp.data)

    def test_unauthenticated_access_redirects_to_login(self):
        """Test that unauthenticated requests to protected dashboards redirect to login."""
        endpoints = ['/admin/dashboard', '/examiner/dashboard', '/student/dashboard']
        for ep in endpoints:
            response = self.client.get(ep, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Please log in to access this page', response.data)
            self.assertIn(b'Sign In to EMP', response.data)

    def test_registration_validation_rules(self):
        """Test password length and mismatch validation on registration."""
        # Password too short
        resp_short = self.client.post('/auth/register/student', data={
            'name': 'Short Pass Student',
            'email': 'short@study.iitm.ac.in',
            'roll_number': '21F1000088',
            'program': 'Foundation Level',
            'password': '123',
            'confirm_password': '123'
        }, follow_redirects=True)
        self.assertIn(b'at least 6 characters', resp_short.data)

        # Password mismatch
        resp_mismatch = self.client.post('/auth/register/student', data={
            'name': 'Mismatch Student',
            'email': 'mismatch@study.iitm.ac.in',
            'roll_number': '21F1000089',
            'program': 'Foundation Level',
            'password': 'Password123',
            'confirm_password': 'Password456'
        }, follow_redirects=True)
        self.assertIn(b'Passwords do not match', resp_mismatch.data)

    def test_deactivated_examiner_access_blocked(self):
        """Test deactivated examiner cannot access examiner dashboard."""
        # 1. Register examiner
        self.client.post('/auth/register/examiner', data={
            'name': 'Prof. Blocked',
            'email': 'blocked@faculty.iitm.ac.in',
            'department': 'Mechanical',
            'contact_information': 'Room 10',
            'password': 'ExaminerPass123',
            'confirm_password': 'ExaminerPass123'
        }, follow_redirects=True)

        # 2. Admin deactivates examiner
        self.client.post('/auth/login', data={
            'email': 'admin@emp.iitm.ac.in',
            'password': 'AdminPassword123!'
        }, follow_redirects=True)

        with self.app.app_context():
            examiner = Examiner.query.join(User).filter(User.email == 'blocked@faculty.iitm.ac.in').first()
            examiner_id = examiner.id

        self.client.post(f'/admin/examiner/{examiner_id}/deactivate', follow_redirects=True)

        # Logout admin
        self.client.get('/auth/logout', follow_redirects=True)

        # Examiner tries to log in
        login_resp = self.client.post('/auth/login', data={
            'email': 'blocked@faculty.iitm.ac.in',
            'password': 'ExaminerPass123'
        }, follow_redirects=True)
        self.assertIn(b'deactivated', login_resp.data.lower())

    def test_logout(self):
        """Test logging out clears user session."""
        self.client.post('/auth/login', data={
            'email': 'admin@emp.iitm.ac.in',
            'password': 'AdminPassword123!'
        }, follow_redirects=True)

        logout_resp = self.client.get('/auth/logout', follow_redirects=True)
        self.assertEqual(logout_resp.status_code, 200)
        self.assertIn(b'successfully logged out', logout_resp.data)

        protected_resp = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertIn(b'Please log in to access this page', protected_resp.data)
        self.assertIn(b'Sign In to EMP', protected_resp.data)


if __name__ == '__main__':
    unittest.main()
