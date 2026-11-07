"""
MediTrack - Patient Management Module Automated Test Suite
Verifies:
1. Patient listing directory view, search, and blood group filters
2. Patient registration input validation (full name, age, gender)
3. Duplicate patient ID detection and rejection
4. Patient profile view with clinical allergies and linked dispensing records
5. Patient profile editing
6. Patient deletion safety guard (blocks deletion when dispensing audit records exist)
7. Safe patient deletion when no dispensing records exist
8. Patient search API (/patients/api/search)
9. Integration with dispensing module (/usage/ prefill and registered patients dropdown)
"""

import unittest
from unittest.mock import patch, MagicMock
from app import create_app


class TestPatientManagement(unittest.TestCase):

    def setUp(self):
        """Initializes test client with authenticated session."""
        self.app = create_app({
            'TESTING': True,
            'SECRET_KEY': 'patients_test_secret_key',
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
    # 1. Patient Directory & Listing
    # -------------------------------------------------------------------------
    def test_patients_index_renders(self):
        """Verifies GET /patients/ renders patient directory with records."""
        self.set_authenticated_session()
        mock_patients = [{
            'id': 1, 'patient_id': 'PAT-10021', 'full_name': 'John Miller', 'age': 42,
            'gender': 'Male', 'phone': '+1-555-0142', 'email': 'john.miller@email.com',
            'blood_group': 'O+', 'address': '45 Elm Street', 'allergies': 'Penicillin',
            'total_prescriptions': 3
        }]
        with patch('app.routes.patients.query_db', return_value=mock_patients):
            resp = self.client.get('/patients/')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Patient Management', resp.data)
            self.assertIn(b'John Miller', resp.data)
            self.assertIn(b'PAT-10021', resp.data)
            self.assertIn(b'Penicillin', resp.data)

    def test_patients_index_search_filter(self):
        """Verifies filtering by search term and blood group."""
        self.set_authenticated_session()
        mock_filtered = [{
            'id': 2, 'patient_id': 'PAT-10045', 'full_name': 'Emily Davis', 'age': 29,
            'gender': 'Female', 'phone': '+1-555-0188', 'email': 'emily.davis@email.com',
            'blood_group': 'A+', 'address': '128 Maple Ave', 'allergies': 'None reported',
            'total_prescriptions': 1
        }]
        with patch('app.routes.patients.query_db', return_value=mock_filtered):
            resp = self.client.get('/patients/?q=Emily&blood_group=A+')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Emily Davis', resp.data)
            self.assertIn(b'A+', resp.data)

    # -------------------------------------------------------------------------
    # 2. Patient Registration (Add)
    # -------------------------------------------------------------------------
    def test_patient_add_page_renders(self):
        """Verifies GET /patients/add renders the registration form."""
        self.set_authenticated_session()
        with patch('app.routes.patients.query_db', return_value=None):
            resp = self.client.get('/patients/add')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Register New Patient', resp.data)
            self.assertIn(b'Patient Demographics', resp.data)

    def test_patient_add_validation_missing_name(self):
        """Verifies registration fails when full name is missing."""
        self.set_authenticated_session()
        resp = self.client.post('/patients/add', data={
            'full_name': '',
            'age': '30',
            'gender': 'Male'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Patient full name is required.', resp.data)

    def test_patient_add_validation_invalid_age(self):
        """Verifies registration fails when age is invalid."""
        self.set_authenticated_session()
        resp = self.client.post('/patients/add', data={
            'full_name': 'Test Person',
            'age': '-5',
            'gender': 'Male'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Please enter a valid age', resp.data)

    def test_patient_add_duplicate_id_rejected(self):
        """Verifies registration rejects duplicate patient IDs."""
        self.set_authenticated_session()
        with patch('app.routes.patients.query_db', return_value={'id': 1}):
            resp = self.client.post('/patients/add', data={
                'patient_id': 'PAT-10021',
                'full_name': 'Duplicate User',
                'age': '40',
                'gender': 'Male'
            })
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'already exists in the system', resp.data)

    def test_patient_add_successful_registration(self):
        """Verifies successful registration redirects to patient view."""
        self.set_authenticated_session()
        # query_db returns None (no duplicate), execute_db returns new ID 6
        with patch('app.routes.patients.query_db', return_value=None), \
             patch('app.routes.patients.execute_db', return_value={'lastrowid': 6, 'rowcount': 1}):
            resp = self.client.post('/patients/add', data={
                'patient_id': 'PAT-10099',
                'full_name': 'Eleanor Vance',
                'age': '36',
                'gender': 'Female',
                'phone': '+1-555-0999',
                'email': 'eleanor@vance.com',
                'blood_group': 'O-',
                'address': '12 Rose Hill Road',
                'allergies': 'Latex, Codeine'
            }, follow_redirects=False)

            self.assertEqual(resp.status_code, 302)
            self.assertIn('/patients/view/6', resp.headers['Location'])

    # -------------------------------------------------------------------------
    # 3. Patient View Profile & Medical History
    # -------------------------------------------------------------------------
    def test_patient_view_renders_profile_and_dispensing_history(self):
        """Verifies viewing patient details shows demographics, allergy banner, and dispensing history."""
        self.set_authenticated_session()
        mock_patient = {
            'id': 1, 'patient_id': 'PAT-10021', 'full_name': 'John Miller', 'age': 42,
            'gender': 'Male', 'phone': '+1-555-0142', 'email': 'john.miller@email.com',
            'blood_group': 'O+', 'address': '45 Elm Street', 'allergies': 'Penicillin, Amoxicillin',
            'created_at': '2026-11-01 10:00:00'
        }
        mock_dispensing = [{
            'id': 1, 'quantity_used': 10, 'department': 'OPD', 'prescribed_by': 'Dr. Ramesh Rao',
            'reason': 'Fever and fatigue', 'usage_date': '2026-11-02 09:30:00',
            'batch_number': 'DOL-2025-B2', 'medicine_name': 'Dolo-650', 'generic_name': 'Paracetamol',
            'dosage_form': 'Tablet', 'strength': '650 mg', 'dispensed_by_name': 'Alex Patel'
        }]

        with patch('app.routes.patients.query_db', side_effect=[mock_patient, mock_dispensing]):
            resp = self.client.get('/patients/view/1')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'John Miller', resp.data)
            self.assertIn(b'PAT-10021', resp.data)
            self.assertIn(b'CRITICAL CLINICAL ALLERGIES ON RECORD', resp.data)
            self.assertIn(b'Penicillin, Amoxicillin', resp.data)
            self.assertIn(b'Dolo-650', resp.data)
            self.assertIn(b'DOL-2025-B2', resp.data)

    # -------------------------------------------------------------------------
    # 4. Patient Edit
    # -------------------------------------------------------------------------
    def test_patient_edit_renders_and_updates(self):
        """Verifies editing patient details."""
        self.set_authenticated_session()
        mock_patient = {
            'id': 1, 'patient_id': 'PAT-10021', 'full_name': 'John Miller', 'age': 42,
            'gender': 'Male', 'phone': '+1-555-0142', 'email': 'john.miller@email.com',
            'blood_group': 'O+', 'address': '45 Elm Street', 'allergies': 'Penicillin'
        }

        with patch('app.routes.patients.query_db', return_value=mock_patient), \
             patch('app.routes.patients.execute_db', return_value={'rowcount': 1}):
            # GET edit form
            resp_get = self.client.get('/patients/edit/1')
            self.assertEqual(resp_get.status_code, 200)
            self.assertIn(b'Edit Patient Profile', resp_get.data)
            self.assertIn(b'John Miller', resp_get.data)

            # POST update
            resp_post = self.client.post('/patients/edit/1', data={
                'full_name': 'John Miller Jr.',
                'age': '43',
                'gender': 'Male',
                'phone': '+1-555-9999',
                'email': 'john.jr@email.com',
                'blood_group': 'O+',
                'address': '99 New Elm Street',
                'allergies': 'Penicillin, Cephalosporins'
            }, follow_redirects=False)

            self.assertEqual(resp_post.status_code, 302)
            self.assertIn('/patients/view/1', resp_post.headers['Location'])

    # -------------------------------------------------------------------------
    # 5. Patient Deletion & Audit Protection
    # -------------------------------------------------------------------------
    def test_patient_delete_blocked_when_dispensing_exists(self):
        """Verifies that deleting a patient who has medical dispensing records is blocked."""
        self.set_authenticated_session(role='admin')
        mock_patient = {'id': 1, 'patient_id': 'PAT-10021', 'full_name': 'John Miller'}
        mock_usage = {'id': 1}  # dispensing record exists

        with patch('app.routes.patients.query_db', side_effect=[mock_patient, mock_usage]):
            resp = self.client.post('/patients/delete/1', follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/patients/view/1', resp.headers['Location'])

    def test_patient_delete_successful_when_no_dispensing(self):
        """Verifies that a patient with no medical records can be deleted cleanly."""
        self.set_authenticated_session(role='admin')
        mock_patient = {'id': 99, 'patient_id': 'PAT-99999', 'full_name': 'Unused Patient'}

        with patch('app.routes.patients.query_db', side_effect=[mock_patient, None]), \
             patch('app.routes.patients.execute_db', return_value={'rowcount': 1}):
            resp = self.client.post('/patients/delete/99', follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/patients/', resp.headers['Location'])

    # -------------------------------------------------------------------------
    # 6. Patient Search API
    # -------------------------------------------------------------------------
    def test_patient_search_api(self):
        """Verifies GET /patients/api/search returns JSON patient list."""
        self.set_authenticated_session()
        mock_results = [{
            'id': 1, 'patient_id': 'PAT-10021', 'full_name': 'John Miller',
            'age': 42, 'gender': 'Male', 'blood_group': 'O+', 'allergies': 'Penicillin'
        }]
        with patch('app.routes.patients.query_db', return_value=mock_results):
            resp = self.client.get('/patients/api/search?q=John')
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertIn('patients', data)
            self.assertEqual(len(data['patients']), 1)
            self.assertEqual(data['patients'][0]['full_name'], 'John Miller')

    # -------------------------------------------------------------------------
    # 7. Integration with Dispensing Module
    # -------------------------------------------------------------------------
    def test_dispensing_module_prefill_and_patient_list(self):
        """Verifies /usage/ receives patient list and honors prefilled patient info from query params."""
        self.set_authenticated_session()
        mock_meds = [{'id': 1, 'name': 'Dolo-650', 'generic_name': 'Paracetamol', 'dosage_form': 'Tablet', 'strength': '650 mg', 'unexpired_stock': 100}]
        mock_patients = [{'id': 1, 'patient_id': 'PAT-10021', 'full_name': 'John Miller', 'age': 42, 'gender': 'Male', 'blood_group': 'O+', 'allergies': 'Penicillin'}]

        with patch('app.routes.usage.query_db', side_effect=[[], mock_meds, mock_patients]):
            resp = self.client.get('/usage/?patient_id=PAT-10021&patient_name=John%20Miller')
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'PAT-10021', resp.data)
            self.assertIn(b'John Miller', resp.data)
            self.assertIn(b'Registered Patient (Quick Select)', resp.data)


if __name__ == '__main__':
    unittest.main()

