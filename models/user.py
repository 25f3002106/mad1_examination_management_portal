from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import db


class User(db.Model):
    """Core user model representing all portal actors (Admin, Examiner, Student)."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin', 'examiner', 'student'
    account_status = db.Column(db.String(20), nullable=False, default='active')  # 'active', 'pending', 'deactivated'
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # One-to-One relationships with profiles
    student_profile = db.relationship(
        'Student',
        back_populates='user',
        uselist=False,
        cascade='all, delete-orphan'
    )
    examiner_profile = db.relationship(
        'Examiner',
        back_populates='user',
        uselist=False,
        cascade='all, delete-orphan'
    )

    def set_password(self, password: str) -> None:
        """Hash and set user password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify candidate password against hash."""
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    @property
    def is_examiner(self) -> bool:
        return self.role == 'examiner'

    @property
    def is_student(self) -> bool:
        return self.role == 'student'

    @property
    def is_active(self) -> bool:
        return self.account_status == 'active'

    def __repr__(self) -> str:
        return f"<User id={self.id} email='{self.email}' role='{self.role}' status='{self.account_status}'>"


class Student(db.Model):
    """Student academic profile model."""
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    roll_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    program = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(120), nullable=True)
    contact_number = db.Column(db.String(20), nullable=True)

    # Relationships
    user = db.relationship('User', back_populates='student_profile')
    bookings = db.relationship('Booking', back_populates='student', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f"<Student id={self.id} roll='{self.roll_number}' program='{self.program}'>"


class Examiner(db.Model):
    """Examiner faculty profile model with administrative approval lifecycle."""
    __tablename__ = 'examiners'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    department = db.Column(db.String(120), nullable=False)
    contact_information = db.Column(db.String(120), nullable=False)
    approval_status = db.Column(
        db.String(20),
        nullable=False,
        default='pending'
    )  # 'pending', 'approved', 'deactivated'

    # Relationships
    user = db.relationship('User', back_populates='examiner_profile')
    assigned_courses = db.relationship('Course', back_populates='examiner')
    assigned_examinations = db.relationship(
        'Examination',
        secondary='examination_examiners',
        back_populates='examiners'
    )
    slots = db.relationship('Slot', back_populates='examiner')
    evaluations = db.relationship('Evaluation', back_populates='examiner')

    @property
    def is_approved(self) -> bool:
        return self.approval_status == 'approved'

    def __repr__(self) -> str:
        return f"<Examiner id={self.id} department='{self.department}' status='{self.approval_status}'>"
