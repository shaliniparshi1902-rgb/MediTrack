-- =============================================================================
-- Migration: Add Patients Table to Existing MediTrack Database
-- Run this script to add the patients table without dropping any existing data.
-- =============================================================================

USE meditrack_db;

-- 1. Create Patients Table if it does not already exist
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

-- 2. Populate with standard baseline patients (Insert Ignore avoids duplicates)
INSERT IGNORE INTO patients (patient_id, full_name, age, gender, phone, email, blood_group, address, allergies) VALUES
('PAT-10021', 'John Miller', 42, 'Male', '+1-555-0142', 'john.miller@email.com', 'O+', '45 Elm Street, Springfield', 'Penicillin, Amoxicillin'),
('PAT-10045', 'Emily Davis', 29, 'Female', '+1-555-0188', 'emily.davis@email.com', 'A+', '128 Maple Avenue, Riverdale', 'None reported'),
('PAT-09941', 'Robert Wilson', 65, 'Male', '+1-555-0231', 'robert.wilson@email.com', 'B+', '77 Oak Lane, Hill Valley', 'Aspirin, NSAIDs'),
('PAT-10089', 'Michael Brown', 51, 'Male', '+1-555-0377', 'mbrown@email.com', 'AB-', '210 Pine Road, Metro City', 'Sulfa drugs'),
('PAT-10092', 'Sophia Martinez', 34, 'Female', '+1-555-0492', 'sophia.m@email.com', 'O-', '59 Cedar Boulevard, Gotham', 'None reported');

-- 3. Backfill any existing patients already recorded in medicine_usage
INSERT IGNORE INTO patients (patient_id, full_name, age, gender, allergies)
SELECT DISTINCT 
    patient_id, 
    patient_name, 
    30 AS age, 
    'Male' AS gender, 
    'None reported' AS allergies
FROM medicine_usage
WHERE patient_id IS NOT NULL 
  AND patient_id != '' 
  AND patient_name IS NOT NULL
  AND patient_id NOT IN (SELECT patient_id FROM patients);
