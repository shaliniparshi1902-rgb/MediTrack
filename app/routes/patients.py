"""
MediTrack - Patient Management Blueprint
Handles patient registration, profile viewing, editing, deletion,
and linkage to medicine dispensing audit histories.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from app.db import query_db, execute_db
from app.utils.decorators import login_required, admin_required

patients_bp = Blueprint('patients', __name__, url_prefix='/patients')

BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
GENDERS = ['Male', 'Female', 'Other']


def generate_next_patient_id():
    """
    Generates a sequential patient identifier, e.g. PAT-10022.
    """
    last_patient = query_db(
        "SELECT patient_id FROM patients WHERE patient_id LIKE 'PAT-%' ORDER BY id DESC LIMIT 1",
        one=True
    )
    if last_patient and last_patient.get('patient_id'):
        try:
            num_part = int(last_patient['patient_id'].replace('PAT-', ''))
            return f"PAT-{num_part + 1:05d}"
        except ValueError:
            pass
    # Fallback based on total count
    cnt_res = query_db("SELECT COUNT(*) AS total FROM patients", one=True)
    count = (cnt_res['total'] if cnt_res else 0) + 10001
    return f"PAT-{count}"


@patients_bp.route('/')
@login_required
def index():
    """
    Renders patient directory table with search and blood group filter.
    """
    search_query = request.args.get('q', '').strip()
    blood_group_filter = request.args.get('blood_group', '').strip()
    gender_filter = request.args.get('gender', '').strip()

    query = """
        SELECT p.*,
               COUNT(u.id) AS total_prescriptions
        FROM patients p
        LEFT JOIN medicine_usage u ON p.patient_id = u.patient_id
        WHERE 1=1
    """
    params = []

    if search_query:
        query += " AND (p.full_name LIKE %s OR p.patient_id LIKE %s OR p.phone LIKE %s OR p.email LIKE %s)"
        term = f"%{search_query}%"
        params.extend([term, term, term, term])

    if blood_group_filter and blood_group_filter in BLOOD_GROUPS:
        query += " AND p.blood_group = %s"
        params.append(blood_group_filter)

    if gender_filter and gender_filter in GENDERS:
        query += " AND p.gender = %s"
        params.append(gender_filter)

    query += " GROUP BY p.id, p.patient_id, p.full_name, p.age, p.gender, p.phone, p.email, p.blood_group, p.address, p.allergies, p.created_at, p.updated_at ORDER BY p.id DESC"

    try:
        patients = query_db(query, tuple(params)) or []
        total_count = len(patients)
        allergies_count = sum(1 for p in patients if p.get('allergies') and p['allergies'].lower() not in ('none', 'none reported', 'n/a', ''))
    except Exception as e:
        current_app.logger.error(f"Error fetching patients: {e}")
        flash("Failed to retrieve patients from database.", "danger")
        patients = []
        total_count = 0
        allergies_count = 0

    return render_template(
        'patients/index.html',
        patients=patients,
        total_count=total_count,
        allergies_count=allergies_count,
        blood_groups=BLOOD_GROUPS,
        genders=GENDERS,
        search_query=search_query,
        selected_blood_group=blood_group_filter,
        selected_gender=gender_filter
    )


@patients_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """
    Registers a new patient with medical demographics and allergy details.
    """
    if request.method == 'POST':
        patient_id = request.form.get('patient_id', '').strip()
        full_name = request.form.get('full_name', '').strip()
        age_str = request.form.get('age', '').strip()
        gender = request.form.get('gender', 'Male').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        blood_group = request.form.get('blood_group', '').strip()
        address = request.form.get('address', '').strip()
        allergies = request.form.get('allergies', '').strip()

        # Validation
        if not full_name:
            flash("Patient full name is required.", "warning")
            return render_template('patients/add_edit.html', is_edit=False, blood_groups=BLOOD_GROUPS, genders=GENDERS, form=request.form)

        try:
            age = int(age_str)
            if age <= 0 or age > 150:
                flash("Please enter a valid age between 1 and 150.", "warning")
                return render_template('patients/add_edit.html', is_edit=False, blood_groups=BLOOD_GROUPS, genders=GENDERS, form=request.form)
        except ValueError:
            flash("Valid age number is required.", "warning")
            return render_template('patients/add_edit.html', is_edit=False, blood_groups=BLOOD_GROUPS, genders=GENDERS, form=request.form)

        # Auto-generate patient ID if left blank
        if not patient_id:
            try:
                patient_id = generate_next_patient_id()
            except Exception:
                patient_id = f"PAT-{int(age_str) + 1000}"

        # Verify uniqueness of patient_id
        existing = query_db("SELECT id FROM patients WHERE patient_id = %s", (patient_id,), one=True)
        if existing:
            flash(f"Patient ID '{patient_id}' already exists in the system.", "danger")
            return render_template('patients/add_edit.html', is_edit=False, blood_groups=BLOOD_GROUPS, genders=GENDERS, form=request.form)

        try:
            res = execute_db(
                """
                INSERT INTO patients (patient_id, full_name, age, gender, phone, email, blood_group, address, allergies)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (patient_id, full_name, age, gender, phone, email, blood_group or None, address, allergies or 'None reported')
            )
            new_id = res['lastrowid']
            flash(f"Patient '{full_name}' ({patient_id}) has been successfully registered.", "success")
            return redirect(url_for('patients.view', patient_id=new_id))

        except Exception as e:
            current_app.logger.error(f"Error registering patient: {e}")
            flash(f"Registration failed: {e}", "danger")
            return render_template('patients/add_edit.html', is_edit=False, blood_groups=BLOOD_GROUPS, genders=GENDERS, form=request.form)

    # GET request: prefill suggested patient ID
    suggested_id = ""
    try:
        suggested_id = generate_next_patient_id()
    except Exception:
        suggested_id = "PAT-10050"

    return render_template(
        'patients/add_edit.html',
        is_edit=False,
        blood_groups=BLOOD_GROUPS,
        genders=GENDERS,
        suggested_id=suggested_id,
        form={'patient_id': suggested_id}
    )


@patients_bp.route('/view/<int:patient_id>')
@login_required
def view(patient_id):
    """
    Displays patient demographic profile, blood group badge, allergies warnings,
    and all associated dispensing records.
    """
    patient = query_db("SELECT * FROM patients WHERE id = %s", (patient_id,), one=True)
    if not patient:
        flash("Patient record not found.", "danger")
        return redirect(url_for('patients.index'))

    # Retrieve all medicines dispensed to this patient
    dispensing_history = query_db(
        """
        SELECT u.*, b.batch_number, b.expiry_date,
               m.name AS medicine_name, m.generic_name, m.dosage_form, m.strength,
               usr.full_name AS dispensed_by_name
        FROM medicine_usage u
        JOIN batches b ON u.batch_id = b.id
        JOIN medicines m ON b.medicine_id = m.id
        JOIN users usr ON u.dispensed_by = usr.id
        WHERE u.patient_id = %s OR u.patient_name = %s
        ORDER BY u.usage_date DESC
        """,
        (patient['patient_id'], patient['full_name'])
    ) or []

    total_units_received = sum(int(row['quantity_used']) for row in dispensing_history)

    has_allergies = bool(
        patient.get('allergies') and 
        patient['allergies'].strip().lower() not in ('none', 'none reported', 'n/a', '')
    )

    return render_template(
        'patients/view.html',
        patient=patient,
        dispensing_history=dispensing_history,
        total_units_received=total_units_received,
        has_allergies=has_allergies
    )


@patients_bp.route('/edit/<int:patient_id>', methods=['GET', 'POST'])
@login_required
def edit(patient_id):
    """
    Edits existing patient profile information.
    """
    patient = query_db("SELECT * FROM patients WHERE id = %s", (patient_id,), one=True)
    if not patient:
        flash("Patient not found.", "danger")
        return redirect(url_for('patients.index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        age_str = request.form.get('age', '').strip()
        gender = request.form.get('gender', 'Male').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        blood_group = request.form.get('blood_group', '').strip()
        address = request.form.get('address', '').strip()
        allergies = request.form.get('allergies', '').strip()

        if not full_name:
            flash("Full name is required.", "warning")
            return render_template('patients/add_edit.html', is_edit=True, patient=patient, form=request.form, blood_groups=BLOOD_GROUPS, genders=GENDERS)

        try:
            age = int(age_str)
            if age <= 0 or age > 150:
                flash("Please enter a valid age.", "warning")
                return render_template('patients/add_edit.html', is_edit=True, patient=patient, form=request.form, blood_groups=BLOOD_GROUPS, genders=GENDERS)
        except ValueError:
            flash("Valid age number is required.", "warning")
            return render_template('patients/add_edit.html', is_edit=True, patient=patient, form=request.form, blood_groups=BLOOD_GROUPS, genders=GENDERS)

        try:
            execute_db(
                """
                UPDATE patients
                SET full_name = %s, age = %s, gender = %s, phone = %s, email = %s,
                    blood_group = %s, address = %s, allergies = %s
                WHERE id = %s
                """,
                (full_name, age, gender, phone, email, blood_group or None, address, allergies or 'None reported', patient_id)
            )
            flash(f"Patient profile for '{full_name}' updated successfully.", "success")
            return redirect(url_for('patients.view', patient_id=patient_id))
        except Exception as e:
            current_app.logger.error(f"Error updating patient {patient_id}: {e}")
            flash(f"Update failed: {e}", "danger")

    return render_template('patients/add_edit.html', is_edit=True, patient=patient, form=patient, blood_groups=BLOOD_GROUPS, genders=GENDERS)


@patients_bp.route('/delete/<int:patient_id>', methods=['POST'])
@login_required
@admin_required
def delete(patient_id):
    """
    Deletes patient record if no dispensing records exist.
    Blocks deletion if dispensing logs are present to maintain clinical audit trail.
    """
    patient = query_db("SELECT id, patient_id, full_name FROM patients WHERE id = %s", (patient_id,), one=True)
    if not patient:
        flash("Patient not found.", "danger")
        return redirect(url_for('patients.index'))

    # Check if patient has dispensing records
    usage = query_db(
        "SELECT id FROM medicine_usage WHERE patient_id = %s OR patient_name = %s LIMIT 1",
        (patient['patient_id'], patient['full_name']),
        one=True
    )
    if usage:
        flash(
            f"Cannot delete patient '{patient['full_name']}' ({patient['patient_id']}) because they have active medical dispensing records. "
            f"Clinical audit trails must be preserved for hospital compliance.",
            "danger"
        )
        return redirect(url_for('patients.view', patient_id=patient_id))

    try:
        execute_db("DELETE FROM patients WHERE id = %s", (patient_id,))
        flash(f"Patient '{patient['full_name']}' ({patient['patient_id']}) was deleted successfully.", "success")
    except Exception as e:
        current_app.logger.error(f"Error deleting patient {patient_id}: {e}")
        flash(f"Failed to delete patient: {e}", "danger")

    return redirect(url_for('patients.index'))


@patients_bp.route('/api/search')
@login_required
def api_search():
    """
    API endpoint to search patients for autocomplete in dispensing forms.
    Returns patient_id, full_name, allergies, and blood_group.
    """
    term = request.args.get('q', '').strip()
    if not term:
        patients = query_db(
            "SELECT id, patient_id, full_name, age, gender, blood_group, allergies FROM patients ORDER BY full_name ASC LIMIT 20"
        ) or []
    else:
        like_term = f"%{term}%"
        patients = query_db(
            """
            SELECT id, patient_id, full_name, age, gender, blood_group, allergies
            FROM patients
            WHERE full_name LIKE %s OR patient_id LIKE %s
            ORDER BY full_name ASC LIMIT 10
            """,
            (like_term, like_term)
        ) or []

    return jsonify({'patients': patients})
