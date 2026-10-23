import os
import sys

# Ensure current directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import secrets
import random
import io
import base64
import json
import pyotp
import qrcode
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from database import get_db, init_db

import threading
import time

app = FastAPI(title="Kranthi High School - Billing & Receipt Management System")

# Ensure DB initialized on startup
init_db()

def _background_cloud_sync_worker():
    """Background daemon thread to auto-push pending sync_queue records and run scheduled 4:30 PM Google Drive backup"""
    last_gdrive_sync_day = ""
    while True:
        try:
            # 1. Real-time Turso Cloud Sync (every 20s)
            cfg = cloud_sync.get_sync_config()
            if cfg.get("enabled") and cfg.get("db_url") and cfg.get("auth_token"):
                cloud_sync.push_local_outbox_to_cloud()
        except Exception:
            pass

        try:
            # 2. Automated Google Drive Daily Backup at 4:30 PM (16:30)
            now = datetime.now()
            today_str = now.strftime('%Y-%m-%d')
            # Trigger window: 16:30 (4:30 PM) onwards if not yet run today
            if (now.hour > 16 or (now.hour == 16 and now.minute >= 30)) and last_gdrive_sync_day != today_str:
                gdrive_cfg = gdrive_sync.get_gdrive_config()
                if gdrive_cfg.get("auto_sync_eod", True) and gdrive_sync.is_gdrive_configured()[0]:
                    print(f"[GDRIVE] Executing scheduled 4:30 PM EOD backup for {today_str}...")
                    res = gdrive_sync.upload_database_to_drive()
                    print(f"[GDRIVE] 4:30 PM EOD Backup Result: {res.get('message', res)}")
                    last_gdrive_sync_day = today_str
        except Exception as e:
            print(f"[GDRIVE CRON ERROR]: {e}")

        time.sleep(20)

@app.on_event("startup")
def start_sync_worker():
    # Hydrate local DB with latest data from Turso cloud (users, students, payments, fees)
    try:
        cfg = cloud_sync.get_sync_config()
        if cfg.get("enabled"):
            print("[STARTUP] Hydrating database from Turso Cloud...")
            cloud_sync.pull_cloud_data_into_local_db()
    except Exception as e:
        print(f"[STARTUP HYDRATION ERROR]: {e}")

    t = threading.Thread(target=_background_cloud_sync_worker, daemon=True)
    t.start()

# Serve static files (HTML, JS, CSS, Images)
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/api/system/version")
def get_system_version():
    """Serves the latest release version info for the 1-Click Silent Auto-Updater"""
    v_file = os.path.join(STATIC_DIR, "version.json")
    if os.path.exists(v_file):
        try:
            with open(v_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": "1.0.0", "files": ["main.py", "database.py", "cloud_sync.py", "gdrive_sync.py", "index.html", "app.js", "receipt.html"]}

# Helper function to convert SQLite rows to dict
def dict_from_row(row):
    return dict(row) if row else None

# ----------------- PYDANTIC MODELS -----------------

class LoginRequest(BaseModel):
    username: str
    password: str
    session_id: Optional[str] = ""

class FeeStructureUpdate(BaseModel):
    class_name: str
    student_type: str
    term_name: str = "Annual"
    tuition_fee: float
    activity_fee: float = 0.0
    exam_fee: float = 0.0
    residential_fee: float = 0.0
    default_transport_fee: float = 0.0

class StudentAdmissionRequest(BaseModel):
    admission_no: str
    roll_no: Optional[str] = ""
    student_name: str
    branch: str = "Branch 1"
    gender: str = "Male"
    class_name: str
    section: str = "A"
    academic_year: str = "2026-2027"
    student_type: str # 'Day Scholar' or 'Residential'
    has_transport: bool = False
    transport_fee: float = 0.0
    bus_route: Optional[str] = ""
    parent_name: str
    parent_phone: str
    parent_email: Optional[str] = ""
    address: Optional[str] = ""
    requested_discount: float = 0.0
    discount_reason: Optional[str] = ""
    initial_payment_amount: float = 0.0
    initial_payment_mode: str = "Cash"
    initial_payment_ref: Optional[str] = ""
    session_id: Optional[str] = ""

class PreAdmissionDiscountRequest(BaseModel):
    admission_no: str
    student_name: str
    class_name: str
    standard_fee: float
    requested_discount: float
    reason: Optional[str] = ""

class DiscountActionRequest(BaseModel):
    request_id: int
    action: str # 'Approve' or 'Reject'
    approved_discount: float
    admin_remarks: Optional[str] = ""

class AdmissionChangeRequest(BaseModel):
    student_id: int
    request_type: str # 'MODIFY_DETAILS' or 'CANCEL_ADMISSION'
    reason: str
    proposed_data: Optional[dict] = {}

class AdmissionChangeActionRequest(BaseModel):
    request_id: int
    action: str # 'Approve' or 'Reject'
    admin_remarks: Optional[str] = ""

class BulkImportBatchActionRequest(BaseModel):
    batch_id: int
    action: str # 'Approve' or 'Reject'
    admin_remarks: Optional[str] = ""

class PaymentCreateRequest(BaseModel):
    student_id: int
    amount_paid: float
    payment_mode: str # 'Cash', 'UPI', 'Cheque', 'Bank Transfer'
    transaction_ref: Optional[str] = ""
    installment_label: Optional[str] = ""
    notes: Optional[str] = ""
    session_id: Optional[str] = ""

class RequestOtpRequest(BaseModel):
    mobile: str

class VerifyOtpRequest(BaseModel):
    mobile: str
    otp_code: str
    session_id: Optional[str] = ""

class StaffUserCreate(BaseModel):
    full_name: str
    mobile: str

class StaffStatusToggle(BaseModel):
    user_id: int
    is_active: int

class StaffUserUpdate(BaseModel):
    user_id: int
    full_name: str
    mobile: str

class StaffUserDelete(BaseModel):
    user_id: int

class UserSessionLogRequest(BaseModel):
    session_id: str
    username: str
    action_type: str # 'LOGOUT' or 'AUTO_TIMEOUT'
    action_details: Optional[str] = ""

def record_activity_log(session_id: str, username: str, full_name: str, role: str, branch: str, action_type: str, action_details: str = "", entity_id: str = "", amount: float = 0.0):
    """Logs user login, logout, new admission, and fee payment events for audit trails"""
    try:
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_activity_logs (session_id, username, full_name, role, branch, action_type, action_details, entity_id, amount, timestamp, date_only)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, username, full_name, role, branch or "Branch 1", action_type, action_details, entity_id, amount, ts, date_str))
        conn.commit()
        conn.close()

        # Queue log to Turso cloud
        try:
            log_payload = {
                "session_id": session_id,
                "username": username,
                "full_name": full_name,
                "role": role,
                "branch": branch or "Branch 1",
                "action_type": action_type,
                "action_details": action_details,
                "entity_id": entity_id,
                "amount": amount,
                "timestamp": ts,
                "date_only": date_str
            }
            cloud_sync.queue_transaction_locally('activity_log', f"{session_id}_{ts}", 'INSERT', log_payload, branch or "Branch 1")
        except Exception:
            pass
    except Exception as e:
        print(f"[AUDIT LOG ERROR]: {e}")

# ----------------- AUTHENTICATION & OTP APIS -----------------

@app.post("/api/auth/request-otp")
def request_otp(data: RequestOtpRequest):
    raw_input = data.mobile.strip().replace(" ", "").replace("-", "")
    is_sa = raw_input.upper().startswith("SA")
    mobile = raw_input[2:] if is_sa else raw_input
    if len(mobile) == 12 and mobile.startswith("91"):
        mobile = mobile[2:]

    conn = get_db()
    cursor = conn.cursor()

    # Differentiate between SA Super Admin and T3 Cashier
    if is_sa:
        user = cursor.execute("SELECT * FROM users WHERE username = ? OR (phone = ? AND role = 'T1')", (f"SA{mobile}", mobile)).fetchone()
    else:
        user = cursor.execute("SELECT * FROM users WHERE username = ? OR (phone = ? AND role = 'T3')", (mobile, mobile)).fetchone()
        if not user:
            user = cursor.execute("SELECT * FROM users WHERE username = ? OR phone = ?", (mobile, mobile)).fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=403, detail=f"No account registered for {raw_input}. Please contact School Admin.")

    if not user['is_active']:
        conn.close()
        raise HTTPException(status_code=403, detail="Your access has been BLOCKED by Admin. Please contact Management.")

    # Generate 6-digit OTP
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")

    # Invalidate previous unused OTPs for this number
    cursor.execute("UPDATE otps SET is_used = 1 WHERE mobile IN (?, ?) AND is_used = 0", (mobile, raw_input))

    # Insert new OTP
    cursor.execute("""
        INSERT INTO otps (mobile, otp_code, expires_at, is_used)
        VALUES (?, ?, ?, 0)
    """, (raw_input, otp_code, expires_at))

    conn.commit()
    conn.close()

    otp_msg = f"Kranthi High School Login OTP: {otp_code}. Valid for 5 minutes. Do not share with anyone."

    return {
        "status": "success",
        "mobile": raw_input,
        "otp_code": otp_code, # Sent back so user sees it instantly / can send via WhatsApp
        "message": f"OTP generated successfully for {raw_input}.",
        "whatsapp_url": f"https://wa.me/91{mobile}?text={otp_msg}"
    }

@app.post("/api/auth/check-method")
def check_auth_method(data: RequestOtpRequest):
    """Check if the user has Google/Microsoft Authenticator configured or uses fallback SMS/OTP"""
    raw_input = data.mobile.strip().replace(" ", "").replace("-", "")
    is_sa = raw_input.upper().startswith("SA")
    mobile = raw_input[2:] if is_sa else raw_input
    if len(mobile) == 12 and mobile.startswith("91"):
        mobile = mobile[2:]

    conn = get_db()
    cursor = conn.cursor()
    if is_sa:
        user = cursor.execute("SELECT id, username, full_name, role, phone, is_active, totp_secret FROM users WHERE username = ? OR (phone = ? AND role = 'T1')", (f"SA{mobile}", mobile)).fetchone()
    else:
        user = cursor.execute("SELECT id, username, full_name, role, phone, is_active, totp_secret FROM users WHERE username = ? OR (phone = ? AND role = 'T3')", (mobile, mobile)).fetchone()
        if not user:
            user = cursor.execute("SELECT id, username, full_name, role, phone, is_active, totp_secret FROM users WHERE username = ? OR phone = ?", (mobile, mobile)).fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=403, detail=f"No account registered for {raw_input}.")
    if not user['is_active']:
        raise HTTPException(status_code=403, detail="Your access has been BLOCKED by Admin. Please contact Management.")

    has_totp = bool(user['totp_secret'] and len(user['totp_secret'].strip()) > 8)

    return {
        "status": "success",
        "mobile": raw_input,
        "full_name": user['full_name'],
        "role": user['role'],
        "has_authenticator": has_totp
    }

@app.post("/api/auth/verify-otp")
def verify_otp(data: VerifyOtpRequest):
    raw_input = data.mobile.strip().replace(" ", "").replace("-", "")
    is_sa = raw_input.upper().startswith("SA")
    mobile = raw_input[2:] if is_sa else raw_input
    if len(mobile) == 12 and mobile.startswith("91"):
        mobile = mobile[2:]

    otp_input = data.otp_code.strip()

    conn = get_db()
    cursor = conn.cursor()

    if is_sa:
        user = cursor.execute("SELECT * FROM users WHERE (username = ? OR (phone = ? AND role = 'T1')) AND is_active = 1", (f"SA{mobile}", mobile)).fetchone()
    else:
        user = cursor.execute("SELECT * FROM users WHERE (username = ? OR (phone = ? AND role = 'T3')) AND is_active = 1", (mobile, mobile)).fetchone()
        if not user:
            user = cursor.execute("SELECT * FROM users WHERE (username = ? OR phone = ?) AND is_active = 1", (mobile, mobile)).fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="User not found or access blocked.")

    # 1. First check if user has TOTP (Google/Microsoft Authenticator) enabled
    if user['totp_secret'] and len(user['totp_secret'].strip()) > 8:
        totp = pyotp.TOTP(user['totp_secret'].strip())
        if totp.verify(otp_input, valid_window=1):
            conn.close()
            # Record audit login event
            sess_id = (data.session_id or f"sess_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}").strip()
            record_activity_log(
                session_id=sess_id,
                username=user['username'],
                full_name=user['full_name'],
                role=user['role'],
                branch="Branch 1",
                action_type="LOGIN",
                action_details="Staff logged in via Authenticator OTP"
            )
            return {
                "status": "success",
                "method": "authenticator",
                "session_id": sess_id,
                "user": dict_from_row(user)
            }

    # 2. Check traditional OTP table (Fallback or setup mode)
    otp_row = cursor.execute("""
        SELECT * FROM otps 
        WHERE mobile IN (?, ?) AND otp_code = ? AND is_used = 0
        ORDER BY id DESC LIMIT 1
    """, (mobile, raw_input, otp_input)).fetchone()

    if not otp_row:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid 6-digit Authenticator code or OTP. Please check your phone.")

    exp_time = datetime.strptime(otp_row['expires_at'], "%Y-%m-%d %H:%M:%S")
    if datetime.now() > exp_time:
        conn.close()
        raise HTTPException(status_code=401, detail="This code has expired. Please check your Authenticator app.")

    # Mark OTP as used
    cursor.execute("UPDATE otps SET is_used = 1 WHERE id = ?", (otp_row['id'],))
    conn.commit()
    conn.close()

    # Record audit login event
    sess_id = (data.session_id or f"sess_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}").strip()
    record_activity_log(
        session_id=sess_id,
        username=user['username'],
        full_name=user['full_name'],
        role=user['role'],
        branch="Branch 1",
        action_type="LOGIN",
        action_details="Staff logged in via SMS/Fallback OTP"
    )

    return {
        "status": "success",
        "method": "otp",
        "session_id": sess_id,
        "user": dict_from_row(user)
    }

@app.post("/api/auth/login")
def login(creds: LoginRequest):
    conn = get_db()
    user = conn.execute("""
        SELECT id, username, full_name, role, phone, is_active 
        FROM users 
        WHERE (username = ? OR phone = ?) AND password_hash = ? AND is_active = 1
    """, (creds.username.strip(), creds.username.strip(), creds.password.strip())).fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials or account blocked.")

    sess_id = (creds.session_id or f"sess_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}").strip()
    record_activity_log(
        session_id=sess_id,
        username=user['username'],
        full_name=user['full_name'],
        role=user['role'],
        branch="Branch 1",
        action_type="LOGIN",
        action_details="User logged in via Password"
    )

    return {
        "status": "success",
        "session_id": sess_id,
        "user": dict_from_row(user)
    }

@app.post("/api/auth/session-log")
def log_session_event(req: UserSessionLogRequest):
    """Records client-triggered session events like LOGOUT or AUTO_TIMEOUT"""
    conn = get_db()
    user = conn.execute("SELECT id, username, full_name, role FROM users WHERE username = ?", (req.username.strip(),)).fetchone()
    conn.close()

    full_name = user['full_name'] if user else req.username
    role = user['role'] if user else "T3"

    record_activity_log(
        session_id=req.session_id.strip(),
        username=req.username.strip(),
        full_name=full_name,
        role=role,
        branch="Branch 1",
        action_type=req.action_type.strip(),
        action_details=req.action_details.strip() or f"User ended session ({req.action_type})"
    )

    return {"status": "success"}

@app.get("/api/audit-logs")
def get_audit_logs(target_date: str = Query(...), operator_user: str = Query(...)):
    """
    Returns session & activity audit logs for target_date.
    Role hierarchy rules:
    - Super Admin (T1): Can view logs of both T3 (Cashiers) and T2 (Admins), and own logs.
    - Admin (T2): Can view logs of T3 (Cashiers) only.
    - Cashier (T3): Denied (403 Forbidden).
    """
    conn = get_db()
    cursor = conn.cursor()

    # Verify operator role
    op = cursor.execute("SELECT id, username, role FROM users WHERE username = ?", (operator_user.strip(),)).fetchone()
    if not op:
        conn.close()
        raise HTTPException(status_code=403, detail="Unauthorized operator.")

    op_role = op['role']
    if op_role not in ['T1', 'T2']:
        conn.close()
        raise HTTPException(status_code=403, detail="Audit log access is restricted to Administrators only.")

    # Target date formatted as YYYY-MM-DD
    clean_date = target_date.strip()

    if op_role == 'T1':
        # Super Admin sees all logs (T1, T2, T3)
        rows = cursor.execute("""
            SELECT id, session_id, username, full_name, role, branch, action_type, action_details, entity_id, amount, timestamp, date_only
            FROM user_activity_logs
            WHERE date_only = ?
            ORDER BY timestamp DESC
        """, (clean_date,)).fetchall()
    else:
        # T2 Admin sees T3 Cashiers only
        rows = cursor.execute("""
            SELECT id, session_id, username, full_name, role, branch, action_type, action_details, entity_id, amount, timestamp, date_only
            FROM user_activity_logs
            WHERE date_only = ? AND role = 'T3'
            ORDER BY timestamp DESC
        """, (clean_date,)).fetchall()

    conn.close()

    logs = [dict_from_row(r) for r in rows]

    # Group into sessions for convenient timeline display
    sessions_map = {}
    for log in logs:
        s_id = log['session_id'] or f"unknown_{log['username']}"
        if s_id not in sessions_map:
            sessions_map[s_id] = {
                "session_id": s_id,
                "username": log['username'],
                "full_name": log['full_name'],
                "role": log['role'],
                "branch": log['branch'],
                "login_time": None,
                "logout_time": None,
                "logout_type": None,
                "total_actions": 0,
                "actions": []
            }
        
        entry = sessions_map[s_id]
        if log['action_type'] == 'LOGIN':
            if not entry['login_time'] or log['timestamp'] < entry['login_time']:
                entry['login_time'] = log['timestamp']
        elif log['action_type'] in ['LOGOUT', 'AUTO_TIMEOUT']:
            entry['logout_time'] = log['timestamp']
            entry['logout_type'] = log['action_type']
        else:
            entry['total_actions'] += 1

        entry['actions'].append(log)

    # Sort actions inside each session chronologically
    session_list = list(sessions_map.values())
    for s in session_list:
        s['actions'].sort(key=lambda x: x['timestamp'])

    return {
        "status": "success",
        "target_date": clean_date,
        "operator_role": op_role,
        "total_logs": len(logs),
        "sessions": session_list,
        "raw_logs": logs
    }

# ----------------- AUTHENTICATOR (TOTP) SETUP APIS -----------------

@app.get("/api/staff/{user_id}/authenticator-qr")
def get_authenticator_qr(user_id: int):
    """Generates or retrieves TOTP secret and returns base64 PNG QR code for Google/Microsoft Authenticator"""
    conn = get_db()
    cursor = conn.cursor()
    user = cursor.execute("SELECT id, username, full_name, role, phone, totp_secret FROM users WHERE id = ?", (user_id,)).fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found.")

    secret = user['totp_secret']
    if not secret or len(secret.strip()) < 8:
        # Generate new base32 secret
        secret = pyotp.random_base32()
        cursor.execute("UPDATE users SET totp_secret = ? WHERE id = ?", (secret, user_id))
        conn.commit()

    conn.close()

    label = f"{user['full_name']} ({user['phone'] or user['username']})"
    issuer = "Kranthi High School"
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=label, issuer_name=issuer)

    # Render QR code image to base64 PNG
    qr = qrcode.QRCode(
        version=1,
        box_size=8,
        border=3,
        error_correction=qrcode.constants.ERROR_CORRECT_M
    )
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1e1b4b", back_color="#ffffff")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return {
        "status": "success",
        "user_id": user_id,
        "full_name": user['full_name'],
        "mobile": user['phone'] or user['username'],
        "secret_key": secret,
        "provisioning_uri": provisioning_uri,
        "qr_image_data": f"data:image/png;base64,{qr_b64}"
    }

@app.post("/api/staff/{user_id}/reset-authenticator")
def reset_authenticator(user_id: int):
    """Admin reset authenticator (e.g. if staff changed phone)"""
    conn = get_db()
    cursor = conn.cursor()
    new_secret = pyotp.random_base32()
    cursor.execute("UPDATE users SET totp_secret = ? WHERE id = ?", (new_secret, user_id))
    conn.commit()
    conn.close()
    return {
        "status": "success",
        "message": "Authenticator reset successfully. New QR code generated."
    }

# ----------------- STAFF USERS MANAGEMENT (ADMIN) -----------------

@app.get("/api/staff/list")
def get_staff_users():
    conn = get_db()
    # Only return front desk / billing users (role == 'T3')
    rows = conn.execute("""
        SELECT id, username, full_name, role, phone, totp_secret, is_active, created_at 
        FROM users 
        WHERE role = 'T3'
        ORDER BY id ASC
    """).fetchall()
    conn.close()
    
    staff_list = []
    for r in rows:
        d = dict_from_row(r)
        d['role_name'] = 'Billing Desk'
        d['has_authenticator'] = bool(r['totp_secret'] and len(r['totp_secret'].strip()) > 8)
        # do not leak raw secret in list
        del d['totp_secret']
        staff_list.append(d)
        
    return {
        "status": "success",
        "count": len(staff_list),
        "staff": staff_list
    }

@app.post("/api/staff/add")
def add_staff_user(data: StaffUserCreate, operator_user: str = Query("admin")):
    mobile = data.mobile.strip().replace(" ", "").replace("-", "")
    if len(mobile) == 12 and mobile.startswith("91"):
        mobile = mobile[2:]

    if len(mobile) != 10 or not mobile.isdigit():
        raise HTTPException(status_code=400, detail="Please enter a valid 10-digit mobile number.")

    conn = get_db()
    cursor = conn.cursor()

    # Limit to 10 billing staff users max
    count = cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'T3';").fetchone()[0]
    if count >= 10:
        conn.close()
        raise HTTPException(status_code=400, detail="Maximum limit of 10 staff users reached. Please remove an existing user to add a new one.")

    # Check if mobile exists
    existing = cursor.execute("SELECT id FROM users WHERE username = ? OR phone = ?", (mobile, mobile)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="A user with this mobile number is already registered.")

    cursor.execute("""
        INSERT INTO users (username, password_hash, full_name, role, phone, is_active)
        VALUES (?, '', ?, 'T3', ?, 1)
    """, (mobile, data.full_name.strip().upper(), mobile))

    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Staff user {data.full_name.upper()} ({mobile}) added successfully!"}

@app.post("/api/staff/update")
def update_staff_user(data: StaffUserUpdate):
    mobile = data.mobile.strip().replace(" ", "").replace("-", "")
    if len(mobile) == 12 and mobile.startswith("91"):
        mobile = mobile[2:]

    if len(mobile) != 10 or not mobile.isdigit():
        raise HTTPException(status_code=400, detail="Please enter a valid 10-digit mobile number.")

    conn = get_db()
    cursor = conn.cursor()

    user = cursor.execute("SELECT id, role FROM users WHERE id = ?", (data.user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    # Check mobile collision
    existing = cursor.execute("SELECT id FROM users WHERE (username = ? OR phone = ?) AND id != ?", (mobile, mobile, data.user_id)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="This mobile number is already assigned to another user.")

    cursor.execute("""
        UPDATE users 
        SET full_name = ?, username = ?, phone = ? 
        WHERE id = ?
    """, (data.full_name.strip().upper(), mobile, mobile, data.user_id))

    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Staff user details updated successfully!"}

@app.post("/api/staff/delete")
def delete_staff_user(data: StaffUserDelete):
    conn = get_db()
    cursor = conn.cursor()

    user = cursor.execute("SELECT id, role, full_name FROM users WHERE id = ?", (data.user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    if user['role'] != 'T3':
        conn.close()
        raise HTTPException(status_code=403, detail="Cannot delete administrative accounts.")

    cursor.execute("DELETE FROM users WHERE id = ?", (data.user_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"User {user['full_name']} has been permanently removed."}

@app.post("/api/staff/toggle-status")
def toggle_staff_status(data: StaffStatusToggle):
    conn = get_db()
    cursor = conn.cursor()

    user = cursor.execute("SELECT role FROM users WHERE id = ?", (data.user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    cursor.execute("UPDATE users SET is_active = ? WHERE id = ?", (data.is_active, data.user_id))
    conn.commit()
    conn.close()

    action_label = "Unblocked / Active" if data.is_active == 1 else "Blocked"
    return {"status": "success", "message": f"User access status updated to: {action_label}"}

# ----------------- FEE STRUCTURE APIS (T1 & T2) -----------------

@app.get("/api/fee-structures")
def get_fee_structures():
    conn = get_db()
    rows = conn.execute("SELECT * FROM fee_structures ORDER BY class_name ASC, student_type ASC").fetchall()
    conn.close()
    return [dict_from_row(r) for r in rows]

@app.post("/api/fee-structures/update")
def update_fee_structure(data: FeeStructureUpdate, request: Request):
    total = data.tuition_fee + data.activity_fee + data.exam_fee
    if data.student_type == 'Residential':
        total += data.residential_fee

    conn = get_db()
    conn.execute("""
        INSERT INTO fee_structures (class_name, student_type, term_name, tuition_fee, activity_fee, exam_fee, residential_fee, default_transport_fee, total_base_fee, updated_by, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Admin', CURRENT_TIMESTAMP)
        ON CONFLICT(class_name, student_type, term_name) DO UPDATE SET
            tuition_fee = excluded.tuition_fee,
            activity_fee = excluded.activity_fee,
            exam_fee = excluded.exam_fee,
            residential_fee = excluded.residential_fee,
            default_transport_fee = excluded.default_transport_fee,
            total_base_fee = excluded.total_base_fee,
            updated_by = excluded.updated_by,
            updated_at = CURRENT_TIMESTAMP
    """, (data.class_name, data.student_type, data.term_name, data.tuition_fee, data.activity_fee, data.exam_fee, data.residential_fee, data.default_transport_fee, total))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Fee structure updated for {data.class_name} ({data.student_type})"}

# ----------------- STUDENT ADMISSION & DISCOUNT -----------------

@app.get("/api/fee-structures/calculate")
def calculate_fee(class_name: str = Query(...), student_type: str = Query(...)):
    conn = get_db()
    row = conn.execute("""
        SELECT * FROM fee_structures 
        WHERE class_name = ? AND student_type = ?
    """, (class_name, student_type)).fetchone()
    conn.close()

    if not row:
        return {"base_fee": 30000.0, "tuition": 25000.0, "activity": 3000.0, "exam": 2000.0, "residential": 0.0}
    return dict_from_row(row)

@app.post("/api/students/admit")
def admit_student(req: StudentAdmissionRequest, operator_role: str = Query("T3"), operator_user: str = Query("frontdesk")):
    conn = get_db()

    # Check if admission number exists
    existing = conn.execute("SELECT id FROM students WHERE admission_no = ?", (req.admission_no.strip(),)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Admission Number already exists!")

    # Calculate standard fee
    fee_struct = conn.execute("""
        SELECT total_base_fee FROM fee_structures 
        WHERE class_name = ? AND student_type = ?
    """, (req.class_name, req.student_type)).fetchone()
    base_fee = fee_struct['total_base_fee'] if fee_struct else 30000.0

    transport_fee = req.transport_fee if req.student_type == 'Day Scholar' and req.has_transport else 0.0
    gross_fee = base_fee + transport_fee

    discount_amount = 0.0
    discount_status = "None"
    needs_approval = False

    if req.requested_discount > 0:
        if operator_role in ['T1', 'T2']:
            # T1/T2 can directly grant discount
            discount_amount = req.requested_discount
            discount_status = "Approved"
        else:
            # T3 needs approval
            discount_status = "Pending"
            needs_approval = True

    final_agreed_fee = gross_fee - discount_amount

    # Insert student
    branch_val = req.branch.strip() if req.branch else "Branch 1"
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO students (
            admission_no, roll_no, student_name, branch, gender, class_name, section, 
            academic_year, student_type, has_transport, transport_fee, bus_route,
            parent_name, parent_phone, parent_email, address, standard_fee, 
            discount_amount, final_agreed_fee, discount_status, admission_date, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req.admission_no.strip(), req.roll_no.strip(), req.student_name.strip(), branch_val, req.gender, req.class_name, req.section,
        req.academic_year, req.student_type, 1 if req.has_transport else 0, transport_fee, req.bus_route,
        req.parent_name.strip(), req.parent_phone.strip(), req.parent_email, req.address,
        gross_fee, discount_amount, final_agreed_fee, discount_status,
        datetime.now().strftime("%Y-%m-%d"), operator_user
    ))
    student_id = cursor.lastrowid

    # If discount needs approval, insert to discount_requests
    if needs_approval:
        cursor.execute("""
            INSERT INTO discount_requests (
                student_id, admission_no, student_name, class_name, standard_fee, requested_discount, reason, requested_by, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
        """, (student_id, req.admission_no, req.student_name, req.class_name, gross_fee, req.requested_discount, req.discount_reason, operator_user))

    # If initial payment was made during admission
    receipt_data = None
    if req.initial_payment_amount > 0:
        b_code = "B2" if ("2" in branch_val) else "B1"
        receipt_no = f"KHS{b_code}-{datetime.now().strftime('%Y')}-{random.randint(10000, 99999)}"
        token = secrets.token_urlsafe(16)
        expires = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
        balance = final_agreed_fee - req.initial_payment_amount

        cursor.execute("""
            INSERT INTO payments (
                receipt_no, student_id, admission_no, branch, installment_no, installment_label,
                total_agreed_fee, previously_paid, amount_paid, balance_due,
                payment_mode, transaction_ref, collected_by, payment_date,
                receipt_token, token_expires_at, notes
            ) VALUES (?, ?, ?, ?, 1, '1st Installment (Admission)', ?, 0.0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            receipt_no, student_id, req.admission_no, branch_val, final_agreed_fee, req.initial_payment_amount, balance,
            req.initial_payment_mode, req.initial_payment_ref, operator_user,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), token, expires, "Admission Fee Deposit"
        ))

        receipt_data = {
            "receipt_no": receipt_no,
            "receipt_token": token,
            "amount_paid": req.initial_payment_amount,
            "balance_due": balance,
            "parent_phone": req.parent_phone
        }

    conn.commit()
    conn.close()

    # Automatically queue transaction for real-time cloud sync
    try:
        import cloud_sync
        student_payload = {
            "admission_no": req.admission_no.strip(),
            "roll_no": req.roll_no.strip(),
            "student_name": req.student_name.strip(),
            "branch": branch_val,
            "gender": req.gender,
            "class_name": req.class_name,
            "section": req.section,
            "academic_year": req.academic_year,
            "student_type": req.student_type,
            "has_transport": 1 if req.has_transport else 0,
            "transport_fee": transport_fee,
            "bus_route": req.bus_route,
            "parent_name": req.parent_name.strip(),
            "parent_phone": req.parent_phone.strip(),
            "parent_email": req.parent_email,
            "address": req.address,
            "standard_fee": gross_fee,
            "discount_amount": discount_amount,
            "final_agreed_fee": final_agreed_fee,
            "discount_status": discount_status,
            "admission_date": datetime.now().strftime("%Y-%m-%d"),
            "created_by": operator_user,
            "status": "Active"
        }
        cloud_sync.queue_transaction_locally('student', req.admission_no.strip(), 'INSERT', student_payload, branch_val)

        if receipt_data:
            payment_payload = {
                "receipt_no": receipt_data['receipt_no'],
                "admission_no": req.admission_no.strip(),
                "branch": branch_val,
                "installment_no": 1,
                "installment_label": "1st Installment (Admission)",
                "total_agreed_fee": final_agreed_fee,
                "previously_paid": 0.0,
                "amount_paid": req.initial_payment_amount,
                "balance_due": receipt_data['balance_due'],
                "payment_mode": req.initial_payment_mode,
                "transaction_ref": req.initial_payment_ref,
                "collected_by": operator_user,
                "payment_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "receipt_token": receipt_data['receipt_token'],
                "token_expires_at": (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S"),
                "notes": "Admission Fee Deposit"
            }
            cloud_sync.queue_transaction_locally('payment', receipt_data['receipt_no'], 'INSERT', payment_payload, branch_val)

        # Attempt background push if cloud sync is enabled
        cfg = cloud_sync.get_sync_config()
        if cfg.get("enabled"):
            cloud_sync.push_local_outbox_to_cloud()
    except Exception as e:
        print(f"[CLOUD SYNC HOOK NOTICE]: {e}")

    # Record audit log for New Admission
    try:
        sess_id = (req.session_id or f"sess_{operator_user}").strip()
        record_activity_log(
            session_id=sess_id,
            username=operator_user,
            full_name=operator_user,
            role=operator_role,
            branch=branch_val,
            action_type="NEW_ADMISSION",
            action_details=f"Admitted student {req.student_name.strip()} ({req.class_name}-{req.section})",
            entity_id=req.admission_no.strip(),
            amount=req.initial_payment_amount
        )
    except Exception as e:
        print(f"[AUDIT LOG ERROR ADMISSION]: {e}")

    return {
        "status": "success",
        "student_id": student_id,
        "message": "Student admitted successfully!" + (" Discount request submitted for Admin approval." if needs_approval else ""),
        "receipt": receipt_data
    }

# ----------------- DISCOUNT APPROVAL WORKFLOW (T1 & T2) -----------------

@app.post("/api/discounts/request-approval")
def request_pre_admission_discount(req: PreAdmissionDiscountRequest, operator_user: str = Query("frontdesk")):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO discount_requests (
            student_id, admission_no, student_name, class_name, standard_fee, requested_discount, reason, requested_by, status
        ) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, 'Pending')
    """, (req.admission_no.strip(), req.student_name.strip(), req.class_name, req.standard_fee, req.requested_discount, req.reason, operator_user))
    req_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"status": "success", "request_id": req_id, "message": "Discount approval request sent to Admin."}

@app.get("/api/discounts/status/{request_id}")
def check_discount_status(request_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM discount_requests WHERE id = ?", (request_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    return dict_from_row(row)

@app.get("/api/discounts/pending")
def get_pending_discounts():
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM discount_requests 
        WHERE status = 'Pending' 
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return [dict_from_row(r) for r in rows]

@app.post("/api/discounts/action")
def action_discount(req: DiscountActionRequest, approver_user: str = Query("admin")):
    conn = get_db()
    cursor = conn.cursor()

    req_row = cursor.execute("SELECT * FROM discount_requests WHERE id = ?", (req.request_id,)).fetchone()
    if not req_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Discount request not found")

    student_id = req_row['student_id']

    if req.action == 'Approve':
        cursor.execute("""
            UPDATE discount_requests 
            SET status = 'Approved', approved_by = ?, approved_discount = ?, admin_remarks = ?, actioned_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (approver_user, req.approved_discount, req.admin_remarks, req.request_id))

        if student_id:
            # Recalculate student final agreed fee if student already admitted
            student = cursor.execute("SELECT standard_fee FROM students WHERE id = ?", (student_id,)).fetchone()
            new_agreed = student['standard_fee'] - req.approved_discount
            cursor.execute("""
                UPDATE students 
                SET discount_amount = ?, final_agreed_fee = ?, discount_status = 'Approved'
                WHERE id = ?
            """, (req.approved_discount, new_agreed, student_id))
            cursor.execute("UPDATE payments SET total_agreed_fee = ? WHERE student_id = ?", (new_agreed, student_id))

    else:
        cursor.execute("""
            UPDATE discount_requests 
            SET status = 'Rejected', approved_by = ?, admin_remarks = ?, actioned_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (approver_user, req.admin_remarks, req.request_id))

        if student_id:
            cursor.execute("UPDATE students SET discount_status = 'Rejected' WHERE id = ?", (student_id,))

    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Discount request marked as {req.action}", "approved_discount": req.approved_discount}

# ----------------- ADMISSION MODIFICATION & CANCELLATION APPROVAL WORKFLOW -----------------

@app.post("/api/admissions/request-change")
def request_admission_change(req: AdmissionChangeRequest, operator_user: str = Query("frontdesk")):
    conn = get_db()
    cursor = conn.cursor()

    student = cursor.execute("SELECT * FROM students WHERE id = ?", (req.student_id,)).fetchone()
    if not student:
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found.")

    if student['status'] == 'Cancelled':
        conn.close()
        raise HTTPException(status_code=400, detail="This admission is already cancelled.")

    # Check if there is already a pending request for this student
    existing = cursor.execute("""
        SELECT id FROM admission_change_requests 
        WHERE student_id = ? AND status = 'Pending'
    """, (req.student_id,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="A change/cancellation request is already pending Admin approval for this student.")

    current_data_json = json.dumps(dict_from_row(student))
    proposed_data_json = json.dumps(req.proposed_data or {})

    cursor.execute("""
        INSERT INTO admission_change_requests (
            student_id, admission_no, request_type, current_data, proposed_data, reason, requested_by, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending')
    """, (req.student_id, student['admission_no'], req.request_type, current_data_json, proposed_data_json, req.reason.strip(), operator_user))

    req_id = cursor.lastrowid
    conn.commit()
    conn.close()

    msg_type = "Admission Cancellation" if req.request_type == 'CANCEL_ADMISSION' else "Admission Details Modification"
    return {
        "status": "success",
        "request_id": req_id,
        "message": f"{msg_type} request submitted successfully for School Admin approval."
    }

@app.get("/api/admissions/pending-changes")
def get_pending_admission_changes():
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM admission_change_requests 
        WHERE status = 'Pending' 
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict_from_row(r)
        d['current_data'] = json.loads(d['current_data']) if d['current_data'] else {}
        d['proposed_data'] = json.loads(d['proposed_data']) if d['proposed_data'] else {}
        results.append(d)
    return results

@app.post("/api/admissions/action-change")
def action_admission_change(req: AdmissionChangeActionRequest, approver_user: str = Query("admin")):
    conn = get_db()
    cursor = conn.cursor()

    req_row = cursor.execute("SELECT * FROM admission_change_requests WHERE id = ?", (req.request_id,)).fetchone()
    if not req_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Request not found")

    student_id = req_row['student_id']

    if req.action == 'Approve':
        cursor.execute("""
            UPDATE admission_change_requests 
            SET status = 'Approved', reviewed_by = ?, admin_remarks = ?, reviewed_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (approver_user, req.admin_remarks, req.request_id))

        if req_row['request_type'] == 'CANCEL_ADMISSION':
            cursor.execute("UPDATE students SET status = 'Cancelled' WHERE id = ?", (student_id,))
        elif req_row['request_type'] == 'MODIFY_DETAILS':
            proposed = json.loads(req_row['proposed_data'] or "{}")
            # Updatable fields: student_name, roll_no, gender, class_name, section, student_type, has_transport, transport_fee, bus_route, parent_name, parent_phone, parent_email, address
            allowed_fields = [
                'student_name', 'roll_no', 'gender', 'class_name', 'section', 
                'student_type', 'has_transport', 'transport_fee', 'bus_route', 
                'parent_name', 'parent_phone', 'parent_email', 'address'
            ]
            updates = []
            vals = []
            for k in allowed_fields:
                if k in proposed:
                    updates.append(f"{k} = ?")
                    vals.append(proposed[k])

            if updates:
                vals.append(student_id)
                cursor.execute(f"UPDATE students SET {', '.join(updates)} WHERE id = ?", vals)

        conn.commit()
        conn.close()
        return {"status": "success", "message": f"Admission {req_row['request_type']} has been APPROVED and applied."}
    else:
        cursor.execute("""
            UPDATE admission_change_requests 
            SET status = 'Rejected', reviewed_by = ?, admin_remarks = ?, reviewed_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (approver_user, req.admin_remarks, req.request_id))
        conn.commit()
        conn.close()
        return {"status": "success", "message": f"Admission change request has been REJECTED."}

# ----------------- PAYMENTS & INSTALLMENTS (T3) -----------------

@app.get("/api/students/search")
def search_students(query: str = Query("")):
    conn = get_db()
    q = f"%{query.strip()}%"
    rows = conn.execute("""
        SELECT s.*, 
            COALESCE((SELECT SUM(amount_paid) FROM payments WHERE student_id = s.id), 0.0) as total_paid,
            (s.final_agreed_fee - COALESCE((SELECT SUM(amount_paid) FROM payments WHERE student_id = s.id), 0.0)) as balance_due,
            (SELECT COUNT(*) FROM payments WHERE student_id = s.id) as payment_count
        FROM students s
        WHERE s.admission_no LIKE ? OR s.student_name LIKE ? OR s.parent_phone LIKE ?
        ORDER BY s.id DESC
        LIMIT 25
    """, (q, q, q)).fetchall()
    conn.close()
    return [dict_from_row(r) for r in rows]

@app.get("/api/students/class-wise")
def get_students_class_wise(class_name: Optional[str] = None, section: Optional[str] = None, status: Optional[str] = None, branch: Optional[str] = None):
    conn = get_db()

    # Get class list summary (counts and financials per class)
    sum_query = """
        SELECT 
            s.class_name,
            COUNT(s.id) as total_students,
            SUM(CASE WHEN s.status != 'Cancelled' THEN 1 ELSE 0 END) as active_students,
            SUM(CASE WHEN s.status = 'Cancelled' THEN 1 ELSE 0 END) as cancelled_students,
            SUM(CASE WHEN s.student_type = 'Day Scholar' AND s.status != 'Cancelled' THEN 1 ELSE 0 END) as day_scholars,
            SUM(CASE WHEN s.student_type = 'Residential' AND s.status != 'Cancelled' THEN 1 ELSE 0 END) as residentials,
            COALESCE(SUM(CASE WHEN s.status != 'Cancelled' THEN s.final_agreed_fee ELSE 0.0 END), 0.0) as total_agreed_fee,
            COALESCE((
                SELECT SUM(p.amount_paid) 
                FROM payments p 
                JOIN students st ON p.student_id = st.id 
                WHERE st.class_name = s.class_name AND st.status != 'Cancelled'
            ), 0.0) as total_collected
        FROM students s
        WHERE 1=1
    """
    sum_params = []
    if branch and branch != 'All':
        sum_query += " AND s.branch = ?"
        sum_params.append(branch)

    sum_query += """
        GROUP BY s.class_name
        ORDER BY 
            CASE 
                WHEN s.class_name = 'PP1' THEN 1
                WHEN s.class_name = 'PP2' THEN 2
                WHEN s.class_name = 'Class 1' THEN 3
                WHEN s.class_name = 'Class 2' THEN 4
                WHEN s.class_name = 'Class 3' THEN 5
                WHEN s.class_name = 'Class 4' THEN 6
                WHEN s.class_name = 'Class 5' THEN 7
                WHEN s.class_name = 'Class 6' THEN 8
                WHEN s.class_name = 'Class 7' THEN 9
                WHEN s.class_name = 'Class 8' THEN 10
                WHEN s.class_name = 'Class 9' THEN 11
                WHEN s.class_name = 'Class 10' THEN 12
                ELSE 99 
            END ASC
    """
    summary_rows = conn.execute(sum_query, tuple(sum_params)).fetchall()

    class_summaries = []
    for r in summary_rows:
        row_dict = dict_from_row(r)
        row_dict['total_balance'] = max(0.0, row_dict['total_agreed_fee'] - row_dict['total_collected'])
        class_summaries.append(row_dict)

    # Detailed list query with optional filters
    query = """
        SELECT s.*,
            COALESCE((SELECT SUM(amount_paid) FROM payments WHERE student_id = s.id), 0.0) as total_paid,
            (s.final_agreed_fee - COALESCE((SELECT SUM(amount_paid) FROM payments WHERE student_id = s.id), 0.0)) as balance_due,
            (SELECT COUNT(*) FROM payments WHERE student_id = s.id) as payment_count,
            (SELECT receipt_token FROM payments WHERE student_id = s.id ORDER BY id DESC LIMIT 1) as latest_receipt_token
        FROM students s
        WHERE 1=1
    """
    params = []
    if branch and branch != 'All':
        query += " AND s.branch = ?"
        params.append(branch)
    if class_name and class_name != 'All':
        query += " AND s.class_name = ?"
        params.append(class_name)
    if section and section != 'All':
        query += " AND s.section = ?"
        params.append(section)
    if status and status != 'All':
        query += " AND s.status = ?"
        params.append(status)

    query += """
        ORDER BY 
            CASE 
                WHEN s.class_name = 'PP1' THEN 1
                WHEN s.class_name = 'PP2' THEN 2
                WHEN s.class_name = 'Class 1' THEN 3
                WHEN s.class_name = 'Class 2' THEN 4
                WHEN s.class_name = 'Class 3' THEN 5
                WHEN s.class_name = 'Class 4' THEN 6
                WHEN s.class_name = 'Class 5' THEN 7
                WHEN s.class_name = 'Class 6' THEN 8
                WHEN s.class_name = 'Class 7' THEN 9
                WHEN s.class_name = 'Class 8' THEN 10
                WHEN s.class_name = 'Class 9' THEN 11
                WHEN s.class_name = 'Class 10' THEN 12
                ELSE 99 
            END ASC,
            s.section ASC,
            CAST(s.roll_no AS INTEGER) ASC,
            s.student_name ASC
    """
    students_rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()

    students = [dict_from_row(r) for r in students_rows]

    # Calculate overall aggregates for the filtered view
    total_enrolled = len(students)
    active_count = sum(1 for s in students if s.get('status') != 'Cancelled')
    total_agreed = sum(s.get('final_agreed_fee', 0.0) for s in students if s.get('status') != 'Cancelled')
    total_paid = sum(s.get('total_paid', 0.0) for s in students if s.get('status') != 'Cancelled')
    total_balance = max(0.0, total_agreed - total_paid)

    return {
        "class_summaries": class_summaries,
        "students": students,
        "stats": {
            "total_enrolled": total_enrolled,
            "active_count": active_count,
            "total_agreed": total_agreed,
            "total_paid": total_paid,
            "total_balance": total_balance
        }
    }

@app.get("/api/students/{student_id}/statement")
def get_student_statement(student_id: int):
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not student:
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")

    payments = conn.execute("""
        SELECT * FROM payments WHERE student_id = ? ORDER BY id ASC
    """, (student_id,)).fetchall()

    pending_change = conn.execute("""
        SELECT * FROM admission_change_requests 
        WHERE student_id = ? AND status = 'Pending' 
        ORDER BY id DESC LIMIT 1
    """, (student_id,)).fetchone()

    conn.close()
    total_paid = sum(p['amount_paid'] for p in payments)
    balance = student['final_agreed_fee'] - total_paid

    pending_change_dict = dict_from_row(pending_change)
    if pending_change_dict:
        pending_change_dict['proposed_data'] = json.loads(pending_change_dict['proposed_data'] or '{}')

    return {
        "student": dict_from_row(student),
        "payments": [dict_from_row(p) for p in payments],
        "total_paid": total_paid,
        "balance_due": max(0.0, balance),
        "pending_change": pending_change_dict
    }

@app.post("/api/payments/collect")
def collect_payment(req: PaymentCreateRequest, cashier_user: str = Query("frontdesk")):
    conn = get_db()
    cursor = conn.cursor()

    student = cursor.execute("SELECT * FROM students WHERE id = ?", (req.student_id,)).fetchone()
    if not student:
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")

    # Get previously paid
    prev = cursor.execute("SELECT COALESCE(SUM(amount_paid), 0.0) as total, COUNT(*) as count FROM payments WHERE student_id = ?", (req.student_id,)).fetchone()
    previously_paid = prev['total']
    installment_no = prev['count'] + 1

    total_agreed = student['final_agreed_fee']
    current_balance = max(0.0, total_agreed - previously_paid)

    if current_balance <= 0.0:
        conn.close()
        raise HTTPException(status_code=400, detail=f"This student has already cleared the full agreed fee of ₹ {total_agreed:,.0f}. Balance Due is ₹ 0.")

    if req.amount_paid > current_balance:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Payment amount (₹ {req.amount_paid:,.0f}) cannot exceed the remaining balance due of ₹ {current_balance:,.0f} (Agreed Total: ₹ {total_agreed:,.0f}).")

    new_balance = max(0.0, current_balance - req.amount_paid)

    student_branch = student['branch'] if 'branch' in student.keys() and student['branch'] else "Branch 1"
    b_code = "B2" if ("2" in str(student_branch)) else "B1"
    receipt_no = f"KHS{b_code}-{datetime.now().strftime('%Y')}-{random.randint(10000, 99999)}"
    token = secrets.token_urlsafe(16)
    expires = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")

    label = req.installment_label if req.installment_label else f"Installment #{installment_no}"

    cursor.execute("""
        INSERT INTO payments (
            receipt_no, student_id, admission_no, branch, installment_no, installment_label,
            total_agreed_fee, previously_paid, amount_paid, balance_due,
            payment_mode, transaction_ref, collected_by, payment_date,
            receipt_token, token_expires_at, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        receipt_no, req.student_id, student['admission_no'], student_branch, installment_no, label,
        total_agreed, previously_paid, req.amount_paid, new_balance,
        req.payment_mode, req.transaction_ref, cashier_user,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), token, expires, req.notes
    ))
    payment_id = cursor.lastrowid
    conn.commit()

    # Formulate messages for WhatsApp
    parent_msg = (
        f"Dear Parent, received Rs. {req.amount_paid:,.0f} towards {student['student_name']}'s school fee "
        f"({label}). Total Agreed: Rs. {total_agreed:,.0f}, Balance Due: Rs. {new_balance:,.0f}. "
        f"Download Receipt (valid for 48 hrs): http://localhost:8000/receipt/{token} - Kranthi High School"
    )

    admin_msg = (
        f"Fee Alert: Rs. {req.amount_paid:,.0f} collected for {student['student_name']} ({student['class_name']}-{student['section']}) "
        f"by {cashier_user}. Mode: {req.payment_mode}. Remaining Balance: Rs. {new_balance:,.0f}."
    )

    conn.close()

    # Automatically queue payment for real-time cloud sync
    try:
        import cloud_sync
        payment_payload = {
            "receipt_no": receipt_no,
            "admission_no": student['admission_no'],
            "branch": student_branch,
            "installment_no": installment_no,
            "installment_label": label,
            "total_agreed_fee": total_agreed,
            "previously_paid": previously_paid,
            "amount_paid": req.amount_paid,
            "balance_due": new_balance,
            "payment_mode": req.payment_mode,
            "transaction_ref": req.transaction_ref,
            "collected_by": cashier_user,
            "payment_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "receipt_token": token,
            "token_expires_at": expires,
            "notes": req.notes
        }
        cloud_sync.queue_transaction_locally('payment', receipt_no, 'INSERT', payment_payload, student_branch)

        # Attempt background push if cloud sync is enabled
        cfg = cloud_sync.get_sync_config()
        if cfg.get("enabled"):
            cloud_sync.push_local_outbox_to_cloud()
    except Exception as e:
        print(f"[CLOUD SYNC PAYMENT HOOK NOTICE]: {e}")

    # Record audit log for Fee Payment
    try:
        sess_id = (req.session_id or f"sess_{cashier_user}").strip()
        record_activity_log(
            session_id=sess_id,
            username=cashier_user,
            full_name=cashier_user,
            role="T3", # Default or staff cashier
            branch=student_branch,
            action_type="FEE_PAYMENT",
            action_details=f"Collected Rs. {req.amount_paid:,.0f} ({label}) for {student['student_name']} ({student['admission_no']}) via {req.payment_mode}",
            entity_id=receipt_no,
            amount=req.amount_paid
        )
    except Exception as e:
        print(f"[AUDIT LOG ERROR PAYMENT]: {e}")

    return {
        "status": "success",
        "payment_id": payment_id,
        "receipt_no": receipt_no,
        "receipt_token": token,
        "installment_no": installment_no,
        "amount_paid": req.amount_paid,
        "balance_due": new_balance,
        "parent_phone": student['parent_phone'],
        "parent_msg": parent_msg,
        "admin_msg": admin_msg
    }

# ----------------- RECEIPT DETAILS & 48-HR VERIFICATION -----------------

@app.get("/api/receipt/{token}")
def get_receipt_data(token: str):
    conn = get_db()
    payment = conn.execute("""
        SELECT p.*, s.student_name, s.class_name, s.section, s.branch, s.student_type, s.has_transport, s.bus_route,
               s.parent_name, s.parent_phone, s.discount_amount
        FROM payments p
        JOIN students s ON p.student_id = s.id
        WHERE p.receipt_token = ?
    """, (token,)).fetchone()

    if not payment:
        conn.close()
        raise HTTPException(status_code=404, detail="Invalid receipt link or token.")

    payment_dict = dict_from_row(payment)

    # Resolve Cashier's First Name instead of raw phone number or system username
    collected_by_raw = payment['collected_by'] or 'Billing Desk'
    cashier_user = conn.execute("""
        SELECT full_name FROM users WHERE username = ? OR phone = ?
    """, (str(collected_by_raw), str(collected_by_raw))).fetchone()
    conn.close()

    if cashier_user and cashier_user['full_name']:
        full_n = cashier_user['full_name'].strip()
        # Take first word / first name (e.g. "NAVEEN" from "NAVEEN KUMAR")
        first_name = full_n.split()[0].title()
        payment_dict['collected_by'] = first_name
    elif str(collected_by_raw).lower() in ['admin', 'superadmin']:
        payment_dict['collected_by'] = 'Admin'
    elif str(collected_by_raw).lower() == 'frontdesk':
        payment_dict['collected_by'] = 'Front Desk'
    else:
        # If string has spaces or words, take first word title-cased
        payment_dict['collected_by'] = str(collected_by_raw).split()[0].title()

    exp_dt = datetime.strptime(payment['token_expires_at'], "%Y-%m-%d %H:%M:%S")
    is_expired = datetime.now() > exp_dt

    return {
        "payment": payment_dict,
        "is_expired": is_expired,
        "expires_in_hours": max(0, int((exp_dt - datetime.now()).total_seconds() / 3600))
    }

# ----------------- END OF DAY & SUMMARY REPORTS -----------------

@app.get("/api/reports/eod")
def get_eod_report(target_date: Optional[str] = None, branch: Optional[str] = None):
    if not target_date:
        target_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_db()
    query = """
        SELECT p.*, s.student_name, s.class_name, s.section, s.branch as student_branch
        FROM payments p
        JOIN students s ON p.student_id = s.id
        WHERE date(p.payment_date) = date(?)
    """
    params = [target_date]
    if branch and branch != 'All':
        query += " AND (p.branch = ? OR s.branch = ?)"
        params.extend([branch, branch])

    query += " ORDER BY p.id DESC"
    rows = conn.execute(query, tuple(params)).fetchall()

    total_amount = sum(r['amount_paid'] for r in rows)
    cash_total = sum(r['amount_paid'] for r in rows if r['payment_mode'] == 'Cash')
    upi_total = sum(r['amount_paid'] for r in rows if r['payment_mode'] == 'UPI')
    bank_total = sum(r['amount_paid'] for r in rows if r['payment_mode'] in ['Bank Transfer', 'Cheque'])

    stud_count_q = "SELECT COUNT(*) FROM students WHERE 1=1"
    stud_count_params = []
    if branch and branch != 'All':
        stud_count_q += " AND branch = ?"
        stud_count_params.append(branch)
    total_students = conn.execute(stud_count_q, tuple(stud_count_params)).fetchone()[0]

    pend_q = """
        SELECT SUM(
            s.final_agreed_fee - (
                SELECT COALESCE(SUM(p.amount_paid), 0.0)
                FROM payments p
                WHERE p.student_id = s.id
            )
        )
        FROM students s
        WHERE s.status != 'Cancelled'
    """
    pend_params = []
    if branch and branch != 'All':
        pend_q += " AND s.branch = ?"
        pend_params.append(branch)

    overall_pending = conn.execute(pend_q, tuple(pend_params)).fetchone()[0] or 0.0

    conn.close()

    branch_label = f" ({branch})" if branch and branch != 'All' else " (All Branches)"
    summary_msg = (
        f"KHS Daily Collection Summary{branch_label} - {target_date} (4:30 PM IST)\n"
        f"-----------------------------------------\n"
        f"Total Receipts: {len(rows)}\n"
        f"Total Collected: Rs. {total_amount:,.0f}\n"
        f"• Cash: Rs. {cash_total:,.0f}\n"
        f"• UPI: Rs. {upi_total:,.0f}\n"
        f"• Cheque/NEFT: Rs. {bank_total:,.0f}\n"
        f"-----------------------------------------\n"
        f"Overall Pending Balance: Rs. {overall_pending:,.0f}"
    )

    return {
        "target_date": target_date,
        "branch": branch or "All",
        "total_receipts": len(rows),
        "total_amount": total_amount,
        "cash_total": cash_total,
        "upi_total": upi_total,
        "bank_total": bank_total,
        "total_students": total_students,
        "overall_pending": overall_pending,
        "summary_msg": summary_msg,
        "transactions": [dict_from_row(r) for r in rows]
    }

# ----------------- BULK EXCEL STUDENT IMPORT -----------------
import io
import openpyxl
from fastapi import UploadFile, File

@app.get("/api/students/download-template")
def download_student_template():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Existing_Students"

    headers = [
        "Admission_No", "Roll_No", "Student_Name", "Branch", "Gender", "Class_Name", "Section",
        "Student_Type", "Has_Transport", "Transport_Fee", "Bus_Route",
        "Parent_Name", "Parent_Phone", "Parent_Address",
        "Agreed_Annual_Fee", "Past_Amount_Already_Paid"
    ]
    ws.append(headers)

    # Sample rows for guidance
    samples = [
        ["KHS-2026-101", "1", "Rahul Reddy", "Male", "Class 5", "A", "Day Scholar", "No", 0, "", "Venkatesh Reddy", "9876501234", "Hyderabad", 40000, 15000],
        ["KHS-2026-102", "2", "Priya Sharma", "Female", "Class 8", "B", "Day Scholar", "Yes", 12000, "Route #4", "Suresh Sharma", "9876501235", "Secunderabad", 62000, 20000],
        ["KHS-2026-103", "3", "Sai Teja", "Male", "Class 10", "A", "Residential", "No", 0, "", "Narayana Swamy", "9876501236", "Warangal", 84000, 30000],
    ]
    for row in samples:
        ws.append(row)

    # Style header row
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = openpyxl.styles.Font(bold=True, color="FFFFFF")
        cell.fill = openpyxl.styles.PatternFill("solid", fgColor="4F46E5")

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=KHS_Existing_Students_Template.xlsx"}
    )

@app.post("/api/students/bulk-import")
async def bulk_import_students(file: UploadFile = File(...), operator_user: str = Query("admin")):
    contents = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
    ws = wb.active

    conn = get_db()
    cursor = conn.cursor()

    # Check if the operator is an Admin (T1 or T2) or Frontdesk Staff (T3)
    user_row = cursor.execute("SELECT role FROM users WHERE username = ? OR phone = ?", (operator_user, operator_user)).fetchone()
    is_admin = bool(user_row and user_row['role'] in ['T1', 'T2']) or (operator_user.lower() in ['admin', 'khs_admin'])

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        conn.close()
        raise HTTPException(status_code=400, detail="The Excel sheet has no data rows.")

    parsed_students = []
    skipped_count = 0

    for idx, row in enumerate(rows[1:], start=2):
        if not row or not row[0]: # Skip blank rows
            continue

        adm_no = str(row[0]).strip()
        roll_no = str(row[1] or "").strip()
        sname = str(row[2] or "").strip()
        
        # Detect if row has Branch at index 3 or standard Gender
        # New format: AdmNo, Roll, Name, Branch, Gender, Class, Sec, Stype, HasTrans, TransFee, BusRoute, PName, PPhone, PAddress, AgreedFee, PastPaid
        if len(row) > 15 and ('branch' in str(row[3] or '').lower() or str(row[3] or '').strip() in ['Branch 1', 'Branch 2']):
            branch_val = str(row[3] or "Branch 1").strip()
            gender = str(row[4] or "Male").strip()
            cname = str(row[5] or "Class 1").strip()
            section = str(row[6] or "A").strip()
            stype = str(row[7] or "Day Scholar").strip()
            has_trans_str = str(row[8] or "No").strip().lower()
            try:
                trans_fee = float(row[9] or 0.0)
            except:
                trans_fee = 0.0
            bus_route = str(row[10] or "").strip()
            pname = str(row[11] or "Parent").strip()
            pphone = str(row[12] or "").strip()
            paddress = str(row[13] or "").strip()
            agreed_idx = 14
            paid_idx = 15
        else:
            # Fallback legacy format (15 cols)
            branch_val = "Branch 1"
            gender = str(row[3] or "Male").strip()
            cname = str(row[4] or "Class 1").strip()
            section = str(row[5] or "A").strip()
            stype = str(row[6] or "Day Scholar").strip()
            has_trans_str = str(row[7] or "No").strip().lower()
            try:
                trans_fee = float(row[8] or 0.0)
            except:
                trans_fee = 0.0
            bus_route = str(row[9] or "").strip()
            pname = str(row[10] or "Parent").strip()
            pphone = str(row[11] or "").strip()
            paddress = str(row[12] or "").strip()
            agreed_idx = 13
            paid_idx = 14

        if 'res' in stype.lower():
            stype = "Residential"
        else:
            stype = "Day Scholar"

        has_trans = 1 if ('yes' in has_trans_str or 'y' == has_trans_str or '1' == has_trans_str) else 0

        # Check existing admission
        existing = cursor.execute("SELECT id FROM students WHERE admission_no = ?", (adm_no,)).fetchone()
        if existing:
            skipped_count += 1
            continue

        # Fees calculation
        fee_struct = cursor.execute("SELECT total_base_fee FROM fee_structures WHERE class_name = ? AND student_type = ?", (cname, stype)).fetchone()
        base_fee = fee_struct['total_base_fee'] if fee_struct else 30000.0
        default_agreed = base_fee + (trans_fee if has_trans else 0.0)

        try:
            custom_agreed = float(row[agreed_idx]) if len(row) > agreed_idx and row[agreed_idx] is not None and float(row[agreed_idx]) > 0 else default_agreed
        except:
            custom_agreed = default_agreed

        try:
            past_paid = float(row[paid_idx]) if len(row) > paid_idx and row[paid_idx] is not None else 0.0
        except:
            past_paid = 0.0

        parsed_students.append({
            "admission_no": adm_no,
            "roll_no": roll_no,
            "student_name": sname,
            "branch": branch_val,
            "gender": gender,
            "class_name": cname,
            "section": section,
            "student_type": stype,
            "has_transport": has_trans,
            "transport_fee": trans_fee,
            "bus_route": bus_route,
            "parent_name": pname,
            "parent_phone": pphone,
            "address": paddress,
            "agreed_fee": custom_agreed,
            "past_paid": past_paid
        })

    if not parsed_students:
        conn.close()
        raise HTTPException(status_code=400, detail=f"No valid new students found in Excel sheet ({skipped_count} skipped as duplicate admission numbers).")

    # If operator is T3 Staff, do NOT import directly: Submit for Admin Approval!
    if not is_admin:
        cursor.execute("""
            INSERT INTO bulk_import_batches (
                file_name, total_rows, valid_rows, student_data_json, uploaded_by, status
            ) VALUES (?, ?, ?, ?, ?, 'Pending')
        """, (file.filename or "student_list.xlsx", len(rows) - 1, len(parsed_students), json.dumps(parsed_students), operator_user))
        batch_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {
            "status": "pending_approval",
            "needs_approval": True,
            "batch_id": batch_id,
            "valid_count": len(parsed_students),
            "skipped_count": skipped_count,
            "message": f"Excel file uploaded ({len(parsed_students)} students parsed). Submitted to School Admin for verification & approval before importing into database."
        }

    # If Admin, process immediately
    imported_count = 0
    for s in parsed_students:
        s_branch = s.get('branch', 'Branch 1')
        cursor.execute("""
            INSERT INTO students (
                admission_no, roll_no, student_name, branch, gender, class_name, section,
                academic_year, student_type, has_transport, transport_fee, bus_route,
                parent_name, parent_phone, address, standard_fee, discount_amount,
                final_agreed_fee, discount_status, admission_date, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '2026-2027', ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, 'Approved', CURRENT_DATE, ?)
        """, (
            s['admission_no'], s['roll_no'], s['student_name'], s_branch, s['gender'], s['class_name'], s['section'],
            s['student_type'], s['has_transport'], s['transport_fee'], s['bus_route'],
            s['parent_name'], s['parent_phone'], s['address'], s['agreed_fee'], s['agreed_fee'], operator_user
        ))
        student_id = cursor.lastrowid

        if s['past_paid'] > 0:
            rec_no = f"KHS-PAST-{random.randint(10000, 99999)}"
            tok = secrets.token_urlsafe(16)
            exp = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
            bal = max(0.0, s['agreed_fee'] - s['past_paid'])

            cursor.execute("""
                INSERT INTO payments (
                    receipt_no, student_id, admission_no, branch, installment_no, installment_label,
                    total_agreed_fee, previously_paid, amount_paid, balance_due,
                    payment_mode, transaction_ref, collected_by, payment_date,
                    receipt_token, token_expires_at, notes
                ) VALUES (?, ?, ?, ?, 1, 'Previous Installments (Carry Forward)', ?, 0.0, ?, ?, 'Cash', 'EXCEL-IMPORT', ?, CURRENT_TIMESTAMP, ?, ?, 'Imported from past school records')
            """, (rec_no, student_id, s['admission_no'], s_branch, s['agreed_fee'], s['past_paid'], bal, operator_user, tok, exp))

        imported_count += 1

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "needs_approval": False,
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "message": f"Successfully imported {imported_count} students into database ({skipped_count} skipped duplicates)."
    }

@app.get("/api/import-batches/pending")
def get_pending_import_batches():
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM bulk_import_batches 
        WHERE status = 'Pending' 
        ORDER BY id DESC
    """).fetchall()
    conn.close()
    
    batches = []
    for r in rows:
        b = dict_from_row(r)
        try:
            b['student_data'] = json.loads(b['student_data_json'])
        except:
            b['student_data'] = []
        batches.append(b)
    return batches

@app.post("/api/import-batches/action")
def action_import_batch(req: BulkImportBatchActionRequest, approver_user: str = Query("admin")):
    conn = get_db()
    cursor = conn.cursor()

    batch = cursor.execute("SELECT * FROM bulk_import_batches WHERE id = ?", (req.batch_id,)).fetchone()
    if not batch:
        conn.close()
        raise HTTPException(status_code=404, detail="Import batch not found.")

    if batch['status'] != 'Pending':
        conn.close()
        raise HTTPException(status_code=400, detail=f"This import batch is already {batch['status']}.")

    if req.action == 'Reject':
        cursor.execute("""
            UPDATE bulk_import_batches 
            SET status = 'Rejected', admin_remarks = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (req.admin_remarks or "Rejected by Admin", approver_user, req.batch_id))
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Bulk import batch rejected."}

    # Action is Approve -> Insert all students into students and payments tables!
    try:
        students = json.loads(batch['student_data_json'])
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail="Failed to decode batch student data.")

    imported_count = 0
    skipped_count = 0

    for s in students:
        # Check duplicate
        existing = cursor.execute("SELECT id FROM students WHERE admission_no = ?", (s['admission_no'],)).fetchone()
        if existing:
            skipped_count += 1
            continue

        s_branch = s.get('branch', 'Branch 1')
        cursor.execute("""
            INSERT INTO students (
                admission_no, roll_no, student_name, branch, gender, class_name, section,
                academic_year, student_type, has_transport, transport_fee, bus_route,
                parent_name, parent_phone, address, standard_fee, discount_amount,
                final_agreed_fee, discount_status, admission_date, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '2026-2027', ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, 'Approved', CURRENT_DATE, ?)
        """, (
            s['admission_no'], s['roll_no'], s['student_name'], s_branch, s['gender'], s['class_name'], s['section'],
            s['student_type'], s['has_transport'], s['transport_fee'], s['bus_route'],
            s['parent_name'], s['parent_phone'], s['address'], s['agreed_fee'], s['agreed_fee'], batch['uploaded_by']
        ))
        student_id = cursor.lastrowid

        if s['past_paid'] > 0:
            rec_no = f"KHS-PAST-{random.randint(10000, 99999)}"
            tok = secrets.token_urlsafe(16)
            exp = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
            bal = max(0.0, s['agreed_fee'] - s['past_paid'])

            cursor.execute("""
                INSERT INTO payments (
                    receipt_no, student_id, admission_no, branch, installment_no, installment_label,
                    total_agreed_fee, previously_paid, amount_paid, balance_due,
                    payment_mode, transaction_ref, collected_by, payment_date,
                    receipt_token, token_expires_at, notes
                ) VALUES (?, ?, ?, ?, 1, 'Previous Installments (Carry Forward)', ?, 0.0, ?, ?, 'Cash', 'EXCEL-IMPORT', ?, CURRENT_TIMESTAMP, ?, ?, 'Imported from approved Excel batch')
            """, (rec_no, student_id, s['admission_no'], s_branch, s['agreed_fee'], s['past_paid'], bal, approver_user, tok, exp))

        imported_count += 1

    cursor.execute("""
        UPDATE bulk_import_batches 
        SET status = 'Approved', admin_remarks = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (req.admin_remarks or f"Approved and imported {imported_count} students", approver_user, req.batch_id))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "message": f"Batch approved! Successfully imported {imported_count} students into the school database."
    }

@app.post("/api/students/load-sample-students")
def load_sample_students(operator_user: str = Query("admin")):
    conn = get_db()
    cursor = conn.cursor()

    # Find highest sample index to avoid collision
    base_samples = [
        ("Rahul Reddy", "Male", "Class 5", "A", "Day Scholar", 0, 0.0, "", "Venkatesh Reddy", "9876543201", "Hyderabad", 40000.0, 15000.0),
        ("Ananya Sharma", "Female", "Class 8", "B", "Day Scholar", 1, 12000.0, "Route #4", "Suresh Sharma", "9876543202", "Secunderabad", 62000.0, 25000.0),
        ("Sai Teja Rao", "Male", "Class 10", "A", "Residential", 0, 0.0, "", "Narayana Swamy", "9876543203", "Warangal", 84000.0, 40000.0),
        ("Divya Patel", "Female", "Class 6", "A", "Day Scholar", 0, 0.0, "", "Kishore Patel", "9876543204", "Hyderabad", 43000.0, 20000.0),
        ("Manoj Kumar", "Male", "Class 9", "A", "Day Scholar", 1, 10000.0, "Route #2", "Srinivas Rao", "9876543205", "Dilsukhnagar", 64000.0, 30000.0),
    ]

    # Find the next free sequence number
    existing_rows = cursor.execute("SELECT admission_no FROM students WHERE admission_no LIKE 'KHS-2026-%'").fetchall()
    existing_nums = set()
    for r in existing_rows:
        try:
            val = int(r[0].replace("KHS-2026-", ""))
            existing_nums.add(val)
        except:
            pass

    next_num = 101
    while any(next_num + i in existing_nums for i in range(5)):
        next_num += 10

    added = 0
    added_names = []

    for idx, (sname, gndr, cname, sec, stype, has_tr, tr_fee, b_route, pname, pphone, paddr, agreed, past_pd) in enumerate(base_samples):
        adm_no = f"KHS-2026-{next_num + idx}"
        r_no = str(idx + 1)

        cursor.execute("""
            INSERT INTO students (
                admission_no, roll_no, student_name, gender, class_name, section,
                academic_year, student_type, has_transport, transport_fee, bus_route,
                parent_name, parent_phone, address, standard_fee, discount_amount,
                final_agreed_fee, discount_status, admission_date, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, '2026-2027', ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, 'Approved', CURRENT_DATE, ?)
        """, (
            adm_no, r_no, sname.upper(), gndr, cname, sec,
            stype, has_tr, tr_fee, b_route,
            pname.upper(), pphone, paddr, agreed, agreed, operator_user
        ))
        s_id = cursor.lastrowid

        if past_pd > 0:
            rec_no = f"KHS-PAST-{random.randint(10000, 99999)}"
            tok = secrets.token_urlsafe(16)
            exp = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
            bal = max(0.0, agreed - past_pd)

            cursor.execute("""
                INSERT INTO payments (
                    receipt_no, student_id, admission_no, installment_no, installment_label,
                    total_agreed_fee, previously_paid, amount_paid, balance_due,
                    payment_mode, transaction_ref, collected_by, payment_date,
                    receipt_token, token_expires_at, notes
                ) VALUES (?, ?, ?, 1, 'Previous Installments (Carry Forward)', ?, 0.0, ?, ?, 'Cash', 'SAMPLE-DATA', ?, CURRENT_TIMESTAMP, ?, ?, 'Sample student past fee')
            """, (rec_no, s_id, adm_no, agreed, past_pd, bal, operator_user, tok, exp))

        added += 1
        added_names.append(f"{sname.upper()} ({adm_no})")

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "added_count": added,
        "message": f"Successfully generated {added} sample students ({', '.join(added_names)})! You can find them in the Fee Collection tab."
    }

# ----------------- BACKUP DATABASE & AUTOMATED SAFEGUARDS -----------------
import shutil

BACKUP_DIR = os.path.join(STATIC_DIR, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

def create_auto_backup(trigger_reason="shutdown"):
    db_path = os.path.join(STATIC_DIR, "khs_billing.db")
    if os.path.exists(db_path):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dest = os.path.join(BACKUP_DIR, f"khs_billing_auto_{trigger_reason}_{timestamp}.db")
        try:
            shutil.copy2(db_path, dest)
            print(f"[BACKUP] Auto-saved database backup to: {dest}")
            # Keep only latest 10 auto-backups to prevent disk clutter
            all_backups = sorted([os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR) if f.endswith(".db")], key=os.path.getmtime)
            while len(all_backups) > 10:
                oldest = all_backups.pop(0)
                try:
                    os.remove(oldest)
                except:
                    pass

            # Sync to Google Drive on shutdown or startup (if auto_sync_eod enabled)
            if trigger_reason in ["shutdown", "startup"]:
                try:
                    gdrive_cfg = gdrive_sync.get_gdrive_config()
                    if gdrive_cfg.get("auto_sync_eod", True) and gdrive_sync.is_gdrive_configured()[0]:
                        print(f"[GDRIVE] Auto-uploading {trigger_reason} database snapshot to Google Drive...")
                        gdrive_res = gdrive_sync.upload_database_to_drive(dest)
                        print(f"[GDRIVE] {trigger_reason} snapshot upload result: {gdrive_res.get('message', gdrive_res)}")
                except Exception as ge:
                    print(f"[GDRIVE {trigger_reason} ERROR]: {ge}")

        except Exception as e:
            print(f"[BACKUP ERROR] Failed to create auto backup: {e}")

@app.on_event("startup")
def on_app_startup():
    create_auto_backup("startup")

@app.on_event("shutdown")
def on_app_shutdown():
    create_auto_backup("shutdown")

@app.get("/api/backup/download")
def download_backup():
    db_path = os.path.join(STATIC_DIR, "khs_billing.db")
    if os.path.exists(db_path):
        backup_name = f"khs_billing_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        return FileResponse(db_path, filename=backup_name, media_type="application/octet-stream")
    raise HTTPException(status_code=404, detail="Database file not found")

@app.post("/api/backup/restore")
async def restore_database(file: UploadFile = File(...), operator_user: str = Query("admin")):
    # Verify Admin privilege
    conn = get_db()
    cursor = conn.cursor()
    user_row = cursor.execute("SELECT role FROM users WHERE username = ? OR phone = ?", (operator_user, operator_user)).fetchone()
    conn.close()

    is_admin = bool(user_row and user_row['role'] in ['T1', 'T2']) or (operator_user.lower() in ['admin', 'khs_admin'])
    if not is_admin:
        raise HTTPException(status_code=403, detail="Access Denied: Only School Admins are authorized to restore the database.")

    contents = await file.read()
    if len(contents) < 100:
        raise HTTPException(status_code=400, detail="Invalid database backup file. File is empty or corrupt.")

    # Safety: auto-save current database before replacing it!
    create_auto_backup("pre_restore")

    db_path = os.path.join(STATIC_DIR, "khs_billing.db")
    temp_path = os.path.join(STATIC_DIR, "khs_billing_temp.db")

    try:
        # Write to temporary file first to test SQLite validity
        with open(temp_path, "wb") as f:
            f.write(contents)

        import sqlite3
        test_conn = sqlite3.connect(temp_path)
        test_cur = test_conn.cursor()
        # Verify required tables exist in the uploaded file
        required_tables = {'students', 'payments', 'users', 'fee_structures'}
        found_tables = {row[0] for row in test_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        test_conn.close()

        if not required_tables.issubset(found_tables):
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid KHS Billing database (missing core school tables).")

        # Atomic replacement
        shutil.move(temp_path, db_path)

        return {
            "status": "success",
            "message": "Database backup restored successfully! All student records, payments, and fee registers have been recovered."
        }
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Failed to restore database: {str(e)}")

# ----------------- GOOGLE DRIVE CLOUD SYNC APIS -----------------
import gdrive_sync
from google_auth_oauthlib.flow import InstalledAppFlow

@app.get("/api/gdrive/status")
def get_gdrive_status():
    configured, msg = gdrive_sync.is_gdrive_configured()
    config = gdrive_sync.get_gdrive_config()
    return {
        "configured": configured,
        "status_message": msg,
        "folder_id": config.get("folder_id", ""),
        "auto_sync_eod": config.get("auto_sync_eod", True),
        "has_token": os.path.exists(gdrive_sync.TOKEN_FILE),
        "has_client_secret": os.path.exists(gdrive_sync.CLIENT_SECRET_FILE)
    }

@app.get("/api/gdrive/auth-url")
def get_gdrive_auth_url():
    if not os.path.exists(gdrive_sync.CLIENT_SECRET_FILE):
        raise HTTPException(status_code=400, detail="client_secret.json not found.")
    
    flow = InstalledAppFlow.from_client_secrets_file(
        gdrive_sync.CLIENT_SECRET_FILE,
        scopes=gdrive_sync.SCOPES,
        redirect_uri="http://localhost:8000/api/gdrive/oauth2callback"
    )
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    return {"auth_url": auth_url}

@app.get("/api/gdrive/oauth2callback", response_class=HTMLResponse)
def gdrive_oauth_callback(code: str = Query(...)):
    flow = InstalledAppFlow.from_client_secrets_file(
        gdrive_sync.CLIENT_SECRET_FILE,
        scopes=gdrive_sync.SCOPES,
        redirect_uri="http://localhost:8000/api/gdrive/oauth2callback"
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    with open(gdrive_sync.TOKEN_FILE, "w") as token:
        token.write(creds.to_json())
    
    # Immediately trigger an initial test backup into the folder
    test_res = gdrive_sync.upload_database_to_drive()

    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>Google Drive Connected</title></head>
    <body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; background: #f8fafc; margin: 0;">
      <div style="background: white; padding: 40px; border-radius: 16px; border: 1px solid #e2e8f0; text-align: center; max-width: 450px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
        <div style="font-size: 48px; color: #16a34a; margin-bottom: 16px;">&#10004;</div>
        <h2 style="color: #0f172a; margin: 0 0 8px 0;">Google Drive Connected!</h2>
        <p style="color: #64748b; font-size: 14px; margin-bottom: 24px;">Your KHS Billing backup is now authorized. Status: {test_res.get('message', 'Ready')}</p>
        <button onclick="window.close()" style="background: #1e1b4b; color: white; border: none; padding: 10px 20px; font-weight: bold; border-radius: 8px; cursor: pointer;">Close Window</button>
      </div>
    </body>
    </html>
    """

class GDriveConfigUpdate(BaseModel):
    folder_id: str
    auto_sync_eod: bool = True

@app.post("/api/gdrive/configure")
def update_gdrive_config(data: GDriveConfigUpdate, operator_user: str = Query("admin")):
    conn = get_db()
    cursor = conn.cursor()
    user_row = cursor.execute("SELECT role FROM users WHERE username = ? OR phone = ?", (operator_user, operator_user)).fetchone()
    conn.close()

    is_admin = bool(user_row and user_row['role'] in ['T1', 'T2']) or (operator_user.lower() in ['admin', 'khs_admin'])
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only Admins can configure Google Drive sync.")

    cfg = gdrive_sync.save_gdrive_config(data.folder_id, data.auto_sync_eod)
    return {"status": "success", "message": "Google Drive configuration saved successfully!", "config": cfg}

@app.post("/api/gdrive/sync-now")
def trigger_gdrive_sync(operator_user: str = Query("admin")):
    result = gdrive_sync.upload_database_to_drive()
    if result.get("status") != "success":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result

# ----------------- MULTI-BRANCH CLOUD SYNC APIS (TURSO / LIBSQL) -----------------
import cloud_sync

class CloudSyncConfigRequest(BaseModel):
    enabled: bool
    db_url: str
    auth_token: str
    branch: str = "Branch 1"
    auto_sync_interval_seconds: int = 30

@app.get("/api/cloud-sync/status")
def get_cloud_sync_status():
    cfg = cloud_sync.get_sync_config()
    conn = get_db()
    cur = conn.cursor()
    pending_count = cur.execute("SELECT COUNT(*) FROM sync_queue WHERE sync_status = 'pending'").fetchone()[0]
    synced_count = cur.execute("SELECT COUNT(*) FROM sync_queue WHERE sync_status = 'synced'").fetchone()[0]
    conn.close()

    return {
        "enabled": cfg.get("enabled", False),
        "db_url": cfg.get("db_url", ""),
        "has_token": bool(cfg.get("auth_token")),
        "branch": cfg.get("branch", "Branch 1"),
        "pending_outbox_count": pending_count,
        "synced_total_count": synced_count
    }

@app.post("/api/cloud-sync/configure")
def configure_cloud_sync(req: CloudSyncConfigRequest, operator_user: str = Query("admin")):
    conn = get_db()
    cursor = conn.cursor()
    user_row = cursor.execute("SELECT role FROM users WHERE username = ? OR phone = ?", (operator_user, operator_user)).fetchone()
    conn.close()

    is_admin = bool(user_row and user_row['role'] in ['T1', 'T2']) or (operator_user.lower() in ['admin', 'khs_admin'])
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only School Admins can configure Multi-Branch Cloud Sync.")

    cloud_sync.save_sync_config({
        "enabled": req.enabled,
        "provider": "turso_http",
        "db_url": req.db_url.strip(),
        "auth_token": req.auth_token.strip(),
        "branch": req.branch,
        "auto_sync_interval_seconds": req.auto_sync_interval_seconds
    })

    # If enabled and credentials provided, test and initialize remote tables
    if req.enabled and req.db_url and req.auth_token:
        ok, msg = cloud_sync.test_cloud_connection(req.db_url, req.auth_token)
        if not ok:
            return {"status": "warning", "message": f"Settings saved, but cloud connection test failed: {msg}"}
        
        # Initialize schema remotely
        cloud_sync.init_remote_schema_if_needed(req.db_url, req.auth_token)

    return {"status": "success", "message": "Multi-Branch Cloud Sync configured successfully!"}

@app.post("/api/cloud-sync/test")
def test_cloud_sync_connection(operator_user: str = Query("admin")):
    cfg = cloud_sync.get_sync_config()
    if not cfg.get("db_url") or not cfg.get("auth_token"):
        raise HTTPException(status_code=400, detail="Cloud Database URL and Auth Token are required.")
    
    ok, msg = cloud_sync.test_cloud_connection(cfg["db_url"], cfg["auth_token"])
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "success", "message": msg}

@app.post("/api/cloud-sync/sync-now")
def trigger_cloud_sync_now(operator_user: str = Query("admin")):
    res = cloud_sync.push_local_outbox_to_cloud()
    return res


# ----------------- FRONTEND ROUTES -----------------

@app.get("/", response_class=HTMLResponse)
def index_page():
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/receipt/{token}", response_class=HTMLResponse)
def receipt_page(token: str):
    with open(os.path.join(STATIC_DIR, "receipt.html"), "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
