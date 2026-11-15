from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database.db import db
from models.user import User, Student, Examiner
from models.course import Course
from models.examination import Examination, RubricCriterion
from models.slot import Slot
from models.booking import Booking
from models.evaluation import Evaluation, CriterionScore
from utils import role_required, get_current_user

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def parse_datetime(dt_str: str):
    """Safely parse HTML datetime-local or date strings."""
    if not dt_str:
        return None
    dt_str = dt_str.strip()
    try:
        if 'T' in dt_str:
            return datetime.fromisoformat(dt_str)
        return datetime.strptime(dt_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


# ==========================================
# 1. ADMIN DASHBOARD
# ==========================================
@admin_bp.route('/dashboard')
@role_required('admin')
def dashboard():
    """Admin centralized dashboard with real database-backed statistics."""
    current_admin = get_current_user()

    total_courses = Course.query.count()
    total_examinations = Examination.query.count()
    total_examiners = Examiner.query.count()
    total_students = Student.query.count()
    total_slots = Slot.query.count()
    total_bookings = Booking.query.count()

    pending_examiners_count = Examiner.query.filter_by(approval_status='pending').count()

    # Get recent pending examiners
    pending_examiners = Examiner.query.filter_by(approval_status='pending').join(User).order_by(User.created_at.desc()).limit(5).all()

    # Get recent examinations
    recent_examinations = Examination.query.order_by(Examination.created_at.desc()).limit(5).all()

    # Get recent courses
    recent_courses = Course.query.order_by(Course.created_at.desc()).limit(5).all()

    return render_template(
        'admin/dashboard.html',
        current_admin=current_admin,
        total_courses=total_courses,
        total_examinations=total_examinations,
        total_examiners=total_examiners,
        total_students=total_students,
        total_slots=total_slots,
        total_bookings=total_bookings,
        pending_examiners_count=pending_examiners_count,
        pending_examiners=pending_examiners,
        recent_examinations=recent_examinations,
        recent_courses=recent_courses
    )


# ==========================================
# 2. COURSE MANAGEMENT
# ==========================================
@admin_bp.route('/courses')
@role_required('admin')
def list_courses():
    """View and search all academic courses."""
    query_str = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'all').strip()

    courses_query = Course.query

    if query_str:
        like_pattern = f"%{query_str}%"
        courses_query = courses_query.filter(
            db.or_(
                Course.code.ilike(like_pattern),
                Course.name.ilike(like_pattern),
                Course.department.ilike(like_pattern)
            )
        )

    if status_filter in ['Active', 'Inactive']:
        courses_query = courses_query.filter(Course.status == status_filter)

    courses = courses_query.order_by(Course.code.asc()).all()

    return render_template(
        'admin/courses/index.html',
        courses=courses,
        search_query=query_str,
        status_filter=status_filter
    )


@admin_bp.route('/courses/create', methods=['GET', 'POST'])
@role_required('admin')
def create_course():
    """Create a new academic course."""
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        department = request.form.get('department', '').strip()
        credits_val = request.form.get('credits', '4').strip()
        status = request.form.get('status', 'Active').strip()

        if not code or not name:
            flash('Course code and course name are mandatory.', 'warning')
            return render_template('admin/courses/form.html', course=None, form_data=request.form)

        # Validate duplicate code
        if Course.query.filter_by(code=code).first():
            flash(f"A course with code '{code}' already exists.", 'danger')
            return render_template('admin/courses/form.html', course=None, form_data=request.form)

        try:
            credits_num = int(credits_val) if credits_val.isdigit() else 4
            new_course = Course(
                code=code,
                name=name,
                description=description or None,
                department=department or None,
                credits=credits_num,
                status=status
            )
            db.session.add(new_course)
            db.session.commit()
            flash(f"Course '{code} - {name}' created successfully.", 'success')
            return redirect(url_for('admin.list_courses'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating course: {str(e)}", 'danger')

    return render_template('admin/courses/form.html', course=None, form_data=None)


@admin_bp.route('/courses/<int:course_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def edit_course(course_id):
    """Edit existing course details."""
    course = db.session.get(Course, course_id)
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for('admin.list_courses'))

    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        department = request.form.get('department', '').strip()
        credits_val = request.form.get('credits', '4').strip()
        status = request.form.get('status', 'Active').strip()

        if not code or not name:
            flash('Course code and name cannot be empty.', 'warning')
            return render_template('admin/courses/form.html', course=course, form_data=request.form)

        # Check unique code if changed
        existing = Course.query.filter(Course.code == code, Course.id != course.id).first()
        if existing:
            flash(f"Another course with code '{code}' already exists.", 'danger')
            return render_template('admin/courses/form.html', course=course, form_data=request.form)

        try:
            course.code = code
            course.name = name
            course.description = description or None
            course.department = department or None
            course.credits = int(credits_val) if credits_val.isdigit() else 4
            course.status = status
            db.session.commit()
            flash(f"Course '{course.code}' updated successfully.", 'success')
            return redirect(url_for('admin.list_courses'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating course: {str(e)}", 'danger')

    return render_template('admin/courses/form.html', course=course, form_data=None)


@admin_bp.route('/courses/<int:course_id>/delete', methods=['POST'])
@role_required('admin')
def delete_course(course_id):
    """Delete a course if no dependent examinations exist."""
    course = db.session.get(Course, course_id)
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for('admin.list_courses'))

    # Prevent invalid deletion when examinations depend on this course
    exam_count = len(course.examinations)
    if exam_count > 0:
        flash(
            f"Cannot delete course '{course.code}' because {exam_count} examination(s) depend on it. "
            f"Please remove or reassign linked examinations first, or deactivate the course.",
            'danger'
        )
        return redirect(url_for('admin.list_courses'))

    try:
        code = course.code
        db.session.delete(course)
        db.session.commit()
        flash(f"Course '{code}' removed successfully.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting course: {str(e)}", 'danger')

    return redirect(url_for('admin.list_courses'))


@admin_bp.route('/courses/<int:course_id>/toggle-status', methods=['POST'])
@role_required('admin')
def toggle_course_status(course_id):
    """Quickly toggle course between Active and Inactive."""
    course = db.session.get(Course, course_id)
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for('admin.list_courses'))

    course.status = 'Inactive' if course.status == 'Active' else 'Active'
    db.session.commit()
    flash(f"Course '{course.code}' status set to {course.status}.", 'info')
    return redirect(url_for('admin.list_courses'))


# ==========================================
# 3. EXAMINATION MANAGEMENT
# ==========================================
@admin_bp.route('/examinations')
@role_required('admin')
def list_examinations():
    """List, search, and filter all examinations."""
    query_str = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'all').strip()
    course_filter = request.args.get('course_id', 'all').strip()

    exams_query = Examination.query.join(Course)

    if query_str:
        like_pattern = f"%{query_str}%"
        exams_query = exams_query.filter(
            db.or_(
                Examination.name.ilike(like_pattern),
                Course.code.ilike(like_pattern),
                Course.name.ilike(like_pattern)
            )
        )

    if status_filter != 'all':
        exams_query = exams_query.filter(Examination.status == status_filter)

    if course_filter != 'all' and course_filter.isdigit():
        exams_query = exams_query.filter(Examination.course_id == int(course_filter))

    examinations = exams_query.order_by(Examination.created_at.desc()).all()
    courses = Course.query.order_by(Course.code.asc()).all()

    return render_template(
        'admin/examinations/index.html',
        examinations=examinations,
        courses=courses,
        search_query=query_str,
        status_filter=status_filter,
        course_filter=course_filter
    )


@admin_bp.route('/examinations/create', methods=['GET', 'POST'])
@role_required('admin')
def create_examination():
    """Create a new examination assessment."""
    courses = Course.query.filter_by(status='Active').order_by(Course.code.asc()).all()
    approved_examiners = Examiner.query.filter_by(approval_status='approved').join(User).order_by(User.name.asc()).all()

    if request.method == 'POST':
        course_id = request.form.get('course_id', '').strip()
        name = request.form.get('name', '').strip()
        exam_type = request.form.get('exam_type', 'Assessment').strip()
        duration_val = request.form.get('duration', '60').strip()
        max_marks_val = request.form.get('max_marks', '100').strip()
        status = request.form.get('status', 'Draft').strip()

        # Dates
        slot_creation_start = parse_datetime(request.form.get('slot_creation_start_date'))
        slot_creation_end = parse_datetime(request.form.get('slot_creation_end_date'))
        slot_booking_start = parse_datetime(request.form.get('slot_booking_start_date'))
        slot_booking_end = parse_datetime(request.form.get('slot_booking_end_date'))

        examiner_ids = request.form.getlist('examiner_ids')

        # Validation
        if not course_id or not name or not exam_type:
            flash('Please fill in Course, Examination Name, and Type.', 'warning')
            return render_template(
                'admin/examinations/form.html',
                exam=None, courses=courses, approved_examiners=approved_examiners, form_data=request.form
            )

        try:
            duration = int(duration_val)
            max_marks = int(max_marks_val)
            if duration <= 0 or max_marks <= 0:
                flash('Duration and Maximum Marks must be positive numbers.', 'danger')
                return render_template(
                    'admin/examinations/form.html',
                    exam=None, courses=courses, approved_examiners=approved_examiners, form_data=request.form
                )
        except ValueError:
            flash('Invalid numeric format for Duration or Maximum Marks.', 'danger')
            return render_template(
                'admin/examinations/form.html',
                exam=None, courses=courses, approved_examiners=approved_examiners, form_data=request.form
            )

        # Date order validations
        if slot_creation_start and slot_creation_end and slot_creation_start > slot_creation_end:
            flash('Slot Creation Start Date must be earlier than or equal to End Date.', 'danger')
            return render_template(
                'admin/examinations/form.html',
                exam=None, courses=courses, approved_examiners=approved_examiners, form_data=request.form
            )

        if slot_booking_start and slot_booking_end and slot_booking_start > slot_booking_end:
            flash('Slot Booking Start Date must be earlier than or equal to End Date.', 'danger')
            return render_template(
                'admin/examinations/form.html',
                exam=None, courses=courses, approved_examiners=approved_examiners, form_data=request.form
            )

        try:
            new_exam = Examination(
                course_id=int(course_id),
                name=name,
                exam_type=exam_type,
                duration=duration,
                max_marks=max_marks,
                slot_creation_start_date=slot_creation_start,
                slot_creation_end_date=slot_creation_end,
                slot_booking_start_date=slot_booking_start,
                slot_booking_end_date=slot_booking_end,
                status=status
            )

            # Assign examiners
            if examiner_ids:
                selected_examiners = Examiner.query.filter(Examiner.id.in_([int(eid) for eid in examiner_ids])).all()
                new_exam.examiners = selected_examiners

            db.session.add(new_exam)
            db.session.commit()
            flash(f"Examination '{new_exam.name}' created successfully.", 'success')
            return redirect(url_for('admin.view_examination', exam_id=new_exam.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating examination: {str(e)}", 'danger')

    return render_template(
        'admin/examinations/form.html',
        exam=None,
        courses=courses,
        approved_examiners=approved_examiners,
        form_data=None
    )


@admin_bp.route('/examinations/<int:exam_id>')
@role_required('admin')
def view_examination(exam_id):
    """Detailed examination control center, rubrics, slots, and examiners."""
    exam = db.session.get(Examination, exam_id)
    if not exam:
        flash("Examination not found.", "danger")
        return redirect(url_for('admin.list_examinations'))

    approved_examiners = Examiner.query.filter_by(approval_status='approved').join(User).order_by(User.name.asc()).all()

    return render_template(
        'admin/examinations/view.html',
        exam=exam,
        approved_examiners=approved_examiners
    )


@admin_bp.route('/examinations/<int:exam_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def edit_examination(exam_id):
    """Edit examination attributes, assigned examiners, and timelines."""
    exam = db.session.get(Examination, exam_id)
    if not exam:
        flash("Examination not found.", "danger")
        return redirect(url_for('admin.list_examinations'))

    courses = Course.query.order_by(Course.code.asc()).all()
    approved_examiners = Examiner.query.filter_by(approval_status='approved').join(User).order_by(User.name.asc()).all()

    if request.method == 'POST':
        course_id = request.form.get('course_id', '').strip()
        name = request.form.get('name', '').strip()
        exam_type = request.form.get('exam_type', 'Assessment').strip()
        duration_val = request.form.get('duration', '60').strip()
        max_marks_val = request.form.get('max_marks', '100').strip()
        status = request.form.get('status', 'Draft').strip()

        slot_creation_start = parse_datetime(request.form.get('slot_creation_start_date'))
        slot_creation_end = parse_datetime(request.form.get('slot_creation_end_date'))
        slot_booking_start = parse_datetime(request.form.get('slot_booking_start_date'))
        slot_booking_end = parse_datetime(request.form.get('slot_booking_end_date'))

        examiner_ids = request.form.getlist('examiner_ids')

        if not course_id or not name or not exam_type:
            flash('Please fill in Course, Name, and Type.', 'warning')
            return render_template(
                'admin/examinations/form.html',
                exam=exam, courses=courses, approved_examiners=approved_examiners, form_data=request.form
            )

        try:
            duration = int(duration_val)
            max_marks = int(max_marks_val)
            if duration <= 0 or max_marks <= 0:
                flash('Duration and Maximum Marks must be positive.', 'danger')
                return render_template(
                    'admin/examinations/form.html',
                    exam=exam, courses=courses, approved_examiners=approved_examiners, form_data=request.form
                )
        except ValueError:
            flash('Invalid numeric format for Duration or Maximum Marks.', 'danger')
            return render_template(
                'admin/examinations/form.html',
                exam=exam, courses=courses, approved_examiners=approved_examiners, form_data=request.form
            )

        # Rubric consistency check if max_marks decreased
        if max_marks < exam.total_rubric_marks:
            flash(
                f"New maximum marks ({max_marks}) is lower than existing total rubric criteria marks ({exam.total_rubric_marks}). "
                f"Please adjust the rubrics first.",
                'danger'
            )
            return render_template(
                'admin/examinations/form.html',
                exam=exam, courses=courses, approved_examiners=approved_examiners, form_data=request.form
            )

        # Date validations
        if slot_creation_start and slot_creation_end and slot_creation_start > slot_creation_end:
            flash('Slot Creation Start Date must be earlier than or equal to End Date.', 'danger')
            return render_template(
                'admin/examinations/form.html',
                exam=exam, courses=courses, approved_examiners=approved_examiners, form_data=request.form
            )

        if slot_booking_start and slot_booking_end and slot_booking_start > slot_booking_end:
            flash('Slot Booking Start Date must be earlier than or equal to End Date.', 'danger')
            return render_template(
                'admin/examinations/form.html',
                exam=exam, courses=courses, approved_examiners=approved_examiners, form_data=request.form
            )

        try:
            exam.course_id = int(course_id)
            exam.name = name
            exam.exam_type = exam_type
            exam.duration = duration
            exam.max_marks = max_marks
            exam.slot_creation_start_date = slot_creation_start
            exam.slot_creation_end_date = slot_creation_end
            exam.slot_booking_start_date = slot_booking_start
            exam.slot_booking_end_date = slot_booking_end
            exam.status = status

            # Update assigned examiners
            selected_examiners = Examiner.query.filter(Examiner.id.in_([int(eid) for eid in examiner_ids])).all() if examiner_ids else []
            exam.examiners = selected_examiners

            db.session.commit()
            flash(f"Examination '{exam.name}' updated successfully.", 'success')
            return redirect(url_for('admin.view_examination', exam_id=exam.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating examination: {str(e)}", 'danger')

    return render_template(
        'admin/examinations/form.html',
        exam=exam,
        courses=courses,
        approved_examiners=approved_examiners,
        form_data=None
    )


@admin_bp.route('/examinations/<int:exam_id>/delete', methods=['POST'])
@role_required('admin')
def delete_examination(exam_id):
    """Delete an examination if no student bookings exist."""
    exam = db.session.get(Examination, exam_id)
    if not exam:
        flash("Examination not found.", "danger")
        return redirect(url_for('admin.list_examinations'))

    if exam.total_bookings_count > 0:
        flash(
            f"Cannot delete examination '{exam.name}' because {exam.total_bookings_count} student booking(s) exist. "
            f"Please close or complete the examination instead.",
            'danger'
        )
        return redirect(url_for('admin.view_examination', exam_id=exam.id))

    try:
        name = exam.name
        db.session.delete(exam)
        db.session.commit()
        flash(f"Examination '{name}' has been deleted.", 'success')
        return redirect(url_for('admin.list_examinations'))
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting examination: {str(e)}", 'danger')
        return redirect(url_for('admin.view_examination', exam_id=exam.id))


@admin_bp.route('/examinations/<int:exam_id>/assign-examiners', methods=['POST'])
@role_required('admin')
def assign_examiners_to_exam(exam_id):
    """Assign or reassign examiners to an examination."""
    exam = db.session.get(Examination, exam_id)
    if not exam:
        flash("Examination not found.", "danger")
        return redirect(url_for('admin.list_examinations'))

    examiner_ids = request.form.getlist('examiner_ids')
    selected_examiners = Examiner.query.filter(Examiner.id.in_([int(eid) for eid in examiner_ids])).all() if examiner_ids else []
    exam.examiners = selected_examiners
    db.session.commit()

    flash(f"Assigned examiners updated for '{exam.name}'.", 'success')
    return redirect(url_for('admin.view_examination', exam_id=exam.id))


# ==========================================
# 4. EXAMINATION RUBRIC MANAGEMENT
# ==========================================
@admin_bp.route('/examinations/<int:exam_id>/rubrics/add', methods=['POST'])
@role_required('admin')
def add_rubric_criterion(exam_id):
    """Add a rubric criterion ensuring total marks do not exceed exam maximum marks."""
    exam = db.session.get(Examination, exam_id)
    if not exam:
        flash("Examination not found.", "danger")
        return redirect(url_for('admin.list_examinations'))

    # Check if student evaluations have been submitted
    if exam.has_evaluations_submitted():
        flash("Cannot modify rubric criteria because student evaluations have already been recorded.", "danger")
        return redirect(url_for('admin.view_examination', exam_id=exam.id))

    criterion_name = request.form.get('criterion_name', '').strip()
    max_marks_val = request.form.get('max_marks', '').strip()
    weightage_val = request.form.get('weightage', '1.0').strip()
    description = request.form.get('description', '').strip()

    if not criterion_name or not max_marks_val:
        flash("Criterion name and maximum marks are required.", "warning")
        return redirect(url_for('admin.view_examination', exam_id=exam.id))

    try:
        max_marks = float(max_marks_val)
        weightage = float(weightage_val) if weightage_val else 1.0
        if max_marks <= 0:
            flash("Criterion maximum marks must be greater than zero.", "danger")
            return redirect(url_for('admin.view_examination', exam_id=exam.id))
    except ValueError:
        flash("Invalid numbers provided for marks or weightage.", "danger")
        return redirect(url_for('admin.view_examination', exam_id=exam.id))

    # Validate that total criterion marks do not exceed examination maximum marks
    current_total = exam.total_rubric_marks
    if current_total + max_marks > float(exam.max_marks):
        flash(
            f"Cannot add criterion. Total rubric marks ({current_total + max_marks:.1f}) would exceed "
            f"the examination maximum marks ({exam.max_marks:.1f}). Available: {exam.rubric_marks_remaining:.1f}",
            "danger"
        )
        return redirect(url_for('admin.view_examination', exam_id=exam.id))

    try:
        criterion = RubricCriterion(
            examination_id=exam.id,
            criterion_name=criterion_name,
            max_marks=max_marks,
            weightage=weightage,
            description=description or None
        )
        db.session.add(criterion)
        db.session.commit()
        flash(f"Rubric criterion '{criterion_name}' added successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding rubric criterion: {str(e)}", "danger")

    return redirect(url_for('admin.view_examination', exam_id=exam.id))


@admin_bp.route('/examinations/<int:exam_id>/rubrics/<int:rubric_id>/edit', methods=['POST'])
@role_required('admin')
def edit_rubric_criterion(exam_id, rubric_id):
    """Edit an existing rubric criterion."""
    exam = db.session.get(Examination, exam_id)
    criterion = db.session.get(RubricCriterion, rubric_id)
    if not exam or not criterion or criterion.examination_id != exam.id:
        flash("Criterion or Examination not found.", "danger")
        return redirect(url_for('admin.list_examinations'))

    if exam.has_evaluations_submitted():
        flash("Cannot modify rubric criteria after student evaluations have been recorded.", "danger")
        return redirect(url_for('admin.view_examination', exam_id=exam.id))

    criterion_name = request.form.get('criterion_name', '').strip()
    max_marks_val = request.form.get('max_marks', '').strip()
    weightage_val = request.form.get('weightage', '1.0').strip()
    description = request.form.get('description', '').strip()

    if not criterion_name or not max_marks_val:
        flash("Criterion name and maximum marks cannot be empty.", "warning")
        return redirect(url_for('admin.view_examination', exam_id=exam.id))

    try:
        max_marks = float(max_marks_val)
        weightage = float(weightage_val) if weightage_val else 1.0
        if max_marks <= 0:
            flash("Criterion maximum marks must be greater than zero.", "danger")
            return redirect(url_for('admin.view_examination', exam_id=exam.id))
    except ValueError:
        flash("Invalid numbers provided for marks or weightage.", "danger")
        return redirect(url_for('admin.view_examination', exam_id=exam.id))

    # Check sum without this criterion's old marks
    sum_without_current = exam.total_rubric_marks - float(criterion.max_marks)
    if sum_without_current + max_marks > float(exam.max_marks):
        flash(
            f"Cannot update criterion. Total rubric marks ({sum_without_current + max_marks:.1f}) would exceed "
            f"examination maximum marks ({exam.max_marks:.1f}).",
            "danger"
        )
        return redirect(url_for('admin.view_examination', exam_id=exam.id))

    try:
        criterion.criterion_name = criterion_name
        criterion.max_marks = max_marks
        criterion.weightage = weightage
        criterion.description = description or None
        db.session.commit()
        flash(f"Criterion '{criterion_name}' updated successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating criterion: {str(e)}", "danger")

    return redirect(url_for('admin.view_examination', exam_id=exam.id))


@admin_bp.route('/examinations/<int:exam_id>/rubrics/<int:rubric_id>/delete', methods=['POST'])
@role_required('admin')
def delete_rubric_criterion(exam_id, rubric_id):
    """Remove a rubric criterion."""
    exam = db.session.get(Examination, exam_id)
    criterion = db.session.get(RubricCriterion, rubric_id)
    if not exam or not criterion or criterion.examination_id != exam.id:
        flash("Criterion or Examination not found.", "danger")
        return redirect(url_for('admin.list_examinations'))

    if exam.has_evaluations_submitted():
        flash("Cannot remove rubric criteria after evaluations have been recorded.", "danger")
        return redirect(url_for('admin.view_examination', exam_id=exam.id))

    try:
        name = criterion.criterion_name
        db.session.delete(criterion)
        db.session.commit()
        flash(f"Criterion '{name}' removed successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error removing criterion: {str(e)}", "danger")

    return redirect(url_for('admin.view_examination', exam_id=exam.id))


# ==========================================
# 5. EXAMINATION TIMELINE CONTROLS
# ==========================================
@admin_bp.route('/examinations/<int:exam_id>/status/<string:new_status>', methods=['POST'])
@role_required('admin')
def update_examination_status(exam_id, new_status):
    """Directly control examination workflow and open/close slot creation and booking."""
    exam = db.session.get(Examination, exam_id)
    if not exam:
        flash("Examination not found.", "danger")
        return redirect(url_for('admin.list_examinations'))

    valid_statuses = ['Draft', 'Slot Creation', 'Booking Open', 'Closed', 'Completed']
    if new_status not in valid_statuses:
        flash(f"Invalid status '{new_status}'.", "danger")
        return redirect(url_for('admin.view_examination', exam_id=exam.id))

    exam.status = new_status
    if new_status == 'Completed':
        for slot in exam.slots:
            for b in slot.bookings:
                if b.status != 'Cancelled' and b.attendance == 'present' and b.evaluation is not None and b.evaluation.status == 'submitted':
                    b.status = 'Completed'
    db.session.commit()
    flash(f"Examination status updated to '{new_status}'.", "success")
    return redirect(url_for('admin.view_examination', exam_id=exam.id))


@admin_bp.route('/examinations/<int:exam_id>/publish-results', methods=['POST'])
@role_required('admin')
def publish_results(exam_id):
    """Publish examination results for student viewing."""
    exam = db.session.get(Examination, exam_id)
    if not exam:
        flash("Examination not found.", "danger")
        return redirect(url_for('admin.list_examinations'))

    exam.results_published = True
    for slot in exam.slots:
        for booking in slot.bookings:
            if booking.evaluation:
                booking.evaluation.is_published = True
                if booking.status != 'Cancelled' and booking.attendance == 'present' and booking.evaluation.status == 'submitted':
                    booking.status = 'Completed'
    db.session.commit()
    flash(f"Results for '{exam.name}' have been published to students.", "success")
    return redirect(url_for('admin.view_examination', exam_id=exam.id))


# ==========================================
# 6. EXAMINER MANAGEMENT
# ==========================================
@admin_bp.route('/examiners')
@role_required('admin')
def list_examiners():
    """List, search, and manage examiner registration requests and active examiners."""
    query_str = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'all').strip()

    examiners_query = Examiner.query.join(User)

    if query_str:
        like_pattern = f"%{query_str}%"
        examiners_query = examiners_query.filter(
            db.or_(
                User.name.ilike(like_pattern),
                User.email.ilike(like_pattern),
                Examiner.department.ilike(like_pattern),
                Examiner.contact_information.ilike(like_pattern),
                Examiner.id == (int(query_str) if query_str.isdigit() else -1)
            )
        )

    if status_filter in ['pending', 'approved', 'deactivated']:
        examiners_query = examiners_query.filter(Examiner.approval_status == status_filter)

    # Order pending requests to the top
    examiners = examiners_query.order_by(
        db.case((Examiner.approval_status == 'pending', 1), else_=2),
        User.created_at.desc()
    ).all()

    return render_template(
        'admin/examiners/index.html',
        examiners=examiners,
        search_query=query_str,
        status_filter=status_filter
    )


@admin_bp.route('/examiners/<int:examiner_id>')
@role_required('admin')
def view_examiner(examiner_id):
    """View full examiner profile, contact details, and assigned examinations."""
    examiner = db.session.get(Examiner, examiner_id)
    if not examiner:
        flash("Examiner not found.", "danger")
        return redirect(url_for('admin.list_examiners'))

    all_examinations = Examination.query.order_by(Examination.name.asc()).all()

    return render_template(
        'admin/examiners/view.html',
        examiner=examiner,
        all_examinations=all_examinations
    )


@admin_bp.route('/examiner/<int:examiner_id>/approve', methods=['POST'])
@role_required('admin')
def approve_examiner(examiner_id):
    """Approve a pending examiner registration."""
    examiner = db.session.get(Examiner, examiner_id)
    if not examiner:
        flash("Examiner not found.", "danger")
        return redirect(url_for('admin.list_examiners'))

    examiner.approval_status = 'approved'
    examiner.user.account_status = 'active'
    db.session.commit()

    flash(f"Examiner {examiner.user.name} ({examiner.user.email}) has been approved.", 'success')
    return redirect(request.referrer or url_for('admin.list_examiners'))


@admin_bp.route('/examiner/<int:examiner_id>/deactivate', methods=['POST'])
@role_required('admin')
def deactivate_examiner(examiner_id):
    """Reject or deactivate an examiner."""
    examiner = db.session.get(Examiner, examiner_id)
    if not examiner:
        flash("Examiner not found.", "danger")
        return redirect(url_for('admin.list_examiners'))

    examiner.approval_status = 'deactivated'
    examiner.user.account_status = 'deactivated'
    db.session.commit()

    flash(f"Examiner {examiner.user.name} has been deactivated.", 'warning')
    return redirect(request.referrer or url_for('admin.list_examiners'))


@admin_bp.route('/examiners/<int:examiner_id>/reactivate', methods=['POST'])
@role_required('admin')
def reactivate_examiner(examiner_id):
    """Reactivate a previously deactivated examiner."""
    examiner = db.session.get(Examiner, examiner_id)
    if not examiner:
        flash("Examiner not found.", "danger")
        return redirect(url_for('admin.list_examiners'))

    examiner.approval_status = 'approved'
    examiner.user.account_status = 'active'
    db.session.commit()

    flash(f"Examiner {examiner.user.name} has been reactivated.", 'success')
    return redirect(request.referrer or url_for('admin.list_examiners'))


# ==========================================
# 7. STUDENT MANAGEMENT
# ==========================================
@admin_bp.route('/students')
@role_required('admin')
def list_students():
    """View and search all registered students."""
    query_str = request.args.get('q', '').strip()
    program_filter = request.args.get('program', 'all').strip()

    students_query = Student.query.join(User)

    if query_str:
        like_pattern = f"%{query_str}%"
        students_query = students_query.filter(
            db.or_(
                User.name.ilike(like_pattern),
                User.email.ilike(like_pattern),
                Student.roll_number.ilike(like_pattern),
                Student.department.ilike(like_pattern),
                Student.id == (int(query_str) if query_str.isdigit() else -1)
            )
        )

    if program_filter != 'all':
        students_query = students_query.filter(Student.program == program_filter)

    students = students_query.order_by(Student.roll_number.asc()).all()

    # Get distinct programs for dropdown filter
    programs = db.session.query(Student.program).distinct().all()
    programs_list = [p[0] for p in programs if p[0]]

    return render_template(
        'admin/students/index.html',
        students=students,
        search_query=query_str,
        program_filter=program_filter,
        programs=programs_list
    )


@admin_bp.route('/students/<int:student_id>')
@role_required('admin')
def view_student(student_id):
    """View student profile, contact information, and exam bookings."""
    student = db.session.get(Student, student_id)
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for('admin.list_students'))

    return render_template(
        'admin/students/view.html',
        student=student
    )


# ==========================================
# 8. EXAMINATION SLOTS OVERVIEW & REASSIGNMENT
# ==========================================
@admin_bp.route('/slots')
@role_required('admin')
def list_slots():
    """Admin overview of all examination slots with searching and filtering."""
    query_str = request.args.get('q', '').strip()
    course_filter = request.args.get('course_id', 'all').strip()
    exam_filter = request.args.get('exam_id', 'all').strip()
    examiner_filter = request.args.get('examiner_id', 'all').strip()
    status_filter = request.args.get('status', 'all').strip()

    slots_query = Slot.query.join(Examination).join(Course).outerjoin(Examiner).outerjoin(User, Examiner.user_id == User.id)

    if query_str:
        like_pattern = f"%{query_str}%"
        conds = [
            Examination.name.ilike(like_pattern),
            Course.code.ilike(like_pattern),
            Course.name.ilike(like_pattern),
            User.name.ilike(like_pattern),
            Slot.room_or_link.ilike(like_pattern),
        ]
        if query_str.isdigit():
            conds.append(Slot.id == int(query_str))
        slots_query = slots_query.filter(db.or_(*conds))

    if course_filter != 'all' and course_filter.isdigit():
        slots_query = slots_query.filter(Course.id == int(course_filter))

    if exam_filter != 'all' and exam_filter.isdigit():
        slots_query = slots_query.filter(Examination.id == int(exam_filter))

    if examiner_filter != 'all' and examiner_filter.isdigit():
        slots_query = slots_query.filter(Slot.examiner_id == int(examiner_filter))

    if status_filter != 'all':
        slots_query = slots_query.filter(Slot.status == status_filter)

    slots = slots_query.order_by(Slot.start_time.desc()).all()

    courses = Course.query.order_by(Course.code.asc()).all()
    examinations = Examination.query.order_by(Examination.name.asc()).all()
    approved_examiners = Examiner.query.filter_by(approval_status='approved').join(User).order_by(User.name.asc()).all()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    return render_template(
        'admin/slots/index.html',
        slots=slots,
        courses=courses,
        examinations=examinations,
        examiners=approved_examiners,
        search_query=query_str,
        course_filter=course_filter,
        exam_filter=exam_filter,
        examiner_filter=examiner_filter,
        status_filter=status_filter,
        now=now
    )


@admin_bp.route('/slots/<int:slot_id>/reassign-examiner', methods=['POST'])
@role_required('admin')
def reassign_slot_examiner(slot_id):
    """Reassign slot examiner in exceptional situations while preserving consistency."""
    slot = db.session.get(Slot, slot_id)
    if not slot:
        flash("Examination slot not found.", "danger")
        return redirect(url_for('admin.list_slots'))

    new_examiner_id = request.form.get('examiner_id')

    if not new_examiner_id or not new_examiner_id.isdigit():
        flash("Please select a valid examiner.", "warning")
        return redirect(url_for('admin.list_slots'))

    new_examiner = db.session.get(Examiner, int(new_examiner_id))
    if not new_examiner or new_examiner.approval_status != 'approved':
        flash("Only approved examiners can be assigned.", "danger")
        return redirect(url_for('admin.list_slots'))

    old_examiner_name = slot.examiner.user.name if (slot.examiner and slot.examiner.user) else "Unassigned"

    # Ensure new examiner is assigned to the examination
    if new_examiner not in slot.examination.examiners:
        slot.examination.examiners.append(new_examiner)

    # Reassign slot ownership
    slot.examiner_id = new_examiner.id

    # If any unsubmitted evaluations exist in this slot, update examiner_id
    for booking in slot.bookings:
        if booking.evaluation and booking.evaluation.status == 'draft':
            booking.evaluation.examiner_id = new_examiner.id

    db.session.commit()
    flash(f"Slot #{slot.id} examiner successfully reassigned from {old_examiner_name} to {new_examiner.user.name}.", "success")
    return redirect(request.referrer or url_for('admin.list_slots'))


# ==========================================
# 9. BOOKING MANAGEMENT & RESCHEDULING
# ==========================================
@admin_bp.route('/bookings')
@role_required('admin')
def list_bookings():
    """Admin complete overview of all bookings with multi-attribute search and filtering."""
    query_str = request.args.get('q', '').strip()
    course_filter = request.args.get('course_id', 'all').strip()
    exam_filter = request.args.get('exam_id', 'all').strip()
    status_filter = request.args.get('status', 'all').strip()

    bookings_query = (
        Booking.query
        .join(Student, Booking.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .join(Slot, Booking.slot_id == Slot.id)
        .join(Examination, Slot.examination_id == Examination.id)
        .join(Course, Examination.course_id == Course.id)
    )

    if query_str:
        like_pattern = f"%{query_str}%"
        conds = [
            User.name.ilike(like_pattern),
            Student.roll_number.ilike(like_pattern),
            Examination.name.ilike(like_pattern),
            Course.code.ilike(like_pattern),
        ]
        if query_str.isdigit():
            conds.append(Booking.id == int(query_str))
            conds.append(Student.id == int(query_str))
        bookings_query = bookings_query.filter(db.or_(*conds))

    if course_filter != 'all' and course_filter.isdigit():
        bookings_query = bookings_query.filter(Course.id == int(course_filter))

    if exam_filter != 'all' and exam_filter.isdigit():
        bookings_query = bookings_query.filter(Examination.id == int(exam_filter))

    if status_filter != 'all':
        if status_filter == 'active':
            bookings_query = bookings_query.filter(Booking.status.in_(['Booked', 'confirmed']))
        else:
            bookings_query = bookings_query.filter(Booking.status == status_filter)

    bookings = bookings_query.order_by(Booking.booking_time.desc()).all()

    courses = Course.query.order_by(Course.code.asc()).all()
    examinations = Examination.query.order_by(Examination.name.asc()).all()

    return render_template(
        'admin/bookings/index.html',
        bookings=bookings,
        courses=courses,
        examinations=examinations,
        search_query=query_str,
        course_filter=course_filter,
        exam_filter=exam_filter,
        status_filter=status_filter
    )


@admin_bp.route('/bookings/<int:booking_id>')
@role_required('admin')
def view_booking(booking_id):
    """View detailed record and history of a single student booking."""
    booking = db.session.get(Booking, booking_id)
    if not booking:
        flash("Booking record not found.", "danger")
        return redirect(url_for('admin.list_bookings'))

    return render_template(
        'admin/bookings/view.html',
        booking=booking
    )


@admin_bp.route('/bookings/<int:booking_id>/reschedule', methods=['GET', 'POST'])
@role_required('admin')
def reschedule_booking(booking_id):
    """Admin rescheduling of an existing student booking to an alternative available slot."""
    booking = db.session.get(Booking, booking_id)
    if not booking:
        flash("Booking record not found.", "danger")
        return redirect(url_for('admin.list_bookings'))

    current_slot = booking.slot
    exam = current_slot.examination
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Restrictions: cannot reschedule cancelled, completed, evaluated, or published bookings
    if booking.status == 'Cancelled':
        flash("Cannot reschedule a cancelled booking.", "warning")
        return redirect(url_for('admin.view_booking', booking_id=booking.id))

    if booking.status == 'Completed' or exam.status == 'Completed':
        flash("Cannot reschedule a booking for a completed examination.", "danger")
        return redirect(url_for('admin.view_booking', booking_id=booking.id))

    if exam.results_published or (booking.evaluation and booking.evaluation.is_published):
        flash("Cannot reschedule a booking once examination results have been published.", "danger")
        return redirect(url_for('admin.view_booking', booking_id=booking.id))

    if booking.evaluation and booking.evaluation.status == 'submitted':
        flash("Cannot reschedule a booking that has already been evaluated.", "danger")
        return redirect(url_for('admin.view_booking', booking_id=booking.id))

    if request.method == 'POST':
        new_slot_id = request.form.get('new_slot_id')
        reason = request.form.get('reason', '').strip()

        if not new_slot_id or not new_slot_id.isdigit():
            flash("Please select a valid destination slot.", "warning")
            return redirect(url_for('admin.reschedule_booking', booking_id=booking.id))

        new_slot = db.session.get(Slot, int(new_slot_id))
        if not new_slot:
            flash("Selected slot does not exist.", "danger")
            return redirect(url_for('admin.reschedule_booking', booking_id=booking.id))

        # Must be for the same examination
        if new_slot.examination_id != exam.id:
            flash("Cannot reschedule to a slot for a different examination.", "danger")
            return redirect(url_for('admin.reschedule_booking', booking_id=booking.id))

        if new_slot.id == current_slot.id:
            flash("The student is already assigned to this slot.", "info")
            return redirect(url_for('admin.reschedule_booking', booking_id=booking.id))

        # Check availability & capacity
        if new_slot.available_seats <= 0 or new_slot.status != 'Available':
            flash("The selected slot is full or unavailable.", "danger")
            return redirect(url_for('admin.reschedule_booking', booking_id=booking.id))

        current_admin = get_current_user()

        # Update historical record and audit trail
        old_slot_id = current_slot.id
        old_time_str = current_slot.start_time.strftime('%Y-%m-%d %H:%M')
        new_time_str = new_slot.start_time.strftime('%Y-%m-%d %H:%M')
        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

        audit_entry = (
            f"[{now_str}] Rescheduled by Admin ({current_admin.name or current_admin.email}) "
            f"from Slot #{old_slot_id} ({old_time_str}) to Slot #{new_slot.id} ({new_time_str}). "
            f"Reason: {reason or 'Administrative rescheduling'}"
        )

        booking.history_notes = (
            f"{booking.history_notes}\n{audit_entry}".strip()
            if booking.history_notes else audit_entry
        )
        booking.original_slot_id = booking.original_slot_id or old_slot_id
        booking.rescheduled_at = datetime.now(timezone.utc)
        booking.rescheduled_by = current_admin.name or 'Admin'
        booking.rescheduling_reason = reason or 'Administrative rescheduling'

        # Check if student previously had a cancelled row in new_slot to prevent constraint clash
        existing_new_slot_booking = Booking.query.filter_by(
            student_id=booking.student_id,
            slot_id=new_slot.id
        ).first()

        if existing_new_slot_booking and existing_new_slot_booking.id != booking.id:
            db.session.delete(existing_new_slot_booking)
            db.session.flush()

        booking.slot_id = new_slot.id
        booking.status = 'Booked'

        # Update slot statuses
        current_slot.update_status_from_capacity()
        new_slot.update_status_from_capacity()

        db.session.commit()

        flash(
            f"Booking #{booking.id} ({booking.student.user.name}) has been successfully rescheduled "
            f"to Slot #{new_slot.id} on {new_slot.start_time.strftime('%d %b %Y at %H:%M')}.",
            "success"
        )
        return redirect(url_for('admin.view_booking', booking_id=booking.id))

    # GET: Fetch alternative slots for this examination
    alternative_slots = (
        Slot.query
        .filter(
            Slot.examination_id == exam.id,
            Slot.id != current_slot.id,
            Slot.status == 'Available'
        )
        .order_by(Slot.start_time.asc())
        .all()
    )

    available_alternatives = [s for s in alternative_slots if s.available_seats > 0]

    return render_template(
        'admin/bookings/reschedule.html',
        booking=booking,
        current_slot=current_slot,
        exam=exam,
        available_slots=available_alternatives,
        now=now
    )


# ==========================================
# 10. HISTORICAL DATA OVERVIEW
# ==========================================
@admin_bp.route('/history')
@role_required('admin')
def historical_overview():
    """Admin view of historical examinations, past slots, historical bookings, and published results."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1. Past / Completed Examinations
    completed_exams = Examination.query.filter(
        db.or_(
            Examination.status.in_(['Completed', 'Closed']),
            Examination.slot_booking_end_date < now
        )
    ).order_by(Examination.created_at.desc()).all()

    # 2. Past / Completed Slots
    past_slots = Slot.query.filter(
        db.or_(
            Slot.status.in_(['Completed', 'Cancelled']),
            Slot.end_time <= now
        )
    ).order_by(Slot.start_time.desc()).all()

    # 3. Historical Bookings (Cancelled, Completed, or past slots)
    historical_bookings = (
        Booking.query.join(Slot)
        .filter(
            db.or_(
                Booking.status.in_(['Cancelled', 'Completed']),
                Slot.end_time <= now,
                Booking.attendance.in_(['present', 'absent']),
                Booking.score.isnot(None)
            )
        )
        .order_by(Booking.booking_time.desc())
        .all()
    )

    # 4. Submitted Evaluations & Published Results
    evaluations = (
        Evaluation.query
        .order_by(Evaluation.created_at.desc())
        .all()
    )

    return render_template(
        'admin/history/index.html',
        completed_exams=completed_exams,
        past_slots=past_slots,
        historical_bookings=historical_bookings,
        evaluations=evaluations,
        now=now
    )
