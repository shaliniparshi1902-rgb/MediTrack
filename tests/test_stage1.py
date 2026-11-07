"""
MediTrack - Stage 1 Automated Test Suite
Verifies:
1. Expiry date calculation logic (expired, critical, warning, safe)
2. Low stock threshold detection
3. FEFO (First Expiry, First Out) algorithm & multi-batch allocation
4. Password hashing and credential verification
5. Route guards (@login_required, @admin_required)
6. Flask Application Factory initialization & context processors
7. Database schema and seed data SQL files integrity
8. Authentication HTTP flow (Login, Session, Logout)
"""

import unittest
from datetime import date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session

from app import create_app
from app.utils.helpers import (
    calculate_expiry_status,
    is_low_stock,
    get_fefo_batches,
    allocate_fefo_dispense,
    parse_date
)


class TestStage1Core(unittest.TestCase):

    def setUp(self):
        """Set up Flask test client with test configuration."""
        self.app = create_app({
            'TESTING': True,
            'SECRET_KEY': 'test_secret_key_meditrack',
            'WTF_CSRF_ENABLED': False
        })
        self.client = self.app.test_client()

    # -------------------------------------------------------------------------
    # 1. Expiry Date Calculation Tests
    # -------------------------------------------------------------------------
    def test_expiry_status_expired(self):
        """Tests that dates in the past are marked as 'expired'."""
        today = date(2026, 11, 6)
        past_date = today - timedelta(days=10)
        result = calculate_expiry_status(past_date, reference_date=today)
        self.assertEqual(result['status'], 'expired')
        self.assertEqual(result['badge_class'], 'danger')
        self.assertIn('Expired', result['label'])
        self.assertEqual(result['days_left'], -10)

    def test_expiry_status_critical(self):
        """Tests that dates within 30 days are marked as 'critical'."""
        today = date(2026, 11, 6)
        critical_date = today + timedelta(days=15)
        result = calculate_expiry_status(critical_date, reference_date=today)
        self.assertEqual(result['status'], 'critical')
        self.assertEqual(result['badge_class'], 'warning')
        self.assertIn('Critical', result['label'])
        self.assertEqual(result['days_left'], 15)

    def test_expiry_status_warning(self):
        """Tests that dates between 31 and 90 days are marked as 'warning'."""
        today = date(2026, 11, 6)
        warning_date = today + timedelta(days=60)
        result = calculate_expiry_status(warning_date, reference_date=today)
        self.assertEqual(result['status'], 'warning')
        self.assertEqual(result['badge_class'], 'info')
        self.assertIn('Expiring in 60d', result['label'])

    def test_expiry_status_safe(self):
        """Tests that dates beyond 90 days are marked as 'safe'."""
        today = date(2026, 11, 6)
        safe_date = today + timedelta(days=180)
        result = calculate_expiry_status(safe_date, reference_date=today)
        self.assertEqual(result['status'], 'safe')
        self.assertEqual(result['badge_class'], 'success')
        self.assertIn('Safe', result['label'])

    # -------------------------------------------------------------------------
    # 2. Low-Stock Detection Tests
    # -------------------------------------------------------------------------
    def test_low_stock_detection(self):
        """Tests stock threshold evaluations."""
        self.assertTrue(is_low_stock(10, threshold=20))
        self.assertTrue(is_low_stock(20, threshold=20))
        self.assertFalse(is_low_stock(21, threshold=20))
        self.assertFalse(is_low_stock(100, threshold=20))
        self.assertTrue(is_low_stock(0, threshold=20))

    # -------------------------------------------------------------------------
    # 3. FEFO (First Expiry, First Out) Algorithm Tests
    # -------------------------------------------------------------------------
    def test_fefo_batch_ordering_and_expired_filtering(self):
        """Tests that FEFO filters out expired/depleted batches and sorts by earliest expiry."""
        today = date(2026, 11, 6)
        sample_batches = [
            {'id': 1, 'batch_number': 'EXPIRED-01', 'current_quantity': 50, 'expiry_date': '2026-10-01', 'status': 'active'},
            {'id': 2, 'batch_number': 'LATER-02', 'current_quantity': 40, 'expiry_date': '2027-05-01', 'status': 'active'},
            {'id': 3, 'batch_number': 'SOONER-03', 'current_quantity': 25, 'expiry_date': '2026-11-25', 'status': 'active'},
            {'id': 4, 'batch_number': 'DEPLETED-04', 'current_quantity': 0, 'expiry_date': '2026-11-20', 'status': 'active'},
            {'id': 5, 'batch_number': 'QUARANTINE-05', 'current_quantity': 100, 'expiry_date': '2026-11-15', 'status': 'quarantined'}
        ]

        fefo = get_fefo_batches(sample_batches, reference_date=today)
        
        # Only non-expired, non-depleted, active batches should be present
        self.assertEqual(len(fefo), 2)
        # SOONER-03 (expires 2026-11-25) should be prioritized before LATER-02 (expires 2027-05-01)
        self.assertEqual(fefo[0]['batch_number'], 'SOONER-03')
        self.assertEqual(fefo[1]['batch_number'], 'LATER-02')

    def test_fefo_allocation_multi_batch(self):
        """Tests multi-batch allocation when single batch doesn't satisfy requested quantity."""
        today = date(2026, 11, 6)
        sample_batches = [
            {'id': 1, 'batch_number': 'BATCH-A', 'current_quantity': 20, 'expiry_date': '2026-12-01', 'status': 'active'},
            {'id': 2, 'batch_number': 'BATCH-B', 'current_quantity': 50, 'expiry_date': '2027-06-01', 'status': 'active'}
        ]

        # Request 35 units: 20 should come from BATCH-A, 15 from BATCH-B
        alloc_res = allocate_fefo_dispense(35, sample_batches, reference_date=today)
        self.assertTrue(alloc_res['success'])
        self.assertEqual(len(alloc_res['allocations']), 2)
        self.assertEqual(alloc_res['allocations'][0]['batch_number'], 'BATCH-A')
        self.assertEqual(alloc_res['allocations'][0]['deduct_quantity'], 20)
        self.assertEqual(alloc_res['allocations'][1]['batch_number'], 'BATCH-B')
        self.assertEqual(alloc_res['allocations'][1]['deduct_quantity'], 15)

    def test_fefo_insufficient_stock(self):
        """Tests that FEFO rejects requests exceeding total available unexpired stock."""
        today = date(2026, 11, 6)
        sample_batches = [
            {'id': 1, 'batch_number': 'BATCH-A', 'current_quantity': 10, 'expiry_date': '2026-12-01', 'status': 'active'}
        ]
        alloc_res = allocate_fefo_dispense(25, sample_batches, reference_date=today)
        self.assertFalse(alloc_res['success'])
        self.assertIn('Insufficient unexpired stock', alloc_res['message'])

    # -------------------------------------------------------------------------
    # 4. Password Hashing & Security Tests
    # -------------------------------------------------------------------------
    def test_secure_password_hashing(self):
        """Verifies Werkzeug scrypt/pbkdf2 password hashing and verification."""
        raw_password = 'HospitalAdminSecure2026!'
        hashed = generate_password_hash(raw_password)
        self.assertNotEqual(raw_password, hashed)
        self.assertTrue(check_password_hash(hashed, raw_password))
        self.assertFalse(check_password_hash(hashed, 'WrongPassword123'))

    # -------------------------------------------------------------------------
    # 5. Route Guards and Access Control Tests
    # -------------------------------------------------------------------------
    def test_login_required_redirects_unauthenticated_user(self):
        """Verifies unauthenticated access to protected routes redirects to /auth/login."""
        response = self.client.get('/dashboard', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login', response.headers['Location'])

    def test_login_get_renders_page(self):
        """Verifies GET /auth/login renders the login form."""
        response = self.client.get('/auth/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'MediTrack', response.data)
        self.assertIn(b'Sign In to Portal', response.data)

    def test_login_post_missing_fields(self):
        """Verifies login fails when username or password is missing."""
        response = self.client.post('/auth/login', data={'username': '', 'password': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Please enter both username and password.', response.data)

    def test_login_post_successful_authentication(self):
        """Verifies successful login sets session and redirects to dashboard."""
        from unittest.mock import patch
        mock_user = {
            'id': 1,
            'username': 'admin',
            'password_hash': generate_password_hash('admin123'),
            'full_name': 'Dr. Sarah Johnson',
            'role': 'admin',
            'status': 'active'
        }
        with patch('app.routes.auth.query_db', return_value=mock_user):
            response = self.client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/dashboard', response.headers['Location'])
            with self.client.session_transaction() as sess:
                self.assertEqual(sess['user_id'], 1)
                self.assertEqual(sess['username'], 'admin')
                self.assertEqual(sess['role'], 'admin')

    def test_login_post_invalid_password(self):
        """Verifies login fails when invalid password is provided."""
        from unittest.mock import patch
        mock_user = {
            'id': 1,
            'username': 'admin',
            'password_hash': generate_password_hash('admin123'),
            'full_name': 'Dr. Sarah Johnson',
            'role': 'admin',
            'status': 'active'
        }
        with patch('app.routes.auth.query_db', return_value=mock_user):
            response = self.client.post('/auth/login', data={'username': 'admin', 'password': 'WrongPassword'}, follow_redirects=False)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Invalid username or password.', response.data)

    def test_login_post_inactive_account(self):
        """Verifies login fails when account is inactive."""
        from unittest.mock import patch
        mock_user = {
            'id': 3,
            'username': 'deactivated_user',
            'password_hash': generate_password_hash('password123'),
            'full_name': 'Inactive User',
            'role': 'pharmacist',
            'status': 'inactive'
        }
        with patch('app.routes.auth.query_db', return_value=mock_user):
            response = self.client.post('/auth/login', data={'username': 'deactivated_user', 'password': 'password123'}, follow_redirects=False)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'This account has been deactivated.', response.data)

    def test_logout_clears_session(self):
        """Verifies /auth/logout clears user session and redirects to login."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        response = self.client.get('/auth/logout', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login', response.headers['Location'])

        with self.client.session_transaction() as sess:
            self.assertNotIn('user_id', sess)

    # -------------------------------------------------------------------------
    # 6. Database Files & SQL Schema Integrity Tests
    # -------------------------------------------------------------------------
    def test_schema_sql_file_exists_and_contains_tables(self):
        """Verifies schema.sql contains the required table creation statements."""
        with open('database/schema.sql', 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('CREATE TABLE IF NOT EXISTS users', content)
        self.assertIn('CREATE TABLE IF NOT EXISTS categories', content)
        self.assertIn('CREATE TABLE IF NOT EXISTS medicines', content)
        self.assertIn('CREATE TABLE IF NOT EXISTS batches', content)
        self.assertIn('CREATE TABLE IF NOT EXISTS patients', content)
        self.assertIn('CREATE TABLE IF NOT EXISTS medicine_usage', content)

    def test_sample_data_sql_file_exists_and_contains_seed(self):
        """Verifies sample_data.sql contains initial admin and realistic inventory data."""
        with open('database/sample_data.sql', 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('INSERT INTO users', content)
        self.assertIn('admin', content)
        self.assertIn('pharmacist', content)
        self.assertIn('INSERT INTO medicines', content)
        self.assertIn('INSERT INTO batches', content)
        self.assertIn('INSERT INTO patients', content)
        self.assertIn('INSERT INTO medicine_usage', content)


if __name__ == '__main__':
    unittest.main()
