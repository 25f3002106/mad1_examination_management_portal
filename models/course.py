from datetime import datetime, timezone
from database.db import db


class Course(db.Model):
    """Academic course entity for examinations."""
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    department = db.Column(db.String(100), nullable=True)
    credits = db.Column(db.Integer, default=4, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Active')  # 'Active', 'Inactive'
    examiner_id = db.Column(db.Integer, db.ForeignKey('examiners.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    examiner = db.relationship('Examiner', back_populates='assigned_courses')
    # Note: No cascade delete-orphan so that deletion can be guarded when exams exist
    examinations = db.relationship('Examination', back_populates='course')

    @property
    def title(self) -> str:
        """Alias for backward compatibility."""
        return self.name

    @title.setter
    def title(self, val: str):
        self.name = val

    @property
    def is_active(self) -> bool:
        return self.status == 'Active'

    def __repr__(self) -> str:
        return f"<Course {self.code}: {self.name} [{self.status}]>"
