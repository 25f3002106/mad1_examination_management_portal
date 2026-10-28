from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database.db import db
from models.user import User, Student, Examiner

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login and route them to their respective dashboards."""
    # Redirect if already authenticated (on GET)
    if request.method == 'GET' and 'user_id' in session and 'user_role' in session:
        role = session['user_role']
        if role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif role == 'examiner':
            return redirect(url_for('examiner.dashboard'))
        elif role == 'student':
            return redirect(url_for('student.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both email and password.', 'warning')
            return render_template('auth/login.html', email=email)

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Invalid email or password. Please try again.', 'danger')
            return render_template('auth/login.html', email=email)

        # Check account status
        if user.account_status == 'deactivated':
            flash('Your account has been deactivated. Please contact the administrator.', 'danger')
            return render_template('auth/login.html', email=email)

        # Handle examiner approval verification
        if user.role == 'examiner':
            examiner = user.examiner_profile
            if not examiner or examiner.approval_status == 'pending':
                session['user_id'] = user.id
                session['user_role'] = user.role
                session['user_name'] = user.name
                session['user_email'] = user.email
                flash('Your examiner registration is pending administrator approval.', 'info')
                return redirect(url_for('auth.pending_approval'))
            elif examiner.approval_status == 'deactivated':
                flash('Your examiner account has been deactivated by the administrator.', 'danger')
                return render_template('auth/login.html', email=email)

        # Establish authenticated session
        session.clear()
        session['user_id'] = user.id
        session['user_role'] = user.role
        session['user_name'] = user.name
        session['user_email'] = user.email

        flash(f"Welcome back, {user.name}!", 'success')

        next_url = request.args.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)

        if user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user.role == 'examiner':
            return redirect(url_for('examiner.dashboard'))
        elif user.role == 'student':
            return redirect(url_for('student.dashboard'))
        else:
            return redirect(url_for('index'))

    return render_template('auth/login.html')


@auth_bp.route('/register/student', methods=['GET', 'POST'])
def register_student():
    """Handle student registration."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        roll_number = request.form.get('roll_number', '').strip().upper()
        program = request.form.get('program', '').strip()
        department = request.form.get('department', '').strip()
        contact_number = request.form.get('contact_number', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not all([name, email, roll_number, program, password, confirm_password]):
            flash('Please fill in all mandatory fields.', 'warning')
            return render_template('auth/register_student.html', form_data=request.form)

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'warning')
            return render_template('auth/register_student.html', form_data=request.form)

        if password != confirm_password:
            flash('Passwords do not match. Please re-enter.', 'danger')
            return render_template('auth/register_student.html', form_data=request.form)

        if User.query.filter_by(email=email).first():
            flash('An account with this email address already exists.', 'danger')
            return render_template('auth/register_student.html', form_data=request.form)

        if Student.query.filter_by(roll_number=roll_number).first():
            flash('A student with this roll number is already registered.', 'danger')
            return render_template('auth/register_student.html', form_data=request.form)

        try:
            user = User(
                name=name,
                email=email,
                role='student',
                account_status='active'
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()

            student = Student(
                user_id=user.id,
                roll_number=roll_number,
                program=program,
                department=department or None,
                contact_number=contact_number or None
            )
            db.session.add(student)
            db.session.commit()

            # Automatically log student in after registration
            session.clear()
            session['user_id'] = user.id
            session['user_role'] = user.role
            session['user_name'] = user.name
            session['user_email'] = user.email

            flash('Registration successful! Welcome to your Student Dashboard.', 'success')
            return redirect(url_for('student.dashboard'))

        except Exception:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.', 'danger')
            return render_template('auth/register_student.html', form_data=request.form)

    return render_template('auth/register_student.html')


@auth_bp.route('/register/examiner', methods=['GET', 'POST'])
def register_examiner():
    """Handle examiner registration with mandatory pending approval status."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        department = request.form.get('department', '').strip()
        contact_information = request.form.get('contact_information', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not all([name, email, department, contact_information, password, confirm_password]):
            flash('Please fill in all mandatory fields.', 'warning')
            return render_template('auth/register_examiner.html', form_data=request.form)

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'warning')
            return render_template('auth/register_examiner.html', form_data=request.form)

        if password != confirm_password:
            flash('Passwords do not match. Please re-enter.', 'danger')
            return render_template('auth/register_examiner.html', form_data=request.form)

        if User.query.filter_by(email=email).first():
            flash('An account with this email address already exists.', 'danger')
            return render_template('auth/register_examiner.html', form_data=request.form)

        try:
            user = User(
                name=name,
                email=email,
                role='examiner',
                account_status='pending'
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()

            examiner = Examiner(
                user_id=user.id,
                department=department,
                contact_information=contact_information,
                approval_status='pending'
            )
            db.session.add(examiner)
            db.session.commit()

            session.clear()
            session['user_id'] = user.id
            session['user_role'] = user.role
            session['user_name'] = user.name
            session['user_email'] = user.email

            flash('Registration submitted! Your examiner account is pending Administrator approval.', 'info')
            return redirect(url_for('auth.pending_approval'))

        except Exception:
            db.session.rollback()
            flash('An error occurred during examiner registration. Please try again.', 'danger')
            return render_template('auth/register_examiner.html', form_data=request.form)

    return render_template('auth/register_examiner.html')


@auth_bp.route('/pending-approval')
def pending_approval():
    """Informing page for examiners awaiting administrative approval."""
    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    return render_template('auth/pending_approval.html', user=user)


@auth_bp.route('/logout')
def logout():
    """Clear session and log out the user."""
    session.clear()
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/unauthorized')
def unauthorized():
    """Explicit unauthorized access page."""
    return render_template('403.html'), 403
