"""
MediTrack - Inventory Blueprint
Handles CRUD operations for medicines and batches, stock filtering,
search, and detailed medicine views.
"""

from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from app.db import query_db, execute_db
from app.utils.decorators import login_required, admin_required
from app.utils.helpers import calculate_expiry_status, is_low_stock, parse_date

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')


@inventory_bp.route('/')
@login_required
def index():
    """
    Lists medicines with aggregated stock counts, search, category filter, and status filters.
    """
    today = date.today()
    thirty_days = today + timedelta(days=30)

    # Filter parameters
    search_query = request.args.get('q', '').strip()
    category_id = request.args.get('category_id', '').strip()
    status_filter = request.args.get('status', 'all').strip()

    # Base query for medicines list
    query = """
        SELECT 
            m.id, m.name, m.generic_name, m.dosage_form, m.strength,
            m.manufacturer, m.min_stock_threshold, m.storage_rack,
            c.id AS category_id, c.name AS category_name,
            COUNT(DISTINCT b.id) AS total_batches,
            COALESCE(SUM(CASE WHEN b.expiry_date >= %s AND b.status = 'active' THEN b.current_quantity ELSE 0 END), 0) AS active_stock,
            COALESCE(SUM(CASE WHEN b.expiry_date < %s AND b.current_quantity > 0 THEN b.current_quantity ELSE 0 END), 0) AS expired_stock,
            MIN(CASE WHEN b.expiry_date >= %s AND b.status = 'active' AND b.current_quantity > 0 THEN b.expiry_date ELSE NULL END) AS earliest_expiry
        FROM medicines m
        JOIN categories c ON m.category_id = c.id
        LEFT JOIN batches b ON m.id = b.medicine_id
        WHERE 1=1
    """
    params = [today, today, today]

    if search_query:
        query += " AND (m.name LIKE %s OR m.generic_name LIKE %s OR b.batch_number LIKE %s)"
        like_term = f"%{search_query}%"
        params.extend([like_term, like_term, like_term])

    if category_id and category_id.isdigit():
        query += " AND m.category_id = %s"
        params.append(int(category_id))

    query += " GROUP BY m.id, m.name, m.generic_name, m.dosage_form, m.strength, m.manufacturer, m.min_stock_threshold, m.storage_rack, c.id, c.name"

    # Status filter logic using HAVING
    if status_filter == 'low_stock':
        query += " HAVING active_stock <= m.min_stock_threshold"
    elif status_filter == 'expired':
        query += " HAVING expired_stock > 0"
    elif status_filter == 'critical' or status_filter == 'expiring_soon':
        query += " HAVING earliest_expiry IS NOT NULL AND earliest_expiry <= %s"
        params.append(thirty_days)

    query += " ORDER BY m.name ASC"

    try:
        medicines = query_db(query, tuple(params)) or []
        for med in medicines:
            med['is_low'] = int(med['active_stock']) <= int(med['min_stock_threshold'])
            if med['earliest_expiry']:
                med['expiry_info'] = calculate_expiry_status(med['earliest_expiry'], today)
            else:
                med['expiry_info'] = None

        categories = query_db("SELECT id, name FROM categories ORDER BY name ASC") or []
    except Exception as e:
        current_app.logger.error(f"Error loading inventory index: {e}")
        flash("Failed to retrieve inventory data from database.", "danger")
        medicines = []
        categories = []

    return render_template(
        'inventory/index.html',
        medicines=medicines,
        categories=categories,
        search_query=search_query,
        selected_category=category_id,
        selected_status=status_filter
    )


@inventory_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """
    Adds a new medicine and an optional initial batch.
    """
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        generic_name = request.form.get('generic_name', '').strip()
        category_id = request.form.get('category_id', '').strip()
        dosage_form = request.form.get('dosage_form', 'Tablet').strip()
        strength = request.form.get('strength', '').strip()
        manufacturer = request.form.get('manufacturer', '').strip()
        min_stock_threshold = request.form.get('min_stock_threshold', '20').strip()
        storage_rack = request.form.get('storage_rack', '').strip()

        # Batch fields (optional initial batch)
        batch_number = request.form.get('batch_number', '').strip()
        initial_quantity = request.form.get('initial_quantity', '').strip()
        mfg_date_str = request.form.get('mfg_date', '').strip()
        expiry_date_str = request.form.get('expiry_date', '').strip()
        unit_price = request.form.get('unit_price', '0.00').strip()
        supplier = request.form.get('supplier', '').strip()

        # Validation
        if not name or not generic_name or not category_id or not strength:
            flash("Please provide Medicine Name, Generic Name, Category, and Strength.", "warning")
            categories = query_db("SELECT id, name FROM categories ORDER BY name ASC") or []
            return render_template('inventory/add_edit.html', is_edit=False, categories=categories, form=request.form)

        try:
            min_thresh = max(1, int(min_stock_threshold))
        except ValueError:
            min_thresh = 20

        try:
            # 1. Insert medicine record
            med_res = execute_db(
                """
                INSERT INTO medicines (category_id, name, generic_name, dosage_form, strength, manufacturer, min_stock_threshold, storage_rack)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (int(category_id), name, generic_name, dosage_form, strength, manufacturer, min_thresh, storage_rack)
            )
            medicine_id = med_res['lastrowid']

            # 2. If batch details provided, insert initial batch
            if batch_number and initial_quantity and mfg_date_str and expiry_date_str:
                qty = max(1, int(initial_quantity))
                mfg = parse_date(mfg_date_str)
                exp = parse_date(expiry_date_str)
                price = max(0.0, float(unit_price or 0.0))

                if exp <= mfg:
                    flash("Warning: Expiry date must be after manufacturing date. Batch was not saved.", "warning")
                else:
                    execute_db(
                        """
                        INSERT INTO batches (medicine_id, batch_number, initial_quantity, current_quantity, mfg_date, expiry_date, unit_price, supplier, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
                        """,
                        (medicine_id, batch_number, qty, qty, mfg, exp, price, supplier)
                    )

            flash(f"Medicine '{name}' has been successfully added to inventory.", "success")
            return redirect(url_for('inventory.view', medicine_id=medicine_id))

        except Exception as e:
            current_app.logger.error(f"Error adding medicine: {e}")
            flash(f"Failed to add medicine: {e}", "danger")
            categories = query_db("SELECT id, name FROM categories ORDER BY name ASC") or []
            return render_template('inventory/add_edit.html', is_edit=False, categories=categories, form=request.form)

    categories = query_db("SELECT id, name FROM categories ORDER BY name ASC") or []
    return render_template('inventory/add_edit.html', is_edit=False, categories=categories, form=request.form)


@inventory_bp.route('/edit/<int:medicine_id>', methods=['GET', 'POST'])
@login_required
def edit(medicine_id):
    """
    Edits existing medicine master information.
    """
    med = query_db("SELECT * FROM medicines WHERE id = %s", (medicine_id,), one=True)
    if not med:
        flash("Medicine not found.", "danger")
        return redirect(url_for('inventory.index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        generic_name = request.form.get('generic_name', '').strip()
        category_id = request.form.get('category_id', '').strip()
        dosage_form = request.form.get('dosage_form', 'Tablet').strip()
        strength = request.form.get('strength', '').strip()
        manufacturer = request.form.get('manufacturer', '').strip()
        min_stock_threshold = request.form.get('min_stock_threshold', '20').strip()
        storage_rack = request.form.get('storage_rack', '').strip()

        if not name or not generic_name or not category_id or not strength:
            flash("Please fill in all mandatory fields.", "warning")
            categories = query_db("SELECT id, name FROM categories ORDER BY name ASC") or []
            return render_template('inventory/add_edit.html', is_edit=True, medicine=med, categories=categories, form=request.form)

        try:
            min_thresh = max(1, int(min_stock_threshold))
            execute_db(
                """
                UPDATE medicines
                SET category_id = %s, name = %s, generic_name = %s, dosage_form = %s,
                    strength = %s, manufacturer = %s, min_stock_threshold = %s, storage_rack = %s
                WHERE id = %s
                """,
                (int(category_id), name, generic_name, dosage_form, strength, manufacturer, min_thresh, storage_rack, medicine_id)
            )
            flash(f"Medicine '{name}' updated successfully.", "success")
            return redirect(url_for('inventory.view', medicine_id=medicine_id))
        except Exception as e:
            current_app.logger.error(f"Error updating medicine {medicine_id}: {e}")
            flash(f"Update failed: {e}", "danger")

    categories = query_db("SELECT id, name FROM categories ORDER BY name ASC") or []
    return render_template('inventory/add_edit.html', is_edit=True, medicine=med, categories=categories)


@inventory_bp.route('/view/<int:medicine_id>')
@login_required
def view(medicine_id):
    """
    Displays full medicine details, all associated batches with expiry tracking,
    and chronological usage history.
    """
    today = date.today()
    med = query_db(
        """
        SELECT m.*, c.name AS category_name
        FROM medicines m
        JOIN categories c ON m.category_id = c.id
        WHERE m.id = %s
        """,
        (medicine_id,),
        one=True
    )
    if not med:
        flash("Medicine not found.", "danger")
        return redirect(url_for('inventory.index'))

    batches = query_db(
        """
        SELECT *
        FROM batches
        WHERE medicine_id = %s
        ORDER BY expiry_date ASC
        """,
        (medicine_id,)
    ) or []

    total_active_stock = 0
    total_expired_stock = 0

    for b in batches:
        b['expiry_info'] = calculate_expiry_status(b['expiry_date'], today)
        exp_date = parse_date(b['expiry_date'])
        if exp_date and exp_date >= today and b['status'] == 'active':
            total_active_stock += int(b['current_quantity'])
        elif exp_date and exp_date < today:
            total_expired_stock += int(b['current_quantity'])

    # Recent usage records for this medicine
    usage_history = query_db(
        """
        SELECT u.*, b.batch_number, usr.full_name AS dispenser_name
        FROM medicine_usage u
        JOIN batches b ON u.batch_id = b.id
        JOIN users usr ON u.dispensed_by = usr.id
        WHERE b.medicine_id = %s
        ORDER BY u.usage_date DESC
        LIMIT 20
        """,
        (medicine_id,)
    ) or []

    return render_template(
        'inventory/view.html',
        medicine=med,
        batches=batches,
        usage_history=usage_history,
        total_active_stock=total_active_stock,
        total_expired_stock=total_expired_stock,
        is_low_stock=total_active_stock <= int(med['min_stock_threshold'])
    )


@inventory_bp.route('/batch/add/<int:medicine_id>', methods=['POST'])
@login_required
def add_batch(medicine_id):
    """
    Adds a new batch to an existing medicine.
    """
    batch_number = request.form.get('batch_number', '').strip()
    quantity_str = request.form.get('quantity', '').strip()
    mfg_date_str = request.form.get('mfg_date', '').strip()
    expiry_date_str = request.form.get('expiry_date', '').strip()
    unit_price_str = request.form.get('unit_price', '0.00').strip()
    supplier = request.form.get('supplier', '').strip()

    if not batch_number or not quantity_str or not mfg_date_str or not expiry_date_str:
        flash("All batch fields (Batch #, Quantity, Mfg Date, Expiry Date) are required.", "warning")
        return redirect(url_for('inventory.view', medicine_id=medicine_id))

    try:
        qty = int(quantity_str)
        if qty <= 0:
            flash("Batch quantity must be a positive number.", "warning")
            return redirect(url_for('inventory.view', medicine_id=medicine_id))

        mfg = parse_date(mfg_date_str)
        exp = parse_date(expiry_date_str)
        if exp <= mfg:
            flash("Expiry date must be after manufacturing date.", "warning")
            return redirect(url_for('inventory.view', medicine_id=medicine_id))

        price = max(0.0, float(unit_price_str or 0.0))

        # Check unique batch number
        existing = query_db("SELECT id FROM batches WHERE batch_number = %s", (batch_number,), one=True)
        if existing:
            flash(f"Batch number '{batch_number}' already exists in inventory.", "danger")
            return redirect(url_for('inventory.view', medicine_id=medicine_id))

        execute_db(
            """
            INSERT INTO batches (medicine_id, batch_number, initial_quantity, current_quantity, mfg_date, expiry_date, unit_price, supplier, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
            """,
            (medicine_id, batch_number, qty, qty, mfg, exp, price, supplier)
        )
        flash(f"Batch '{batch_number}' ({qty} units) added successfully.", "success")

    except Exception as e:
        current_app.logger.error(f"Error adding batch to medicine {medicine_id}: {e}")
        flash(f"Failed to add batch: {e}", "danger")

    return redirect(url_for('inventory.view', medicine_id=medicine_id))


@inventory_bp.route('/batch/delete/<int:batch_id>', methods=['POST'])
@login_required
@admin_required
def delete_batch(batch_id):
    """
    Deletes or marks a batch as depleted/quarantined.
    """
    batch = query_db("SELECT id, medicine_id, batch_number FROM batches WHERE id = %s", (batch_id,), one=True)
    if not batch:
        flash("Batch not found.", "danger")
        return redirect(url_for('inventory.index'))

    # Check if this batch has dispensing history
    usage = query_db("SELECT id FROM medicine_usage WHERE batch_id = %s LIMIT 1", (batch_id,), one=True)
    if usage:
        # Instead of deleting, mark as depleted or quarantined to preserve hospital audit logs
        execute_db("UPDATE batches SET status = 'quarantined' WHERE id = %s", (batch_id,))
        flash(f"Batch '{batch['batch_number']}' has historical usage records and cannot be permanently removed. Status updated to 'quarantined'.", "warning")
    else:
        execute_db("DELETE FROM batches WHERE id = %s", (batch_id,))
        flash(f"Batch '{batch['batch_number']}' deleted successfully.", "success")

    return redirect(url_for('inventory.view', medicine_id=batch['medicine_id']))


@inventory_bp.route('/delete/<int:medicine_id>', methods=['POST'])
@login_required
@admin_required
def delete(medicine_id):
    """
    Deletes a medicine master record if no usage history exists.
    """
    med = query_db("SELECT id, name FROM medicines WHERE id = %s", (medicine_id,), one=True)
    if not med:
        flash("Medicine not found.", "danger")
        return redirect(url_for('inventory.index'))

    # Check if any associated batch has dispensing history
    usage = query_db(
        """
        SELECT u.id 
        FROM medicine_usage u
        JOIN batches b ON u.batch_id = b.id
        WHERE b.medicine_id = %s
        LIMIT 1
        """,
        (medicine_id,),
        one=True
    )
    if usage:
        flash(f"Cannot delete '{med['name']}' because it has dispensing and audit log records.", "danger")
        return redirect(url_for('inventory.view', medicine_id=medicine_id))

    try:
        execute_db("DELETE FROM medicines WHERE id = %s", (medicine_id,))
        flash(f"Medicine '{med['name']}' and its batches were deleted successfully.", "success")
    except Exception as e:
        current_app.logger.error(f"Error deleting medicine {medicine_id}: {e}")
        flash(f"Could not delete medicine: {e}", "danger")

    return redirect(url_for('inventory.index'))
