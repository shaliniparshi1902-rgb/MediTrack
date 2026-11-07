"""
MediTrack - Medicine Usage & Dispensing Blueprint
Implements hospital medicine dispensing with automated FEFO (First Expiry, First Out)
batch allocation, transactional stock decrement, and audit trail logging.
"""

from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from app.db import query_db, get_db
from app.utils.decorators import login_required
from app.utils.helpers import allocate_fefo_dispense, get_fefo_batches

usage_bp = Blueprint('usage', __name__, url_prefix='/usage')

DEPARTMENTS = [
    'Emergency',
    'ICU',
    'General Ward',
    'OPD',
    'Surgery',
    'Pediatrics',
    'Cardiology'
]


@usage_bp.route('/')
@login_required
def index():
    """
    Renders medicine dispensing portal with active inventory options
    and chronological usage history.
    """
    today = date.today()

    dept_filter = request.args.get('department', '').strip()
    med_filter = request.args.get('medicine_id', '').strip()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()

    # Query usage logs with join
    query = """
        SELECT 
            u.id, u.quantity_used, u.department, u.patient_name, u.patient_id,
            u.prescribed_by, u.reason, u.usage_date,
            b.batch_number, b.expiry_date,
            m.name AS medicine_name, m.generic_name, m.dosage_form, m.strength,
            usr.full_name AS dispensed_by_name
        FROM medicine_usage u
        JOIN batches b ON u.batch_id = b.id
        JOIN medicines m ON b.medicine_id = m.id
        JOIN users usr ON u.dispensed_by = usr.id
        WHERE 1=1
    """
    params = []

    if dept_filter and dept_filter in DEPARTMENTS:
        query += " AND u.department = %s"
        params.append(dept_filter)

    if med_filter and med_filter.isdigit():
        query += " AND m.id = %s"
        params.append(int(med_filter))

    if from_date:
        query += " AND DATE(u.usage_date) >= %s"
        params.append(from_date)

    if to_date:
        query += " AND DATE(u.usage_date) <= %s"
        params.append(to_date)

    query += " ORDER BY u.usage_date DESC LIMIT 100"

    try:
        usage_logs = query_db(query, tuple(params)) or []

        # List of medicines that have unexpired stock for dispensing dropdown
        available_meds = query_db(
            """
            SELECT m.id, m.name, m.generic_name, m.dosage_form, m.strength,
                   COALESCE(SUM(b.current_quantity), 0) AS unexpired_stock
            FROM medicines m
            JOIN batches b ON m.id = b.medicine_id
            WHERE b.status = 'active' AND b.expiry_date >= %s AND b.current_quantity > 0
            GROUP BY m.id, m.name, m.generic_name, m.dosage_form, m.strength
            HAVING unexpired_stock > 0
            ORDER BY m.name ASC
            """,
            (today,)
        ) or []

        # Registered patients list for quick selection & allergy alerts
        try:
            registered_patients = query_db(
                "SELECT id, patient_id, full_name, age, gender, blood_group, allergies FROM patients ORDER BY full_name ASC"
            ) or []
        except Exception:
            registered_patients = []

    except Exception as e:
        current_app.logger.error(f"Error loading usage page: {e}")
        usage_logs = []
        available_meds = []
        registered_patients = []

    return render_template(
        'usage/index.html',
        usage_logs=usage_logs,
        medicines=available_meds,
        patients=registered_patients,
        departments=DEPARTMENTS,
        selected_dept=dept_filter,
        selected_med=med_filter,
        prefill_patient_id=request.args.get('patient_id', '').strip(),
        prefill_patient_name=request.args.get('patient_name', '').strip(),
        from_date=from_date,
        to_date=to_date
    )


@usage_bp.route('/dispense', methods=['POST'])
@login_required
def dispense():
    """
    Dispenses medicine to a department/patient.
    Employs automated FEFO algorithm across available batches and executes
    database updates within a safe ACID transaction.
    """
    today = date.today()

    med_id_str = request.form.get('medicine_id', '').strip()
    qty_str = request.form.get('quantity', '').strip()
    department = request.form.get('department', '').strip()
    patient_name = request.form.get('patient_name', '').strip()
    patient_id = request.form.get('patient_id', '').strip()
    prescribed_by = request.form.get('prescribed_by', '').strip()
    reason = request.form.get('reason', '').strip()

    # Form Validation
    if not med_id_str or not qty_str or not department or not patient_name:
        flash("Please fill in Medicine, Quantity, Department, and Patient Name.", "warning")
        return redirect(url_for('usage.index'))

    if department not in DEPARTMENTS:
        flash("Invalid department selected.", "danger")
        return redirect(url_for('usage.index'))

    try:
        medicine_id = int(med_id_str)
        requested_qty = int(qty_str)
        if requested_qty <= 0:
            flash("Dispense quantity must be greater than zero.", "warning")
            return redirect(url_for('usage.index'))
    except ValueError:
        flash("Invalid medicine or quantity format.", "danger")
        return redirect(url_for('usage.index'))

    # Verify Medicine
    medicine = query_db("SELECT id, name FROM medicines WHERE id = %s", (medicine_id,), one=True)
    if not medicine:
        flash("Selected medicine not found in inventory.", "danger")
        return redirect(url_for('usage.index'))

    # Retrieve all active batches for this medicine
    batches = query_db(
        """
        SELECT id, batch_number, current_quantity, expiry_date, status
        FROM batches
        WHERE medicine_id = %s
        ORDER BY expiry_date ASC
        """,
        (medicine_id,)
    ) or []

    # Calculate FEFO Allocation
    allocation_res = allocate_fefo_dispense(requested_qty, batches, reference_date=today)
    if not allocation_res['success']:
        flash(f"Cannot dispense: {allocation_res['message']}", "danger")
        return redirect(url_for('usage.index'))

    allocations = allocation_res['allocations']
    dispenser_user_id = session.get('user_id')

    # Execute Transaction
    conn = get_db()
    cursor = conn.cursor()
    try:
        batch_summary_list = []

        for item in allocations:
            batch_id = item['batch_id']
            deduct_qty = item['deduct_quantity']
            batch_no = item['batch_number']
            batch_summary_list.append(f"{batch_no} ({deduct_qty} units)")

            # 1. Decrement batch current_quantity
            cursor.execute(
                """
                UPDATE batches
                SET current_quantity = current_quantity - %s,
                    status = CASE WHEN current_quantity - %s = 0 THEN 'depleted' ELSE status END
                WHERE id = %s
                """,
                (deduct_qty, deduct_qty, batch_id)
            )

            # 2. Insert usage record
            cursor.execute(
                """
                INSERT INTO medicine_usage 
                    (batch_id, quantity_used, department, patient_name, patient_id, prescribed_by, reason, dispensed_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (batch_id, deduct_qty, department, patient_name, patient_id, prescribed_by, reason, dispenser_user_id)
            )

        # Commit transaction
        conn.commit()
        cursor.close()

        batches_text = ", ".join(batch_summary_list)
        flash(
            f"Successfully dispensed {requested_qty} units of '{medicine['name']}' to {patient_name} ({department}). "
            f"FEFO allocation: {batches_text}.",
            "success"
        )

    except Exception as e:
        conn.rollback()
        cursor.close()
        current_app.logger.error(f"Transaction failed during dispensing: {e}")
        flash(f"Dispensing transaction failed: {e}", "danger")

    return redirect(url_for('usage.index'))


@usage_bp.route('/api/preview-fefo/<int:medicine_id>')
@login_required
def preview_fefo_api(medicine_id):
    """
    API endpoint that returns FEFO calculation preview for the frontend.
    """
    today = date.today()
    try:
        qty = int(request.args.get('quantity', 1))
    except ValueError:
        qty = 1

    batches = query_db(
        """
        SELECT id, batch_number, current_quantity, expiry_date, status
        FROM batches
        WHERE medicine_id = %s
        ORDER BY expiry_date ASC
        """,
        (medicine_id,)
    ) or []

    res = allocate_fefo_dispense(qty, batches, reference_date=today)
    return jsonify(res)
