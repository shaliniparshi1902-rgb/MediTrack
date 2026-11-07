-- =============================================================================
-- MediTrack - Sample Seed Data for Demonstration & Evaluation
-- =============================================================================

USE meditrack_db;

-- -----------------------------------------------------------------------------
-- 1. Seed Users (Default Credentials)
-- Admin: username 'admin', password 'admin123'
-- Pharmacist: username 'pharmacist', password 'pharma123'
-- -----------------------------------------------------------------------------
INSERT INTO users (id, username, password_hash, full_name, email, role, status) VALUES
(1, 'admin', 'scrypt:32768:8:1$1adB1iUcrYQC92ef$521a6f904612c309fe2f0f446a10557c5da0496296638784c230c6d82b4322b0293597b9f89c6c937cea2a8011349080009ef0db3a94d080f6e3a36ba287a35c', 'Dr. Sarah Johnson', 'admin@meditrack.hospital', 'admin', 'active'),
(2, 'pharmacist', 'scrypt:32768:8:1$Uh7MQ8fGfxoMRx8Z$c18b60f05519cd1f10eca78eb902f1ca711321ca9c797f1b796790eee7fd0099759c68f460829af7195fc75ed140c8fd6380e245831edd5febe17e04f1ddd5d9', 'Alex Patel', 'pharmacist@meditrack.hospital', 'pharmacist', 'active')
ON DUPLICATE KEY UPDATE username=VALUES(username);

-- -----------------------------------------------------------------------------
-- 2. Seed Categories
-- -----------------------------------------------------------------------------
INSERT INTO categories (id, name, description) VALUES
(1, 'Antibiotics', 'Broad-spectrum and targeted antibacterial medications'),
(2, 'Analgesics & Antipyretics', 'Pain management and fever reduction drugs'),
(3, 'Cardiovascular', 'Heart medications, anti-hypertensives, and anti-arrhythmics'),
(4, 'Emergency & Critical Care', 'Fast-acting emergency resuscitation and life-support drugs'),
(5, 'Gastrointestinal', 'Acid reducers, anti-emetics, and GI tract treatments'),
(6, 'Respiratory', 'Bronchodilators, inhalers, and anti-asthmatic agents'),
(7, 'IV Fluids & Electrolytes', 'Intravenous rehydration and electrolyte maintenance solutions')
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- -----------------------------------------------------------------------------
-- 3. Seed Medicines
-- -----------------------------------------------------------------------------
INSERT INTO medicines (id, category_id, name, generic_name, dosage_form, strength, manufacturer, min_stock_threshold, storage_rack) VALUES
(1, 2, 'Dolo-650', 'Paracetamol', 'Tablet', '650 mg', 'Micro Labs Ltd', 50, 'Rack A-1'),
(2, 1, 'Augmentin 625 Duo', 'Amoxicillin + Clavulanic Acid', 'Tablet', '625 mg', 'GlaxoSmithKline', 30, 'Rack A-3'),
(3, 1, 'Monocef 1g', 'Ceftriaxone Sodium', 'Injection', '1 g', 'Aristo Pharmaceuticals', 25, 'Rack B-2'),
(4, 4, 'Atropine Inj', 'Atropine Sulfate', 'Injection', '0.6 mg/ml', 'Neon Laboratories', 15, 'Emergency Crash Cart 1'),
(5, 5, 'Pan-40', 'Pantoprazole Sodium', 'Tablet', '40 mg', 'Alkem Laboratories', 40, 'Rack C-1'),
(6, 6, 'Asthalin Inhaler', 'Salbutamol Sulfate', 'Inhaler', '100 mcg/dose', 'Cipla Ltd', 15, 'Rack C-4'),
(7, 7, 'Normal Saline (0.9% NaCl)', 'Sodium Chloride', 'IV Fluid', '500 ml', 'Baxter Healthcare', 40, 'IV Storage Bay 2'),
(8, 3, 'Amlong 5', 'Amlodipine Besylate', 'Tablet', '5 mg', 'Cadila Healthcare', 30, 'Rack D-1'),
(9, 1, 'Azithral 500', 'Azithromycin', 'Tablet', '500 mg', 'Alembic Pharmaceuticals', 20, 'Rack A-4'),
(10, 4, 'Adrenaline Tartrate Inj', 'Epinephrine / Adrenaline', 'Injection', '1 mg/ml', 'Troikaa Pharma', 20, 'Emergency Crash Cart 2')
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- -----------------------------------------------------------------------------
-- 4. Seed Batches (Varied dates to test: Expired, Critical <30d, Warning <90d, Safe)
-- -----------------------------------------------------------------------------
INSERT INTO batches (id, medicine_id, batch_number, initial_quantity, current_quantity, mfg_date, expiry_date, unit_price, supplier, status) VALUES
-- Batch 1: Expired (Expired in Oct 2026)
(1, 1, 'DOL-2024-B1', 200, 45, '2024-10-01', '2026-10-15', 2.50, 'Apex Med Supplies', 'active'),
-- Batch 2: Safe (Expires in 2027)
(2, 1, 'DOL-2025-B2', 500, 380, '2025-05-01', '2027-11-30', 2.65, 'Apex Med Supplies', 'active'),
-- Batch 3: Critical Expiring Soon (< 30 days - e.g., 2026-11-20)
(3, 2, 'AUG-2024-09', 150, 18, '2024-11-01', '2026-11-20', 18.00, 'MedLife Pharma Dist', 'active'),
-- Batch 4: Safe (Expires 2027)
(4, 2, 'AUG-2025-04', 300, 240, '2025-04-10', '2027-04-10', 19.50, 'MedLife Pharma Dist', 'active'),
-- Batch 5: Low-Stock & Critical Expiring Soon (< 30 days - e.g., 2026-11-28)
(5, 3, 'MON-2024-77', 100, 8, '2024-11-15', '2026-11-28', 55.00, 'BioCare Distributors', 'active'),
-- Batch 6: Safe (Expires 2028)
(6, 3, 'MON-2025-12', 200, 175, '2025-06-01', '2028-05-30', 58.00, 'BioCare Distributors', 'active'),
-- Batch 7: Low-Stock (< 15 units)
(7, 4, 'ATR-2025-01', 50, 12, '2025-01-10', '2027-01-10', 32.00, 'Emergency Med Direct', 'active'),
-- Batch 8: Warning Window (Expires within 60-90 days - Jan 2027)
(8, 5, 'PAN-2025-X3', 250, 120, '2025-01-20', '2027-01-15', 7.50, 'Alkem Regional Depot', 'active'),
-- Batch 9: Expired (Expired in Aug 2026)
(9, 6, 'AST-2024-11', 80, 22, '2024-08-01', '2026-08-31', 120.00, 'Cipla Direct Agency', 'active'),
-- Batch 10: Safe (Expires 2027)
(10, 6, 'AST-2025-06', 100, 65, '2025-06-15', '2027-06-15', 125.00, 'Cipla Direct Agency', 'active'),
-- Batch 11: Safe (Expires 2027)
(11, 7, 'NS-2025-88', 400, 310, '2025-03-01', '2027-09-01', 45.00, 'Baxter Healthcare Supply', 'active'),
-- Batch 12: Safe (Expires 2028)
(12, 8, 'AML-2025-02', 150, 110, '2025-02-01', '2028-02-01', 4.00, 'Cadila Wholesalers', 'active'),
-- Batch 13: Low Stock (< 10 units)
(13, 9, 'AZI-2025-55', 100, 9, '2025-05-01', '2027-05-01', 22.00, 'Alembic Dist', 'active'),
-- Batch 14: Critical Expiring Soon (< 30 days - e.g., 2026-11-25)
(14, 10, 'ADR-2024-44', 50, 14, '2024-11-25', '2026-11-25', 40.00, 'Emergency Med Direct', 'active')
ON DUPLICATE KEY UPDATE batch_number=VALUES(batch_number);

-- -----------------------------------------------------------------------------
-- 5. Seed Patients
-- -----------------------------------------------------------------------------
INSERT INTO patients (id, patient_id, full_name, age, gender, phone, email, blood_group, address, allergies) VALUES
(1, 'PAT-10021', 'John Miller', 42, 'Male', '+1-555-0142', 'john.miller@email.com', 'O+', '45 Elm Street, Springfield', 'Penicillin, Amoxicillin'),
(2, 'PAT-10045', 'Emily Davis', 29, 'Female', '+1-555-0188', 'emily.davis@email.com', 'A+', '128 Maple Avenue, Riverdale', 'None reported'),
(3, 'PAT-09941', 'Robert Wilson', 65, 'Male', '+1-555-0231', 'robert.wilson@email.com', 'B+', '77 Oak Lane, Hill Valley', 'Aspirin, NSAIDs'),
(4, 'PAT-10089', 'Michael Brown', 51, 'Male', '+1-555-0377', 'mbrown@email.com', 'AB-', '210 Pine Road, Metro City', 'Sulfa drugs'),
(5, 'PAT-10092', 'Sophia Martinez', 34, 'Female', '+1-555-0492', 'sophia.m@email.com', 'O-', '59 Cedar Boulevard, Gotham', 'None reported')
ON DUPLICATE KEY UPDATE patient_id=VALUES(patient_id);

-- -----------------------------------------------------------------------------
-- 6. Seed Medicine Usage Logs
-- -----------------------------------------------------------------------------
INSERT INTO medicine_usage (id, batch_id, quantity_used, department, patient_name, patient_id, prescribed_by, reason, dispensed_by, usage_date) VALUES
(1, 2, 10, 'OPD', 'John Miller', 'PAT-10021', 'Dr. Ramesh Rao', 'High fever and bodily fatigue', 2, '2026-11-02 09:30:00'),
(2, 4, 6, 'General Ward', 'Emily Davis', 'PAT-10045', 'Dr. A. Sharma', 'Post-operative prophylaxis', 2, '2026-11-03 11:15:00'),
(3, 5, 2, 'ICU', 'Robert Wilson', 'PAT-09941', 'Dr. Sarah Johnson', 'Severe bacterial sepsis', 1, '2026-11-04 14:00:00'),
(4, 7, 1, 'Emergency', 'Michael Brown', 'PAT-10089', 'Dr. K. Nair', 'Acute bradycardia management', 1, '2026-11-05 16:45:00'),
(5, 11, 4, 'Surgery', 'Sophia Martinez', 'PAT-10092', 'Dr. T. Joseph', 'Intra-operative fluid maintenance', 2, '2026-11-06 10:20:00')
ON DUPLICATE KEY UPDATE patient_name=VALUES(patient_name);
