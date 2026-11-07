"""
MediTrack - Application Factory Module
Initializes Flask app, registers blueprints, sets context processors,
handles errors, and binds database teardown callbacks.
"""

from datetime import timedelta, datetime
import os
import logging
from flask import Flask, render_template, redirect, url_for
from config import Config
from app.db import close_db, ensure_tables_exist
from app.utils.helpers import calculate_expiry_status, is_low_stock, parse_date

# Configure application logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
)


def create_app(test_config=None):
    """
    Application Factory for MediTrack Flask application.
    """
    app = Flask(__name__, instance_relative_config=True)

    # Load default configuration
    app.config.from_object(Config)

    # Override with test config if provided
    if test_config:
        app.config.update(test_config)

    # Session lifetime configuration (8 hours)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

    # Register Database Connection Teardown
    app.teardown_appcontext(close_db)

    # Register Context Processors & Jinja Template Filters
    @app.context_processor
    def inject_utilities():
        return {
            'calculate_expiry_status': calculate_expiry_status,
            'is_low_stock': is_low_stock,
            'app_name': 'MediTrack',
            'now': datetime.now(),
        }

    @app.template_filter('expiry_badge')
    def expiry_badge_filter(expiry_date):
        res = calculate_expiry_status(expiry_date)
        return res['badge_class']

    @app.template_filter('expiry_label')
    def expiry_label_filter(expiry_date):
        res = calculate_expiry_status(expiry_date)
        return res['label']

    @app.template_filter('date_format')
    def date_format_filter(value, fmt='%d %b %Y'):
        try:
            d = parse_date(value)
            return d.strftime(fmt) if d else 'N/A'
        except Exception:
            return str(value)

    # Register Blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.inventory import inventory_bp
    from app.routes.patients import patients_bp
    from app.routes.usage import usage_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(usage_bp)
    app.register_blueprint(reports_bp)

    # Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('base.html', error_code=404, error_message="The requested page could not be found."), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        app.logger.error(f"Internal Server Error: {e}")
        return render_template('base.html', error_code=500, error_message="An internal server error occurred. Please try again later."), 500

    # Ensure database tables exist if live connection is available
    if not app.config.get('TESTING'):
        try:
            ensure_tables_exist(app)
        except Exception as err:
            app.logger.debug(f"Auto-table verification deferred: {err}")

    return app
