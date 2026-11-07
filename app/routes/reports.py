"""
MediTrack - Reports Blueprint
Generates hospital reports: Expired medicines, Low-stock alerts,
Expiring-soon tracking, Historical usage logs, and CSV data export.
"""

from datetime import date, timedelta
from flask import Blueprint, render_template, request, Response, flash, current_app
from app.db import query_db
from app.utils.decorators import login_required
from app.utils.helpers import calculate_expiry_status, generate_csv_string

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.route('/')
@login_required
def index():
    """
    Renders filterable reports dashboard for inventory, expiry, and consumption.
    """
    today = date.today()
    tab = request.args.get('tab', 'expired').strip().lower()
    days_window = int(request.args.get('days', 30))
    department = request.args.get('department', '').strip()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()

    expired_list = []
    low_stock_list = []
    expiring_soon_list = []
    usage_list = []
    summary = {}

    try:
        # 1. Expired Medicines Data
        if tab == 'expired':
            expired_list = query_db(
                """
                SELECT 
                    b.id, b.batch_number, b.current_quantity, b.expiry_date, b.unit_price, b.supplier,
                    (b.current_quantity * b.unit_price) AS financial_loss,
                    m.name AS medicine_name, m.generic_name, m.dosage_form, m.strength, m.storage_rack,
                    c.name AS category_name
                FROM batches b
                JOIN medicines m ON b.medicine_id = m.id
                JOIN categories c ON m.category_id = c.id
                WHERE b.expiry_date < %s AND b.current_quantity > 0
                ORDER BY b.expiry_date DESC
                """,
                (today,)
            ) or []

            total_loss = sum(float(item['financial_loss'] or 0) for item in expired_list)
            total_units = sum(int(item['current_quantity']) for item in expired_list)
            summary = {
                'total_batches': len(expired_list),
                'total_units': total_units,
                'total_financial_loss': total_loss
            }

        # 2. Low-Stock Alert Data
        elif tab == 'low_stock':
            low_stock_list = query_db(
                """
                SELECT 
                    m.id, m.name, m.generic_name, m.dosage_form, m.strength,
                    m.min_stock_threshold, m.storage_rack, c.name AS category_name,
                    COALESCE(SUM(CASE WHEN b.expiry_date >= %s AND b.status = 'active' THEN b.current_quantity ELSE 0 END), 0) AS active_stock
                FROM medicines m
                JOIN categories c ON m.category_id = c.id
                LEFT JOIN batches b ON m.id = b.medicine_id
                GROUP BY m.id, m.name, m.generic_name, m.dosage_form, m.strength, m.min_stock_threshold, m.storage_rack, c.name
                HAVING active_stock <= m.min_stock_threshold
                ORDER BY active_stock ASC
                """,
                (today,)
            ) or []

            for item in low_stock_list:
                item['deficit'] = max(0, int(item['min_stock_threshold']) - int(item['active_stock']))

            summary = {
                'total_low_stock_medicines': len(low_stock_list),
                'total_deficit_units': sum(item['deficit'] for item in low_stock_list)
            }

        # 3. Expiring Soon Data
        elif tab == 'expiring_soon':
            target_date = today + timedelta(days=days_window)
            expiring_soon_list = query_db(
                """
                SELECT 
                    b.id, b.batch_number, b.current_quantity, b.expiry_date, b.unit_price, b.supplier,
                    (b.current_quantity * b.unit_price) AS value_at_risk,
                    m.name AS medicine_name, m.generic_name, m.dosage_form, m.strength, m.storage_rack,
                    c.name AS category_name
                FROM batches b
                JOIN medicines m ON b.medicine_id = m.id
                JOIN categories c ON m.category_id = c.id
                WHERE b.expiry_date >= %s AND b.expiry_date <= %s AND b.status = 'active' AND b.current_quantity > 0
                ORDER BY b.expiry_date ASC
                """,
                (today, target_date)
            ) or []

            for item in expiring_soon_list:
                item['expiry_info'] = calculate_expiry_status(item['expiry_date'], today)

            summary = {
                'total_batches': len(expiring_soon_list),
                'total_units': sum(int(item['current_quantity']) for item in expiring_soon_list),
                'total_value_at_risk': sum(float(item['value_at_risk'] or 0) for item in expiring_soon_list),
                'days_window': days_window
            }

        # 4. Medicine Usage / Consumption Data
        elif tab == 'usage':
            query = """
                SELECT 
                    u.id, u.quantity_used, u.department, u.patient_name, u.patient_id,
                    u.prescribed_by, u.reason, u.usage_date,
                    b.batch_number, b.expiry_date,
                    m.name AS medicine_name, m.generic_name, m.dosage_form,
                    usr.full_name AS dispensed_by_name
                FROM medicine_usage u
                JOIN batches b ON u.batch_id = b.id
                JOIN medicines m ON b.medicine_id = m.id
                JOIN users usr ON u.dispensed_by = usr.id
                WHERE 1=1
            """
            params = []
            if department:
                query += " AND u.department = %s"
                params.append(department)
            if from_date:
                query += " AND DATE(u.usage_date) >= %s"
                params.append(from_date)
            if to_date:
                query += " AND DATE(u.usage_date) <= %s"
                params.append(to_date)

            query += " ORDER BY u.usage_date DESC LIMIT 200"
            usage_list = query_db(query, tuple(params)) or []

            summary = {
                'total_dispensed_events': len(usage_list),
                'total_units_consumed': sum(int(item['quantity_used']) for item in usage_list)
            }

    except Exception as e:
        current_app.logger.error(f"Error generating report '{tab}': {e}")
        flash(f"Error fetching report: {e}", "danger")

    return render_template(
        'reports/index.html',
        active_tab=tab,
        summary=summary,
        expired_list=expired_list,
        low_stock_list=low_stock_list,
        expiring_soon_list=expiring_soon_list,
        usage_list=usage_list,
        days_window=days_window,
        selected_dept=department,
        from_date=from_date,
        to_date=to_date
    )


@reports_bp.route('/export/csv')
@login_required
def export_csv():
    """
    Generates and streams a downloadable CSV report.
    """
    today = date.today()
    report_type = request.args.get('type', 'expired').strip().lower()

    if report_type == 'expired':
        rows = query_db(
            """
            SELECT m.name, m.generic_name, c.name, b.batch_number, b.expiry_date,
                   b.current_quantity, b.unit_price, (b.current_quantity * b.unit_price), b.supplier, m.storage_rack
            FROM batches b
            JOIN medicines m ON b.medicine_id = m.id
            JOIN categories c ON m.category_id = c.id
            WHERE b.expiry_date < %s AND b.current_quantity > 0
            ORDER BY b.expiry_date DESC
            """,
            (today,)
        ) or []
        headers = [
            'Medicine Name', 'Generic Name', 'Category', 'Batch #', 'Expiry Date',
            'Expired Quantity', 'Unit Price ($)', 'Financial Loss ($)', 'Supplier', 'Storage Rack'
        ]
        data = [[r[k] for k in r] for r in rows]

    elif report_type == 'low_stock':
        rows = query_db(
            """
            SELECT m.name, m.generic_name, c.name, m.dosage_form, m.strength,
                   m.min_stock_threshold,
                   COALESCE(SUM(CASE WHEN b.expiry_date >= %s AND b.status = 'active' THEN b.current_quantity ELSE 0 END), 0) AS current_stock,
                   m.storage_rack
            FROM medicines m
            JOIN categories c ON m.category_id = c.id
            LEFT JOIN batches b ON m.id = b.medicine_id
            GROUP BY m.id, m.name, m.generic_name, c.name, m.dosage_form, m.strength, m.min_stock_threshold, m.storage_rack
            HAVING current_stock <= m.min_stock_threshold
            ORDER BY current_stock ASC
            """,
            (today,)
        ) or []
        headers = [
            'Medicine Name', 'Generic Name', 'Category', 'Dosage Form', 'Strength',
            'Min Stock Threshold', 'Current Active Stock', 'Storage Rack'
        ]
        data = [[r[k] for k in r] for r in rows]

    elif report_type == 'expiring_soon':
        days = int(request.args.get('days', 30))
        target_date = today + timedelta(days=days)
        rows = query_db(
            """
            SELECT m.name, m.generic_name, c.name, b.batch_number, b.expiry_date,
                   DATEDIFF(b.expiry_date, %s) AS days_left,
                   b.current_quantity, b.unit_price, (b.current_quantity * b.unit_price), b.supplier
            FROM batches b
            JOIN medicines m ON b.medicine_id = m.id
            JOIN categories c ON m.category_id = c.id
            WHERE b.expiry_date >= %s AND b.expiry_date <= %s AND b.status = 'active' AND b.current_quantity > 0
            ORDER BY b.expiry_date ASC
            """,
            (today, today, target_date)
        ) or []
        headers = [
            'Medicine Name', 'Generic Name', 'Category', 'Batch #', 'Expiry Date',
            'Days Remaining', 'Quantity at Risk', 'Unit Price ($)', 'Value at Risk ($)', 'Supplier'
        ]
        data = [[r[k] for k in r] for r in rows]

    elif report_type == 'usage':
        rows = query_db(
            """
            SELECT u.usage_date, m.name, m.generic_name, b.batch_number, u.quantity_used,
                   u.department, u.patient_name, u.patient_id, u.prescribed_by, u.reason, usr.full_name
            FROM medicine_usage u
            JOIN batches b ON u.batch_id = b.id
            JOIN medicines m ON b.medicine_id = m.id
            JOIN users usr ON u.dispensed_by = usr.id
            ORDER BY u.usage_date DESC
            LIMIT 1000
            """
        ) or []
        headers = [
            'Date & Time', 'Medicine Name', 'Generic Name', 'Batch #', 'Quantity Used',
            'Department', 'Patient Name', 'Patient ID', 'Prescribing Doctor', 'Reason / Indication', 'Dispensed By'
        ]
        data = [[r[k] for k in r] for r in rows]

    else:
        return Response("Invalid report type.", status=400)

    csv_content = generate_csv_string(headers, data)
    filename = f"meditrack_{report_type}_report_{today.strftime('%Y%m%d')}.csv"

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
