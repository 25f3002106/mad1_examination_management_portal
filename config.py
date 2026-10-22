import os

basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, 'instance')
os.makedirs(instance_dir, exist_ok=True)


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'emp-iitm-mad1-secret-key-2026')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Default Admin initialization credentials
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@emp.iitm.ac.in')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'AdminPassword123!')
    ADMIN_NAME = os.environ.get('ADMIN_NAME', 'System Administrator')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f"sqlite:///{os.path.join(instance_dir, 'emp.sqlite')}"
    )


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = 'testing-secret-key'


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f"sqlite:///{os.path.join(instance_dir, 'emp_prod.sqlite')}"
    )


config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
