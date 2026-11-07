-- =============================================================================
-- MediTrack - Smart Hospital Medicine Inventory and Expiry Management System
-- Database Schema (MySQL 8.0+)
-- =============================================================================

CREATE DATABASE IF NOT EXISTS meditrack_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE meditrack_db;

-- -----------------------------------------------------------------------------
-- 1. Users Table (Administrators and Pharmacists)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    role ENUM('admin', 'pharmacist') NOT NULL DEFAULT 'pharmacist',
    status ENUM('active', 'inactive') NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_username (username),
    INDEX idx_user_role (role)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 2. Medicine Categories Table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_category_name (name)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 3. Medicines Master Table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS medicines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NOT NULL,
    name VARCHAR(150) NOT NULL,
    generic_name VARCHAR(150) NOT NULL,
    dosage_form ENUM('Tablet', 'Capsule', 'Injection', 'Syrup', 'IV Fluid', 'Ointment', 'Inhaler', 'Drops') NOT NULL DEFAULT 'Tablet',
    strength VARCHAR(50) NOT NULL,
    manufacturer VARCHAR(150),
    min_stock_threshold INT NOT NULL DEFAULT 20,
    storage_rack VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    INDEX idx_medicine_name (name),
    INDEX idx_medicine_generic (generic_name),
    INDEX idx_medicine_category (category_id)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 4. Medicine Batches Table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS batches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    medicine_id INT NOT NULL,
    batch_number VARCHAR(50) NOT NULL UNIQUE,
    initial_quantity INT NOT NULL,
    current_quantity INT NOT NULL DEFAULT 0,
    mfg_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    supplier VARCHAR(150),
    status ENUM('active', 'quarantined', 'depleted') NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (medicine_id) REFERENCES medicines(id) ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX idx_batch_number (batch_number),
    INDEX idx_batch_expiry (expiry_date),
    INDEX idx_batch_quantity (current_quantity),
    INDEX idx_batch_status (status)
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 5. Patients Table
-- -----------------------------------------------------------------------------
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

-- -----------------------------------------------------------------------------
-- 6. Medicine Usage / Dispensing Tracking Table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS medicine_usage (
    id INT AUTO_INCREMENT PRIMARY KEY,
    batch_id INT NOT NULL,
    quantity_used INT NOT NULL,
    department ENUM('Emergency', 'ICU', 'General Ward', 'OPD', 'Surgery', 'Pediatrics', 'Cardiology') NOT NULL DEFAULT 'OPD',
    patient_name VARCHAR(150),
    patient_id VARCHAR(50),
    prescribed_by VARCHAR(100),
    reason VARCHAR(255),
    dispensed_by INT NOT NULL,
    usage_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (batch_id) REFERENCES batches(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (dispensed_by) REFERENCES users(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    INDEX idx_usage_date (usage_date),
    INDEX idx_usage_department (department),
    INDEX idx_usage_batch (batch_id)
) ENGINE=InnoDB;
