from datetime import datetime, timezone
from database.db import db


class Slot(db.Model):
    """Specific examination time and capacity window created by an examiner."""
    __tablename__ = 'slots'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    examination_id = db.Column(db.Integer, db.ForeignKey('examinations.id', ondelete='CASCADE'), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey('examiners.id', ondelete='SET NULL'), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=30)
    room_or_link = db.Column(db.String(150), nullable=True)
    status = db.Column(db.String(30), nullable=False, default='Available')  # 'Available', 'Full', 'Cancelled', 'Completed'
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    examination = db.relationship('Examination', back_populates='slots')
    examiner = db.relationship('Examiner', back_populates='slots')
    bookings = db.relationship('Booking', back_populates='slot', cascade='all, delete-orphan')

    @property
    def booked_count(self) -> int:
        return len([b for b in self.bookings if b.status in ('confirmed', 'Booked')])

    @property
    def available_seats(self) -> int:
        return max(0, self.capacity - self.booked_count)

    def update_status_from_capacity(self) -> None:
        """Update slot status based on current active bookings and capacity."""
        if self.status not in ('Cancelled', 'Completed'):
            if self.available_seats <= 0:
                self.status = 'Full'
            else:
                self.status = 'Available'

    def __repr__(self) -> str:
        return f'<Slot id={self.id} exam_id={self.examination_id} examiner_id={self.examiner_id} cap={self.capacity}>'
