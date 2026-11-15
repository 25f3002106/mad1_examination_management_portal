from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from sqlalchemy import and_

from database.db import db
from models.user import Examiner
from models.examination import Examination, RubricCriterion
from models.slot import Slot
from models.booking import Booking
from models.evaluation import Evaluation, CriterionScore
from utils import login_required, examiner_approved_required, get_current_user

examiner_bp = Blueprint('examiner', __name__, url_prefix='/examiner')


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def get_current_examiner():
    """Return the Examiner profile for the logged-in user, or None."""
    user = get_current_user()
    if user and user.examiner_profile:
        return user.examiner_profile
    return None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@examiner_bp.route('/dashboard')
@login_required
@examiner_approved_required
def dashboard():
    """Examiner dashboard with real database-backed statistics."""
    user = get_current_user()
    examiner = user.examiner_profile

    # Assigned examinations
    assigned_exams = examiner.assigned_examinations

    # Slots created by this examiner
    examiner_slots = Slot.query.filter_by(examiner_id=examiner.id).all()
    slots_created = len(examiner_slots)

    # Total confirmed/booked bookings across examiner's slots
    slot_ids = [s.id for s in examiner_slots]
    students_booked = 0
    if slot_ids:
        students_booked = Booking.query.filter(
            Booking.slot_id.in_(slot_ids),
            Booking.status.in_(['confirmed', 'Booked', 'Completed'])
        ).count()

    # Evaluations: pending vs completed
    booking_ids_in_my_slots = [
        b.id for s in examiner_slots for b in s.bookings if b.status in ('confirmed', 'Booked', 'Completed')
    ]
    pending_evaluations = 0
    completed_evaluations = 0
    if booking_ids_in_my_slots:
        completed_evaluations = Evaluation.query.filter(
            Evaluation.booking_id.in_(booking_ids_in_my_slots),
            Evaluation.status == 'submitted'
        ).count()
        pending_evaluations = len(booking_ids_in_my_slots) - completed_evaluations

    return render_template(
        'examiner/dashboard.html',
        user=user,
        examiner=examiner,
        assigned_exams_count=len(assigned_exams),
        slots_created=slots_created,
        students_booked=students_booked,
        pending_evaluations=pending_evaluations,
        completed_evaluations=completed_evaluations,
        assigned_exams=assigned_exams,
    )


# ---------------------------------------------------------------------------
# Assigned Examinations
# ---------------------------------------------------------------------------

@examiner_bp.route('/examinations')
@login_required
@examiner_approved_required
def examinations():
    """List examinations assigned to this examiner."""
    examiner = get_current_examiner()
    assigned = examiner.assigned_examinations
    return render_template(
        'examiner/examinations/index.html',
        examiner=examiner,
        examinations=assigned,
    )


@examiner_bp.route('/examinations/<int:exam_id>')
@login_required
@examiner_approved_required
def examination_view(exam_id):
    """View details of an assigned examination."""
    examiner = get_current_examiner()
    exam = db.session.get(Examination, exam_id)
    if exam is None:
        abort(404)
    # Security: only assigned examiners may view
    if examiner not in exam.examiners:
        flash('You do not have access to this examination.', 'danger')
        return redirect(url_for('examiner.examinations'))

    # Slots created by this examiner for this exam
    slots = Slot.query.filter_by(examination_id=exam_id, examiner_id=examiner.id).order_by(Slot.start_time).all()
    now = datetime.now(timezone.utc)
    can_create = exam.can_create_slots(now)
    # Can edit/delete: only before booking starts or exam status allows
    booking_started = exam.status not in ('Draft', 'Slot Creation')

    return render_template(
        'examiner/examinations/view.html',
        examiner=examiner,
        exam=exam,
        slots=slots,
        can_create=can_create,
        booking_started=booking_started,
        now=now,
    )


# ---------------------------------------------------------------------------
# Slot Management
# ---------------------------------------------------------------------------

@examiner_bp.route('/examinations/<int:exam_id>/slots/create', methods=['GET', 'POST'])
@login_required
@examiner_approved_required
def slot_create(exam_id):
    """Create a new slot for an examination."""
    examiner = get_current_examiner()
    exam = db.session.get(Examination, exam_id)
    if exam is None:
        abort(404)

    # Must be assigned
    if examiner not in exam.examiners:
        flash('You do not have access to this examination.', 'danger')
        return redirect(url_for('examiner.examinations'))

    now = datetime.now(timezone.utc)

    # Must be within slot creation window
    if not exam.can_create_slots(now):
        flash('Slot creation is not currently permitted for this examination.', 'warning')
        return redirect(url_for('examiner.examination_view', exam_id=exam_id))

    if request.method == 'POST':
        date_str = request.form.get('date', '').strip()
        start_str = request.form.get('start_time', '').strip()
        end_str = request.form.get('end_time', '').strip()
        capacity_str = request.form.get('capacity', '').strip()
        room_or_link = request.form.get('room_or_link', '').strip()

        errors = []

        # Parse datetime
        try:
            start_time = datetime.strptime(f'{date_str} {start_str}', '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
            end_time = datetime.strptime(f'{date_str} {end_str}', '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        except ValueError:
            errors.append('Invalid date or time format.')
            start_time = end_time = None

        # Capacity
        try:
            capacity = int(capacity_str)
            if capacity <= 0:
                errors.append('Capacity must be greater than zero.')
        except (ValueError, TypeError):
            errors.append('Capacity must be a valid integer.')
            capacity = None

        if start_time and end_time:
            # start < end
            if start_time >= end_time:
                errors.append('Start time must be before end time.')

            # No past slots
            if start_time <= now:
                errors.append('Slot start time must be in the future.')

            # Duration respect: slot duration >= exam duration
            if not errors:
                slot_duration_minutes = (end_time - start_time).total_seconds() / 60
                if slot_duration_minutes < exam.duration:
                    errors.append(
                        f'Slot duration ({int(slot_duration_minutes)} min) must be at least the examination duration ({exam.duration} min).'
                    )

            # Overlap check: same examiner, same day
            if not errors:
                overlapping = Slot.query.filter(
                    Slot.examiner_id == examiner.id,
                    Slot.status != 'Cancelled',
                    Slot.start_time < end_time,
                    Slot.end_time > start_time,
                ).first()
                if overlapping:
                    errors.append('This slot overlaps with one of your existing slots.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template(
                'examiner/slots/form.html',
                examiner=examiner,
                exam=exam,
                form_data=request.form,
                action='create',
            )

        slot = Slot(
            examination_id=exam_id,
            examiner_id=examiner.id,
            start_time=start_time,
            end_time=end_time,
            capacity=capacity,
            room_or_link=room_or_link or None,
            status='Available',
        )
        db.session.add(slot)
        db.session.commit()
        flash('Slot created successfully.', 'success')
        return redirect(url_for('examiner.examination_view', exam_id=exam_id))

    return render_template(
        'examiner/slots/form.html',
        examiner=examiner,
        exam=exam,
        form_data={},
        action='create',
    )


@examiner_bp.route('/slots/<int:slot_id>/edit', methods=['GET', 'POST'])
@login_required
@examiner_approved_required
def slot_edit(slot_id):
    """Edit an existing slot (only before booking starts)."""
    examiner = get_current_examiner()
    slot = db.session.get(Slot, slot_id)
    if slot is None:
        abort(404)

    # Ownership check
    if slot.examiner_id != examiner.id:
        flash('You can only edit your own slots.', 'danger')
        return redirect(url_for('examiner.examinations'))

    exam = slot.examination

    # Blocked if booking has started or slot has bookings
    booking_started = exam.status not in ('Draft', 'Slot Creation')
    if booking_started or slot.booked_count > 0:
        flash('Slot cannot be edited once booking has started or students are booked.', 'warning')
        return redirect(url_for('examiner.examination_view', exam_id=exam.id))

    now = datetime.now(timezone.utc)

    if request.method == 'POST':
        date_str = request.form.get('date', '').strip()
        start_str = request.form.get('start_time', '').strip()
        end_str = request.form.get('end_time', '').strip()
        capacity_str = request.form.get('capacity', '').strip()
        room_or_link = request.form.get('room_or_link', '').strip()

        errors = []

        try:
            start_time = datetime.strptime(f'{date_str} {start_str}', '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
            end_time = datetime.strptime(f'{date_str} {end_str}', '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        except ValueError:
            errors.append('Invalid date or time format.')
            start_time = end_time = None

        try:
            capacity = int(capacity_str)
            if capacity <= 0:
                errors.append('Capacity must be greater than zero.')
        except (ValueError, TypeError):
            errors.append('Capacity must be a valid integer.')
            capacity = None

        if start_time and end_time:
            if start_time >= end_time:
                errors.append('Start time must be before end time.')
            if start_time <= now:
                errors.append('Slot start time must be in the future.')
            if not errors:
                slot_duration_minutes = (end_time - start_time).total_seconds() / 60
                if slot_duration_minutes < exam.duration:
                    errors.append(
                        f'Slot duration ({int(slot_duration_minutes)} min) must be at least the examination duration ({exam.duration} min).'
                    )
            if not errors:
                overlapping = Slot.query.filter(
                    Slot.examiner_id == examiner.id,
                    Slot.id != slot_id,
                    Slot.status != 'Cancelled',
                    Slot.start_time < end_time,
                    Slot.end_time > start_time,
                ).first()
                if overlapping:
                    errors.append('This slot overlaps with one of your existing slots.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template(
                'examiner/slots/form.html',
                examiner=examiner,
                exam=exam,
                slot=slot,
                form_data=request.form,
                action='edit',
            )

        slot.start_time = start_time
        slot.end_time = end_time
        slot.capacity = capacity
        slot.room_or_link = room_or_link or None
        db.session.commit()
        flash('Slot updated successfully.', 'success')
        return redirect(url_for('examiner.examination_view', exam_id=exam.id))

    # Pre-populate form with existing slot data
    slot_start_naive = slot.start_time.replace(tzinfo=None) if slot.start_time.tzinfo else slot.start_time
    form_data = {
        'date': slot.start_time.strftime('%Y-%m-%d'),
        'start_time': slot.start_time.strftime('%H:%M'),
        'end_time': slot.end_time.strftime('%H:%M'),
        'capacity': slot.capacity,
        'room_or_link': slot.room_or_link or '',
    }

    return render_template(
        'examiner/slots/form.html',
        examiner=examiner,
        exam=exam,
        slot=slot,
        form_data=form_data,
        action='edit',
    )


@examiner_bp.route('/slots/<int:slot_id>/cancel', methods=['POST'])
@login_required
@examiner_approved_required
def slot_cancel(slot_id):
    """Cancel a slot (only before booking starts and if no bookings)."""
    examiner = get_current_examiner()
    slot = db.session.get(Slot, slot_id)
    if slot is None:
        abort(404)

    if slot.examiner_id != examiner.id:
        flash('You can only cancel your own slots.', 'danger')
        return redirect(url_for('examiner.examinations'))

    exam = slot.examination
    booking_started = exam.status not in ('Draft', 'Slot Creation')

    if booking_started or slot.booked_count > 0:
        flash('Slot cannot be cancelled once booking has started or students are booked.', 'warning')
    else:
        slot.status = 'Cancelled'
        db.session.commit()
        flash('Slot cancelled successfully.', 'success')

    return redirect(url_for('examiner.examination_view', exam_id=exam.id))


# ---------------------------------------------------------------------------
# Booked Students
# ---------------------------------------------------------------------------

@examiner_bp.route('/students')
@login_required
@examiner_approved_required
def students():
    """All confirmed bookings for this examiner's slots."""
    examiner = get_current_examiner()
    slot_ids = [s.id for s in Slot.query.filter_by(examiner_id=examiner.id).all()]

    bookings = []
    if slot_ids:
        bookings = (
            Booking.query
            .filter(Booking.slot_id.in_(slot_ids), Booking.status.in_(['confirmed', 'Booked', 'Completed']))
            .order_by(Booking.booking_time.desc())
            .all()
        )

    return render_template(
        'examiner/students/index.html',
        examiner=examiner,
        bookings=bookings,
    )


@examiner_bp.route('/slots/<int:slot_id>/students')
@login_required
@examiner_approved_required
def slot_students(slot_id):
    """Students booked into a specific slot."""
    examiner = get_current_examiner()
    slot = db.session.get(Slot, slot_id)
    if slot is None:
        abort(404)

    if slot.examiner_id != examiner.id:
        flash('You can only view students in your own slots.', 'danger')
        return redirect(url_for('examiner.students'))

    bookings = Booking.query.filter(
        Booking.slot_id == slot_id,
        Booking.status.in_(['confirmed', 'Booked', 'Completed'])
    ).all()

    return render_template(
        'examiner/students/slot_students.html',
        examiner=examiner,
        slot=slot,
        bookings=bookings,
    )


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

@examiner_bp.route('/evaluate/<int:booking_id>', methods=['GET', 'POST'])
@login_required
@examiner_approved_required
def evaluate(booking_id):
    """Submit or update rubric-based evaluation for a student booking."""
    examiner = get_current_examiner()
    booking = db.session.get(Booking, booking_id)
    if booking is None:
        abort(404)

    # Security: booking must be in examiner's own slot
    slot = booking.slot
    if slot.examiner_id != examiner.id:
        flash('You can only evaluate students booked in your own slots.', 'danger')
        return redirect(url_for('examiner.students'))

    if booking.status not in ('confirmed', 'Booked', 'Completed'):
        flash('Only confirmed bookings can be evaluated.', 'warning')
        return redirect(url_for('examiner.students'))

    exam = slot.examination
    rubrics = exam.rubrics

    # Fetch or create draft evaluation
    evaluation = booking.evaluation

    if request.method == 'POST':
        general_remarks = request.form.get('remarks', '').strip()
        errors = []
        criterion_marks = {}

        for rubric in rubrics:
            key = f'criterion_{rubric.id}'
            raw = request.form.get(key, '').strip()
            try:
                marks = float(raw)
                if marks < 0 or marks > rubric.max_marks:
                    errors.append(
                        f'Marks for "{rubric.criterion_name}" must be between 0 and {rubric.max_marks}.'
                    )
                criterion_marks[rubric.id] = marks
            except (ValueError, TypeError):
                errors.append(f'Invalid marks for "{rubric.criterion_name}".')

        if errors:
            for err in errors:
                flash(err, 'danger')
            # Rebuild evaluation for display
            existing_scores = {}
            if evaluation:
                existing_scores = {cs.rubric_criterion_id: cs for cs in evaluation.criterion_scores}
            return render_template(
                'examiner/evaluate/form.html',
                examiner=examiner,
                booking=booking,
                slot=slot,
                exam=exam,
                rubrics=rubrics,
                evaluation=evaluation,
                existing_scores=existing_scores,
                form_data=request.form,
            )

        # Compute total
        total = sum(criterion_marks.values())
        if total > exam.max_marks:
            flash(f'Total marks ({total}) cannot exceed examination maximum marks ({exam.max_marks}).', 'danger')
            existing_scores = {}
            if evaluation:
                existing_scores = {cs.rubric_criterion_id: cs for cs in evaluation.criterion_scores}
            return render_template(
                'examiner/evaluate/form.html',
                examiner=examiner,
                booking=booking,
                slot=slot,
                exam=exam,
                rubrics=rubrics,
                evaluation=evaluation,
                existing_scores=existing_scores,
                form_data=request.form,
            )

        now = datetime.now(timezone.utc)

        publish_result = request.form.get('publish_result', '').lower() in ('true', '1', 'on') or exam.results_published

        if evaluation is None:
            evaluation = Evaluation(
                booking_id=booking.id,
                examiner_id=examiner.id,
                evaluation_date=now,
                total_marks=total,
                remarks=general_remarks,
                status='submitted',
                is_published=publish_result,
                created_at=now,
            )
            db.session.add(evaluation)
            db.session.flush()  # get evaluation.id

            for rubric in rubrics:
                cs = CriterionScore(
                    evaluation_id=evaluation.id,
                    rubric_criterion_id=rubric.id,
                    marks_awarded=criterion_marks[rubric.id],
                )
                db.session.add(cs)
        else:
            evaluation.total_marks = total
            evaluation.remarks = general_remarks
            evaluation.status = 'submitted'
            evaluation.evaluation_date = now
            if publish_result:
                evaluation.is_published = True
            # Update criterion scores
            existing_map = {cs.rubric_criterion_id: cs for cs in evaluation.criterion_scores}
            for rubric in rubrics:
                if rubric.id in existing_map:
                    existing_map[rubric.id].marks_awarded = criterion_marks[rubric.id]
                else:
                    cs = CriterionScore(
                        evaluation_id=evaluation.id,
                        rubric_criterion_id=rubric.id,
                        marks_awarded=criterion_marks[rubric.id],
                    )
                    db.session.add(cs)

        # Update booking
        booking.attendance = 'present'
        booking.score = total
        booking.status = 'Completed'
        db.session.commit()

        flash('Evaluation submitted successfully.', 'success')
        return redirect(url_for('examiner.evaluations'))

    # GET: pre-populate if evaluation already exists
    existing_scores = {}
    if evaluation:
        existing_scores = {cs.rubric_criterion_id: cs for cs in evaluation.criterion_scores}

    return render_template(
        'examiner/evaluate/form.html',
        examiner=examiner,
        booking=booking,
        slot=slot,
        exam=exam,
        rubrics=rubrics,
        evaluation=evaluation,
        existing_scores=existing_scores,
        form_data={},
    )


# ---------------------------------------------------------------------------
# Evaluation History
# ---------------------------------------------------------------------------

@examiner_bp.route('/evaluations')
@login_required
@examiner_approved_required
def evaluations():
    """Evaluation history for this examiner — submitted and pending."""
    examiner = get_current_examiner()
    slot_ids = [s.id for s in Slot.query.filter_by(examiner_id=examiner.id).all()]

    all_bookings = []
    if slot_ids:
        all_bookings = (
            Booking.query
            .filter(Booking.slot_id.in_(slot_ids), Booking.status.in_(['confirmed', 'Booked', 'Completed']))
            .all()
        )

    # Separate into evaluated and pending
    evaluated = [b for b in all_bookings if b.evaluation and b.evaluation.status == 'submitted']
    pending = [b for b in all_bookings if not b.evaluation or b.evaluation.status != 'submitted']

    return render_template(
        'examiner/evaluations/index.html',
        examiner=examiner,
        evaluated=evaluated,
        pending=pending,
    )
