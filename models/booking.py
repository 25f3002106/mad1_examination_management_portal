from datetime import datetime, timezone
from database.db import db


class Booking(db.Model):
    """Student booking registration for an examination slot."""
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey('slots.id', ondelete='CASCADE'), nullable=False)
    booking_time = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(30), nullable=False, default='confirmed')  # 'confirmed', 'cancelled'
    attendance = db.Column(db.String(30), nullable=False, default='pending')  # 'pending', 'present', 'absent'
    score = db.Column(db.Float, nullable=True)

    # Rescheduling and historical audit trail
    original_slot_id = db.Column(db.Integer, nullable=True)
    rescheduled_at = db.Column(db.DateTime, nullable=True)
    rescheduled_by = db.Column(db.String(50), nullable=True)
    rescheduling_reason = db.Column(db.Text, nullable=True)
    history_notes = db.Column(db.Text, nullable=True)

    # Relationships
    student = db.relationship('Student', back_populates='bookings')
    slot = db.relationship('Slot', back_populates='bookings')
    evaluation = db.relationship('Evaluation', back_populates='booking', uselist=False)

    @property
    def is_active(self) -> bool:
        return self.status in ('confirmed', 'Booked')

    # Uniqueness constraint: a student can only book a given slot once
    __table_args__ = (
        db.UniqueConstraint('student_id', 'slot_id', name='uq_student_slot_booking'),
    )

    def __repr__(self) -> str:
        return f"<Booking id={self.id} student={self.student_id} slot={self.slot_id} status='{self.status}'>"
