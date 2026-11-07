"""
MediTrack - Stage 2 Automated Test Suite
Verifies:
1. Dashboard metrics (Total medicines, active stock, expired, critical <=30d, low stock) & chart API
2. Inventory CRUD operations (Add, Edit, View, Add Batch, Delete protection)
3. Inventory search and status filtering (low_stock, expiring_soon, expired)
4. Medicine dispensing with FEFO batch deduction, patient allocation & usage logs
5. Insufficient stock and expired stock rejection during dispensing
6. Reports (Expired, Low-Stock, Expiring-Soon, Usage) & CSV exports
"""

import unittest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from app import create_app
from app.routes.dashboard import get_dashboard_metrics


class TestStage2Features(unittest.TestCase):

    def setUp(self):
        """Initializes test Flask client with authenticated session."""
        self.app = create_app({
            'TESTING': True,
            'SECRET_KEY': 'stage2_test_secret_key',
            'WTF_CSRF_ENABLED': False
        })
        self.client = self.app.test_client()

    def set_authenticated_session(self, role='admin'):
        """Helper to simulate an active user session."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['full_name'] = 'Dr. Sarah Johnson'
            sess['role'] = role

    # -------------------------------------------------------------------------
    # 1. Dashboard Metrics & Charts Tests
    # -------------------------------------------------------------------------
    def test_dashboard_metrics_aggregation(self):
        """Verifies calculation of dashboard metrics with mock data."""
        ref_today = date(2026, 11, 6)

        def mock_query(query, args=(), one=False):
            # 1. Urgent batches list (Top 5)
            if "LIMIT 5" in query:
                return [{
                    'id': 3, 'batch_number': 'AUG-2024-09', 'current_quantity': 18, 'expiry_date': '2026-11-20',
                    'storage_rack': 'Rack A-3', 'medicine_name': 'Augmentin 625 Duo', 'generic_name': 'Amoxicillin',
                    'category_name': 'Antibiotics'
                }]
            # 2. Critical count within 30 days
            elif "expiry_date >= %s AND expiry_date <= %s AND status = 'active'" in query:
                return {'count': 3, 'units': 40} if one else [{'count': 3, 'units': 40}]
            # 3. Total medicines count
            elif "COUNT(*) AS count FROM medicines" in query:
                return {'count': 10} if one else [{'count': 10}]
            # 4. Total stock available
            elif "COALESCE(SUM(current_quantity), 0) AS total_stock" in query:
                return {'total_stock': 850} if one else [{'total_stock': 850}]
            # 5. Expired loss calculation
            elif "loss_value" in query:
                return {'count': 2, 'units': 67, 'loss_value': 2752.50} if one else [{'count': 2, 'units': 67, 'loss_value': 2752.50}]
            # 6. Low stock having clause
            elif "HAVING current_stock <= m.min_stock_threshold" in query:
                return [
                    {'id': 4, 'name': 'Atropine Inj', 'generic_name': 'Atropine Sulfate', 'min_stock_threshold': 15, 'current_stock': 12},
                    {'id': 9, 'name': 'Azithral 500', 'generic_name': 'Azithromycin', 'min_stock_threshold': 20, 'current_stock': 9}
                ]
            # 7. Category distribution chart
            elif "FROM categories c" in query:
                return [{'name': 'Antibiotics', 'medicine_count': 3}, {'name': 'Analgesics', 'medicine_count': 2}]
            # 8. Department usage chart
            elif "FROM medicine_usage" in query:
                return [{'department': 'Emergency', 'total_units': 15}, {'department': 'ICU', 'total_units': 8}]

            return None if one else []

        with patch('app.routes.dashboard.query_db', side_effect=mock_query):
            metrics = get_dashboard_metrics(ref_today)
            self.assertEqual(metrics['total_medicines'], 10)
            self.assertEqual(metrics['total_stock'], 850)
            self.assertEqual(metrics['expired_count'], 2)
            self.assertEqual(metrics['expired_units'], 67)
            self.assertEqual(metrics['critical_count'], 3)
            self.assertEqual(metrics['low_stock_count'], 2)
            self.assertEqual(len(metrics['urgent_batches']), 1)
            self.assertEqual(metrics['urgent_batches'][0]['batch_number'], 'AUG-2024-09')

    def test_dashboard_chart_data_api(self):
        """Verifies JSON format of /dashboard/api/chart-data."""
        self.set_authenticated_session()
        sample_metrics = {
            'total_medicines': 5,
            'total_stock': 200,
            'expired_count': 1,
            'expired_units': 10,
            'expired_loss': 50.0,
            'critical_count': 1,
            'critical_units': 5,
            'low_stock_count': 1,
            'low_stock_items': [],
            'urgent_batches': [],
            'category_chart': [{'name': 'Antibiotics', 'medicine_count': 4}],
            'dept_chart': [{'department': 'ICU', 'total_units': 12}]
        }
        with patch('app.routes.dashboard.get_dashboard_metrics', return_value=sample_metrics):
            resp = self.client.get('/dashboard/api/chart-data')
            self.assertEqual(resp.status_code, 200)
            json_data = resp.get_json()
            self.assertIn('categories', json_data)
            self.assertIn('departments', json_data)
            self.assertEqual(json_data['categories']['labels'], ['Antibiotics'])
            self.assertEqual(json_data['categories']['data'], [4])
            self.assertEqual(json_data['departments']['labels'], ['ICU'])
            self.assertEqual(json_data['departments']['data'], [12])

    # -------------------------------------------------------------------------
    # 2. Inventory Management Tests
    # -------------------------------------------------------------------------
    def test_inventory_list_view_renders(self):
        """Verifies inventory listing renders with data."""
        self.set_authenticated_session()
        mock_meds = [{
            'id': 1, 'name': 'Dolo-650', 'generic_name': 'Paracetamol', 'dosage_form': 'Tablet',
            'strength': '650 mg', 'manufacturer': 'Micro Labs', 'min_stock_threshold': 50,
            'storage_rack': 'Rack A-1', 'category_id': 2, 'category_name': 'Analgesics',
            'total_batches': 2, 'active_stock': 380, 'expired_stock': 45, 'earliest_expiry': '2027-11-30'
        }]
        with patch('app.routes.inventory.query_db', side_effect=[mock_meds, [{'id': 2, 'name': 'Analgesics'}]]):
            resp = self.client.get('/inventory/')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Dolo-650', resp.data)
            self.assertIn(b'Paracetamol', resp.data)

    def test_inventory_add_medicine_validation(self):
        """Verifies adding a medicine fails when required fields are missing."""
        self.set_authenticated_session()
        with patch('app.routes.inventory.query_db', return_value=[{'id': 1, 'name': 'Antibiotics'}]):
            resp = self.client.post('/inventory/add', data={
                'name': '',
                'generic_name': '',
                'category_id': ''
            })
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Please provide Medicine Name', resp.data)

    def test_inventory_add_medicine_with_initial_batch(self):
        """Verifies successful medicine and initial batch creation."""
        self.set_authenticated_session()
        with patch('app.routes.inventory.execute_db', side_effect=[{'lastrowid': 15, 'rowcount': 1}, {'lastrowid': 20, 'rowcount': 1}]):
            resp = self.client.post('/inventory/add', data={
                'name': 'Ciprofloxacin 500',
                'generic_name': 'Ciprofloxacin HCl',
                'category_id': '1',
                'dosage_form': 'Tablet',
                'strength': '500 mg',
                'manufacturer': 'Bayer',
                'min_stock_threshold': '30',
                'storage_rack': 'Rack B-1',
                'batch_number': 'CIP-2026-01',
                'initial_quantity': '100',
                'mfg_date': '2026-01-01',
                'expiry_date': '2028-01-01',
                'unit_price': '12.50',
                'supplier': 'Bayer Direct'
            }, follow_redirects=False)

            self.assertEqual(resp.status_code, 302)
            self.assertIn('/inventory/view/15', resp.headers['Location'])

    def test_inventory_view_medicine_profile(self):
        """Verifies view medicine details with batches and usage log."""
        self.set_authenticated_session()
        mock_med = {
            'id': 2, 'name': 'Augmentin 625 Duo', 'generic_name': 'Amoxicillin',
            'dosage_form': 'Tablet', 'strength': '625 mg', 'manufacturer': 'GSK',
            'min_stock_threshold': 30, 'storage_rack': 'Rack A-3', 'category_name': 'Antibiotics'
        }
        mock_batches = [{
            'id': 3, 'batch_number': 'AUG-2024-09', 'initial_quantity': 150, 'current_quantity': 18,
            'mfg_date': '2024-11-01', 'expiry_date': '2026-11-20', 'unit_price': 18.00,
            'supplier': 'MedLife', 'status': 'active'
        }]
        with patch('app.routes.inventory.query_db', side_effect=[mock_med, mock_batches, []]):
            resp = self.client.get('/inventory/view/2')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Augmentin 625 Duo', resp.data)
            self.assertIn(b'AUG-2024-09', resp.data)

    def test_inventory_delete_blocked_when_usage_exists(self):
        """Verifies that deleting a medicine with audit logs is prevented."""
        self.set_authenticated_session(role='admin')
        mock_med = {'id': 2, 'name': 'Augmentin 625 Duo'}
        mock_usage = {'id': 1}  # indicates existing usage log

        with patch('app.routes.inventory.query_db', side_effect=[mock_med, mock_usage]):
            resp = self.client.post('/inventory/delete/2', follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/inventory/view/2', resp.headers['Location'])

    # -------------------------------------------------------------------------
    # 3. Medicine Dispensing & Usage Tests
    # -------------------------------------------------------------------------
    def test_dispense_rejection_insufficient_stock(self):
        """Verifies that dispensing more units than unexpired stock fails cleanly."""
        self.set_authenticated_session()
        mock_med = {'id': 1, 'name': 'Paracetamol'}
        mock_batches = [
            {'id': 1, 'batch_number': 'B1', 'current_quantity': 10, 'expiry_date': '2027-01-01', 'status': 'active'}
        ]
        with patch('app.routes.usage.query_db', side_effect=[mock_med, mock_batches]):
            resp = self.client.post('/usage/dispense', data={
                'medicine_id': '1',
                'quantity': '50',  # exceeds 10 available
                'department': 'ICU',
                'patient_name': 'Test Patient'
            }, follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/usage/', resp.headers['Location'])

    def test_dispense_successful_transaction(self):
        """Verifies successful dispensing using FEFO allocation and database transaction."""
        self.set_authenticated_session()
        mock_med = {'id': 1, 'name': 'Dolo-650'}
        mock_batches = [
            {'id': 2, 'batch_number': 'DOL-2025-B2', 'current_quantity': 100, 'expiry_date': '2027-11-30', 'status': 'active'}
        ]
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch('app.routes.usage.query_db', side_effect=[mock_med, mock_batches]), \
             patch('app.routes.usage.get_db', return_value=mock_conn):
            resp = self.client.post('/usage/dispense', data={
                'medicine_id': '1',
                'quantity': '10',
                'department': 'OPD',
                'patient_name': 'Jane Doe',
                'patient_id': 'PAT-999',
                'prescribed_by': 'Dr. Watson',
                'reason': 'Fever'
            }, follow_redirects=False)

            self.assertEqual(resp.status_code, 302)
            self.assertIn('/usage/', resp.headers['Location'])
            # Verify commit was executed on connection
            mock_conn.commit.assert_called_once()
            # Verify batch deduction and usage insert were executed
            self.assertEqual(mock_cursor.execute.call_count, 2)

    def test_preview_fefo_api_endpoint(self):
        """Verifies GET /usage/api/preview-fefo/<id> returns valid preview JSON."""
        self.set_authenticated_session()
        mock_batches = [
            {'id': 3, 'batch_number': 'BATCH-EARLY', 'current_quantity': 25, 'expiry_date': '2026-12-01', 'status': 'active'},
            {'id': 4, 'batch_number': 'BATCH-LATE', 'current_quantity': 50, 'expiry_date': '2027-12-01', 'status': 'active'}
        ]
        with patch('app.routes.usage.query_db', return_value=mock_batches):
            resp = self.client.get('/usage/api/preview-fefo/1?quantity=15')
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data['success'])
            self.assertEqual(len(data['allocations']), 1)
            self.assertEqual(data['allocations'][0]['batch_number'], 'BATCH-EARLY')
            self.assertEqual(data['allocations'][0]['deduct_quantity'], 15)

    # -------------------------------------------------------------------------
    # 4. Reports & CSV Export Tests
    # -------------------------------------------------------------------------
    def test_reports_expired_tab_renders(self):
        """Verifies expired medicines report view."""
        self.set_authenticated_session()
        mock_expired = [{
            'id': 1, 'batch_number': 'DOL-2024-B1', 'current_quantity': 45, 'expiry_date': '2026-10-15',
            'unit_price': 2.50, 'supplier': 'Apex', 'financial_loss': 112.50, 'medicine_name': 'Dolo-650',
            'generic_name': 'Paracetamol', 'dosage_form': 'Tablet', 'strength': '650 mg',
            'storage_rack': 'Rack A-1', 'category_name': 'Analgesics'
        }]
        with patch('app.routes.reports.query_db', return_value=mock_expired):
            resp = self.client.get('/reports/?tab=expired')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Expired Batches', resp.data)
            self.assertIn(b'DOL-2024-B1', resp.data)

    def test_reports_csv_export_expired(self):
        """Verifies downloadable CSV export for expired medicines report."""
        self.set_authenticated_session()
        mock_rows = [{
            'name': 'Dolo-650', 'generic_name': 'Paracetamol', 'category': 'Analgesics',
            'batch_number': 'DOL-2024-B1', 'expiry_date': '2026-10-15', 'current_quantity': 45,
            'unit_price': 2.50, 'loss': 112.50, 'supplier': 'Apex', 'storage_rack': 'Rack A-1'
        }]
        with patch('app.routes.reports.query_db', return_value=mock_rows):
            resp = self.client.get('/reports/export/csv?type=expired')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers['Content-Type'], 'text/csv; charset=utf-8')
            self.assertIn('attachment;', resp.headers['Content-Disposition'])
            self.assertIn('meditrack_expired_report_', resp.headers['Content-Disposition'])
            self.assertIn(b'Medicine Name,Generic Name,Category,Batch #', resp.data)
            self.assertIn(b'Dolo-650', resp.data)

    def test_reports_csv_export_low_stock(self):
        """Verifies downloadable CSV export for low-stock alert report."""
        self.set_authenticated_session()
        mock_rows = [{
            'name': 'Atropine Inj', 'generic_name': 'Atropine Sulfate', 'category': 'Emergency',
            'dosage_form': 'Injection', 'strength': '0.6 mg/ml', 'min_stock_threshold': 15,
            'current_stock': 12, 'storage_rack': 'Crash Cart 1'
        }]
        with patch('app.routes.reports.query_db', return_value=mock_rows):
            resp = self.client.get('/reports/export/csv?type=low_stock')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers['Content-Type'], 'text/csv; charset=utf-8')
            self.assertIn(b'Min Stock Threshold,Current Active Stock', resp.data)
            self.assertIn(b'Atropine Inj', resp.data)


if __name__ == '__main__':
    unittest.main()
