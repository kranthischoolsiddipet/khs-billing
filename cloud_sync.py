import os
import json
import sqlite3
import requests
from datetime import datetime

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloud_sync_config.json")
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "khs_billing.db")

def get_sync_config():
    if not os.path.exists(CONFIG_FILE):
        return {
            "enabled": False,
            "provider": "turso_http", # "turso_http" or "custom_api"
            "db_url": "",             # e.g. https://[db-name]-[org].turso.io or libsql://
            "auth_token": "",         # Turso Auth Token
            "branch": "Branch 1",
            "auto_sync_interval_seconds": 30
        }
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except:
        return {"enabled": False, "provider": "turso_http", "db_url": "", "auth_token": "", "branch": "Branch 1", "auto_sync_interval_seconds": 30}

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
                        discount_amount, final_agreed_fee, discount_status, admission_date, created_by, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    data.get('created_by', 'frontdesk'), data.get('status', 'Active')
                ]
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
