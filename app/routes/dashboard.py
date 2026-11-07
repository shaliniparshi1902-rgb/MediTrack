"""
MediTrack - Dashboard Blueprint
Provides inventory overview metrics, expiry warnings, low-stock alerts,
and analytics charts data for hospital administration.
"""

from datetime import date, timedelta
from flask import Blueprint, render_template, jsonify, session, current_app
from app.db import query_db
from app.utils.decorators import login_required
from app.utils.helpers import calculate_expiry_status

dashboard_bp = Blueprint('dashboard', __name__)


def get_dashboard_metrics(ref_date=None):
    """
    Computes key performance indicators for the hospital inventory.
    """
    today = ref_date or date.today()
    thirty_days = today + timedelta(days=30)

    # 1. Total Medicines Count
    med_res = query_db("SELECT COUNT(*) AS count FROM medicines", one=True)
    total_medicines = med_res['count'] if med_res else 0

    # 2. Total Available Stock (active and not expired)
    stock_res = query_db(
        """
        SELECT COALESCE(SUM(current_quantity), 0) AS total_stock
        FROM batches
        WHERE status = 'active' AND expiry_date >= %s AND current_quantity > 0
        """,
        (today,),
        one=True
    )
    total_stock = int(stock_res['total_stock']) if stock_res else 0

    # 3. Expired Batches (already past expiry date with remaining units)
    expired_res = query_db(
        """
        SELECT 
            COUNT(*) AS count,
            COALESCE(SUM(current_quantity), 0) AS units,
            COALESCE(SUM(current_quantity * unit_price), 0.0) AS loss_value
        FROM batches
        WHERE expiry_date < %s AND current_quantity > 0
        """,
        (today,),
        one=True
    )
    expired_count = expired_res['count'] if expired_res else 0
    expired_units = int(expired_res['units']) if expired_res else 0
    expired_loss = float(expired_res['loss_value']) if expired_res else 0.0

    # 4. Medicines Expiring Within 30 Days (Critical window)
    critical_res = query_db(
        """
        SELECT 
            COUNT(*) AS count,
            COALESCE(SUM(current_quantity), 0) AS units
        FROM batches
        WHERE expiry_date >= %s AND expiry_date <= %s AND status = 'active' AND current_quantity > 0
        """,
        (today, thirty_days),
        one=True
    )
    critical_count = critical_res['count'] if critical_res else 0
    critical_units = int(critical_res['units']) if critical_res else 0

    # 5. Low-Stock Medicines (Aggregate unexpired stock <= min_stock_threshold)
    low_stock_query = """
        SELECT m.id, m.name, m.generic_name, m.min_stock_threshold,
               COALESCE(SUM(CASE WHEN b.expiry_date >= %s AND b.status = 'active' THEN b.current_quantity ELSE 0 END), 0) AS current_stock
        FROM medicines m
        LEFT JOIN batches b ON m.id = b.medicine_id
        GROUP BY m.id, m.name, m.generic_name, m.min_stock_threshold
        HAVING current_stock <= m.min_stock_threshold
    """
    low_stock_list = query_db(low_stock_query, (today,)) or []
    low_stock_count = len(low_stock_list)

    # 6. Critical Batches Alert List (Top 5 batches expiring soonest)
    urgent_batches = query_db(
        """
        SELECT b.id, b.batch_number, b.current_quantity, b.expiry_date, m.storage_rack,
               m.name AS medicine_name, m.generic_name, c.name AS category_name
        FROM batches b
        JOIN medicines m ON b.medicine_id = m.id
        JOIN categories c ON m.category_id = c.id
        WHERE b.expiry_date >= %s AND b.expiry_date <= %s AND b.status = 'active' AND b.current_quantity > 0
        ORDER BY b.expiry_date ASC
        LIMIT 5
        """,
        (today, thirty_days)
    ) or []

    for b in urgent_batches:
        b['status_info'] = calculate_expiry_status(b['expiry_date'], today)

    # 7. Category Distribution (for chart)
    category_chart = query_db(
        """
        SELECT c.name, COUNT(m.id) AS medicine_count
        FROM categories c
        LEFT JOIN medicines m ON c.id = m.category_id
        GROUP BY c.id, c.name
        ORDER BY medicine_count DESC
        """
    ) or []

    # 8. Department Usage Breakdown (for chart)
    dept_chart = query_db(
        """
        SELECT department, COALESCE(SUM(quantity_used), 0) AS total_units
        FROM medicine_usage
        GROUP BY department
        ORDER BY total_units DESC
        """
    ) or []

    return {
        'total_medicines': total_medicines,
        'total_stock': total_stock,
        'expired_count': expired_count,
        'expired_units': expired_units,
        'expired_loss': expired_loss,
        'critical_count': critical_count,
        'critical_units': critical_units,
        'low_stock_count': low_stock_count,
        'low_stock_items': low_stock_list[:5],
        'urgent_batches': urgent_batches,
        'category_chart': category_chart,
        'dept_chart': dept_chart
    }


@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@login_required
def index():
    """
    Renders main hospital inventory dashboard with KPI metrics,
    expiry warnings, and analytics charts.
    """
    try:
        metrics = get_dashboard_metrics()
    except Exception as e:
        current_app.logger.error(f"Error fetching dashboard metrics: {e}")
        metrics = {
            'total_medicines': 0,
            'total_stock': 0,
            'expired_count': 0,
            'expired_units': 0,
            'expired_loss': 0.0,
            'critical_count': 0,
            'critical_units': 0,
            'low_stock_count': 0,
            'low_stock_items': [],
            'urgent_batches': [],
            'category_chart': [],
            'dept_chart': []
        }

    return render_template('dashboard/index.html', metrics=metrics)


@dashboard_bp.route('/dashboard/api/chart-data')
@login_required
def chart_data_api():
    """
    API endpoint returning JSON serialized chart data for Chart.js.
    """
    metrics = get_dashboard_metrics()
    return jsonify({
        'categories': {
            'labels': [row['name'] for row in metrics['category_chart']],
            'data': [row['medicine_count'] for row in metrics['category_chart']]
        },
        'departments': {
            'labels': [row['department'] for row in metrics['dept_chart']],
            'data': [int(row['total_units']) for row in metrics['dept_chart']]
        }
    })
