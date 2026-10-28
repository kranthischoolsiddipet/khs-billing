import os
import json
import sqlite3
import requests
from datetime import datetime

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloud_sync_config.json")
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "khs_billing.db")

# Embedded fallback credentials for cloud database sync (Render / Cloud environment)
DEFAULT_TURSO_URL = "libsql://khs-billing-kranthischoolsiddipet.aws-ap-south-1.turso.io"
DEFAULT_TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTI0Mjk0NzQsImlkIjoiMDFhMTU1MTktNGQwMS03NGJkLTlkMjQtODEyZDAxNmRiYTg2Iiwia2lkIjoiUFRGaVdLU3ZndTFmS05kVUlsazJYMDdBR091eTVvU3pyQVYxX2hZUDN2NCIsInJpZCI6ImRlYjZlZGI4LTk2MTUtNDE3NC04ZTkxLTFkZTFmODg5ZDViZCJ9.k70_3KFb9jXiHOqme7MA9WHA7R00VfryQUfb6mx7Ng6z6u1U7BhzJuBcqFJKnpx6iTonZNI0CpPTsMxK1IguAQ"

def get_sync_config():
    # If environment variables are set (like on Render), use them automatically!
    env_db_url = os.environ.get("TURSO_DB_URL", "").strip()
    env_token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if env_db_url and env_token:
        return {
            "enabled": True,
            "provider": "turso_http",
            "db_url": env_db_url,
            "auth_token": env_token,
            "branch": "All",
            "auto_sync_interval_seconds": 20
        }

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                if data.get("db_url") and data.get("auth_token"):
                    return data
        except:
            pass

    # Fallback to default school Turso database
    return {
        "enabled": True,
        "provider": "turso_http",
        "db_url": DEFAULT_TURSO_URL,
        "auth_token": DEFAULT_TURSO_TOKEN,
        "branch": "All",
        "auto_sync_interval_seconds": 20
    }

def save_sync_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    return True

def normalize_turso_url(url: str) -> str:
    """Ensures url uses https:// and endpoints /v2/pipeline for Turso HTTP API"""
    u = url.strip()
    if u.startswith("libsql://"):
        u = "https://" + u[len("libsql://"):]
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    u = u.rstrip("/")
    if not u.endswith("/v2/pipeline"):
        u = u + "/v2/pipeline"
    return u

def pull_cloud_data_into_local_db(sync_users: bool = True):
    """
    Pulls fee_structures, students, payments, and logs from Turso Cloud Database into local SQLite.
    If sync_users is True, users list is synced and pruned to match the Cloud Database,
    while preserving active session_tokens on the current machine!
    """
    cfg = get_sync_config()
    if not cfg.get("enabled") or not cfg.get("db_url") or not cfg.get("auth_token"):
        return False, "Cloud sync not enabled"

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    try:
        # 1. Pull Users (Synchronize users and delete users that were removed in the Cloud)
        if sync_users:
            ok, res = execute_remote_turso_queries([{"sql": "SELECT id, username, password_hash, full_name, role, phone, is_active, totp_secret, session_token, COALESCE(can_promote, 0) FROM users;"}], cfg['db_url'], cfg['auth_token'])
            if ok and res.get('results'):
                rows = res['results'][0]['response']['result']['rows']
                remote_usernames = []
                for r in rows:
                    vals = [c.get('value') for c in r]
                    u_name = vals[1]
                    remote_usernames.append(u_name)
                    # Don't overwrite active session_token locally if cloud has empty string
                    cur.execute("""
                        INSERT INTO users (username, password_hash, full_name, role, phone, is_active, totp_secret, session_token, can_promote)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(username) DO UPDATE SET
                            password_hash=excluded.password_hash,
                            full_name=excluded.full_name,
                            role=excluded.role,
                            phone=excluded.phone,
                            is_active=excluded.is_active,
                            totp_secret=excluded.totp_secret,
                            can_promote=excluded.can_promote,
                            session_token=CASE 
                                WHEN excluded.session_token != '' THEN excluded.session_token 
                                ELSE users.session_token 
                            END;
                    """, vals[1:])

                # Prune local T3 staff users that no longer exist on Turso Cloud
                if remote_usernames:
                    placeholders = ','.join('?' * len(remote_usernames))
                    cur.execute(f"DELETE FROM users WHERE role = 'T3' AND username NOT IN ({placeholders})", remote_usernames)

        # 2. Pull Fee Structures
        ok, res = execute_remote_turso_queries([{"sql": "SELECT class_name, student_type, term_name, tuition_fee, activity_fee, exam_fee, residential_fee, default_transport_fee, total_base_fee FROM fee_structures;"}], cfg['db_url'], cfg['auth_token'])
        if ok and res.get('results'):
            rows = res['results'][0]['response']['result']['rows']
            for r in rows:
                vals = [c.get('value') for c in r]
                cur.execute("""
                    INSERT OR REPLACE INTO fee_structures (class_name, student_type, term_name, tuition_fee, activity_fee, exam_fee, residential_fee, default_transport_fee, total_base_fee)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, vals)

        # 3. Pull Students (Preserve existing student id by using UPDATE or INSERT)
        ok, res = execute_remote_turso_queries([{"sql": "SELECT admission_no, roll_no, student_name, branch, gender, class_name, section, academic_year, student_type, has_transport, transport_fee, bus_route, parent_name, parent_phone, parent_email, address, standard_fee, discount_amount, final_agreed_fee, discount_status, admission_date, created_by, status, COALESCE(previous_due, 0.0) FROM students;"}], cfg['db_url'], cfg['auth_token'])
        if ok and res.get('results'):
            rows = res['results'][0]['response']['result']['rows']
            for r in rows:
                vals = [c.get('value') for c in r]
                adm_no = vals[0]
                existing_s = cur.execute("SELECT id FROM students WHERE admission_no = ?", (adm_no,)).fetchone()
                if existing_s:
                    cur.execute("""
                        UPDATE students SET
                            roll_no = ?, student_name = ?, branch = ?, gender = ?, class_name = ?, section = ?,
                            academic_year = ?, student_type = ?, has_transport = ?, transport_fee = ?, bus_route = ?,
                            parent_name = ?, parent_phone = ?, parent_email = ?, address = ?, standard_fee = ?,
                            discount_amount = ?, final_agreed_fee = ?, discount_status = ?, admission_date = ?,
                            created_by = ?, status = ?, previous_due = ?
                        WHERE id = ?
                    """, vals[1:] + [existing_s[0]])
                else:
                    cur.execute("""
                        INSERT INTO students (admission_no, roll_no, student_name, branch, gender, class_name, section, academic_year, student_type, has_transport, transport_fee, bus_route, parent_name, parent_phone, parent_email, address, standard_fee, discount_amount, final_agreed_fee, discount_status, admission_date, created_by, status, previous_due)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, vals)

        # 4. Pull Payments
        ok, res = execute_remote_turso_queries([{"sql": "SELECT receipt_no, admission_no, branch, installment_no, installment_label, total_agreed_fee, previously_paid, amount_paid, balance_due, payment_mode, transaction_ref, collected_by, payment_date, receipt_token, token_expires_at, notes FROM payments;"}], cfg['db_url'], cfg['auth_token'])
        if ok and res.get('results'):
            rows = res['results'][0]['response']['result']['rows']
            for r in rows:
                vals = [c.get('value') for c in r]
                cur.execute("""
                    INSERT OR REPLACE INTO payments (receipt_no, student_id, admission_no, branch, installment_no, installment_label, total_agreed_fee, previously_paid, amount_paid, balance_due, payment_mode, transaction_ref, collected_by, payment_date, receipt_token, token_expires_at, notes)
                    VALUES (?, (SELECT id FROM students WHERE admission_no = ?), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [vals[0], vals[1], vals[1]] + vals[2:])

        # 5. Pull User Activity Logs
        try:
            ok, res = execute_remote_turso_queries([{"sql": "SELECT session_id, username, full_name, role, branch, action_type, action_details, entity_id, amount, timestamp, date_only, COALESCE(ip_address, ''), COALESCE(device_browser, '') FROM user_activity_logs;"}], cfg['db_url'], cfg['auth_token'])
            if ok and res.get('results'):
                rows = res['results'][0]['response']['result']['rows']
                for r in rows:
                    vals = [c.get('value') for c in r]
                    # Avoid duplicate activity logs
                    cur.execute("""
                        INSERT INTO user_activity_logs (session_id, username, full_name, role, branch, action_type, action_details, entity_id, amount, timestamp, date_only, ip_address, device_browser)
                        SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        WHERE NOT EXISTS (
                            SELECT 1 FROM user_activity_logs 
                            WHERE session_id = ? AND timestamp = ? AND action_type = ?
                        )
                    """, vals + [vals[0], vals[9], vals[5]])
        except Exception as e_act:
            print(f"[PULL ACTIVITY LOGS NOTICE]: {e_act}")

        # 6. Pull IP Access Logs
        try:
            ok, res = execute_remote_turso_queries([{"sql": "SELECT ip_address, endpoint, method, COALESCE(device_browser, ''), COALESCE(username, 'Visitor / Public'), status_code, timestamp, date_only FROM ip_access_logs ORDER BY id DESC LIMIT 500;"}], cfg['db_url'], cfg['auth_token'])
            if ok and res.get('results'):
                rows = res['results'][0]['response']['result']['rows']
                for r in rows:
                    vals = [c.get('value') for c in r]
                    cur.execute("""
                        INSERT INTO ip_access_logs (ip_address, endpoint, method, device_browser, username, status_code, timestamp, date_only)
                        SELECT ?, ?, ?, ?, ?, ?, ?, ?
                        WHERE NOT EXISTS (
                            SELECT 1 FROM ip_access_logs 
                            WHERE ip_address = ? AND timestamp = ? AND endpoint = ?
                        )
                    """, vals + [vals[0], vals[6], vals[1]])
        except Exception as e_ip:
            print(f"[PULL IP LOGS NOTICE]: {e_ip}")

        # 7. Pull Admission Change Requests (Fee Revisions, Details Changes, Cancellations)
        try:
            ok, res = execute_remote_turso_queries([{"sql": "SELECT id, student_id, admission_no, request_type, current_data, proposed_data, reason, requested_by, status, admin_remarks, reviewed_by, created_at, reviewed_at FROM admission_change_requests ORDER BY id DESC LIMIT 200;"}], cfg['db_url'], cfg['auth_token'])
            if ok and res.get('results'):
                rows = res['results'][0]['response']['result']['rows']
                for r in rows:
                    vals = [c.get('value') for c in r]
                    cur.execute("""
                        INSERT INTO admission_change_requests (id, student_id, admission_no, request_type, current_data, proposed_data, reason, requested_by, status, admin_remarks, reviewed_by, created_at, reviewed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            status = excluded.status,
                            admin_remarks = excluded.admin_remarks,
                            reviewed_by = excluded.reviewed_by,
                            reviewed_at = excluded.reviewed_at;
                    """, vals)
        except Exception as e_acr:
            print(f"[PULL ADMISSION CHANGES NOTICE]: {e_acr}")

        # 8. Pull Discount Requests
        try:
            ok, res = execute_remote_turso_queries([{"sql": "SELECT id, student_id, admission_no, student_name, class_name, standard_fee, requested_discount, reason, requested_by, status, approved_by, approved_discount, admin_remarks, created_at, actioned_at FROM discount_requests ORDER BY id DESC LIMIT 200;"}], cfg['db_url'], cfg['auth_token'])
            if ok and res.get('results'):
                rows = res['results'][0]['response']['result']['rows']
                for r in rows:
                    vals = [c.get('value') for c in r]
                    cur.execute("""
                        INSERT INTO discount_requests (id, student_id, admission_no, student_name, class_name, standard_fee, requested_discount, reason, requested_by, status, approved_by, approved_discount, admin_remarks, created_at, actioned_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            status = excluded.status,
                            approved_by = excluded.approved_by,
                            approved_discount = excluded.approved_discount,
                            admin_remarks = excluded.admin_remarks,
                            actioned_at = excluded.actioned_at;
                    """, vals)
        except Exception as e_dr:
            print(f"[PULL DISCOUNT REQUESTS NOTICE]: {e_dr}")

        conn.commit()
        conn.close()
        return True, "Cloud pull complete"
    except Exception as e:
        conn.close()
        return False, str(e)

def normalize_turso_url(url: str):
    """Ensures url uses https:// and endpoints /v2/pipeline for Turso HTTP API"""
    u = url.strip()
    if u.startswith("libsql://"):
        u = "https://" + u[len("libsql://"):]
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    u = u.rstrip("/")
    if not u.endswith("/v2/pipeline"):
        u = u + "/v2/pipeline"
    return u

def execute_remote_turso_queries(queries: list, db_url: str, auth_token: str):
    """
    Executes multiple SQL statements atomically over Turso's standard v2 HTTP Pipeline API.
    Returns (success: bool, response_data or error_msg)
    """
    endpoint = normalize_turso_url(db_url)
    headers = {
        "Authorization": f"Bearer {auth_token.strip()}",
        "Content-Type": "application/json"
    }

    requests_payload = []
    for q in queries:
        sql = q["sql"]
        args = q.get("args", [])
        formatted_args = []
        for a in args:
            if a is None:
                formatted_args.append({"type": "null"})
            elif isinstance(a, int):
                formatted_args.append({"type": "integer", "value": str(a)})
            elif isinstance(a, float):
                formatted_args.append({"type": "float", "value": a})
            else:
                formatted_args.append({"type": "text", "value": str(a)})

        requests_payload.append({
            "type": "execute",
            "stmt": {
                "sql": sql,
                "args": formatted_args
            }
        })

    requests_payload.append({"type": "close"})

    payload = {"requests": requests_payload}

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=12)
        if resp.status_code == 200:
            return True, resp.json()
        return False, f"Cloud HTTP {resp.status_code}: {resp.text}"
    except Exception as e:
        return False, f"Cloud connection failed: {str(e)}"

def test_cloud_connection(db_url: str, auth_token: str):
    """Verifies that Turso HTTP endpoint responds and can execute SELECT 1"""
    success, res = execute_remote_turso_queries([{"sql": "SELECT 1 as test_val;"}], db_url, auth_token)
    if not success:
        return False, str(res)
    return True, "Successfully connected to Cloud Database!"

def init_remote_schema_if_needed(db_url: str, auth_token: str):
    """Initializes tables on the remote cloud database if they don't exist yet"""
    tables_sql = [
        {"sql": """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admission_no TEXT UNIQUE NOT NULL,
                roll_no TEXT,
                student_name TEXT NOT NULL,
                branch TEXT DEFAULT 'Branch 1',
                gender TEXT,
                class_name TEXT NOT NULL,
                section TEXT DEFAULT 'A',
                academic_year TEXT DEFAULT '2026-2027',
                student_type TEXT NOT NULL,
                has_transport INTEGER DEFAULT 0,
                transport_fee REAL DEFAULT 0.0,
                bus_route TEXT,
                parent_name TEXT NOT NULL,
                parent_phone TEXT NOT NULL,
                parent_email TEXT,
                address TEXT,
                standard_fee REAL NOT NULL DEFAULT 0.0,
                discount_amount REAL NOT NULL DEFAULT 0.0,
                final_agreed_fee REAL NOT NULL DEFAULT 0.0,
                discount_status TEXT DEFAULT 'None',
                admission_date TEXT NOT NULL,
                created_by TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'Active'
            );
        """},
        {"sql": """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_no TEXT UNIQUE NOT NULL,
                student_id INTEGER NOT NULL,
                admission_no TEXT NOT NULL,
                branch TEXT DEFAULT 'Branch 1',
                installment_no INTEGER NOT NULL DEFAULT 1,
                installment_label TEXT,
                total_agreed_fee REAL NOT NULL,
                previously_paid REAL NOT NULL DEFAULT 0.0,
                amount_paid REAL NOT NULL,
                balance_due REAL NOT NULL,
                payment_mode TEXT NOT NULL,
                transaction_ref TEXT,
                collected_by TEXT NOT NULL,
                payment_date TEXT NOT NULL,
                receipt_token TEXT UNIQUE NOT NULL,
                token_expires_at TEXT NOT NULL,
                sms_sent INTEGER DEFAULT 0,
                admin_alerted INTEGER DEFAULT 0,
                notes TEXT
            );
        """},
        {"sql": """
            CREATE TABLE IF NOT EXISTS discount_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                admission_no TEXT,
                student_name TEXT,
                class_name TEXT,
                standard_fee REAL NOT NULL,
                requested_discount REAL NOT NULL,
                reason TEXT,
                requested_by TEXT NOT NULL,
                status TEXT DEFAULT 'Pending',
                approved_by TEXT,
                approved_discount REAL DEFAULT 0.0,
                admin_remarks TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                actioned_at TEXT
            );
        """},
        {"sql": """
            CREATE TABLE IF NOT EXISTS user_activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                username TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                branch TEXT DEFAULT 'Branch 1',
                action_type TEXT NOT NULL,
                action_details TEXT,
                entity_id TEXT,
                amount REAL DEFAULT 0.0,
                timestamp TEXT NOT NULL,
                date_only TEXT NOT NULL,
                ip_address TEXT DEFAULT '',
                device_browser TEXT DEFAULT ''
            );
        """},
        {"sql": "ALTER TABLE user_activity_logs ADD COLUMN ip_address TEXT DEFAULT '';"},
        {"sql": "ALTER TABLE user_activity_logs ADD COLUMN device_browser TEXT DEFAULT '';"},
        {"sql": "ALTER TABLE users ADD COLUMN can_promote INTEGER DEFAULT 0;"},
        {"sql": "ALTER TABLE students ADD COLUMN previous_due REAL DEFAULT 0.0;"},
        {"sql": """
            CREATE TABLE IF NOT EXISTS ip_access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL,
                device_browser TEXT DEFAULT '',
                username TEXT DEFAULT 'Visitor / Public',
                status_code INTEGER DEFAULT 200,
                timestamp TEXT NOT NULL,
                date_only TEXT NOT NULL
            );
        """},
        {"sql": "CREATE INDEX IF NOT EXISTS idx_iplogs_date ON ip_access_logs(date_only);"},
        {"sql": "CREATE INDEX IF NOT EXISTS idx_iplogs_ip ON ip_access_logs(ip_address);"},
        {"sql": """
            CREATE TABLE IF NOT EXISTS admission_change_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                admission_no TEXT NOT NULL,
                request_type TEXT NOT NULL,
                current_data TEXT NOT NULL,
                proposed_data TEXT NOT NULL,
                reason TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                status TEXT DEFAULT 'Pending',
                admin_remarks TEXT,
                reviewed_by TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TEXT
            );
        """}
    ]
    return execute_remote_turso_queries(tables_sql, db_url, auth_token)

def queue_transaction_locally(entity_type: str, entity_id: str, operation: str, payload: dict, branch: str):
    """Appends dirty transaction to local sync_queue outbox for automatic transmission"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sync_queue (entity_type, entity_id, operation, payload_json, branch, sync_status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        """, (entity_type, entity_id, operation, json.dumps(payload), branch))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[SYNC QUEUE ERROR]: {e}")
        return False

def sync_user_session_token_direct(username: str, session_token: str):
    """Immediately updates user's session_token on Turso Cloud without waiting for outbox queue"""
    cfg = get_sync_config()
    if not cfg.get("enabled") or not cfg.get("db_url") or not cfg.get("auth_token"):
        return False
    try:
        sql = "UPDATE users SET session_token = ? WHERE username = ?;"
        args = [session_token.strip(), username.strip()]
        ok, res = execute_remote_turso_queries([{"sql": sql, "args": args}], cfg['db_url'], cfg['auth_token'])
        return ok
    except Exception as e:
        print(f"[SYNC TOKEN DIRECT ERROR]: {e}")
        return False

def sync_user_totp_secret_direct(username: str, totp_secret: str):
    """Immediately updates user's totp_secret on Turso Cloud so 2FA works across web and desktop without delay"""
    cfg = get_sync_config()
    if not cfg.get("enabled") or not cfg.get("db_url") or not cfg.get("auth_token"):
        return False
    try:
        sql = "UPDATE users SET totp_secret = ? WHERE username = ?;"
        args = [totp_secret.strip(), username.strip()]
        ok, res = execute_remote_turso_queries([{"sql": sql, "args": args}], cfg['db_url'], cfg['auth_token'])
        return ok
    except Exception as e:
        print(f"[SYNC TOTP DIRECT ERROR]: {e}")
        return False

def sync_user_password_direct(username: str, password_hash: str):
    """Immediately updates user's password_hash (PIN) on Turso Cloud without waiting for outbox queue"""
    cfg = get_sync_config()
    if not cfg.get("enabled") or not cfg.get("db_url") or not cfg.get("auth_token"):
        return False
    try:
        sql = "UPDATE users SET password_hash = ? WHERE username = ?;"
        args = [password_hash.strip(), username.strip()]
        ok, res = execute_remote_turso_queries([{"sql": sql, "args": args}], cfg['db_url'], cfg['auth_token'])
        return ok
    except Exception as e:
        print(f"[SYNC PIN DIRECT ERROR]: {e}")
        return False

def sync_fee_structure_direct(class_name: str, student_type: str, term_name: str, tuition_fee: float, activity_fee: float, exam_fee: float, residential_fee: float, default_transport_fee: float, total_base_fee: float, updated_by: str = "Admin"):
    """
    Synchronously updates fee structure on Turso Cloud Database!
    Prevents background cloud pulls from overwriting newly updated fee master rates.
    """
    cfg = get_sync_config()
    db_url = cfg.get("turso_db_url") or cfg.get("db_url") or DEFAULT_TURSO_URL
    auth_token = cfg.get("turso_auth_token") or cfg.get("auth_token") or DEFAULT_TURSO_TOKEN
    if not db_url or not auth_token:
        return False
    try:
        sql = """
            INSERT INTO fee_structures (
                class_name, student_type, term_name, tuition_fee, activity_fee, exam_fee,
                residential_fee, default_transport_fee, total_base_fee, updated_by, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(class_name, student_type, term_name) DO UPDATE SET
                tuition_fee = excluded.tuition_fee,
                activity_fee = excluded.activity_fee,
                exam_fee = excluded.exam_fee,
                residential_fee = excluded.residential_fee,
                default_transport_fee = excluded.default_transport_fee,
                total_base_fee = excluded.total_base_fee,
                updated_by = excluded.updated_by,
                updated_at = CURRENT_TIMESTAMP;
        """
        ok, res = execute_remote_turso_queries([{
            "sql": sql,
            "args": [
                class_name.strip(), student_type.strip(), term_name.strip(),
                float(tuition_fee), float(activity_fee), float(exam_fee),
                float(residential_fee), float(default_transport_fee),
                float(total_base_fee), updated_by.strip()
            ]
        }], db_url, auth_token)
        return ok
    except Exception as e:
        print(f"[SYNC FEE STRUCTURE DIRECT ERROR]: {e}")
        return False

def sync_student_agreed_fee_direct(admission_no: str, new_fee: float, calc_discount: float, request_id: int = None, approver_user: str = "admin", admin_remarks: str = ""):
    """
    Immediately and synchronously applies fee revision to Turso Cloud database!
    Ensures that when a background worker or web server pulls from cloud, the new fee is already committed,
    preventing any possibility of the balance reverting back to the old fee.
    """
    cfg = get_sync_config()
    if not cfg.get("enabled") or not cfg.get("db_url") or not cfg.get("auth_token"):
        return False
    try:
        queries = [
            {
                "sql": "UPDATE students SET final_agreed_fee = ?, discount_amount = ?, discount_status = 'Approved' WHERE admission_no = ?;",
                "args": [float(new_fee), float(calc_discount), admission_no.strip()]
            },
            {
                "sql": "UPDATE payments SET total_agreed_fee = ? WHERE admission_no = ?;",
                "args": [float(new_fee), admission_no.strip()]
            }
        ]
        if request_id:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            queries.append({
                "sql": "UPDATE admission_change_requests SET status = 'Approved', reviewed_by = ?, admin_remarks = ?, reviewed_at = ? WHERE id = ?;",
                "args": [approver_user.strip(), admin_remarks.strip(), now_str, int(request_id)]
            })
        ok, res = execute_remote_turso_queries(queries, cfg['db_url'], cfg['auth_token'])
        print(f"[DIRECT CLOUD FEE REVISION SYNC]: admission_no={admission_no}, new_fee={new_fee}, success={ok}")
        return ok
    except Exception as e:
        print(f"[SYNC FEE DIRECT ERROR]: {e}")
        return False

def sync_admission_change_request_direct(req_id: int, student_id: int, admission_no: str, request_type: str, current_data: str, proposed_data: str, reason: str, requested_by: str):
    """
    Immediately and synchronously pushes new admission change requests to Turso Cloud!
    Guarantees that pending approval queues and student governance history sync across all PCs instantly.
    """
    cfg = get_sync_config()
    if not cfg.get("enabled") or not cfg.get("db_url") or not cfg.get("auth_token"):
        return False
    try:
        sql = """
            INSERT INTO admission_change_requests (
                id, student_id, admission_no, request_type, current_data, proposed_data, reason, requested_by, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
            ON CONFLICT(id) DO UPDATE SET
                status = 'Pending',
                reason = excluded.reason;
        """
        args = [
            int(req_id), int(student_id), admission_no.strip(),
            request_type.strip(), current_data, proposed_data,
            reason.strip(), requested_by.strip()
        ]
        ok, res = execute_remote_turso_queries([{"sql": sql, "args": args}], cfg['db_url'], cfg['auth_token'])
        print(f"[DIRECT CLOUD ADMISSION CHANGE SYNC]: id={req_id}, admission_no={admission_no}, success={ok}")
        return ok
    except Exception as e:
        print(f"[SYNC ADMISSION CHANGE DIRECT ERROR]: {e}")
        return False

def sync_discount_request_direct(req_id: int, student_id: int, admission_no: str, student_name: str, class_name: str, standard_fee: float, requested_discount: float, reason: str, requested_by: str):
    """
    Immediately and synchronously pushes new admission discount requests to Turso Cloud!
    """
    cfg = get_sync_config()
    if not cfg.get("enabled") or not cfg.get("db_url") or not cfg.get("auth_token"):
        return False
    try:
        sql = """
            INSERT INTO discount_requests (
                id, student_id, admission_no, student_name, class_name, standard_fee, requested_discount, reason, requested_by, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
            ON CONFLICT(id) DO UPDATE SET
                status = 'Pending',
                reason = excluded.reason;
        """
        args = [
            int(req_id), int(student_id) if student_id else None, (admission_no or '').strip(),
            (student_name or '').strip(), (class_name or '').strip(),
            float(standard_fee or 0.0), float(requested_discount or 0.0),
            (reason or '').strip(), (requested_by or 'frontdesk').strip()
        ]
        ok, res = execute_remote_turso_queries([{"sql": sql, "args": args}], cfg['db_url'], cfg['auth_token'])
        print(f"[DIRECT CLOUD DISCOUNT REQUEST SYNC]: id={req_id}, student_name={student_name}, success={ok}")
        return ok
    except Exception as e:
        print(f"[SYNC DISCOUNT REQUEST DIRECT ERROR]: {e}")
        return False

def sync_discount_action_direct(req_id: int, action: str, approver_user: str, approved_discount: float, admin_remarks: str = ""):
    """
    Immediately and synchronously updates discount request status (Approved/Rejected) on Turso Cloud!
    Also synchronously updates the student's discount_amount, final_agreed_fee, and payments if the student is already admitted.
    """
    cfg = get_sync_config()
    if not cfg.get("enabled") or not cfg.get("db_url") or not cfg.get("auth_token"):
        return False
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        queries = [
            {
                "sql": """
                    UPDATE discount_requests 
                    SET status = ?, approved_by = ?, approved_discount = ?, admin_remarks = ?, actioned_at = ?
                    WHERE id = ?;
                """,
                "args": [
                    action.strip(), approver_user.strip(), float(approved_discount or 0.0),
                    (admin_remarks or '').strip(), now_str, int(req_id)
                ]
            }
        ]
        if action == 'Approved':
            # Check if this discount request is tied to an existing student in Turso cloud by admission_no
            queries.append({
                "sql": """
                    UPDATE students 
                    SET discount_amount = ?, final_agreed_fee = max(0.0, standard_fee - ?), discount_status = 'Approved'
                    WHERE admission_no = (SELECT admission_no FROM discount_requests WHERE id = ?);
                """,
                "args": [float(approved_discount or 0.0), float(approved_discount or 0.0), int(req_id)]
            })
            queries.append({
                "sql": """
                    UPDATE payments 
                    SET total_agreed_fee = (SELECT final_agreed_fee FROM students WHERE admission_no = (SELECT admission_no FROM discount_requests WHERE id = ?))
                    WHERE admission_no = (SELECT admission_no FROM discount_requests WHERE id = ?);
                """,
                "args": [int(req_id), int(req_id)]
            })
        elif action == 'Rejected':
            queries.append({
                "sql": """
                    UPDATE students 
                    SET discount_status = 'Rejected'
                    WHERE admission_no = (SELECT admission_no FROM discount_requests WHERE id = ?);
                """,
                "args": [int(req_id)]
            })

        ok, res = execute_remote_turso_queries(queries, cfg['db_url'], cfg['auth_token'])
        print(f"[DIRECT CLOUD DISCOUNT ACTION SYNC]: id={req_id}, action={action}, success={ok}")
        return ok
    except Exception as e:
        print(f"[SYNC DISCOUNT ACTION DIRECT ERROR]: {e}")
        return False

def push_local_outbox_to_cloud():
    """
    Pushes pending rows from sync_queue to Cloud Database via HTTP API.
    Marks them 'synced' on success.
    """
    cfg = get_sync_config()
    if not cfg.get("enabled") or not cfg.get("db_url") or not cfg.get("auth_token"):
        return {"status": "disabled", "synced": 0, "message": "Cloud sync is not enabled/configured."}

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    pending_items = cur.execute("""
        SELECT * FROM sync_queue WHERE sync_status = 'pending' ORDER BY id ASC LIMIT 50
    """).fetchall()

    if not pending_items:
        conn.close()
        return {"status": "up_to_date", "synced": 0, "message": "Everything is already synced!"}

    queries = []
    item_ids = []

    for item in pending_items:
        data = json.loads(item['payload_json'])
        op = item['operation']
        etype = item['entity_type']
        item_ids.append(item['id'])

        if etype == 'student' and op == 'INSERT':
            queries.append({
                "sql": """
                    INSERT OR REPLACE INTO students (
                        admission_no, roll_no, student_name, branch, gender, class_name, section,
                        academic_year, student_type, has_transport, transport_fee, bus_route,
                        parent_name, parent_phone, parent_email, address, standard_fee,
                        discount_amount, final_agreed_fee, discount_status, admission_date, created_by, status, previous_due
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                "args": [
                    data.get('admission_no'), data.get('roll_no', ''), data.get('student_name'),
                    data.get('branch', 'Branch 1'), data.get('gender', 'Male'), data.get('class_name'),
                    data.get('section', 'A'), data.get('academic_year', '2026-2027'), data.get('student_type', 'Day Scholar'),
                    1 if data.get('has_transport') else 0, float(data.get('transport_fee', 0.0)), data.get('bus_route', ''),
                    data.get('parent_name'), data.get('parent_phone'), data.get('parent_email', ''), data.get('address', ''),
                    float(data.get('standard_fee', 0.0)), float(data.get('discount_amount', 0.0)),
                    float(data.get('final_agreed_fee', 0.0)), data.get('discount_status', 'None'),
                    data.get('admission_date', datetime.now().strftime("%Y-%m-%d")),
                    data.get('created_by', 'frontdesk'), data.get('status', 'Active'),
                    float(data.get('previous_due', 0.0))
                ]
            })

        elif etype == 'student' and op == 'UPDATE':
            queries.append({
                "sql": """
                    UPDATE students SET
                        roll_no = COALESCE(NULLIF(?, ''), roll_no),
                        student_name = COALESCE(NULLIF(?, ''), student_name),
                        branch = COALESCE(NULLIF(?, ''), branch),
                        gender = COALESCE(NULLIF(?, ''), gender),
                        class_name = COALESCE(NULLIF(?, ''), class_name),
                        section = COALESCE(NULLIF(?, ''), section),
                        academic_year = COALESCE(NULLIF(?, ''), academic_year),
                        student_type = COALESCE(NULLIF(?, ''), student_type),
                        has_transport = CASE WHEN ? IS NOT NULL THEN ? ELSE has_transport END,
                        transport_fee = CASE WHEN ? IS NOT NULL THEN ? ELSE transport_fee END,
                        bus_route = COALESCE(?, bus_route),
                        parent_name = COALESCE(NULLIF(?, ''), parent_name),
                        parent_phone = COALESCE(NULLIF(?, ''), parent_phone),
                        parent_email = COALESCE(?, parent_email),
                        address = COALESCE(?, address),
                        standard_fee = CASE WHEN ? IS NOT NULL THEN ? ELSE standard_fee END,
                        discount_amount = CASE WHEN ? IS NOT NULL THEN ? ELSE discount_amount END,
                        final_agreed_fee = CASE WHEN ? IS NOT NULL THEN ? ELSE final_agreed_fee END,
                        discount_status = COALESCE(NULLIF(?, 'None'), discount_status),
                        admission_date = COALESCE(NULLIF(?, ''), admission_date),
                        created_by = COALESCE(NULLIF(?, ''), created_by),
                        status = COALESCE(NULLIF(?, ''), status),
                        previous_due = CASE WHEN ? IS NOT NULL THEN ? ELSE previous_due END
                    WHERE admission_no = ?
                """,
                "args": [
                    data.get('roll_no'), data.get('student_name'),
                    data.get('branch'), data.get('gender'), data.get('class_name'),
                    data.get('section'), data.get('academic_year'), data.get('student_type'),
                    1 if data.get('has_transport') else (0 if 'has_transport' in data else None),
                    1 if data.get('has_transport') else 0,
                    float(data['transport_fee']) if 'transport_fee' in data and data['transport_fee'] is not None else None,
                    float(data.get('transport_fee', 0.0)),
                    data.get('bus_route'),
                    data.get('parent_name'), data.get('parent_phone'), data.get('parent_email'), data.get('address'),
                    float(data['standard_fee']) if 'standard_fee' in data and data['standard_fee'] is not None else None,
                    float(data.get('standard_fee', 0.0)),
                    float(data['discount_amount']) if 'discount_amount' in data and data['discount_amount'] is not None else None,
                    float(data.get('discount_amount', 0.0)),
                    float(data['final_agreed_fee']) if 'final_agreed_fee' in data and data['final_agreed_fee'] is not None else None,
                    float(data.get('final_agreed_fee', 0.0)),
                    data.get('discount_status'),
                    data.get('admission_date'),
                    data.get('created_by'), data.get('status'),
                    float(data['previous_due']) if 'previous_due' in data and data['previous_due'] is not None else None,
                    float(data.get('previous_due', 0.0)),
                    data.get('admission_no')
                ]
            })

        elif etype == 'user_permission' and op == 'UPDATE':
            queries.append({
                "sql": "UPDATE users SET can_promote = ? WHERE id = ?;",
                "args": [int(data.get('can_promote', 0)), int(data.get('user_id', 0))]
            })

        elif etype == 'user_totp' and op == 'UPDATE':
            queries.append({
                "sql": "UPDATE users SET totp_secret = ? WHERE username = ? OR id = ?;",
                "args": [data.get('totp_secret', ''), data.get('username', ''), int(data.get('user_id', 0))]
            })

        elif etype == 'user_password' and op == 'UPDATE':
            queries.append({
                "sql": "UPDATE users SET password_hash = ? WHERE username = ? OR id = ?;",
                "args": [data.get('password_hash', ''), data.get('username', ''), int(data.get('user_id', 0))]
            })

        elif etype == 'user_account' and op == 'INSERT':
            queries.append({
                "sql": """
                    INSERT INTO users (username, password_hash, full_name, role, phone, is_active)
                    VALUES (?, '', ?, 'T3', ?, 1)
                    ON CONFLICT(username) DO UPDATE SET
                        full_name = excluded.full_name,
                        phone = excluded.phone,
                        is_active = 1;
                """,
                "args": [data.get('username'), data.get('full_name'), data.get('phone')]
            })

        elif etype == 'user_account' and op == 'UPDATE':
            queries.append({
                "sql": "UPDATE users SET full_name = ?, username = ?, phone = ? WHERE id = ? OR username = ?;",
                "args": [data.get('full_name'), data.get('username'), data.get('phone'), int(data.get('user_id', 0)), data.get('old_username', data.get('username'))]
            })

        elif etype == 'user_account' and op == 'DELETE':
            queries.append({
                "sql": "DELETE FROM users WHERE username = ? OR id = ?;",
                "args": [data.get('username'), int(data.get('user_id', 0))]
            })

        elif etype == 'user_status' and op == 'UPDATE':
            queries.append({
                "sql": "UPDATE users SET is_active = ? WHERE id = ? OR username = ?;",
                "args": [int(data.get('is_active', 1)), int(data.get('user_id', 0)), data.get('username', '')]
            })

        elif etype == 'payment' and op == 'INSERT':
            queries.append({
                "sql": """
                    INSERT OR REPLACE INTO payments (
                        receipt_no, student_id, admission_no, branch, installment_no, installment_label,
                        total_agreed_fee, previously_paid, amount_paid, balance_due,
                        payment_mode, transaction_ref, collected_by, payment_date,
                        receipt_token, token_expires_at, notes
                    ) VALUES (?, (SELECT id FROM students WHERE admission_no = ?), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                "args": [
                    data.get('receipt_no'), data.get('admission_no'), data.get('admission_no'),
                    data.get('branch', 'Branch 1'), int(data.get('installment_no', 1)),
                    data.get('installment_label', ''), float(data.get('total_agreed_fee', 0.0)),
                    float(data.get('previously_paid', 0.0)), float(data.get('amount_paid', 0.0)),
                    float(data.get('balance_due', 0.0)), data.get('payment_mode', 'Cash'),
                    data.get('transaction_ref', ''), data.get('collected_by', 'frontdesk'),
                    data.get('payment_date'), data.get('receipt_token'),
                    data.get('token_expires_at'), data.get('notes', '')
                ]
            })

        elif etype == 'payments_total_agreed' and op == 'UPDATE':
            queries.append({
                "sql": "UPDATE payments SET total_agreed_fee = ? WHERE admission_no = ?;",
                "args": [float(data.get('total_agreed_fee', 0.0)), data.get('admission_no')]
            })

        elif etype == 'activity_log' and op == 'INSERT':
            queries.append({
                "sql": """
                    INSERT INTO user_activity_logs (
                        session_id, username, full_name, role, branch,
                        action_type, action_details, entity_id, amount, timestamp, date_only,
                        ip_address, device_browser
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                "args": [
                    data.get('session_id', ''), data.get('username', ''), data.get('full_name', ''),
                    data.get('role', 'T3'), data.get('branch', 'Branch 1'),
                    data.get('action_type', ''), data.get('action_details', ''),
                    data.get('entity_id', ''), float(data.get('amount', 0.0)),
                    data.get('timestamp', ''), data.get('date_only', ''),
                    data.get('ip_address', ''), data.get('device_browser', '')
                ]
            })

        elif etype == 'ip_access_log' and op == 'INSERT':
            queries.append({
                "sql": """
                    INSERT INTO ip_access_logs (
                        ip_address, endpoint, method, device_browser,
                        username, status_code, timestamp, date_only
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                "args": [
                    data.get('ip_address', ''), data.get('endpoint', ''), data.get('method', 'GET'),
                    data.get('device_browser', ''), data.get('username', 'Visitor / Public'),
                    int(data.get('status_code', 200)), data.get('timestamp', ''), data.get('date_only', '')
                ]
            })

        elif etype == 'user_session' and op == 'UPDATE':
            queries.append({
                "sql": "UPDATE users SET session_token = ? WHERE username = ?;",
                "args": [data.get('session_token', ''), data.get('username', '')]
            })

        elif etype == 'admission_change' and op == 'INSERT':
            queries.append({
                "sql": """
                    INSERT INTO admission_change_requests (
                        id, student_id, admission_no, request_type, current_data, proposed_data, reason, requested_by, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
                    ON CONFLICT(id) DO UPDATE SET
                        status = 'Pending',
                        reason = excluded.reason;
                """,
                "args": [
                    int(data.get('id', 0)), int(data.get('student_id', 0)), data.get('admission_no', ''),
                    data.get('request_type', ''), data.get('current_data', '{}'), data.get('proposed_data', '{}'),
                    data.get('reason', ''), data.get('requested_by', 'frontdesk')
                ]
            })

        elif etype == 'admission_change' and op == 'UPDATE':
            queries.append({
                "sql": "UPDATE admission_change_requests SET status = ?, admin_remarks = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP WHERE id = ?;",
                "args": [data.get('status', 'Pending'), data.get('admin_remarks', ''), data.get('reviewed_by', 'admin'), int(data.get('id', 0))]
            })

        elif etype == 'discount_request' and op == 'INSERT':
            queries.append({
                "sql": """
                    INSERT INTO discount_requests (
                        id, student_id, admission_no, student_name, class_name, standard_fee, requested_discount, reason, requested_by, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
                    ON CONFLICT(id) DO UPDATE SET
                        status = 'Pending',
                        requested_discount = excluded.requested_discount;
                """,
                "args": [
                    int(data.get('id', 0)), data.get('student_id'), data.get('admission_no', ''),
                    data.get('student_name', ''), data.get('class_name', ''), float(data.get('standard_fee', 0.0)),
                    float(data.get('requested_discount', 0.0)), data.get('reason', ''), data.get('requested_by', 'frontdesk')
                ]
            })

        elif etype == 'discount_request' and op == 'UPDATE':
            queries.append({
                "sql": "UPDATE discount_requests SET status = ?, approved_by = ?, approved_discount = ?, admin_remarks = ?, actioned_at = CURRENT_TIMESTAMP WHERE id = ?;",
                "args": [data.get('status', 'Approved'), data.get('approved_by', 'admin'), float(data.get('approved_discount', 0.0)), data.get('admin_remarks', ''), int(data.get('id', 0))]
            })

        elif etype == 'fee_structure' and op in ['INSERT', 'UPDATE']:
            queries.append({
                "sql": """
                    INSERT INTO fee_structures (
                        class_name, student_type, term_name, tuition_fee, activity_fee, exam_fee,
                        residential_fee, default_transport_fee, total_base_fee, updated_by, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(class_name, student_type, term_name) DO UPDATE SET
                        tuition_fee = excluded.tuition_fee,
                        activity_fee = excluded.activity_fee,
                        exam_fee = excluded.exam_fee,
                        residential_fee = excluded.residential_fee,
                        default_transport_fee = excluded.default_transport_fee,
                        total_base_fee = excluded.total_base_fee,
                        updated_by = excluded.updated_by,
                        updated_at = CURRENT_TIMESTAMP;
                """,
                "args": [
                    data.get('class_name', '').strip(), data.get('student_type', 'Day Scholar').strip(),
                    data.get('term_name', 'Annual').strip(), float(data.get('tuition_fee', 0.0)),
                    float(data.get('activity_fee', 0.0)), float(data.get('exam_fee', 0.0)),
                    float(data.get('residential_fee', 0.0)), float(data.get('default_transport_fee', 0.0)),
                    float(data.get('total_base_fee', 0.0)), data.get('updated_by', 'Admin')
                ]
            })

    success, res = execute_remote_turso_queries(queries, cfg['db_url'], cfg['auth_token'])
    has_sub_error = False
    if success and isinstance(res, dict) and 'results' in res:
        for r_item in res['results']:
            if r_item.get('type') == 'error':
                has_sub_error = True
                res = r_item.get('error', {}).get('message', 'Subquery execution error')
                break

    if success and not has_sub_error:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.executemany("UPDATE sync_queue SET sync_status = 'synced', synced_at = ? WHERE id = ?", [(now_str, i) for i in item_ids])
        conn.commit()
        conn.close()
        return {"status": "success", "synced": len(item_ids), "message": f"Successfully synced {len(item_ids)} transactions to Cloud!"}
    else:
        # Mark attempt
        cur.executemany("UPDATE sync_queue SET sync_attempts = sync_attempts + 1, last_error = ? WHERE id = ?", [(str(res), i) for i in item_ids])
        conn.commit()
        conn.close()
        return {"status": "failed", "synced": 0, "error": str(res)}
