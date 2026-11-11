from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from sqlalchemy import or_

from database.db import db
from models.user import User, Student
from models.course import Course
from models.examination import Examination
from models.slot import Slot
from models.booking import Booking
from models.evaluation import Evaluation
from utils import login_required, role_required, get_current_user, get_current_student

student_bp = Blueprint('student', __name__, url_prefix='/student')


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _to_utc(dt):
    """Ensure datetime is tz-aware UTC for consistent comparisons."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _get_active_exam_booking(student_id, exam_id):
    """Return active booking for student in exam, or None."""
    return Booking.query.join(Slot).filter(
        Slot.examination_id == exam_id,
        Booking.student_id == student_id,
        Booking.status.in_(['Booked', 'confirmed'])
    ).first()


# ---------------------------------------------------------------------------
# 1. Dashboard
# ---------------------------------------------------------------------------

@student_bp.route('/dashboard')
@login_required
@role_required('student')
def dashboard():
    """Student portal dashboard with real database-backed metrics."""
    user = get_current_user()
    student = get_current_student()
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for('auth.logout'))

    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)

    # 1. Available examinations open for booking
    all_booking_open_exams = Examination.query.filter_by(status='Booking Open').all()
    available_exams = [e for e in all_booking_open_exams if e.can_book_slots(now)]
    available_exams_count = len(available_exams)

    # 2. Available examination slots in open exams
    available_slots_count = 0
    if available_exams:
        exam_ids = [e.id for e in available_exams]
        open_slots = Slot.query.filter(
            Slot.examination_id.in_(exam_ids),
            Slot.status == 'Available'
        ).all()
        available_slots_count = sum(
            1 for s in open_slots
            if s.available_seats > 0 and _to_utc(s.start_time) > now
        )

    # Student's all bookings
    student_bookings = Booking.query.filter_by(student_id=student.id).order_by(Booking.booking_time.desc()).all()

    # 3. Upcoming examinations (active bookings with slot start_time in the future)
    upcoming_bookings = [
        b for b in student_bookings
        if b.status in ('Booked', 'confirmed') and _to_utc(b.slot.start_time) > now
    ]
    upcoming_exams_count = len(upcoming_bookings)

    # 4. My booked slots (total active bookings)
    my_booked_slots_count = len([
        b for b in student_bookings if b.status in ('Booked', 'confirmed')
    ])

    # 5. Published results count
    published_results = [
        b for b in student_bookings
        if b.evaluation and (b.evaluation.is_published or b.slot.examination.results_published)
    ]
    published_results_count = len(published_results)

    # 6. Completed examinations count (past slots, completed status, or evaluated)
    completed_exams = [
        b for b in student_bookings
        if b.status == 'Completed' or (b.status in ('Booked', 'confirmed') and (_to_utc(b.slot.end_time) <= now or b.attendance == 'present' or b.evaluation is not None))
    ]
    completed_exams_count = len(completed_exams)

    return render_template(
        'student/dashboard.html',
        user=user,
        student=student,
        available_exams_count=available_exams_count,
        available_slots_count=available_slots_count,
        upcoming_exams_count=upcoming_exams_count,
        my_booked_slots_count=my_booked_slots_count,
        published_results_count=published_results_count,
        completed_exams_count=completed_exams_count,
        upcoming_bookings=upcoming_bookings[:5],
        recent_results=published_results[:3],
        now=now_naive,
    )


# ---------------------------------------------------------------------------
# 2. Examination Browsing & Filtering
# ---------------------------------------------------------------------------

@student_bp.route('/examinations')
@login_required
@role_required('student')
def examinations():
    """Browse, search, and filter available examinations."""
    student = get_current_student()
    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)

    search_query = request.args.get('q', '').strip()
    course_filter = request.args.get('course_id', '').strip()
    type_filter = request.args.get('type', '').strip()
    status_filter = request.args.get('status', 'booking_open').strip()

    # Start with active courses only
    query = Examination.query.join(Course).filter(Course.status == 'Active')

    if status_filter == 'booking_open':
        query = query.filter(Examination.status == 'Booking Open')
    elif status_filter != 'all':
        query = query.filter(Examination.status == status_filter)

    if search_query:
        query = query.filter(
            or_(
                Examination.name.ilike(f'%{search_query}%'),
                Course.name.ilike(f'%{search_query}%'),
                Course.code.ilike(f'%{search_query}%'),
            )
        )

    if course_filter.isdigit():
        query = query.filter(Examination.course_id == int(course_filter))

    if type_filter and type_filter != 'all':
        query = query.filter(Examination.exam_type == type_filter)

    exams_list = query.order_by(Examination.slot_booking_end_date.asc()).all()

    # Get active bookings map for this student {exam_id: booking}
    my_active_bookings = {
        b.slot.examination_id: b
        for b in Booking.query.filter_by(student_id=student.id).all()
        if b.status in ('Booked', 'confirmed')
    }

    courses = Course.query.filter_by(status='Active').order_by(Course.code.asc()).all()

    return render_template(
        'student/examinations/index.html',
        student=student,
        examinations=exams_list,
        courses=courses,
        now=now_naive,
        search_query=search_query,
        course_filter=course_filter,
        type_filter=type_filter,
        status_filter=status_filter,
        my_active_bookings=my_active_bookings,
    )


@student_bp.route('/examinations/<int:exam_id>')
@login_required
@role_required('student')
def examination_view(exam_id):
    """View examination details and available slots for booking."""
    student = get_current_student()
    exam = db.session.get(Examination, exam_id)
    if not exam:
        abort(404)

    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)
    is_bookable = exam.can_book_slots(now) and exam.course.status == 'Active'

    # Check if student already has an active booking for this examination
    existing_active_booking = _get_active_exam_booking(student.id, exam.id)

    # Slots for this examination
    slots = Slot.query.filter_by(examination_id=exam.id).order_by(Slot.start_time.asc()).all()

    return render_template(
        'student/examinations/view.html',
        student=student,
        exam=exam,
        slots=slots,
        is_bookable=is_bookable,
        existing_active_booking=existing_active_booking,
        now=now_naive,
    )


# ---------------------------------------------------------------------------
# 3 & 4. Slot Booking Engine
# ---------------------------------------------------------------------------

@student_bp.route('/slots/<int:slot_id>/book', methods=['POST'])
@login_required
@role_required('student')
def slot_book(slot_id):
    """Book an examination slot with strict backend validation and concurrency guards."""
    student = get_current_student()
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for('auth.login'))

    slot = db.session.get(Slot, slot_id)
    if not slot:
        abort(404)

    exam = slot.examination
    now = datetime.now(timezone.utc)

    # Validation 1: Course must be Active
    if exam.course.status != 'Active':
        flash("This course is inactive. Slot booking is disabled.", "danger")
        return redirect(url_for('student.examinations'))

    # Validation 2: Examination must be open for booking within authorized period
    if not exam.can_book_slots(now):
        flash("Booking is not currently open for this examination.", "warning")
        return redirect(url_for('student.examination_view', exam_id=exam.id))

    # Validation 3: Slot must be Available and in the future
    if slot.status != 'Available' or _to_utc(slot.start_time) <= now:
        flash("This slot is unavailable or in the past.", "danger")
        return redirect(url_for('student.examination_view', exam_id=exam.id))

    # Validation 4: Prevent duplicate active bookings for the same examination
    active_exam_booking = _get_active_exam_booking(student.id, exam.id)
    if active_exam_booking:
        flash(
            f"You already have an active booking for '{exam.name}'. "
            "Please cancel your existing booking before selecting a new slot.",
            "warning"
        )
        return redirect(url_for('student.examination_view', exam_id=exam.id))

    # Concurrency & Capacity Guard: Use transaction and re-check capacity
    try:
        # Check active bookings directly from database
        current_active_count = Booking.query.filter(
            Booking.slot_id == slot.id,
            Booking.status.in_(['Booked', 'confirmed'])
        ).count()

        if current_active_count >= slot.capacity:
            slot.status = 'Full'
            db.session.commit()
            flash("This slot has just reached full capacity. Please select another slot.", "danger")
            return redirect(url_for('student.examination_view', exam_id=exam.id))

        # Check if student previously had a cancelled booking for this exact slot
        existing_booking = Booking.query.filter_by(
            student_id=student.id,
            slot_id=slot.id
        ).first()

        if existing_booking:
            if existing_booking.status in ('Booked', 'confirmed'):
                flash("You have already booked this slot.", "info")
                return redirect(url_for('student.booking_view', booking_id=existing_booking.id))
            # Reactivate cancelled booking
            existing_booking.status = 'Booked'
            existing_booking.booking_time = now
            booking = existing_booking
        else:
            booking = Booking(
                student_id=student.id,
                slot_id=slot.id,
                booking_time=now,
                status='Booked',
                attendance='pending',
            )
            db.session.add(booking)

        # Update slot status if full
        if current_active_count + 1 >= slot.capacity:
            slot.status = 'Full'
        else:
            slot.status = 'Available'

        db.session.commit()

        flash(
            f"Slot booked successfully! Your booking confirmation ID is #{booking.id}.",
            "success"
        )
        return redirect(url_for('student.booking_view', booking_id=booking.id))

    except Exception as e:
        db.session.rollback()
        flash("An error occurred while reserving your slot. Please try again.", "danger")
        return redirect(url_for('student.examination_view', exam_id=exam.id))


# ---------------------------------------------------------------------------
# 5 & 6. Booking Management & Cancellation
# ---------------------------------------------------------------------------

@student_bp.route('/bookings')
@login_required
@role_required('student')
def bookings():
    """List all student bookings with status and action links."""
    student = get_current_student()
    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)

    all_bookings = (
        Booking.query.filter_by(student_id=student.id)
        .join(Slot)
        .order_by(Slot.start_time.desc())
        .all()
    )

    return render_template(
        'student/bookings/index.html',
        student=student,
        bookings=all_bookings,
        now=now_naive,
    )


@student_bp.route('/bookings/<int:booking_id>')
@login_required
@role_required('student')
def booking_view(booking_id):
    """View detailed confirmation receipt for a single booking."""
    student = get_current_student()
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.student_id != student.id:
        abort(404)

    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)
    exam = booking.slot.examination

    # Determine if cancellable: booking is active, exam booking window open or before slot start
    can_cancel = (
        booking.status in ('Booked', 'confirmed')
        and _to_utc(booking.slot.start_time) > now
        and exam.can_book_slots(now)
    )

    return render_template(
        'student/bookings/view.html',
        student=student,
        booking=booking,
        can_cancel=can_cancel,
        now=now_naive,
    )


@student_bp.route('/bookings/<int:booking_id>/cancel', methods=['POST'])
@login_required
@role_required('student')
def booking_cancel(booking_id):
    """Cancel a booked slot before deadline, restoring slot capacity."""
    student = get_current_student()
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.student_id != student.id:
        abort(404)

    if booking.status not in ('Booked', 'confirmed'):
        flash("Only active bookings can be cancelled.", "warning")
        return redirect(url_for('student.bookings'))

    now = datetime.now(timezone.utc)
    slot = booking.slot
    exam = slot.examination

    # Rule: cannot cancel past slots
    if _to_utc(slot.start_time) <= now:
        flash("You cannot cancel a booking for a slot that has already begun or passed.", "danger")
        return redirect(url_for('student.booking_view', booking_id=booking.id))

    # Rule: cannot cancel after booking deadline has closed
    if not exam.can_book_slots(now):
        flash("Booking cancellation deadline for this examination has passed.", "danger")
        return redirect(url_for('student.booking_view', booking_id=booking.id))

    # Perform cancellation
    booking.status = 'Cancelled'

    # Restore slot availability
    if slot.status == 'Full':
        slot.status = 'Available'

    db.session.commit()

    flash(
        f"Booking #{booking.id} has been cancelled successfully. The seat has been restored.",
        "success"
    )
    return redirect(url_for('student.bookings'))


# ---------------------------------------------------------------------------
# 7. Examination History
# ---------------------------------------------------------------------------

@student_bp.route('/history')
@login_required
@role_required('student')
def history():
    """Complete academic examination history for the logged-in student."""
    student = get_current_student()
    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)

    all_bookings = (
        Booking.query.filter_by(student_id=student.id)
        .join(Slot)
        .order_by(Slot.start_time.desc())
        .all()
    )

    return render_template(
        'student/history.html',
        student=student,
        bookings=all_bookings,
        now=now_naive,
    )


# ---------------------------------------------------------------------------
# 8. Results and Feedback
# ---------------------------------------------------------------------------

@student_bp.route('/results')
@login_required
@role_required('student')
def results():
    """List all published results and feedback scorecards."""
    student = get_current_student()

    # Query only bookings that have published evaluations
    student_bookings = Booking.query.filter_by(student_id=student.id).all()
    published_bookings = [
        b for b in student_bookings
        if b.evaluation and (b.evaluation.is_published or b.slot.examination.results_published)
    ]

    return render_template(
        'student/results/index.html',
        student=student,
        bookings=published_bookings,
    )


@student_bp.route('/results/<int:booking_id>')
@login_required
@role_required('student')
def result_view(booking_id):
    """Detailed result scorecard with criterion-wise marks and examiner remarks."""
    student = get_current_student()
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.student_id != student.id:
        abort(404)

    evaluation = booking.evaluation
    exam = booking.slot.examination

    # Rule: unpublished results MUST NOT be visible to students
    is_published = evaluation and (evaluation.is_published or exam.results_published)
    if not is_published:
        flash("Results for this examination have not been published yet.", "warning")
        return redirect(url_for('student.results'))

    return render_template(
        'student/results/view.html',
        student=student,
        booking=booking,
        evaluation=evaluation,
        exam=exam,
    )


# ---------------------------------------------------------------------------
# 9. Profile Management
# ---------------------------------------------------------------------------

@student_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@role_required('student')
def profile():
    """View and edit permitted student profile information."""
    user = get_current_user()
    student = get_current_student()
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        # Permitted editable fields only: name, department, contact_number, program
        name = request.form.get('name', '').strip()
        department = request.form.get('department', '').strip()
        contact_number = request.form.get('contact_number', '').strip()
        program = request.form.get('program', '').strip()

        errors = []
        if not name:
            errors.append("Name cannot be empty.")
        if not program:
            errors.append("Academic Program cannot be empty.")

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template(
                'student/profile.html',
                user=user,
                student=student,
            )

        # Apply permitted updates
        user.name = name
        student.department = department or None
        student.contact_number = contact_number or None
        student.program = program

        db.session.commit()
        flash("Your profile has been updated successfully.", "success")
        return redirect(url_for('student.profile'))

    return render_template(
        'student/profile.html',
        user=user,
        student=student,
    )
