import sqlite3
import os
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "khs_billing.db")

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL, -- Mobile Number (10 digits) or admin handle
        password_hash TEXT DEFAULT '',
        full_name TEXT NOT NULL,
        role TEXT NOT NULL, -- 'T1' (Super Admin), 'T2' (Admin), 'T3' (Front Desk)
        phone TEXT,
        totp_secret TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Migration for existing database
    cursor.execute("PRAGMA table_info(users)")
    cols = [col[1] for col in cursor.fetchall()]
    if 'totp_secret' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT DEFAULT ''")

    # OTP Table (For Mobile Number + OTP Login)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS otps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mobile TEXT NOT NULL,
        otp_code TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        is_used INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Fee Structures Master (Set by T1 & T2)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fee_structures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_name TEXT NOT NULL, -- e.g. "PP1", "PP2", "1st", "2nd"..."10th"
        student_type TEXT NOT NULL DEFAULT 'Day Scholar', -- 'Day Scholar' or 'Residential'
        term_name TEXT NOT NULL,  -- 'Term 1', 'Term 2', 'Term 3' or 'Annual'
        tuition_fee REAL NOT NULL DEFAULT 0.0,
        activity_fee REAL NOT NULL DEFAULT 0.0,
        exam_fee REAL NOT NULL DEFAULT 0.0,
        residential_fee REAL NOT NULL DEFAULT 0.0,
        default_transport_fee REAL NOT NULL DEFAULT 0.0,
        total_base_fee REAL NOT NULL DEFAULT 0.0,
        updated_by TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(class_name, student_type, term_name)
    );
    """)

    # 3. Students Table (Admission records)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admission_no TEXT UNIQUE NOT NULL,
        roll_no TEXT,
        student_name TEXT NOT NULL,
        gender TEXT,
        class_name TEXT NOT NULL,
        section TEXT DEFAULT 'A',
        academic_year TEXT DEFAULT '2026-2027',
        student_type TEXT NOT NULL, -- 'Day Scholar' or 'Residential'
        has_transport INTEGER DEFAULT 0,
        transport_fee REAL DEFAULT 0.0,
        bus_route TEXT,
        parent_name TEXT NOT NULL,
        parent_phone TEXT NOT NULL,
        parent_email TEXT,
        address TEXT,
        standard_fee REAL NOT NULL DEFAULT 0.0, -- Base fee before discount
        discount_amount REAL NOT NULL DEFAULT 0.0,
        final_agreed_fee REAL NOT NULL DEFAULT 0.0, -- standard_fee + transport_fee - discount
        discount_status TEXT DEFAULT 'None', -- 'None', 'Pending', 'Approved', 'Rejected'
        admission_date TEXT NOT NULL,
        created_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 4. Discount Requests (T3 requests -> T1/T2 approves)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS discount_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        admission_no TEXT,
        student_name TEXT,
        class_name TEXT,
        standard_fee REAL NOT NULL,
        requested_discount REAL NOT NULL,
        reason TEXT,
        requested_by TEXT NOT NULL, -- T3 staff username
        status TEXT DEFAULT 'Pending', -- 'Pending', 'Approved', 'Rejected'
        approved_by TEXT, -- T1 or T2 username
        approved_discount REAL DEFAULT 0.0,
        admin_remarks TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        actioned_at TEXT,
        FOREIGN KEY (student_id) REFERENCES students(id)
    );
    """)

    # 4b. Admission Change & Cancellation Requests (T3 requests -> T1/T2 approves)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admission_change_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        admission_no TEXT NOT NULL,
        request_type TEXT NOT NULL, -- 'MODIFY_DETAILS' or 'CANCEL_ADMISSION'
        current_data TEXT NOT NULL, -- JSON snapshot of current student state
        proposed_data TEXT NOT NULL, -- JSON snapshot of proposed modified state (or cancellation meta)
        reason TEXT NOT NULL,
        requested_by TEXT NOT NULL,
        status TEXT DEFAULT 'Pending', -- 'Pending', 'Approved', 'Rejected'
        admin_remarks TEXT,
        reviewed_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        reviewed_at TEXT,
        FOREIGN KEY (student_id) REFERENCES students(id)
    );
    """)

    # 4c. Bulk Excel Import Approval Batches (T3 uploads -> Admin reviews & approves)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bulk_import_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT NOT NULL,
        total_rows INTEGER NOT NULL DEFAULT 0,
        valid_rows INTEGER NOT NULL DEFAULT 0,
        student_data_json TEXT NOT NULL, -- JSON array of parsed student records
        uploaded_by TEXT NOT NULL,
        status TEXT DEFAULT 'Pending', -- 'Pending', 'Approved', 'Rejected'
        admin_remarks TEXT,
        reviewed_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        reviewed_at TEXT
    );
    """)

    # Ensure status and branch columns exist in students (e.g. Active, Cancelled)
    cursor.execute("PRAGMA table_info(students)")
    student_cols = [col[1] for col in cursor.fetchall()]
    if 'status' not in student_cols:
        cursor.execute("ALTER TABLE students ADD COLUMN status TEXT DEFAULT 'Active'")
    if 'branch' not in student_cols:
        cursor.execute("ALTER TABLE students ADD COLUMN branch TEXT DEFAULT 'Branch 1'")

    # 5. Payments & Receipts (Flexible Installments)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_no TEXT UNIQUE NOT NULL, -- e.g. KHS-2026-0001
        student_id INTEGER NOT NULL,
        admission_no TEXT NOT NULL,
        branch TEXT DEFAULT 'Branch 1',
        installment_no INTEGER NOT NULL DEFAULT 1,
        installment_label TEXT, -- e.g. "1st Installment (At Admission)"
        total_agreed_fee REAL NOT NULL,
        previously_paid REAL NOT NULL DEFAULT 0.0,
        amount_paid REAL NOT NULL,
        balance_due REAL NOT NULL,
        payment_mode TEXT NOT NULL, -- 'Cash', 'UPI', 'Cheque', 'Bank Transfer'
        transaction_ref TEXT, -- UPI UTR / Cheque No
        collected_by TEXT NOT NULL, -- Front desk username
        payment_date TEXT NOT NULL, -- YYYY-MM-DD HH:MM
        receipt_token TEXT UNIQUE NOT NULL, -- For 48hr secure parent download
        token_expires_at TEXT NOT NULL,
        sms_sent INTEGER DEFAULT 0,
        admin_alerted INTEGER DEFAULT 0,
        notes TEXT,
        FOREIGN KEY (student_id) REFERENCES students(id)
    );
    """)

    cursor.execute("PRAGMA table_info(payments)")
    payment_cols = [col[1] for col in cursor.fetchall()]
    if 'branch' not in payment_cols:
        cursor.execute("ALTER TABLE payments ADD COLUMN branch TEXT DEFAULT 'Branch 1'")

    # 5b. Offline-to-Online Sync Queue (Outbox Pattern)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sync_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL, -- 'student', 'payment', 'discount_request'
        entity_id TEXT NOT NULL,   -- admission_no or receipt_no
        operation TEXT NOT NULL,   -- 'INSERT', 'UPDATE', 'DELETE'
        payload_json TEXT NOT NULL,
        branch TEXT NOT NULL,      -- 'Branch 1' or 'Branch 2'
        sync_status TEXT DEFAULT 'pending', -- 'pending', 'synced', 'failed'
        sync_attempts INTEGER DEFAULT 0,
        last_error TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        synced_at TEXT
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_status ON sync_queue(sync_status);")

    # 6. Seed Default Users if not present
    cursor.execute("SELECT COUNT(*) FROM users;")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("""
        INSERT INTO users (username, password_hash, full_name, role, phone)
        VALUES (?, ?, ?, ?, ?);
        """, [
            ('superadmin', 'admin123', 'Super Administrator', 'T1', '9876543210'),
            ('admin', 'admin123', 'Principal / School Admin', 'T2', '9876543211'),
            ('frontdesk', 'desk123', 'KHS Billing Desk', 'T3', '9876543212')
        ])

    # 7. Seed Default Fee Master if empty
    cursor.execute("SELECT COUNT(*) FROM fee_structures;")
    if cursor.fetchone()[0] == 0:
        classes = [
            ("PP1", 20000, 2000, 1000, 15000),
            ("PP2", 22000, 2000, 1000, 15000),
            ("Class 1", 26000, 2500, 1500, 18000),
            ("Class 2", 28000, 2500, 1500, 18000),
            ("Class 3", 30000, 2500, 1500, 18000),
            ("Class 4", 32000, 2500, 1500, 18000),
            ("Class 5", 35000, 3000, 2000, 20000),
            ("Class 6", 38000, 3000, 2000, 20000),
            ("Class 7", 40000, 3000, 2000, 20000),
            ("Class 8", 44000, 3500, 2500, 22000),
            ("Class 9", 48000, 3500, 2500, 25000),
            ("Class 10", 52000, 4000, 3000, 25000),
        ]
        for cname, tuition, act, exam, res in classes:
            # Day Scholar
            tot_day = tuition + act + exam
            cursor.execute("""
            INSERT OR IGNORE INTO fee_structures (class_name, student_type, term_name, tuition_fee, activity_fee, exam_fee, residential_fee, total_base_fee, updated_by)
            VALUES (?, 'Day Scholar', 'Annual', ?, ?, ?, 0.0, ?, 'system');
            """, (cname, tuition, act, exam, tot_day))
            
            # Residential
            tot_res = tuition + act + exam + res
            cursor.execute("""
            INSERT OR IGNORE INTO fee_structures (class_name, student_type, term_name, tuition_fee, activity_fee, exam_fee, residential_fee, total_base_fee, updated_by)
            VALUES (?, 'Residential', 'Annual', ?, ?, ?, ?, ?, 'system');
            """, (cname, tuition, act, exam, res, tot_res))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("KHS Billing Database initialized successfully.")
