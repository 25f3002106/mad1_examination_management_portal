from datetime import datetime, timezone
from database.db import db

# Association Table for Many-to-Many relationship between Examinations and Examiners
examination_examiners = db.Table(
    'examination_examiners',
    db.Column('examination_id', db.Integer, db.ForeignKey('examinations.id', ondelete='CASCADE'), primary_key=True),
    db.Column('examiner_id', db.Integer, db.ForeignKey('examiners.id', ondelete='CASCADE'), primary_key=True)
)


class Examination(db.Model):
    """Examination assessment model with course, timeline, and examiner associations."""
    __tablename__ = 'examinations'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='RESTRICT'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    exam_type = db.Column(db.String(50), nullable=False, default='Assessment')  # 'Viva', 'Practical', 'Project Demo', 'Assessment'
    duration = db.Column(db.Integer, nullable=False, default=60)  # in minutes
    max_marks = db.Column(db.Integer, nullable=False, default=100)

    # Timeline controls
    slot_creation_start_date = db.Column(db.DateTime, nullable=True)
    slot_creation_end_date = db.Column(db.DateTime, nullable=True)
    slot_booking_start_date = db.Column(db.DateTime, nullable=True)
    slot_booking_end_date = db.Column(db.DateTime, nullable=True)

    status = db.Column(db.String(30), nullable=False, default='Draft')  # 'Draft', 'Slot Creation', 'Booking Open', 'Closed', 'Completed'
    results_published = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    course = db.relationship('Course', back_populates='examinations')
    slots = db.relationship('Slot', back_populates='examination', cascade='all, delete-orphan')
    examiners = db.relationship(
        'Examiner',
        secondary=examination_examiners,
        back_populates='assigned_examinations'
    )
    rubrics = db.relationship(
        'RubricCriterion',
        back_populates='examination',
        cascade='all, delete-orphan',
        order_by='RubricCriterion.id'
    )

    # Aliases for backward compatibility
    @property
    def title(self) -> str:
        return self.name

    @title.setter
    def title(self, value: str):
        self.name = value

    @property
    def duration_minutes(self) -> int:
        return self.duration

    @duration_minutes.setter
    def duration_minutes(self, value: int):
        self.duration = value

    @property
    def total_marks(self) -> int:
        return self.max_marks

    @total_marks.setter
    def total_marks(self, value: int):
        self.max_marks = value

    @property
    def total_rubric_marks(self) -> float:
        """Sum of maximum marks across all defined rubric criteria."""
        return sum(float(r.max_marks) for r in self.rubrics)

    @property
    def rubric_marks_remaining(self) -> float:
        """Remaining marks available to allocate to rubrics."""
        return max(0.0, float(self.max_marks) - self.total_rubric_marks)

    @property
    def total_bookings_count(self) -> int:
        """Total bookings made for slots under this examination."""
        return sum(len(slot.bookings) for slot in self.slots)

    def has_evaluations_submitted(self) -> bool:
        """Check if any student booking has an assigned score or evaluation recorded."""
        for slot in self.slots:
            for booking in slot.bookings:
                if booking.score is not None or booking.attendance == 'present':
                    return True
        return False

    def can_create_slots(self, check_time: datetime = None) -> bool:
        """Check if examiner slot creation is currently permitted based on status and dates."""
        if self.status != 'Slot Creation':
            return False
        if check_time is None:
            check_time = datetime.now(timezone.utc)
        elif check_time.tzinfo is None:
            check_time = check_time.replace(tzinfo=timezone.utc)
        if self.slot_creation_start_date:
            start = self.slot_creation_start_date.replace(tzinfo=timezone.utc) if self.slot_creation_start_date.tzinfo is None else self.slot_creation_start_date
            if check_time < start:
                return False
        if self.slot_creation_end_date:
            end = self.slot_creation_end_date.replace(tzinfo=timezone.utc) if self.slot_creation_end_date.tzinfo is None else self.slot_creation_end_date
            if check_time > end:
                return False
        return True

    def can_book_slots(self, check_time: datetime = None) -> bool:
        """Check if student slot booking is currently permitted based on status and dates."""
        if self.status != 'Booking Open':
            return False
        if check_time is None:
            check_time = datetime.now(timezone.utc)
        elif check_time.tzinfo is None:
            check_time = check_time.replace(tzinfo=timezone.utc)
        if self.slot_booking_start_date:
            start = self.slot_booking_start_date.replace(tzinfo=timezone.utc) if self.slot_booking_start_date.tzinfo is None else self.slot_booking_start_date
            if check_time < start:
                return False
        if self.slot_booking_end_date:
            end = self.slot_booking_end_date.replace(tzinfo=timezone.utc) if self.slot_booking_end_date.tzinfo is None else self.slot_booking_end_date
            if check_time > end:
                return False
        return True

    def __repr__(self) -> str:
        return f"<Examination id={self.id} name='{self.name}' status='{self.status}'>"


class RubricCriterion(db.Model):
    """Rubric evaluation criterion for an examination."""
    __tablename__ = 'rubric_criteria'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    examination_id = db.Column(db.Integer, db.ForeignKey('examinations.id', ondelete='CASCADE'), nullable=False)
    criterion_name = db.Column(db.String(150), nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    weightage = db.Column(db.Float, nullable=True, default=1.0)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    examination = db.relationship('Examination', back_populates='rubrics')
    criterion_scores = db.relationship('CriterionScore', back_populates='rubric_criterion', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f"<RubricCriterion id={self.id} exam_id={self.examination_id} name='{self.criterion_name}' marks={self.max_marks}>"
