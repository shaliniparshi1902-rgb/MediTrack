"""
MediTrack - Hospital Inventory Utility Functions
Contains expiry status calculation, FEFO (First Expiry, First Out) allocation,
low-stock detection, and CSV formatting helpers.
"""

from datetime import date, datetime
import csv
import io
import logging

logger = logging.getLogger(__name__)


def parse_date(value):
    """
    Safely parses an input value into a datetime.date object.
    Supports datetime.date, datetime.datetime, and 'YYYY-MM-DD' strings.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        value = value.strip()
        for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%Y-%m-%d %H:%M:%S'):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    raise ValueError(f"Unable to parse date from value: {value}")


def calculate_expiry_status(expiry_date, reference_date=None):
    """
    Determines the shelf-life status of a medicine batch.

    Thresholds:
    - Expired: expiry_date < today
    - Critical: expires within 30 days
    - Warning: expires between 31 and 90 days
    - Safe: expires in > 90 days

    :param expiry_date: date, datetime, or 'YYYY-MM-DD' string
    :param reference_date: optional baseline date (defaults to date.today())
    :return: dict with status, days_left, badge_class, label
    """
    try:
        exp = parse_date(expiry_date)
        today = reference_date or date.today()
        days_left = (exp - today).days

        if days_left < 0:
            return {
                'status': 'expired',
                'days_left': days_left,
                'badge_class': 'danger',
                'label': f'Expired ({abs(days_left)}d ago)' if days_left != 0 else 'Expired Today'
            }
        elif days_left <= 30:
            return {
                'status': 'critical',
                'days_left': days_left,
                'badge_class': 'warning',
                'label': f'Critical ({days_left}d left)'
            }
        elif days_left <= 90:
            return {
                'status': 'warning',
                'days_left': days_left,
                'badge_class': 'info',
                'label': f'Expiring in {days_left}d'
            }
        else:
            return {
                'status': 'safe',
                'days_left': days_left,
                'badge_class': 'success',
                'label': f'Safe ({days_left}d left)'
            }
    except Exception as e:
        logger.error(f"Error calculating expiry status for {expiry_date}: {e}")
        return {
            'status': 'unknown',
            'days_left': 0,
            'badge_class': 'secondary',
            'label': 'Unknown'
        }


def is_low_stock(current_quantity, threshold=20):
    """
    Checks if stock quantity is below or equal to the minimum threshold.
    """
    try:
        qty = int(current_quantity) if current_quantity is not None else 0
        thresh = int(threshold) if threshold is not None else 20
        return qty <= thresh
    except (ValueError, TypeError):
        return False


def get_fefo_batches(batches, reference_date=None):
    """
    Implements FEFO (First Expiry, First Out) sorting.
    Filters out depleted, inactive, and already expired batches.
    Sorts non-expired active batches by expiry date (earliest first).

    :param batches: List of batch dicts with 'expiry_date', 'current_quantity', 'status'
    :param reference_date: Optional comparison date
    :return: List of eligible batches sorted in FEFO order
    """
    today = reference_date or date.today()
    eligible = []

    for b in batches:
        # Check active status
        if b.get('status') and b['status'].lower() != 'active':
            continue

        # Check positive available quantity
        qty = int(b.get('current_quantity', 0))
        if qty <= 0:
            continue

        # Parse expiry date
        try:
            exp = parse_date(b.get('expiry_date'))
        except (ValueError, TypeError):
            continue

        # Exclude already expired batches (Do not dispense expired drugs)
        if exp < today:
            continue

        batch_copy = dict(b)
        batch_copy['parsed_expiry'] = exp
        eligible.append(batch_copy)

    # Sort primarily by expiry date (ascending), secondarily by batch number
    eligible.sort(key=lambda x: (x['parsed_expiry'], str(x.get('batch_number', ''))))
    return eligible


def allocate_fefo_dispense(requested_qty, batches, reference_date=None):
    """
    Calculates batch-by-batch quantity deduction following FEFO policy.

    :param requested_qty: Total units required
    :param batches: Available batches for the medicine
    :param reference_date: Optional baseline date
    :return: dict with 'success', 'allocations' list, or error message
    """
    if requested_qty <= 0:
        return {'success': False, 'message': 'Requested quantity must be greater than zero.'}

    fefo_list = get_fefo_batches(batches, reference_date)
    total_available = sum(int(b.get('current_quantity', 0)) for b in fefo_list)

    if total_available < requested_qty:
        return {
            'success': False,
            'message': f'Insufficient unexpired stock. Requested: {requested_qty}, Available: {total_available}.',
            'available': total_available
        }

    remaining_needed = requested_qty
    allocations = []

    for b in fefo_list:
        if remaining_needed <= 0:
            break

        current_qty = int(b.get('current_quantity', 0))
        deduct = min(current_qty, remaining_needed)
        remaining_in_batch = current_qty - deduct

        allocations.append({
            'batch_id': b.get('id'),
            'batch_number': b.get('batch_number'),
            'expiry_date': str(b.get('parsed_expiry')),
            'deduct_quantity': deduct,
            'remaining_in_batch': remaining_in_batch
        })

        remaining_needed -= deduct

    return {
        'success': True,
        'total_dispensed': requested_qty,
        'allocations': allocations
    }


def generate_csv_string(headers, rows):
    """
    Generates a UTF-8 encoded CSV string from headers and rows.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return output.getvalue()
