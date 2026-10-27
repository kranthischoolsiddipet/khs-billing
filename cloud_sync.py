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
        {"sql": "CREATE INDEX IF NOT EXISTS idx_iplogs_ip ON ip_access_logs(ip_address);"}
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
                        roll_no = ?, student_name = ?, branch = ?, gender = ?, class_name = ?, section = ?,
                        academic_year = ?, student_type = ?, has_transport = ?, transport_fee = ?, bus_route = ?,
                        parent_name = ?, parent_phone = ?, parent_email = ?, address = ?, standard_fee = ?,
                        discount_amount = ?, final_agreed_fee = ?, discount_status = ?, admission_date = ?,
                        created_by = ?, status = ?, previous_due = ?
                    WHERE admission_no = ?
                """,
                "args": [
                    data.get('roll_no', ''), data.get('student_name'),
                    data.get('branch', 'Branch 1'), data.get('gender', 'Male'), data.get('class_name'),
                    data.get('section', 'A'), data.get('academic_year', '2026-2027'), data.get('student_type', 'Day Scholar'),
                    1 if data.get('has_transport') else 0, float(data.get('transport_fee', 0.0)), data.get('bus_route', ''),
                    data.get('parent_name'), data.get('parent_phone'), data.get('parent_email', ''), data.get('address', ''),
                    float(data.get('standard_fee', 0.0)), float(data.get('discount_amount', 0.0)),
                    float(data.get('final_agreed_fee', 0.0)), data.get('discount_status', 'None'),
                    data.get('admission_date', datetime.now().strftime("%Y-%m-%d")),
                    data.get('created_by', 'frontdesk'), data.get('status', 'Active'),
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

    success, res = execute_remote_turso_queries(queries, cfg['db_url'], cfg['auth_token'])
    if success:
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
