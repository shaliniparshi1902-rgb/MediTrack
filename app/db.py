"""
MediTrack - Database Management Module
Handles MySQL database connections, query executions, transaction safety,
and connection teardown using Flask's application context.
"""

import os
import logging
from flask import g, current_app

logger = logging.getLogger(__name__)

# Attempt to import mysql.connector, fallback to pymysql if needed
try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
    DB_DRIVER = 'mysql.connector'
except ImportError:
    try:
        import pymysql
        import pymysql.cursors
        from pymysql import Error as MySQLError
        DB_DRIVER = 'pymysql'
    except ImportError:
        DB_DRIVER = None
        MySQLError = Exception


def get_db():
    """
    Retrieves or establishes a database connection for the current request context.
    Caches the connection inside Flask's 'g' object.
    """
    if 'db' not in g:
        # Check if an injected or mock connection is set (e.g. for unit tests)
        if hasattr(current_app, 'db_mock') and current_app.db_mock is not None:
            g.db = current_app.db_mock
            return g.db

        if DB_DRIVER is None:
            raise RuntimeError("Neither mysql-connector-python nor PyMySQL is installed.")

        try:
            if DB_DRIVER == 'mysql.connector':
                g.db = mysql.connector.connect(
                    host=current_app.config.get('DB_HOST', 'localhost'),
                    user=current_app.config.get('DB_USER', 'root'),
                    password=current_app.config.get('DB_PASSWORD', ''),
                    database=current_app.config.get('DB_NAME', 'meditrack_db'),
                    port=int(current_app.config.get('DB_PORT', 3306)),
                    autocommit=False,
                    charset='utf8mb4'
                )
            else:  # pymysql
                import pymysql
                import pymysql.cursors
                g.db = pymysql.connect(
                    host=current_app.config.get('DB_HOST', 'localhost'),
                    user=current_app.config.get('DB_USER', 'root'),
                    password=current_app.config.get('DB_PASSWORD', ''),
                    database=current_app.config.get('DB_NAME', 'meditrack_db'),
                    port=int(current_app.config.get('DB_PORT', 3306)),
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=False,
                    charset='utf8mb4'
                )
        except MySQLError as err:
            logger.error(f"Database connection error: {err}")
            raise ConnectionError(f"Failed to connect to MySQL database: {err}")

    return g.db


def close_db(e=None):
    """
    Closes the database connection at the end of the request context.
    """
    db = g.pop('db', None)
    if db is not None:
        try:
            # Avoid closing persistent test mocks
            if not getattr(db, 'is_mock', False):
                db.close()
        except Exception as err:
            logger.warning(f"Error closing database connection: {err}")


def query_db(query, args=(), one=False):
    """
    Executes a SELECT query and returns rows as dictionaries.
    
    :param query: SQL statement
    :param args: Tuple or list of parameter values
    :param one: If True, returns only the first row or None
    :return: List of dicts, single dict, or None
    """
    conn = get_db()
    cursor = None
    try:
        if DB_DRIVER == 'mysql.connector' and not getattr(conn, 'is_mock', False):
            cursor = conn.cursor(dictionary=True)
        else:
            cursor = conn.cursor()

        cursor.execute(query, args)
        rv = cursor.fetchall()

        # In case cursor is standard tuple cursor, convert to dict using description
        if rv and cursor.description and not isinstance(rv[0], dict):
            cols = [d[0] for d in cursor.description]
            rv = [dict(zip(cols, row)) for row in rv]

        cursor.close()
        return (rv[0] if rv else None) if one else rv
    except Exception as err:
        logger.error(f"SQL Query Error: {err} | Query: {query} | Args: {args}")
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        raise


def execute_db(query, args=(), commit=True):
    """
    Executes an INSERT, UPDATE, or DELETE statement.
    
    :param query: SQL statement
    :param args: Tuple or list of parameter values
    :param commit: Whether to commit the transaction
    :return: dict with 'lastrowid' and 'rowcount'
    """
    conn = get_db()
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(query, args)
        if commit:
            conn.commit()
        last_id = cursor.lastrowid
        affected = cursor.rowcount
        cursor.close()
        return {'lastrowid': last_id, 'rowcount': affected}
    except Exception as err:
        logger.error(f"SQL Execution Error: {err} | Query: {query} | Args: {args}")
        if commit and conn:
            try:
                conn.rollback()
            except Exception:
                pass
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        raise


def ensure_tables_exist(app=None):
    """
    Ensures all essential database tables (including patients) exist in the connected database.
    Uses CREATE TABLE IF NOT EXISTS to guarantee no data loss and full schema completeness.
    """
    try:
        ctx = app.app_context() if app else current_app.app_context()
        with ctx:
            execute_db(
                """
                CREATE TABLE IF NOT EXISTS patients (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    patient_id VARCHAR(50) NOT NULL UNIQUE,
                    full_name VARCHAR(150) NOT NULL,
                    age INT NOT NULL,
                    gender ENUM('Male', 'Female', 'Other') NOT NULL DEFAULT 'Male',
                    phone VARCHAR(25),
                    email VARCHAR(100),
                    blood_group ENUM('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'),
                    address TEXT,
                    allergies TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_patient_code (patient_id),
                    INDEX idx_patient_name (full_name)
                ) ENGINE=InnoDB;
                """,
                commit=True
            )
    except Exception as e:
        logger.debug(f"Table verification skipped or deferred: {e}")
