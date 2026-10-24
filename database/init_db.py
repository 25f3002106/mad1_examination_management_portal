import sys
import os
from datetime import datetime, timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.db import db
from models.user import User, Student, Examiner
from models.course import Course
from models.examination import Examination, RubricCriterion, examination_examiners
from models.slot import Slot
from models.booking import Booking
from models.evaluation import Evaluation, CriterionScore


def init_db(app):
    """Programmatically initialize the SQLite database and seed the default Administrator."""
    with app.app_context():
        db.create_all()

        admin_email = app.config.get('ADMIN_EMAIL', 'admin@emp.iitm.ac.in')
        admin_password = app.config.get('ADMIN_PASSWORD', 'AdminPassword123!')
        admin_name = app.config.get('ADMIN_NAME', 'System Administrator')

        existing_admin = User.query.filter_by(email=admin_email).first()
        if not existing_admin:
            admin_user = User(
                name=admin_name,
                email=admin_email,
                role='admin',
                account_status='active',
                created_at=datetime.now(timezone.utc)
            )
            admin_user.set_password(admin_password)
            db.session.add(admin_user)
            db.session.commit()
            print(f"[Database Initialization] Default Admin created successfully: {admin_email}")
        else:
            print(f"[Database Initialization] Admin account already exists: {admin_email}")


if __name__ == '__main__':
    from app import create_app
    app = create_app(os.environ.get('FLASK_CONFIG', 'development'))
    print("[*] Running standalone database initialization...")
    init_db(app)
    print("[*] Complete.")
