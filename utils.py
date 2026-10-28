from functools import wraps
from flask import session, redirect, url_for, flash, request, render_template
from database.db import db
from models.user import User, Examiner


def get_current_user():
    """Retrieve currently authenticated user from session, or None."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.session.get(User, user_id)


def get_current_student():
    """Retrieve currently authenticated student profile, or None."""
    user = get_current_user()
    if user and user.role == 'student' and user.student_profile:
        return user.student_profile
    return None


def login_required(f):
    """Ensure user is authenticated before accessing endpoint."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """Ensure authenticated user holds one of the specified roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login', next=request.url))

            user_role = session.get('user_role')
            if user_role not in allowed_roles:
                return render_template(
                    '403.html',
                    message="You do not have permission to access this resource."
                ), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def examiner_approved_required(f):
    """Ensure authenticated examiner is approved by admin and not pending/deactivated."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))

        user = get_current_user()
        if not user or user.role != 'examiner':
            return render_template('403.html', message="Examiner credentials required."), 403

        examiner = user.examiner_profile
        if not examiner:
            return render_template('403.html', message="Examiner profile not found."), 403

        if examiner.approval_status == 'pending':
            flash('Your examiner registration is currently pending administrator approval.', 'info')
            return redirect(url_for('auth.pending_approval'))

        if examiner.approval_status == 'deactivated' or user.account_status != 'active':
            flash('Your examiner account has been deactivated. Please contact the administrator.', 'danger')
            return redirect(url_for('auth.pending_approval'))

        return f(*args, **kwargs)
    return decorated_function
