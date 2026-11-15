#!/usr/bin/env python3
"""
Examination Management Portal (EMP)
IITM MAD-1 Project Application Entrypoint
"""
import os
from flask import Flask, render_template, session, redirect, url_for
from config import config_by_name
from database.db import db
from database.init_db import init_db
from utils import get_current_user

# Import blueprints
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.examiner import examiner_bp
from routes.student import student_bp


def create_app(config_name='default'):
    """Flask application factory."""
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Initialize SQLAlchemy database instance
    db.init_app(app)

    # Register context processors
    @app.context_processor
    def inject_user():
        return {'current_user': get_current_user()}

    # Global custom error handlers
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(e):
        return render_template('500.html'), 500

    # Main landing route (supports both 'index' and 'main.index')
    def index():
        if 'user_role' in session:
            role = session['user_role']
            if role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif role == 'examiner':
                return redirect(url_for('examiner.dashboard'))
            elif role == 'student':
                return redirect(url_for('student.dashboard'))
        return render_template('index.html')

    app.add_url_rule('/', endpoint='index', view_func=index)
    app.add_url_rule('/', endpoint='main.index', view_func=index)

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(examiner_bp)
    app.register_blueprint(student_bp)

    return app


app = create_app(os.environ.get('FLASK_CONFIG', 'development'))

if __name__ == '__main__':
    # Ensure database tables and default admin exist
    init_db(app)

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
