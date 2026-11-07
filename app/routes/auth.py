"""
MediTrack - Authentication Blueprint
Handles user login, password verification, session management, and logout.
"""

from urllib.parse import urlparse, urljoin
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from app.db import query_db, execute_db

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def is_safe_url(target):
    """
    Validates that a redirect URL is local to avoid open-redirect vulnerabilities.
    """
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handles user login authentication.
    Verifies credentials against the MySQL users table using Werkzeug password hashing.
    """
    # If user is already logged in, redirect straight to dashboard
    if session.get('user_id'):
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        next_page = request.args.get('next')

        if not username or not password:
            flash('Please enter both username and password.', 'warning')
            return render_template('auth/login.html', username=username)

        try:
            # Query user by username
            user = query_db(
                "SELECT id, username, password_hash, full_name, role, status FROM users WHERE username = %s",
                (username,),
                one=True
            )

            if not user:
                flash('Invalid username or password.', 'danger')
                return render_template('auth/login.html', username=username)

            if user.get('status') != 'active':
                flash('This account has been deactivated. Please contact the administrator.', 'danger')
                return render_template('auth/login.html', username=username)

            # Verify password hash
            if not check_password_hash(user['password_hash'], password):
                flash('Invalid username or password.', 'danger')
                return render_template('auth/login.html', username=username)

            # Successfully authenticated: set session
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            session.permanent = True

            flash(f"Welcome back, {user['full_name']}!", 'success')

            if next_page and is_safe_url(next_page):
                return redirect(next_page)
            return redirect(url_for('dashboard.index'))

        except Exception as e:
            current_app.logger.error(f"Login error: {e}")
            flash('An error occurred while connecting to the database. Please verify MySQL service is running.', 'danger')
            return render_template('auth/login.html', username=username)

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    """
    Clears the active session and logs out the user.
    """
    username = session.get('username')
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))
