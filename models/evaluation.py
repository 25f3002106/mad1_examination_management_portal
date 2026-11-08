from datetime import datetime, timezone
from database.db import db


class Evaluation(db.Model):
    """Rubric-based evaluation submitted by an examiner for a student booking."""
    __tablename__ = 'evaluations'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    booking_id = db.Column(
        db.Integer,
        db.ForeignKey('bookings.id', ondelete='CASCADE'),
        unique=True,
        nullable=False
    )
    examiner_id = db.Column(
        db.Integer,
        db.ForeignKey('examiners.id', ondelete='SET NULL'),
        nullable=True
    )
    evaluation_date = db.Column(db.DateTime, nullable=True)
    total_marks = db.Column(db.Float, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='draft')  # 'draft', 'submitted'
    is_published = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    booking = db.relationship('Booking', back_populates='evaluation')
    examiner = db.relationship('Examiner', back_populates='evaluations')
    criterion_scores = db.relationship(
        'CriterionScore',
        back_populates='evaluation',
        cascade='all, delete-orphan'
    )

    @property
    def publication_status(self) -> str:
        return 'Published' if self.is_published else 'Unpublished'

    def __repr__(self) -> str:
        return f'<Evaluation id={self.id} booking={self.booking_id} status="{self.status}" total={self.total_marks}>'


class CriterionScore(db.Model):
    """Individual criterion mark within an evaluation."""
    __tablename__ = 'criterion_scores'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    evaluation_id = db.Column(
        db.Integer,
        db.ForeignKey('evaluations.id', ondelete='CASCADE'),
        nullable=False
    )
    rubric_criterion_id = db.Column(
        db.Integer,
        db.ForeignKey('rubric_criteria.id', ondelete='CASCADE'),
        nullable=False
    )
    marks_awarded = db.Column(db.Float, nullable=False, default=0.0)
    remarks = db.Column(db.Text, nullable=True)

    # Relationships
    evaluation = db.relationship('Evaluation', back_populates='criterion_scores')
    rubric_criterion = db.relationship('RubricCriterion', back_populates='criterion_scores')

    __table_args__ = (
        db.UniqueConstraint('evaluation_id', 'rubric_criterion_id', name='uq_eval_criterion'),
    )

    def __repr__(self) -> str:
        return f'<CriterionScore id={self.id} eval={self.evaluation_id} crit={self.rubric_criterion_id} marks={self.marks_awarded}>'
