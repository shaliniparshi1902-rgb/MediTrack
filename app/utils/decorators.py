"""
MediTrack - Route Authentication & Authorization Decorators
Provides @login_required and @admin_required decorators to guard endpoints.
"""

from functools import wraps
from flask import session, flash, redirect, url_for, request


def login_required(f):
    """
    Decorator that checks if a user is authenticated.
    Redirects unauthenticated users to the login screen with a warning flash.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    Decorator that verifies if the authenticated user has an 'admin' role.
    Redirects non-admin users to the dashboard with an access denied message.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        
        if session.get('role') != 'admin':
            flash('Access denied. Administrator privileges are required for this action.', 'danger')
            return redirect(url_for('dashboard.index'))
            
        return f(*args, **kwargs)
    return decorated_function
