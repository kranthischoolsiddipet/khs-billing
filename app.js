// Current State
let currentUser = null;
let currentStudent = null;
let searchDebounceTimer = null;
let pendingDiscountsList = [];

// Session ID Management for Audit & Activity Trail
function getOrCreateSessionId() {
  let sId = sessionStorage.getItem('khs_session_id');
  if (!sId) {
    sId = 'sess_' + Date.now() + '_' + Math.floor(1000 + Math.random() * 9000);
    sessionStorage.setItem('khs_session_id', sId);
  }
  return sId;
}

// Send session end event to backend
function sendSessionEndEvent(actionType, reason) {
  const sId = sessionStorage.getItem('khs_session_id');
  if (!currentUser || !sId) return;

  const payload = {
    session_id: sId,
    username: currentUser.username || currentUser.phone || 'unknown',
    action_type: actionType, // 'LOGOUT' or 'AUTO_TIMEOUT'
    action_details: reason || (actionType === 'LOGOUT' ? 'Manual user logout' : '15-minute inactivity auto logout')
  };

  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/auth/session-log', new Blob([JSON.stringify(payload)], { type: 'application/json' }));
    } else {
      fetch('/api/auth/session-log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true
      }).catch(() => {});
    }
  } catch (e) {
    console.error("Error logging session end:", e);
  }
}

// ================= INACTIVITY AUTO-LOGOUT (15 MINUTES) =================
const INACTIVITY_TIMEOUT_MS = 15 * 60 * 1000; // 15 Minutes
let inactivityTimer = null;

function resetInactivityTimer() {
  if (inactivityTimer) clearTimeout(inactivityTimer);
  // Only track inactivity if a user is currently logged in
  if (currentUser) {
    inactivityTimer = setTimeout(() => {
      handleAutoLogoutDueToInactivity();
    }, INACTIVITY_TIMEOUT_MS);
  }
}

function handleAutoLogoutDueToInactivity() {
  if (!currentUser) return;
  console.log("[SECURITY] Inactivity timeout reached (15m). Auto logging out user.");
  
  // Record session timeout in backend logs
  sendSessionEndEvent('AUTO_TIMEOUT', '15-minute inactivity session lock');
  sessionStorage.removeItem('khs_session_id');

  currentUser = null;
  localStorage.removeItem('khs_user');
  
  // Hide main UI and show login dialog
  const header = document.getElementById('appTopHeader');
  const main = document.getElementById('appMainContainer');
  if (header) header.classList.add('hidden');
  if (main) main.classList.add('hidden');

  document.getElementById('userNameDisplay').innerText = "Session Timed Out";
  openLoginModal();
  alert("Session Locked: You have been logged out due to 15 minutes of inactivity for security.");
}

function handleManualLogout() {
  if (confirm("Are you sure you want to log out?")) {
    // Record manual logout in backend logs
    sendSessionEndEvent('LOGOUT', 'User clicked manual Logout');
    sessionStorage.removeItem('khs_session_id');

    currentUser = null;
    localStorage.removeItem('khs_user');
    if (inactivityTimer) clearTimeout(inactivityTimer);

    // Hide main UI and show login dialog
    const header = document.getElementById('appTopHeader');
    const main = document.getElementById('appMainContainer');
    if (header) header.classList.add('hidden');
    if (main) main.classList.add('hidden');

    document.getElementById('userNameDisplay').innerText = "Logged Out";
    openLoginModal();
  }
}

// Background session validity check (detects remote forced logout by Admin)
setInterval(async () => {
  if (!currentUser || currentUser.role !== 'T3') return;
  const token = currentUser.session_token || '';
  if (!token) return;

  try {
    const res = await fetch(`/api/auth/session-check?username=${encodeURIComponent(currentUser.username)}&token=${encodeURIComponent(token)}`);
    const data = await res.json();
    if (data && data.active === false) {
      currentUser = null;
      localStorage.removeItem('khs_user');
      sessionStorage.removeItem('khs_session_id');
      if (inactivityTimer) clearTimeout(inactivityTimer);

      const header = document.getElementById('appTopHeader');
      const main = document.getElementById('appMainContainer');
      if (header) header.classList.add('hidden');
      if (main) main.classList.add('hidden');

      document.getElementById('userNameDisplay').innerText = "Session Ended";
      openLoginModal();
      alert("Session Terminated: " + (data.reason || "Your login session has been remotely logged out by Admin."));
    }
  } catch (e) {
    // Ignore network hiccups
  }
}, 6000);

// Attach activity listeners (mouse movement, clicks, keypress, touch)
['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'input'].forEach(evt => {
  window.addEventListener(evt, resetInactivityTimer, { passive: true });
});

// ================= INITIALIZATION & AUTH =================

document.addEventListener('DOMContentLoaded', () => {
  // Check localStorage for saved session
  const savedUser = localStorage.getItem('khs_user');
  if (savedUser) {
    currentUser = JSON.parse(savedUser);
    applyUserRoleUI();
    document.getElementById('loginModal').classList.add('hidden');
    const header = document.getElementById('appTopHeader');
    const main = document.getElementById('appMainContainer');
    if (header) header.classList.remove('hidden');
    if (main) main.classList.remove('hidden');
    resetInactivityTimer();
  } else {
    // Keep entire app hidden until authenticated
    const header = document.getElementById('appTopHeader');
    const main = document.getElementById('appMainContainer');
    if (header) header.classList.add('hidden');
    if (main) main.classList.add('hidden');
    openLoginModal();
  }

  // Pre-fill today's local date for EOD report and Audit Logs
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  const todayStr = `${year}-${month}-${day}`;
  if (document.getElementById('eodDatePicker')) document.getElementById('eodDatePicker').value = todayStr;
  if (document.getElementById('auditDatePicker')) document.getElementById('auditDatePicker').value = todayStr;

  // Initial data loads
  loadPendingDiscounts();
  recalculateBaseFee();
});

function openLoginModal() {
  document.getElementById('loginModal').classList.remove('hidden');
}

function setLoginPreset(username, password) {
  // Deprecated - presets removed for security
}

async function handleLoginSubmit(e) {
  e.preventDefault();
  const u = document.getElementById('loginUsername').value;
  const p = document.getElementById('loginPassword').value;
  const sId = getOrCreateSessionId();

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: p, session_id: sId })
    });

    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || 'Login failed');
      return;
    }

    currentUser = data.user;
    if (data.session_id) sessionStorage.setItem('khs_session_id', data.session_id);
    localStorage.setItem('khs_user', JSON.stringify(currentUser));
    document.getElementById('loginModal').classList.add('hidden');
    const header = document.getElementById('appTopHeader');
    const main = document.getElementById('appMainContainer');
    if (header) header.classList.remove('hidden');
    if (main) main.classList.remove('hidden');
    applyUserRoleUI();
    resetInactivityTimer();

    // Show welcome screen with big school logo on initial login
    switchTab('welcome');

    // Reload contextual data
    loadPendingDiscounts();
    loadFeeMaster();
    loadEodReport();
    if (currentUser.role === 'T1' || currentUser.role === 'T2') {
      loadStaffUsers();
    }
  } catch (err) {
    alert('Server error during login: ' + err);
  }
}

function applyUserRoleUI() {
  if (!currentUser) return;

  // Clean name display (remove any legacy '(T1/T2/T3)' that might be cached in localStorage)
  let cleanName = currentUser.full_name || '';
  cleanName = cleanName.replace(/\s*\([Tt][123]\)/g, '').trim();
  currentUser.full_name = cleanName;
  localStorage.setItem('khs_user', JSON.stringify(currentUser));

  const roleName = (currentUser.role === 'T1') ? 'Super Admin' : (currentUser.role === 'T2' ? 'Admin' : 'Billing Desk');
  document.getElementById('userNameDisplay').innerText = `${cleanName} (${roleName})`;

  const roleBadge = document.getElementById('roleBadge');
  if (roleBadge) {
    if (currentUser.role === 'T1') {
      roleBadge.className = "text-[10px] font-bold px-2 py-0.5 rounded-full uppercase bg-indigo-100 text-indigo-900";
      roleBadge.innerText = "Super Admin";
    } else if (currentUser.role === 'T2') {
      roleBadge.className = "text-[10px] font-bold px-2 py-0.5 rounded-full uppercase bg-purple-100 text-purple-900";
      roleBadge.innerText = "Admin";
    } else {
      roleBadge.className = "text-[10px] font-bold px-2 py-0.5 rounded-full uppercase bg-emerald-100 text-emerald-900";
      roleBadge.innerText = "Billing Desk";
    }
  }

  // Role-based visibility for tabs:
  // Strictly Admin-only tabs: discounts (Approvals), reports, staff
  // Import tab is now available to both T3 and Admin!
  const isAdmin = (currentUser.role === 'T1' || currentUser.role === 'T2');
  
  // Strictly Admin-only tabs: discounts (Approvals Queue), staff user management, and logs (Audit & Session logs)
  const adminOnlyTabIds = ['discounts', 'staff', 'logs', 'iplogs'];
  adminOnlyTabIds.forEach(tabId => {
    const tabBtn = document.getElementById(`tab-${tabId}`);
    if (tabBtn) {
      if (isAdmin) {
        tabBtn.classList.remove('hidden');
      } else {
        tabBtn.classList.add('hidden');
      }
    }
  });

  // Import tab is visible to everyone, but Generate Sample Students is strictly Admin-only!
  const sampleBtn = document.getElementById('btnGenerateSampleStudents');
  if (sampleBtn) {
    if (isAdmin) {
      sampleBtn.classList.remove('hidden');
    } else {
      sampleBtn.classList.add('hidden');
    }
  }

  const adminHeader = document.getElementById('adminNavGroupHeader');
  if (adminHeader) {
    if (isAdmin) {
      adminHeader.classList.remove('hidden');
    } else {
      adminHeader.classList.add('hidden');
    }
  }

  // Update Fee Structure label and table column based on role
  const feeLabel = document.getElementById('tabFeeMasterLabel');
  if (feeLabel) {
    feeLabel.innerText = isAdmin ? "Fee Master (Admin)" : "Fee Structure";
  }
  const thEdit = document.getElementById('thEditFeeMaster');
  if (thEdit) {
    thEdit.style.display = isAdmin ? '' : 'none';
  }

  // Financial Metrics Security: Agreed Annual Fee, Total Collected, Remaining Balance visible ONLY to Admin
  const cardAgreed = document.getElementById('cwCardAgreed');
  const cardPaid = document.getElementById('cwCardPaid');
  const cardBal = document.getElementById('cwCardBalance');
  const thAgreed = document.getElementById('thCwAgreed');
  const thPaid = document.getElementById('thCwPaid');
  const thBal = document.getElementById('thCwBalance');

  [cardAgreed, cardPaid, cardBal].forEach(el => {
    if (el) el.style.display = isAdmin ? '' : 'none';
  });
  [thAgreed, thPaid, thBal].forEach(el => {
    if (el) el.style.display = isAdmin ? '' : 'none';
  });

  // Re-render class-wise table if currently loaded so cells match role
  if (classWiseLoadedStudents && classWiseLoadedStudents.length > 0) {
    renderClassWiseTable(classWiseLoadedStudents);
  }

  // If Billing Desk was on an admin-only tab, redirect to collect
  const currentActiveSec = document.querySelector('div.flex-1 > section:not(.hidden)');
  if (!isAdmin && currentActiveSec && adminOnlyTabIds.some(id => currentActiveSec.id === `sec-${id}`)) {
    switchTab('collect');
  }
}

// ================= TAB NAVIGATION =================

function switchTab(tabId) {
  const isAdmin = currentUser && (currentUser.role === 'T1' || currentUser.role === 'T2');
  const adminOnlyTabIds = ['discounts', 'staff', 'logs', 'iplogs'];

  if (!isAdmin && adminOnlyTabIds.includes(tabId)) {
    alert("Access Denied: Only School Admins have permission to access this section.");
    switchTab('collect');
    return;
  }

  // Hide welcome banner whenever a specific tab is chosen
  const welcomeSec = document.getElementById('sec-welcome');
  if (welcomeSec) {
    if (tabId === 'welcome') {
      welcomeSec.classList.remove('hidden');
    } else {
      welcomeSec.classList.add('hidden');
    }
  }

  // Tab buttons
  ['welcome', 'collect', 'classwise', 'admit', 'feemaster', 'discounts', 'reports', 'import', 'staff', 'logs', 'iplogs'].forEach(id => {
    const btn = document.getElementById(`tab-${id}`);
    const sec = document.getElementById(`sec-${id}`);
    if (btn) {
      if (id === tabId) {
        btn.className = "tab-active w-full text-left px-3.5 py-2.5 rounded-xl text-xs font-bold flex items-center space-x-3 transition";
      } else {
        btn.className = "w-full text-left px-3.5 py-2.5 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100 flex items-center space-x-3 transition";
      }

      // Re-enforce admin-only button hiding so inactive admin buttons do not reappear
      if (!isAdmin && adminOnlyTabIds.includes(id)) {
        btn.classList.add('hidden');
      }
    }
    if (sec && id !== 'welcome') {
      if (id === tabId) {
        sec.classList.remove('hidden');
      } else {
        sec.classList.add('hidden');
      }
    }
  });

  if (tabId === 'classwise') loadClassWiseStudents();
  if (tabId === 'discounts') {
    loadPendingDiscounts();
    loadPendingAdmissionChanges();
    loadPendingImportBatches();
  }
  if (tabId === 'feemaster') loadFeeMaster();
  if (tabId === 'reports') loadEodReport();
  if (tabId === 'staff') loadStaffUsers();
  if (tabId === 'logs') loadAuditLogs();
  if (tabId === 'iplogs') loadIpTrackerLogs();
}

// ================= SEARCH & INSTALLMENT COLLECTION =================

function debounceSearch() {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(performStudentSearch, 300);
}

async function performStudentSearch() {
  const query = document.getElementById('studentSearchInput').value.trim();
  const list = document.getElementById('searchResultsList');

  if (query.length < 1) {
    list.classList.add('hidden');
    list.innerHTML = `<p class="text-[11px] text-slate-400 text-center py-4">Search by Admission No, Student Name, or Phone</p>`;
    return;
  }

  try {
    const res = await fetch(`/api/students/search?query=${encodeURIComponent(query)}`);
    const students = await res.json();

    list.classList.remove('hidden');

    if (students.length === 0) {
      list.innerHTML = `<p class="text-[11px] text-slate-400 text-center py-4">No matching students found for "${query}"</p>`;
      return;
    }

    list.innerHTML = students.map(s => `
      <div onclick="selectStudent(${s.id})" class="p-3 hover:bg-indigo-50 cursor-pointer transition flex items-center justify-between">
        <div>
          <div class="flex items-center space-x-2">
            <span class="font-bold text-xs text-slate-900">${s.student_name}</span>
            <span class="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-700">${s.class_name}-${s.section}</span>
          </div>
          <p class="text-[11px] text-slate-500 mt-0.5">Adm: <span class="font-bold text-slate-700">${s.admission_no}</span> | Phone: ${s.parent_phone || '--'}</p>
        </div>
        <div class="text-right">
          <span class="font-extrabold text-xs ${s.balance_due > 0 ? 'text-rose-600' : 'text-emerald-600'}">
            ${s.balance_due > 0 ? 'Due: ₹' + Number(s.balance_due).toLocaleString('en-IN') : 'Paid Full'}
          </span>
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error(err);
  }
}

let studentPollTimer = null;

async function selectStudent(studentId, isBackgroundPoll = false) {
  try {
    const res = await fetch(`/api/students/${studentId}/statement`);
    if (!res.ok) {
      if (isBackgroundPoll) {
        // Stop polling if student is no longer found
        clearInterval(studentPollTimer);
        return;
      }
      const errData = await res.json().catch(() => ({}));
      alert(errData.detail || 'Unable to load student statement.');
      return;
    }

    const data = await res.json();
    if (!data || !data.student) {
      if (isBackgroundPoll) {
        clearInterval(studentPollTimer);
        return;
      }
      alert('Student record not found or statement unavailable.');
      return;
    }

    currentStudent = data.student;

    if (!isBackgroundPoll) {
      // Hide dropdown results
      const list = document.getElementById('searchResultsList');
      if (list) list.classList.add('hidden');

      // Show change student button & clear search text
      const quickBtn = document.getElementById('quickChangeStudentBtn');
      if (quickBtn) quickBtn.classList.remove('hidden');
      document.getElementById('studentSearchInput').value = `${currentStudent.student_name} (${currentStudent.admission_no})`;

      document.getElementById('noStudentSelectedMsg').classList.add('hidden');
      document.getElementById('selectedStudentPanel').classList.remove('hidden');

      // Start automatic live background polling every 2.5 seconds while this student is open
      clearInterval(studentPollTimer);
      studentPollTimer = setInterval(() => {
        if (currentStudent && currentStudent.id === studentId) {
          selectStudent(studentId, true);
        } else {
          clearInterval(studentPollTimer);
        }
      }, 2500);
    }

    document.getElementById('selStudentName').innerText = currentStudent.student_name;
    document.getElementById('selStudentClass').innerText = `${currentStudent.class_name} - ${currentStudent.section}`;
    
    let typeTxt = currentStudent.student_type;
    if (currentStudent.has_transport) typeTxt += ` + Bus (${currentStudent.bus_route || 'Route'})`;
    document.getElementById('selStudentType').innerText = typeTxt;

    document.getElementById('selAdmNo').innerText = currentStudent.admission_no;
    document.getElementById('selParentName').innerText = currentStudent.parent_name;
    document.getElementById('selParentPhone').innerText = currentStudent.parent_phone;

    document.getElementById('selTotalAgreed').innerText = `₹ ${Number(currentStudent.final_agreed_fee).toLocaleString('en-IN')}`;
    document.getElementById('selTotalPaid').innerText = `₹ ${Number(data.total_paid).toLocaleString('en-IN')}`;
    document.getElementById('selBalanceDue').innerText = `₹ ${Number(data.balance_due).toLocaleString('en-IN')}`;

    // Status Badge & Pending Approval Alert
    const statusBadge = document.getElementById('selStudentStatus');
    const alertBox = document.getElementById('selPendingApprovalAlert');
    const alertIcon = document.getElementById('selPendingApprovalIcon');
    const alertText = document.getElementById('selPendingApprovalText');
    const isCancelled = (currentStudent.status === 'Cancelled');

    if (statusBadge) {
      if (isCancelled) {
        statusBadge.className = "text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-rose-100 text-rose-800 border border-rose-300";
        statusBadge.innerHTML = `<i class="fa-solid fa-ban mr-1"></i>Cancelled / Withdrawn`;
      } else {
        statusBadge.className = "text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300";
        statusBadge.innerHTML = `<i class="fa-solid fa-circle-check mr-1"></i>Active`;
      }
    }

    if (alertBox && alertText) {
      if (isCancelled) {
        alertBox.className = "mt-2 p-2.5 rounded-xl text-xs font-bold border flex items-center space-x-2 bg-rose-50 border-rose-200 text-rose-800";
        if (alertIcon) alertIcon.innerHTML = `<i class="fa-solid fa-circle-xmark text-rose-600 text-sm"></i>`;
        alertText.innerText = "This student admission has been CANCELLED / WITHDRAWN. Fee collections and modifications are disabled.";
        alertBox.classList.remove('hidden');
      } else if (data.pending_change) {
        const reqType = data.pending_change.request_type === 'CANCEL_ADMISSION' ? 'Admission Cancellation' : 'Admission Details Edit';
        alertBox.className = "mt-2 p-2.5 rounded-xl text-xs font-bold border flex items-center space-x-2 bg-amber-50 border-amber-200 text-amber-800";
        if (alertIcon) alertIcon.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-amber-600"></i>`;
        alertText.innerHTML = `<b>Waiting for Admin Approval</b> (${reqType} requested by ${data.pending_change.requested_by}: "${data.pending_change.reason}")`;
        alertBox.classList.remove('hidden');
      } else {
        alertBox.classList.add('hidden');
      }
    }

    currentStudent._current_balance_due = Number(data.balance_due);

    // Default amount input to remaining balance (or 10000 if larger) and cap with max
    const payInput = document.getElementById('payAmountInput');
    const maxHint = document.getElementById('payMaxLimitHint');
    const warningEl = document.getElementById('payAmountWarning');
    if (warningEl && !isBackgroundPoll) { warningEl.classList.add('hidden'); warningEl.innerText = ''; }
    if (payInput && !isBackgroundPoll) payInput.classList.remove('border-rose-500', 'bg-rose-50');

    if (maxHint) {
      maxHint.innerText = `Max: ₹ ${Number(data.balance_due).toLocaleString('en-IN')}`;
    }

    if (payInput) {
      payInput.max = data.balance_due;
      payInput.disabled = (data.balance_due <= 0 || isCancelled);
      
      // CRITICAL FIX: Only set default value on initial student selection!
      // Do NOT overwrite user typing every 2.5 seconds during background polling or if user is focused.
      if (!isBackgroundPoll && document.activeElement !== payInput) {
        payInput.value = (data.balance_due > 0 && !isCancelled) ? Math.min(data.balance_due, 10000) : 0;
      }
    }

    if (!isBackgroundPoll) {
      document.getElementById('payLabelInput').value = `Installment #${data.payments.length + 1}`;
    }

    // Populate history table
    const histTable = document.getElementById('paymentHistoryRows');
    if (data.payments.length === 0) {
      histTable.innerHTML = `<tr><td colspan="7" class="text-center p-3 text-slate-400">No installments recorded yet.</td></tr>`;
    } else {
      histTable.innerHTML = data.payments.map(p => `
        <tr class="hover:bg-slate-50">
          <td class="p-2.5 font-bold text-indigo-700">${p.receipt_no}</td>
          <td class="p-2.5 text-slate-500">${p.payment_date.split(' ')[0]}</td>
          <td class="p-2.5 font-medium">${p.installment_label || '#' + p.installment_no}</td>
          <td class="p-2.5 font-semibold">${p.payment_mode}</td>
          <td class="p-2.5 text-right font-bold text-emerald-700">₹ ${Number(p.amount_paid).toLocaleString('en-IN')}</td>
          <td class="p-2.5 text-right font-bold text-slate-800">₹ ${Number(p.balance_due).toLocaleString('en-IN')}</td>
          <td class="p-2.5 text-center">
            <a href="/receipt/${p.receipt_token}" target="_blank" class="text-[11px] font-bold text-indigo-600 hover:text-indigo-800 bg-indigo-50 px-2 py-1 rounded-lg">
              <i class="fa-solid fa-receipt mr-1"></i> View Receipt
            </a>
          </td>
        </tr>
      `).join('');
    }

  } catch (err) {
    alert('Failed to load student statement: ' + err);
  }
}

function clearSelectedStudent() {
  clearInterval(studentPollTimer);
  currentStudent = null;
  document.getElementById('noStudentSelectedMsg').classList.remove('hidden');
  document.getElementById('selectedStudentPanel').classList.add('hidden');
  document.getElementById('quickChangeStudentBtn').classList.add('hidden');
  const searchInput = document.getElementById('studentSearchInput');
  searchInput.value = '';
  searchInput.focus();
  const list = document.getElementById('searchResultsList');
  if (list) list.classList.add('hidden');
}

function handlePayAmountChange(inputEl) {
  const warningEl = document.getElementById('payAmountWarning');
  if (!currentStudent || currentStudent._current_balance_due === undefined) return;

  const entered = parseFloat(inputEl.value) || 0;
  const maxAllowed = currentStudent._current_balance_due;

  if (entered > maxAllowed) {
    warningEl.innerText = `Exceeds Balance Due! Maximum allowed is ₹ ${Number(maxAllowed).toLocaleString('en-IN')}`;
    warningEl.classList.remove('hidden');
    inputEl.classList.add('border-rose-500', 'bg-rose-50');
  } else {
    warningEl.classList.add('hidden');
    warningEl.innerText = '';
    inputEl.classList.remove('border-rose-500', 'bg-rose-50');
  }
}

async function submitInstallmentPayment() {
  if (!currentStudent) return alert("Select a student first!");

  const amount = parseFloat(document.getElementById('payAmountInput').value);
  if (!amount || amount <= 0) return alert("Please enter a valid payment amount!");

  const balanceDue = currentStudent._current_balance_due !== undefined ? currentStudent._current_balance_due : 0;
  if (balanceDue <= 0) {
    return alert(`This student has already paid the full agreed fee. Current Balance Due is ₹ 0.`);
  }

  if (amount > balanceDue) {
    return alert(`Amount cannot exceed the remaining Balance Due of ₹ ${Number(balanceDue).toLocaleString('en-IN')}. Please enter an amount up to ₹ ${Number(balanceDue).toLocaleString('en-IN')}.`);
  }

  const mode = document.getElementById('payModeSelect').value;
  const ref = document.getElementById('payRefInput').value;
  const label = document.getElementById('payLabelInput').value;
  const operator = currentUser ? currentUser.username : 'frontdesk';

  try {
    const res = await fetch(`/api/payments/collect?cashier_user=${operator}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_id: currentStudent.id,
        amount_paid: amount,
        payment_mode: mode,
        transaction_ref: ref,
        installment_label: label,
        session_id: getOrCreateSessionId()
      })
    });

    const data = await res.json();
    if (!res.ok) return alert(data.detail || "Payment failed");

    // Show Success & WhatsApp modal
    showReceiptSuccessModal(data);

    // Refresh current student ledger
    selectStudent(currentStudent.id);
    loadEodReport();

  } catch (err) {
    alert("Payment error: " + err);
  }
}

// ================= ADMISSION & 1ST INSTALLMENT =================

function toggleTransportSection() {
  const isDay = document.getElementById('admStudentType').value === 'Day Scholar';
  const wrapper = document.getElementById('transportSectionWrapper');
  wrapper.style.display = isDay ? 'block' : 'none';
  if (!isDay) {
    document.getElementById('admHasTransport').checked = false;
    toggleTransportInput();
  }
}

function toggleTransportInput() {
  const hasTrans = document.getElementById('admHasTransport').checked;
  const inputDiv = document.getElementById('transportInputs');
  inputDiv.classList.toggle('hidden', !hasTrans);
  if (!hasTrans) {
    document.getElementById('admTransportFee').value = 0;
  }
  updateAgreedFeePreview();
}

let cachedBaseFee = 30000;

async function recalculateBaseFee() {
  const cname = document.getElementById('admClass').value;
  const stype = document.getElementById('admStudentType').value;

  try {
    const res = await fetch(`/api/fee-structures/calculate?class_name=${encodeURIComponent(cname)}&student_type=${encodeURIComponent(stype)}`);
    const data = await res.json();
    cachedBaseFee = data.total_base_fee || 30000;
    updateAgreedFeePreview();
  } catch (err) {
    console.error(err);
  }
}

// Format Admission Number: Auto-prefix KHSB1-YYYY- or KHSB2-YYYY- based on selected branch
function formatAdmissionNo(input) {
  let val = input.value.toUpperCase();
  const year = new Date().getFullYear();
  const branchSelect = document.getElementById('admBranch');
  const branchVal = branchSelect ? branchSelect.value : 'Branch 1';
  const branchCode = (branchVal === 'Branch 2' || branchVal === '2') ? 'B2' : 'B1';
  const prefix = `KHS${branchCode}-${year}-`;

  // Strip any old prefixes like KHS-, KHSB1-, KHSB2-
  let digits = val.replace(/^KHS(B[12])?-\d{4}-/i, '').replace(/[^0-9]/g, '');

  if (!val.startsWith(`KHS${branchCode}-`)) {
    val = prefix + digits;
  } else {
    val = prefix + digits;
  }
  input.value = val;
}

function handleAdmissionBranchChange() {
  const input = document.getElementById('admNo');
  if (input) {
    formatAdmissionNo(input);
  }
}

// Discount Approval Workflow State
let currentDiscountApprovalState = {
  status: 'None', // 'None', 'NeedsRequest', 'Pending', 'Approved', 'Rejected'
  requestId: null,
  requestedAmount: 0,
  approvedAmount: 0,
  pollTimer: null
};

function onDiscountInputChanged() {
  const discountInput = parseFloat(document.getElementById('admDiscountAmount').value) || 0;
  updateAgreedFeePreview();

  const reqBtn = document.getElementById('btnRequestDiscountApproval');
  const modBtn = document.getElementById('btnModifyDiscount');
  const badge = document.getElementById('discountStatusBadge');
  const alertBox = document.getElementById('discountBlockAlert');
  const alertText = document.getElementById('discountBlockAlertText');
  const submitBtn = document.getElementById('btnSubmitAdmission');

  const isAdmin = currentUser && (currentUser.role === 'T1' || currentUser.role === 'T2');

  if (discountInput <= 0) {
    currentDiscountApprovalState.status = 'None';
    currentDiscountApprovalState.requestId = null;
    currentDiscountApprovalState.requestedAmount = 0;
    currentDiscountApprovalState.approvedAmount = 0;
    clearInterval(currentDiscountApprovalState.pollTimer);

    badge.className = "text-xs font-bold px-3 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200";
    badge.innerText = "No Discount Requested";
    reqBtn.classList.add('hidden');
    modBtn.classList.add('hidden');
    alertBox.classList.add('hidden');
    submitBtn.disabled = false;
    return;
  }

  // When logged in as Admin or Super Admin, grant instant approval without requiring approval queue navigation!
  if (isAdmin) {
    currentDiscountApprovalState.status = 'Approved';
    currentDiscountApprovalState.approvedAmount = discountInput;
    clearInterval(currentDiscountApprovalState.pollTimer);

    badge.className = "text-xs font-bold px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300";
    badge.innerHTML = `<i class="fa-solid fa-circle-check text-emerald-600 mr-1"></i> Admin Concession Approved: ₹ ${Number(discountInput).toLocaleString('en-IN')}`;
    
    reqBtn.classList.add('hidden');
    modBtn.classList.add('hidden');
    
    alertBox.className = "bg-emerald-50 text-emerald-800 text-xs p-2.5 rounded-xl border border-emerald-200 flex items-center space-x-2";
    alertBox.innerHTML = `<i class="fa-solid fa-check-double text-emerald-600"></i> <span>Direct Admin Discount applied (₹ ${Number(discountInput).toLocaleString('en-IN')}). You can complete admission immediately.</span>`;
    alertBox.classList.remove('hidden');
    submitBtn.disabled = false;
    return;
  }

  // If T3 Cashier enters discount, require Admin approval
  currentDiscountApprovalState.status = 'NeedsRequest';
  badge.className = "text-xs font-bold px-3 py-1 rounded-full bg-amber-100 text-amber-800 border border-amber-300";
  badge.innerText = "Approval Required from Admin";
  reqBtn.classList.remove('hidden');
  modBtn.classList.add('hidden');
  alertBox.classList.remove('hidden');
  alertText.innerText = 'Click "Request Approval" above. Admin must approve this discount before you can submit the admission.';
  submitBtn.disabled = true; // Block submission until approved
}

async function submitDiscountForApproval() {
  const admNo = document.getElementById('admNo').value.trim();
  const fName = document.getElementById('admFirstName').value.trim();
  const lName = document.getElementById('admLastName').value.trim();
  const sname = `${fName} ${lName}`.trim();
  const cname = document.getElementById('admClass').value;
  const reason = document.getElementById('admDiscountReason').value.trim();
  const discountAmount = parseFloat(document.getElementById('admDiscountAmount').value) || 0;

  if (!admNo) return alert("Please enter the Admission Number first!");
  if (!fName) return alert("Please enter the Student First Name first!");
  if (discountAmount <= 0) return alert("Please enter a valid discount amount!");

  const hasTrans = document.getElementById('admHasTransport').checked;
  const transFee = hasTrans ? (parseFloat(document.getElementById('admTransportFee').value) || 0) : 0;
  const standardFee = cachedBaseFee + transFee;
  const operatorUser = currentUser ? currentUser.username : 'frontdesk';

  try {
    const res = await fetch(`/api/discounts/request-approval?operator_user=${operatorUser}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        admission_no: admNo,
        student_name: sname,
        class_name: cname,
        standard_fee: standardFee,
        requested_discount: discountAmount,
        reason: reason || "Concession requested at front desk"
      })
    });

    const data = await res.json();
    if (!res.ok) return alert(data.detail || "Failed to send request");

    currentDiscountApprovalState.status = 'Pending';
    currentDiscountApprovalState.requestId = data.request_id;
    currentDiscountApprovalState.requestedAmount = discountAmount;

    // Lock discount fields until modify is clicked
    document.getElementById('admDiscountAmount').disabled = true;
    document.getElementById('admDiscountReason').disabled = true;

    const reqBtn = document.getElementById('btnRequestDiscountApproval');
    const modBtn = document.getElementById('btnModifyDiscount');
    const badge = document.getElementById('discountStatusBadge');
    const alertBox = document.getElementById('discountBlockAlert');
    const alertText = document.getElementById('discountBlockAlertText');
    const submitBtn = document.getElementById('btnSubmitAdmission');

    reqBtn.classList.add('hidden');
    modBtn.classList.remove('hidden');

    badge.className = "text-xs font-bold px-3 py-1 rounded-full bg-indigo-100 text-indigo-800 border border-indigo-300 animate-pulse";
    badge.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Waiting for Admin Approval (Req #${data.request_id})...`;

    alertBox.classList.remove('hidden');
    alertText.innerText = "Request sent to Admin! Waiting for Admin to approve. Once approved, the status will automatically change here and unlock admission submission.";
    submitBtn.disabled = true;

    // Start auto-polling every 2 seconds to check if Admin approves
    clearInterval(currentDiscountApprovalState.pollTimer);
    currentDiscountApprovalState.pollTimer = setInterval(pollDiscountStatus, 2000);

    // Refresh pending queue if open
    loadPendingDiscounts();

  } catch (err) {
    alert("Error sending approval request: " + err);
  }
}

async function pollDiscountStatus() {
  if (!currentDiscountApprovalState.requestId) return;

  try {
    const res = await fetch(`/api/discounts/status/${currentDiscountApprovalState.requestId}`);
    if (!res.ok) return;
    const reqData = await res.json();

    if (reqData.status === 'Approved') {
      clearInterval(currentDiscountApprovalState.pollTimer);
      currentDiscountApprovalState.status = 'Approved';
      currentDiscountApprovalState.approvedAmount = reqData.approved_discount;

      // Update discount input in case admin adjusted the amount
      document.getElementById('admDiscountAmount').value = reqData.approved_discount;
      updateAgreedFeePreview();

      const badge = document.getElementById('discountStatusBadge');
      const alertBox = document.getElementById('discountBlockAlert');
      const submitBtn = document.getElementById('btnSubmitAdmission');
      const modBtn = document.getElementById('btnModifyDiscount');

      badge.className = "text-xs font-bold px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300";
      badge.innerHTML = `<i class="fa-solid fa-circle-check text-emerald-600 mr-1"></i> Discount Approved: ₹ ${Number(reqData.approved_discount).toLocaleString('en-IN')}`;

      alertBox.className = "bg-emerald-50 text-emerald-800 text-xs p-2.5 rounded-xl border border-emerald-200 flex items-center space-x-2";
      alertBox.innerHTML = `<i class="fa-solid fa-check-double text-emerald-600"></i> <span>Discount approved by ${reqData.approved_by || 'Admin'}! You may now submit the admission.</span>`;

      modBtn.classList.remove('hidden');
      submitBtn.disabled = false; // UNLOCKED

    } else if (reqData.status === 'Rejected') {
      clearInterval(currentDiscountApprovalState.pollTimer);
      currentDiscountApprovalState.status = 'Rejected';

      const badge = document.getElementById('discountStatusBadge');
      const alertBox = document.getElementById('discountBlockAlert');
      const submitBtn = document.getElementById('btnSubmitAdmission');
      const modBtn = document.getElementById('btnModifyDiscount');

      badge.className = "text-xs font-bold px-3 py-1 rounded-full bg-rose-100 text-rose-800 border border-rose-300";
      badge.innerHTML = `<i class="fa-solid fa-circle-xmark text-rose-600 mr-1"></i> Discount Rejected by Admin`;

      alertBox.className = "bg-rose-50 text-rose-700 text-xs p-2.5 rounded-xl border border-rose-200 flex items-center space-x-2";
      alertBox.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-rose-500"></i> <span>Discount was rejected (${reqData.admin_remarks || 'Standard fee applies'}). Click "Modify Discount" to change amount or set to 0.</span>`;

      modBtn.classList.remove('hidden');
      submitBtn.disabled = true; // Submission remains blocked
    }
  } catch (err) {
    console.error("Poll status error:", err);
  }
}

function enableDiscountModification() {
  clearInterval(currentDiscountApprovalState.pollTimer);
  document.getElementById('admDiscountAmount').disabled = false;
  document.getElementById('admDiscountReason').disabled = false;
  document.getElementById('admDiscountAmount').focus();

  currentDiscountApprovalState.status = 'NeedsRequest';

  const reqBtn = document.getElementById('btnRequestDiscountApproval');
  const modBtn = document.getElementById('btnModifyDiscount');
  const badge = document.getElementById('discountStatusBadge');
  const alertBox = document.getElementById('discountBlockAlert');
  const alertText = document.getElementById('discountBlockAlertText');
  const submitBtn = document.getElementById('btnSubmitAdmission');

  badge.className = "text-xs font-bold px-3 py-1 rounded-full bg-amber-100 text-amber-800 border border-amber-300";
  badge.innerText = "Discount Modified - Request Approval Required";
  reqBtn.classList.remove('hidden');
  modBtn.classList.add('hidden');
  alertBox.className = "bg-rose-50 text-rose-700 text-xs p-2.5 rounded-xl border border-rose-200 flex items-center space-x-2";
  alertBox.classList.remove('hidden');
  alertText.innerText = 'Discount amount changed. Please click "Request Approval" to submit updated amount to Admin.';
  submitBtn.disabled = true;
}

function resetAdmissionFormState() {
  clearInterval(currentDiscountApprovalState.pollTimer);
  currentDiscountApprovalState = {
    status: 'None',
    requestId: null,
    requestedAmount: 0,
    approvedAmount: 0,
    pollTimer: null
  };
  document.getElementById('admDiscountAmount').disabled = false;
  document.getElementById('admDiscountReason').disabled = false;
  document.getElementById('discountStatusBadge').className = "text-xs font-bold px-3 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200";
  document.getElementById('discountStatusBadge').innerText = "No Discount Requested";
  document.getElementById('btnRequestDiscountApproval').classList.add('hidden');
  document.getElementById('btnModifyDiscount').classList.add('hidden');
  document.getElementById('discountBlockAlert').classList.add('hidden');
  document.getElementById('btnSubmitAdmission').disabled = false;
  updateAgreedFeePreview();
}

function updateAgreedFeePreview() {
  const hasTrans = document.getElementById('admHasTransport').checked;
  const transFee = hasTrans ? (parseFloat(document.getElementById('admTransportFee').value) || 0) : 0;
  const discount = parseFloat(document.getElementById('admDiscountAmount').value) || 0;

  const total = Math.max(0, cachedBaseFee + transFee - discount);

  document.getElementById('calcBaseFeeText').innerText = `₹ ${Number(cachedBaseFee).toLocaleString('en-IN')}`;
  document.getElementById('calcTransportText').innerText = `₹ ${Number(transFee).toLocaleString('en-IN')}`;
  document.getElementById('calcDiscountText').innerText = `₹ ${Number(discount).toLocaleString('en-IN')}`;
  document.getElementById('calcFinalAgreedText').innerText = `₹ ${Number(total).toLocaleString('en-IN')}`;
}

async function handleAdmissionSubmit(e) {
  e.preventDefault();

  const isAdmin = currentUser && (currentUser.role === 'T1' || currentUser.role === 'T2');
  const discountAmount = parseFloat(document.getElementById('admDiscountAmount').value) || 0;

  // If Admin or Super Admin, auto-approve discount directly
  if (isAdmin && discountAmount > 0) {
    currentDiscountApprovalState.status = 'Approved';
    currentDiscountApprovalState.approvedAmount = discountAmount;
  }

  // Safety verification: if T3 requested discount, ensure it is Approved
  if (!isAdmin && discountAmount > 0 && currentDiscountApprovalState.status !== 'Approved') {
    alert("Discount has not been approved by Admin yet! Please request approval and wait for Admin approval before submitting.");
    return;
  }

  const operatorRole = currentUser ? currentUser.role : 'T3';
  const operatorUser = currentUser ? currentUser.username : 'frontdesk';

  const fName = document.getElementById('admFirstName').value.trim();
  const lName = document.getElementById('admLastName').value.trim();
  const sname = `${fName} ${lName}`.trim();

  const branchVal = document.getElementById('admBranch') ? document.getElementById('admBranch').value : 'Branch 1';

  const payload = {
    admission_no: document.getElementById('admNo').value.trim(),
    roll_no: document.getElementById('admRoll').value.trim(),
    student_name: sname,
    branch: branchVal,
    gender: document.getElementById('admGender').value,
    class_name: document.getElementById('admClass').value,
    section: document.getElementById('admSection').value,
    student_type: document.getElementById('admStudentType').value,
    has_transport: document.getElementById('admHasTransport').checked,
    transport_fee: parseFloat(document.getElementById('admTransportFee').value) || 0,
    bus_route: document.getElementById('admBusRoute').value.trim(),
    parent_name: document.getElementById('admParentName').value.trim(),
    parent_phone: document.getElementById('admParentPhone').value.trim(),
    address: document.getElementById('admAddress').value.trim(),
    requested_discount: discountAmount,
    discount_reason: document.getElementById('admDiscountReason').value.trim(),
    initial_payment_amount: parseFloat(document.getElementById('admInitialPay').value) || 0,
    initial_payment_mode: document.getElementById('admPayMode').value,
    initial_payment_ref: document.getElementById('admPayRef').value.trim(),
    session_id: getOrCreateSessionId()
  };

  try {
    const res = await fetch(`/api/students/admit?operator_role=${operatorRole}&operator_user=${operatorUser}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) return alert(data.detail || 'Admission failed');

    alert(data.message);

    if (data.receipt) {
      const studentName = payload.student_name;
      const parentMsg = `Dear Parent, received Rs. ${data.receipt.amount_paid} towards ${studentName}'s admission fee (1st Installment). Remaining Balance: Rs. ${data.receipt.balance_due}. Download Receipt (valid 48h): http://localhost:8000/receipt/${data.receipt.receipt_token} - Kranthi High School`;
      
      showReceiptSuccessModal({
        receipt_no: data.receipt.receipt_no,
        receipt_token: data.receipt.receipt_token,
        amount_paid: data.receipt.amount_paid,
        balance_due: data.receipt.balance_due,
        parent_phone: data.receipt.parent_phone,
        parent_msg: parentMsg
      });
    }

    // Reset Form & Switch to Collection Tab
    document.getElementById('admissionForm').reset();
    resetAdmissionFormState();
    toggleTransportSection();
    recalculateBaseFee();
    loadPendingDiscounts();
    switchTab('collect');

  } catch (err) {
    alert("Admission submission error: " + err);
  }
}

// ================= DISCOUNT APPROVAL QUEUE (T1 & T2) =================

async function loadPendingDiscounts() {
  try {
    const res = await fetch('/api/discounts/pending');
    pendingDiscountsList = await res.json();

    const count = pendingDiscountsList.length;
    const badge = document.getElementById('pendingDiscountBadge');
    const dot = document.getElementById('navDiscountDot');
    
    if (count > 0 && currentUser && ['T1', 'T2'].includes(currentUser.role)) {
      badge.classList.remove('hidden');
      dot.classList.remove('hidden');
      document.getElementById('pendingDiscountCount').innerText = count;
    } else {
      badge.classList.add('hidden');
      dot.classList.add('hidden');
    }

    const table = document.getElementById('discountTable');
    const emptyMsg = document.getElementById('noDiscountsMsg');
    const rows = document.getElementById('discountQueueRows');

    if (count === 0) {
      table.classList.add('hidden');
      emptyMsg.classList.remove('hidden');
    } else {
      table.classList.remove('hidden');
      emptyMsg.classList.add('hidden');

      rows.innerHTML = pendingDiscountsList.map(d => `
        <tr class="hover:bg-slate-50">
          <td class="p-3 font-mono font-bold text-slate-500">#${d.id}</td>
          <td class="p-3">
            <p class="font-bold text-slate-900">${d.student_name}</p>
            <p class="text-[11px] text-slate-500">${d.class_name} | Adm: ${d.admission_no}</p>
          </td>
          <td class="p-3 font-semibold">₹ ${Number(d.standard_fee).toLocaleString('en-IN')}</td>
          <td class="p-3 font-extrabold text-rose-600">₹ ${Number(d.requested_discount).toLocaleString('en-IN')}</td>
          <td class="p-3 italic text-slate-600">"${d.reason || 'None specified'}"</td>
          <td class="p-3 text-[11px] font-bold text-indigo-700">${d.requested_by}</td>
          <td class="p-3 text-right space-x-1">
            ${currentUser && ['T1', 'T2'].includes(currentUser.role) ? `
              <button onclick="actionDiscountRequest(${d.id}, 'Approve', ${d.requested_discount})" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-2.5 py-1.5 rounded-lg text-[11px] shadow-xs transition">
                <i class="fa-solid fa-check mr-1"></i> Approve
              </button>
              <button onclick="actionDiscountRequest(${d.id}, 'Reject', 0)" class="bg-rose-600 hover:bg-rose-700 text-white font-bold px-2.5 py-1.5 rounded-lg text-[11px] shadow-xs transition">
                <i class="fa-solid fa-xmark mr-1"></i> Reject
              </button>
            ` : `
              <span class="text-[10px] text-amber-700 bg-amber-50 px-2 py-1 rounded font-bold">Needs Admin Approval</span>
            `}
          </td>
        </tr>
      `).join('');
    }

  } catch (err) {
    console.error(err);
  }
}

async function actionDiscountRequest(requestId, action, defaultAmount) {
  let approvedAmount = defaultAmount;
  let remarks = "";

  if (action === 'Approve') {
    const input = prompt(`Enter Approved Discount Amount (₹):`, defaultAmount);
    if (input === null) return;
    approvedAmount = parseFloat(input) || 0;
    remarks = prompt("Admin Remarks / Reason (Optional):", "Approved by Management") || "";
  } else {
    if (!confirm("Are you sure you want to REJECT this discount request?")) return;
    remarks = prompt("Reason for Rejection (Optional):", "Standard fee applies") || "";
  }

  const approver = currentUser ? currentUser.username : 'admin';

  try {
    const res = await fetch(`/api/discounts/action?approver_user=${approver}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_id: requestId,
        action: action,
        approved_discount: approvedAmount,
        admin_remarks: remarks
      })
    });

    const data = await res.json();
    alert(data.message);
    loadPendingDiscounts();
  } catch (err) {
    alert("Error actioning discount: " + err);
  }
}

// ================= ADMISSION MODIFICATION & CANCELLATION QUEUE (ADMIN) =================

async function loadPendingAdmissionChanges() {
  try {
    const res = await fetch('/api/admissions/pending-changes');
    const list = await res.json();

    const table = document.getElementById('admissionChangesTable');
    const emptyMsg = document.getElementById('noAdmissionChangesMsg');
    const rows = document.getElementById('admissionChangesRows');

    if (!list || list.length === 0) {
      if (table) table.classList.add('hidden');
      if (emptyMsg) emptyMsg.classList.remove('hidden');
    } else {
      if (table) table.classList.remove('hidden');
      if (emptyMsg) emptyMsg.classList.add('hidden');

      rows.innerHTML = list.map(req => {
        const isCancel = req.request_type === 'CANCEL_ADMISSION';
        const typeBadge = isCancel
          ? `<span class="bg-rose-100 text-rose-800 text-[10px] font-extrabold px-2 py-0.5 rounded-full"><i class="fa-solid fa-ban mr-1"></i>CANCEL ADMISSION</span>`
          : `<span class="bg-indigo-100 text-indigo-800 text-[10px] font-extrabold px-2 py-0.5 rounded-full"><i class="fa-solid fa-pen-to-square mr-1"></i>EDIT DETAILS</span>`;

        let currentSummary = `
          <div class="space-y-0.5">
            <p class="font-bold text-slate-800">${req.current_data.student_name || '--'} ${req.current_data.roll_no ? '<span class="text-[10px] text-indigo-700 font-mono">(Roll: ' + req.current_data.roll_no + ')</span>' : ''}</p>
            <p class="text-[10px] text-slate-500">${req.current_data.class_name || ''} ${req.current_data.section ? '- ' + req.current_data.section : ''} (${req.current_data.student_type || ''})</p>
            <p class="text-[10px] text-slate-500">Parent: ${req.current_data.parent_name || ''} (${req.current_data.parent_phone || ''})</p>
          </div>
        `;

        let proposedSummary = '';
        if (isCancel) {
          proposedSummary = `
            <div class="text-rose-700 font-semibold space-y-0.5">
              <p class="font-bold">Reason: "${req.reason}"</p>
              <p class="text-[10px] text-slate-500">Proposed action: Permanently cancel admission record</p>
            </div>
          `;
        } else {
          const prop = req.proposed_data || {};
          const propRoll = prop.roll_no !== undefined ? prop.roll_no : req.current_data.roll_no;
          proposedSummary = `
            <div class="space-y-0.5">
              <p class="font-bold text-indigo-900">${prop.student_name || req.current_data.student_name} ${propRoll ? '<span class="text-[10px] text-emerald-700 font-mono font-bold">(Roll: ' + propRoll + ')</span>' : ''}</p>
              <p class="text-[10px] text-indigo-700">${prop.class_name || req.current_data.class_name} ${prop.section ? '- ' + prop.section : ''} (${prop.student_type || req.current_data.student_type})</p>
              <p class="text-[10px] text-indigo-700">Parent: ${prop.parent_name || req.current_data.parent_name} (${prop.parent_phone || req.current_data.parent_phone})</p>
              <p class="text-[10px] italic text-slate-600">Reason: "${req.reason}"</p>
            </div>
          `;
        }

        return `
          <tr class="hover:bg-slate-50 transition">
            <td class="p-3">${typeBadge}</td>
            <td class="p-3 font-mono font-bold text-slate-700">${req.admission_no}</td>
            <td class="p-3">${currentSummary}</td>
            <td class="p-3">${proposedSummary}</td>
            <td class="p-3 font-bold text-slate-700 text-[11px]">${req.requested_by}</td>
            <td class="p-3 text-right space-x-1 whitespace-nowrap">
              ${currentUser && ['T1', 'T2'].includes(currentUser.role) ? `
                <button onclick="actionAdmissionChange(${req.id}, 'Approve', '${req.request_type}')" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-2.5 py-1.5 rounded-lg text-[11px] shadow-xs transition">
                  <i class="fa-solid fa-check mr-1"></i> Approve
                </button>
                <button onclick="actionAdmissionChange(${req.id}, 'Reject', '${req.request_type}')" class="bg-rose-600 hover:bg-rose-700 text-white font-bold px-2.5 py-1.5 rounded-lg text-[11px] shadow-xs transition">
                  <i class="fa-solid fa-xmark mr-1"></i> Reject
                </button>
              ` : `
                <span class="text-[10px] text-amber-700 bg-amber-50 px-2 py-1 rounded font-bold">Needs Admin Approval</span>
              `}
            </td>
          </tr>
        `;
      }).join('');
    }
  } catch (err) {
    console.error("Error loading admission changes:", err);
  }
}

async function actionAdmissionChange(requestId, action, type) {
  let remarks = "";
  if (action === 'Approve') {
    if (!confirm(`Are you sure you want to APPROVE this ${type === 'CANCEL_ADMISSION' ? 'Admission Cancellation' : 'Details Modification'}?`)) return;
    remarks = prompt("Admin Approval Remarks (Optional):", "Approved by Management") || "";
  } else {
    if (!confirm(`Are you sure you want to REJECT this request?`)) return;
    remarks = prompt("Reason for Rejection:", "Rejected by Admin") || "Rejected";
  }

  const approver = currentUser ? currentUser.username : 'admin';

  try {
    const res = await fetch(`/api/admissions/action-change?approver_user=${approver}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_id: requestId,
        action: action,
        admin_remarks: remarks
      })
    });

    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Action failed");
      return;
    }

    alert(data.message);
    loadPendingAdmissionChanges();
    if (currentStudent) {
      selectStudent(currentStudent.id);
    }
  } catch (err) {
    alert("Error actioning request: " + err);
  }
}

// ================= BULK IMPORT BATCH APPROVAL QUEUE (ADMIN) =================

async function loadPendingImportBatches() {
  try {
    const res = await fetch('/api/import-batches/pending');
    const list = await res.json();

    const table = document.getElementById('importBatchesTable');
    const emptyMsg = document.getElementById('noImportBatchesMsg');
    const rows = document.getElementById('importBatchesRows');

    if (!list || list.length === 0) {
      if (table) table.classList.add('hidden');
      if (emptyMsg) emptyMsg.classList.remove('hidden');
    } else {
      if (table) table.classList.remove('hidden');
      if (emptyMsg) emptyMsg.classList.add('hidden');

      rows.innerHTML = list.map(b => {
        const previewStudents = (b.student_data || []).slice(0, 3);
        const previewText = previewStudents.map(s => `${s.student_name} (${s.class_name})`).join(', ') + ((b.student_data || []).length > 3 ? ` ...and ${(b.student_data || []).length - 3} more` : '');

        return `
          <tr class="hover:bg-slate-50 transition">
            <td class="p-3 font-mono font-bold text-slate-500">Batch #${b.id}</td>
            <td class="p-3">
              <p class="font-bold text-slate-900 flex items-center space-x-1.5">
                <i class="fa-solid fa-file-excel text-emerald-600"></i>
                <span>${b.file_name}</span>
              </p>
              <p class="text-[10px] text-slate-400">Total Rows in File: ${b.total_rows}</p>
            </td>
            <td class="p-3">
              <span class="bg-indigo-100 text-indigo-800 text-xs font-black px-2.5 py-0.5 rounded-full">
                ${b.valid_rows} Students
              </span>
            </td>
            <td class="p-3 text-xs">
              <p class="font-bold text-slate-800">${b.uploaded_by}</p>
              <p class="text-[10px] text-slate-400">${b.created_at || ''}</p>
            </td>
            <td class="p-3 text-[11px] text-slate-600 max-w-xs truncate" title="${previewText}">
              ${previewText}
            </td>
            <td class="p-3 text-right space-x-1 whitespace-nowrap">
              ${currentUser && ['T1', 'T2'].includes(currentUser.role) ? `
                <button onclick="actionImportBatch(${b.id}, 'Approve', ${b.valid_rows})" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-2.5 py-1.5 rounded-lg text-[11px] shadow-xs transition">
                  <i class="fa-solid fa-check mr-1"></i> Approve & Import
                </button>
                <button onclick="actionImportBatch(${b.id}, 'Reject', ${b.valid_rows})" class="bg-rose-600 hover:bg-rose-700 text-white font-bold px-2.5 py-1.5 rounded-lg text-[11px] shadow-xs transition">
                  <i class="fa-solid fa-xmark mr-1"></i> Reject
                </button>
              ` : `
                <span class="text-[10px] text-amber-700 bg-amber-50 px-2 py-1 rounded font-bold">Needs Admin Approval</span>
              `}
            </td>
          </tr>
        `;
      }).join('');
    }
  } catch (err) {
    console.error("Error loading import batches:", err);
  }
}

async function actionImportBatch(batchId, action, studentCount) {
  let remarks = "";
  if (action === 'Approve') {
    if (!confirm(`Are you sure you want to APPROVE this bulk import? All ${studentCount} students will be immediately saved into the school billing database.`)) return;
    remarks = prompt("Admin Approval Remarks (Optional):", `Approved and added ${studentCount} students`) || "";
  } else {
    if (!confirm(`Are you sure you want to REJECT this bulk import batch?`)) return;
    remarks = prompt("Reason for Rejection:", "Data incorrect or duplicate") || "Rejected by Admin";
  }

  const approver = currentUser ? currentUser.username : 'admin';

  try {
    const res = await fetch(`/api/import-batches/action?approver_user=${approver}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        batch_id: batchId,
        action: action,
        admin_remarks: remarks
      })
    });

    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Action failed");
      return;
    }

    alert(data.message);
    loadPendingImportBatches();
    loadEodReport();
    if (typeof loadClassWiseStudents === 'function') loadClassWiseStudents();
  } catch (err) {
    alert("Error processing import batch: " + err);
  }
}

// Student profile modals for staff: Request Edit & Request Cancel

function openRequestEditModal() {
  if (!currentStudent) return alert("Select a student first!");

  document.getElementById('reqEditStudentName').value = currentStudent.student_name || '';
  if (document.getElementById('reqEditRollNo')) {
    document.getElementById('reqEditRollNo').value = currentStudent.roll_no || '';
  }
  document.getElementById('reqEditClass').value = currentStudent.class_name || 'Class 1';
  document.getElementById('reqEditSection').value = currentStudent.section || '';
  document.getElementById('reqEditStudentType').value = currentStudent.student_type || 'Day Scholar';
  document.getElementById('reqEditParentName').value = currentStudent.parent_name || '';
  document.getElementById('reqEditParentPhone').value = currentStudent.parent_phone || '';
  document.getElementById('reqEditReason').value = '';

  document.getElementById('requestEditModal').classList.remove('hidden');
}

function closeRequestEditModal() {
  document.getElementById('requestEditModal').classList.add('hidden');
}

async function submitRequestEditForm(e) {
  e.preventDefault();
  if (!currentStudent) return;

  const reason = document.getElementById('reqEditReason').value.trim();
  if (!reason) return alert("Please specify the reason for this edit request.");

  const rollVal = document.getElementById('reqEditRollNo') ? document.getElementById('reqEditRollNo').value.trim() : (currentStudent.roll_no || '');

  const proposed = {
    student_name: document.getElementById('reqEditStudentName').value.trim().toUpperCase(),
    roll_no: rollVal,
    class_name: document.getElementById('reqEditClass').value,
    section: document.getElementById('reqEditSection').value.trim().toUpperCase(),
    student_type: document.getElementById('reqEditStudentType').value,
    parent_name: document.getElementById('reqEditParentName').value.trim(),
    parent_phone: document.getElementById('reqEditParentPhone').value.trim()
  };

  const operator = currentUser ? currentUser.username : 'frontdesk';

  try {
    const res = await fetch(`/api/admissions/request-change?operator_user=${operator}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_id: currentStudent.id,
        request_type: 'MODIFY_DETAILS',
        reason: reason,
        proposed_data: proposed
      })
    });

    const data = await res.json();
    if (!res.ok) return alert(data.detail || "Failed to submit change request");

    alert(data.message);
    closeRequestEditModal();
    selectStudent(currentStudent.id);
  } catch (err) {
    alert("Error submitting request: " + err);
  }
}

function openRequestCancelModal() {
  if (!currentStudent) return alert("Select a student first!");
  document.getElementById('reqCancelReason').value = '';
  document.getElementById('requestCancelModal').classList.remove('hidden');
}

function closeRequestCancelModal() {
  document.getElementById('requestCancelModal').classList.add('hidden');
}

async function submitRequestCancelForm(e) {
  e.preventDefault();
  if (!currentStudent) return;

  const reason = document.getElementById('reqCancelReason').value.trim();
  if (!reason) return alert("Please specify the reason for cancellation.");

  const operator = currentUser ? currentUser.username : 'frontdesk';

  try {
    const res = await fetch(`/api/admissions/request-change?operator_user=${operator}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_id: currentStudent.id,
        request_type: 'CANCEL_ADMISSION',
        reason: reason,
        proposed_data: {}
      })
    });

    const data = await res.json();
    if (!res.ok) return alert(data.detail || "Failed to submit cancellation request");

    alert(data.message);
    closeRequestCancelModal();
    selectStudent(currentStudent.id);
  } catch (err) {
    alert("Error submitting cancellation request: " + err);
  }
}

// ================= FEE MASTER (T1 & T2) =================

async function loadFeeMaster() {
  try {
    const res = await fetch('/api/fee-structures');
    const list = await res.json();
    const rows = document.getElementById('feeMasterRows');

    rows.innerHTML = list.map(f => `
      <tr class="hover:bg-slate-50">
        <td class="p-3 font-bold text-slate-900">${f.class_name}</td>
        <td class="p-3">
          <span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${f.student_type === 'Day Scholar' ? 'bg-indigo-50 text-indigo-700' : 'bg-purple-50 text-purple-700'}">
            ${f.student_type}
          </span>
        </td>
        <td class="p-3">₹ ${Number(f.tuition_fee).toLocaleString('en-IN')}</td>
        <td class="p-3">₹ ${Number(f.activity_fee).toLocaleString('en-IN')}</td>
        <td class="p-3">₹ ${Number(f.exam_fee).toLocaleString('en-IN')}</td>
        <td class="p-3 font-semibold text-slate-600">₹ ${Number(f.residential_fee).toLocaleString('en-IN')}</td>
        <td class="p-3 text-right font-extrabold text-indigo-900">₹ ${Number(f.total_base_fee).toLocaleString('en-IN')}</td>
        ${currentUser && ['T1', 'T2'].includes(currentUser.role) ? `
          <td class="p-3 text-center">
            <button onclick="editFeeStructureRow('${f.class_name}', '${f.student_type}', ${f.tuition_fee}, ${f.activity_fee}, ${f.exam_fee}, ${f.residential_fee})" class="text-indigo-600 hover:text-indigo-800 font-bold text-xs bg-indigo-50 px-2.5 py-1 rounded-lg">
              <i class="fa-solid fa-pen-to-square"></i> Edit
            </button>
          </td>
        ` : ''}
      </tr>
    `).join('');
  } catch (err) {
    console.error(err);
  }
}

async function editFeeStructureRow(cname, stype, tuition, act, exam, res) {
  const newTuition = prompt(`Edit Tuition Fee for ${cname} (${stype}):`, tuition);
  if (newTuition === null) return;

  const newAct = prompt(`Edit Activity Fee:`, act);
  if (newAct === null) return;

  const newExam = prompt(`Edit Exam Fee:`, exam);
  if (newExam === null) return;

  let newRes = res;
  if (stype === 'Residential') {
    const resPrompt = prompt(`Edit Hostel/Residential Fee:`, res);
    if (resPrompt === null) return;
    newRes = parseFloat(resPrompt) || 0;
  }

  try {
    const res = await fetch('/api/fee-structures/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        class_name: cname,
        student_type: stype,
        term_name: 'Annual',
        tuition_fee: parseFloat(newTuition) || 0,
        activity_fee: parseFloat(newAct) || 0,
        exam_fee: parseFloat(newExam) || 0,
        residential_fee: newRes
      })
    });
    const data = await res.json();
    alert(data.message);
    loadFeeMaster();
  } catch (err) {
    alert("Error updating fee: " + err);
  }
}

// ================= EOD REPORTS & 4:30 PM SUMMARY =================

async function loadEodReport() {
  const targetDate = document.getElementById('eodDatePicker').value;
  const branchSelect = document.getElementById('eodBranchSelect');
  const branchVal = branchSelect ? branchSelect.value : 'All';

  try {
    const res = await fetch(`/api/reports/eod?target_date=${targetDate}&branch=${encodeURIComponent(branchVal)}`);
    const data = await res.json();
    cachedEodData = data;

    document.getElementById('eodTotalAmount').innerText = `₹ ${Number(data.total_amount).toLocaleString('en-IN')}`;
    document.getElementById('eodReceiptCount').innerText = `${data.total_receipts} Receipts Issued`;
    document.getElementById('eodCashAmount').innerText = `₹ ${Number(data.cash_total).toLocaleString('en-IN')}`;
    document.getElementById('eodUpiAmount').innerText = `₹ ${Number(data.upi_total).toLocaleString('en-IN')}`;
    document.getElementById('eodBankAmount').innerText = `₹ ${Number(data.bank_total).toLocaleString('en-IN')}`;

    document.getElementById('eodMsgBox').innerText = data.summary_msg;

    const txRows = document.getElementById('eodTransactionsRows');
    if (data.transactions.length === 0) {
      txRows.innerHTML = `<tr><td colspan="7" class="text-center p-4 text-slate-400">No transactions recorded on ${targetDate} for ${branchVal === 'All' ? 'any branch' : branchVal}.</td></tr>`;
    } else {
      txRows.innerHTML = data.transactions.map(t => `
        <tr class="hover:bg-slate-50">
          <td class="p-2.5 text-slate-500 font-mono">${t.payment_date.split(' ')[1] || t.payment_date}</td>
          <td class="p-2.5 font-bold text-indigo-700">${t.receipt_no}</td>
          <td class="p-2.5 font-bold text-slate-900">${t.student_name} <span class="text-[10px] text-slate-400 font-normal">(${t.student_branch || t.branch || 'Branch 1'} • ${t.class_name}-${t.section})</span></td>
          <td class="p-2.5 font-medium">${t.installment_label || '#' + t.installment_no}</td>
          <td class="p-2.5 font-semibold">${t.payment_mode}</td>
          <td class="p-2.5 text-slate-500 font-bold">${t.collected_by}</td>
          <td class="p-2.5 text-right font-extrabold text-emerald-700">₹ ${Number(t.amount_paid).toLocaleString('en-IN')}</td>
        </tr>
      `).join('');
    }

  } catch (err) {
    console.error(err);
  }
}

function copyEodMsg() {
  const txt = document.getElementById('eodMsgBox').innerText;
  navigator.clipboard.writeText(txt);
  alert("4:30 PM IST Summary message copied to clipboard!");
}

function triggerRestoreDbClick() {
  const isAdmin = currentUser && (currentUser.role === 'T1' || currentUser.role === 'T2');
  if (!isAdmin) {
    alert("Access Denied: Only School Admins can restore a database backup.");
    return;
  }
  document.getElementById('dbRestoreFileInput').click();
}

async function handleRestoreDbFileChosen() {
  const fileInput = document.getElementById('dbRestoreFileInput');
  if (!fileInput.files || !fileInput.files[0]) return;

  const file = fileInput.files[0];
  if (!confirm(`WARNING: Restoring will overwrite the current live database with the records from "${file.name}".\n\nA fail-safe snapshot of your current database will be automatically preserved in the backups folder first.\n\nAre you sure you want to proceed?`)) {
    fileInput.value = "";
    return;
  }

  const formData = new FormData();
  formData.append('file', file);
  const operator = currentUser ? currentUser.username : 'admin';

  try {
    const res = await fetch(`/api/backup/restore?operator_user=${operator}`, {
      method: 'POST',
      body: formData
    });

    const data = await res.json();
    fileInput.value = "";

    if (!res.ok) {
      alert("Restore Failed: " + (data.detail || "Unknown error"));
      return;
    }

    alert(data.message + "\n\nThe page will now refresh to load your recovered records.");
    window.location.reload();
  } catch (err) {
    fileInput.value = "";
    alert("Error restoring database: " + err);
  }
}

let cachedEodData = null;

async function printEodDaySheet() {
  // Always fetch fresh data for today's local date (or currently selected date if in Reports tab)
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  const localToday = `${year}-${month}-${day}`;

  const datePicker = document.getElementById('eodDatePicker');
  const eodBranchSelect = document.getElementById('eodBranchSelect');
  const quickBranchSelect = document.getElementById('quickDaySheetBranchSelect');

  // Determine branch based on which tab user is triggering it from
  let branchVal = 'All';
  if (quickBranchSelect && document.getElementById('sec-collect') && !document.getElementById('sec-collect').classList.contains('hidden')) {
    branchVal = quickBranchSelect.value || 'All';
  } else if (eodBranchSelect) {
    branchVal = eodBranchSelect.value || 'All';
  } else if (quickBranchSelect) {
    branchVal = quickBranchSelect.value || 'All';
  }

  const targetDate = (datePicker && datePicker.value) ? datePicker.value : localToday;

  let d = null;
  try {
    const res = await fetch(`/api/reports/eod?target_date=${targetDate}&branch=${encodeURIComponent(branchVal)}`);
    if (res.ok) {
      d = await res.json();
      cachedEodData = d;
    }
  } catch (e) {
    console.error(e);
  }

  if (!d) {
    alert("Could not load day sheet data. Please check your connection.");
    return;
  }

  const rows = d.transactions || [];

  const printWindow = window.open('', '_blank', 'width=900,height=750');
  if (!printWindow) {
    alert("Please allow popups in your browser to print the EOD Day Sheet.");
    return;
  }

  const txHtml = rows.map((t, idx) => `
    <tr>
      <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-family: monospace; font-size: 11px;">${idx + 1}</td>
      <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-family: monospace; font-size: 11px;">${t.payment_date.split(' ')[1] || t.payment_date}</td>
      <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-weight: bold; font-family: monospace; font-size: 11px; color: #1e1b4b;">${t.receipt_no}</td>
      <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-weight: bold; font-size: 11px;">${t.student_name} <span style="font-weight: normal; color: #64748b;">(${t.student_branch || t.branch || 'Branch 1'} • ${t.class_name}-${t.section})</span></td>
      <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-size: 11px;">${t.installment_label || '#' + t.installment_no}</td>
      <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-weight: 600; font-size: 11px;">${t.payment_mode}</td>
      <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-size: 11px; color: #475569;">${t.collected_by}</td>
      <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; text-align: right; font-weight: bold; font-size: 12px; color: #047857;">Rs. ${Number(t.amount_paid).toLocaleString('en-IN')}</td>
    </tr>
  `).join('');

  const htmlContent = `
    <!DOCTYPE html>
    <html>
    <head>
      <title>KHS EOD Day Sheet - ${targetDate}</title>
      <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; color: #0f172a; line-height: 1.4; }
        @media print {
          body { margin: 10px; }
          .no-print { display: none; }
        }
        .header { display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 15px; }
        .school-name { font-size: 20px; font-weight: 900; color: #1e1b4b; text-transform: uppercase; letter-spacing: 0.5px; }
        .title { font-size: 13px; font-weight: bold; color: #475569; text-transform: uppercase; }
        .badge { background: #f1f5f9; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 12px; }
        .summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
        .summary-card { border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px 12px; }
        .summary-label { font-size: 10px; font-weight: 800; text-transform: uppercase; color: #64748b; margin-bottom: 4px; }
        .summary-val { font-size: 16px; font-weight: 900; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 25px; }
        th { background: #f8fafc; border-bottom: 2px solid #cbd5e1; padding: 8px; font-size: 11px; font-weight: 800; text-transform: uppercase; color: #334155; text-align: left; }
        .sign-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 30px; margin-top: 40px; padding-top: 20px; border-top: 1px dashed #cbd5e1; }
        .sign-box { text-align: center; }
        .sign-line { border-top: 1px solid #0f172a; margin-top: 45px; margin-bottom: 5px; }
        .sign-label { font-size: 11px; font-weight: bold; color: #334155; }
        .btn { background: #1e1b4b; color: white; border: none; padding: 8px 16px; font-weight: bold; font-size: 12px; border-radius: 6px; cursor: pointer; }
      </style>
    </head>
    <body>
      <div class="no-print" style="margin-bottom: 15px; text-align: right;">
        <button class="btn" onclick="window.print()"><i class="fa-solid fa-print"></i> Print This Sheet</button>
      </div>

      <div class="header">
        <div>
          <div class="school-name">Kranthi High School</div>
          <div class="title">Daily Fee Collection Register & Cash Handover Sheet</div>
        </div>
        <div style="text-align: right;">
          <div class="badge">Date: ${targetDate}</div>
          <div style="font-size: 11px; font-weight: bold; color: #1e1b4b; margin-top: 5px;">Report By: ${currentUser ? (currentUser.full_name || currentUser.username) : 'System Admin'}</div>
          <div style="font-size: 10px; color: #64748b; margin-top: 2px;">Branch Scope: <strong>${d.branch || 'All Branches'}</strong></div>
          <div style="font-size: 10px; color: #94a3b8; margin-top: 2px;">Generated at: ${new Date().toLocaleTimeString()}</div>
        </div>
      </div>

      <div class="summary-grid">
        <div class="summary-card" style="border-left: 4px solid #1e1b4b;">
          <div class="summary-label">Total Day Collection</div>
          <div class="summary-val" style="color: #1e1b4b;">Rs. ${Number(d.total_amount).toLocaleString('en-IN')}</div>
          <div style="font-size: 10px; color: #64748b; margin-top: 2px;">${d.total_receipts} Receipts Issued</div>
        </div>
        <div class="summary-card" style="border-left: 4px solid #059669; background: #f0fdf4;">
          <div class="summary-label" style="color: #047857;">Cash Handover Total</div>
          <div class="summary-val" style="color: #047857;">Rs. ${Number(d.cash_total).toLocaleString('en-IN')}</div>
          <div style="font-size: 10px; color: #059669; margin-top: 2px;">Physical Currency</div>
        </div>
        <div class="summary-card" style="border-left: 4px solid #2563eb;">
          <div class="summary-label" style="color: #1d4ed8;">UPI / QR Digital</div>
          <div class="summary-val" style="color: #1d4ed8;">Rs. ${Number(d.upi_total).toLocaleString('en-IN')}</div>
          <div style="font-size: 10px; color: #64748b; margin-top: 2px;">Credited to Bank</div>
        </div>
        <div class="summary-card" style="border-left: 4px solid #7c3aed;">
          <div class="summary-label" style="color: #6d28d9;">Bank Transfer / Cheque</div>
          <div class="summary-val" style="color: #6d28d9;">Rs. ${Number(d.bank_total).toLocaleString('en-IN')}</div>
          <div style="font-size: 10px; color: #64748b; margin-top: 2px;">Direct Deposit</div>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th style="width: 30px;">#</th>
            <th style="width: 70px;">Time</th>
            <th>Receipt #</th>
            <th>Student Name & Class</th>
            <th>Installment</th>
            <th>Mode</th>
            <th>Cashier</th>
            <th style="text-align: right;">Amount</th>
          </tr>
        </thead>
        <tbody>
          ${txHtml || '<tr><td colspan="8" style="text-align: center; padding: 20px; color: #94a3b8;">No transactions on this date.</td></tr>'}
        </tbody>
      </table>

      <div class="sign-grid" style="grid-template-columns: 1fr 1fr; max-w: 600px; margin: 40px auto 0 auto;">
        <div class="sign-box">
          <div class="sign-line"></div>
          <div class="sign-label">Front Desk Cashier Signature</div>
          <div style="font-size: 11px; font-weight: bold; color: #1e1b4b; margin-top: 3px;">${currentUser ? (currentUser.full_name || currentUser.username) : 'Cashier'}</div>
          <div style="font-size: 10px; color: #64748b;">(Handed over collections)</div>
        </div>
        <div class="sign-box">
          <div class="sign-line"></div>
          <div class="sign-label">Admin / Management Signature</div>
          <div style="font-size: 10px; color: #64748b; margin-top: 17px;">(Verified & Received)</div>
        </div>
      </div>
    </body>
    </html>
  `;

  printWindow.document.open();
  printWindow.document.write(htmlContent);
  printWindow.document.close();
}

// ================= MODAL HELPERS =================

function showReceiptSuccessModal(data) {
  document.getElementById('mReceiptNoText').innerText = `Receipt #${data.receipt_no}`;
  document.getElementById('mAmountPaidText').innerText = `₹ ${Number(data.amount_paid).toLocaleString('en-IN')}`;
  document.getElementById('mBalanceDueText').innerText = `₹ ${Number(data.balance_due).toLocaleString('en-IN')}`;
  document.getElementById('mParentPhoneText').innerText = data.parent_phone;

  // View / Print receipt url
  document.getElementById('mViewReceiptBtn').href = `/receipt/${data.receipt_token}`;

  // WhatsApp click-to-send link (Direct 100% Free)
  const cleanPhone = (data.parent_phone || '').replace(/[^0-9]/g, '');
  const phoneWithCountry = cleanPhone.length === 10 ? '91' + cleanPhone : cleanPhone;
  const encodedMsg = encodeURIComponent(data.parent_msg || `Received Rs. ${data.amount_paid} towards school fee. Receipt: http://localhost:8000/receipt/${data.receipt_token}`);
  
  document.getElementById('mWhatsappBtn').href = `https://wa.me/${phoneWithCountry}?text=${encodedMsg}`;

  document.getElementById('receiptModal').classList.remove('hidden');
}

function closeReceiptModal() {
  document.getElementById('receiptModal').classList.add('hidden');
}

// ================= BULK EXCEL STUDENT IMPORT =================

function handleStudentFileChosen() {
  const fileInput = document.getElementById('excelStudentFile');
  const uploadBtn = document.getElementById('btnUploadStudentsExcel');
  const nameText = document.getElementById('chosenFileNameText');

  if (fileInput.files && fileInput.files[0]) {
    const file = fileInput.files[0];
    nameText.innerHTML = `<span class="text-indigo-600 font-extrabold"><i class="fa-solid fa-file-excel mr-1"></i> ${file.name}</span> (${(file.size / 1024).toFixed(1)} KB)`;
    uploadBtn.disabled = false;
  } else {
    nameText.innerText = "Click here to browse your Excel file (.xlsx)";
    uploadBtn.disabled = true;
  }
}

async function uploadStudentExcelFile() {
  const fileInput = document.getElementById('excelStudentFile');
  if (!fileInput.files || !fileInput.files[0]) return alert("Please select an Excel file first!");

  const uploadBtn = document.getElementById('btnUploadStudentsExcel');
  const resultBox = document.getElementById('importResultBox');

  uploadBtn.disabled = true;
  uploadBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Importing students...`;

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  const operator = currentUser ? currentUser.username : 'admin';

  try {
    const res = await fetch(`/api/students/bulk-import?operator_user=${operator}`, {
      method: 'POST',
      body: formData
    });

    const data = await res.json();
    uploadBtn.innerHTML = `<i class="fa-solid fa-cloud-arrow-up mr-1"></i> Upload & Import Students`;
    uploadBtn.disabled = false;

    resultBox.classList.remove('hidden');
    if (!res.ok) {
      resultBox.className = "p-4 rounded-xl text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200";
      resultBox.innerHTML = `<i class="fa-solid fa-circle-xmark mr-1"></i> Import Error: ${data.detail || 'Failed to process file'}`;
    } else if (data.needs_approval) {
      resultBox.className = "p-4 rounded-xl text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-300";
      resultBox.innerHTML = `
        <div class="flex items-start space-x-2">
          <i class="fa-solid fa-clock-rotate-left text-amber-600 mt-0.5 text-base"></i>
          <div>
            <p class="font-bold text-sm text-amber-900">Submitted for School Admin Approval (Batch #${data.batch_id})</p>
            <p class="mt-1">${data.message}</p>
            <p class="text-[11px] text-amber-700 mt-1">Once verified and approved by the Administrator in the <b>Approvals</b> tab, all ${data.valid_count} students will be added to the school ledger.</p>
          </div>
        </div>
      `;

      // Reset file input
      fileInput.value = "";
      document.getElementById('chosenFileNameText').innerText = "Click here to browse your Excel file (.xlsx)";
      uploadBtn.disabled = true;
    } else {
      resultBox.className = "p-4 rounded-xl text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200";
      resultBox.innerHTML = `<i class="fa-solid fa-circle-check mr-1"></i> ${data.message}`;

      // Reset file input
      fileInput.value = "";
      document.getElementById('chosenFileNameText').innerText = "Click here to browse your Excel file (.xlsx)";
      uploadBtn.disabled = true;

      // Update EOD & search counts
      loadEodReport();
    }
  } catch (err) {
    uploadBtn.innerHTML = `<i class="fa-solid fa-cloud-arrow-up mr-1"></i> Upload & Import Students`;
    uploadBtn.disabled = false;
    alert("Upload failed: " + err);
  }
}

async function loadDemoSampleStudents() {
  if (!confirm("This will add 5 new sample students with previous fee payment records for testing. Proceed?")) return;

  const operator = currentUser ? currentUser.username : 'admin';
  try {
    const res = await fetch(`/api/students/load-sample-students?operator_user=${operator}`, {
      method: 'POST'
    });
    const data = await res.json();
    alert(data.message);

    const resultBox = document.getElementById('importResultBox');
    resultBox.classList.remove('hidden');
    resultBox.className = "p-4 rounded-xl text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200";
    resultBox.innerHTML = `<i class="fa-solid fa-circle-check mr-1"></i> ${data.message}`;

    loadEodReport();
  } catch (err) {
    alert("Failed to load sample students: " + err);
  }
}

function triggerTemplateDownload() {
  window.location.href = '/api/students/download-template';
}

// ================= OTP LOGIN & MOBILE AUTH =================

function switchLoginMode(mode) {
  const tabOtp = document.getElementById('btnTabLoginOtp');
  const tabPwd = document.getElementById('btnTabLoginPwd');
  const boxOtp = document.getElementById('loginOtpContainer');
  const boxPwd = document.getElementById('loginPwdContainer');

  if (mode === 'otp') {
    tabOtp.className = "flex-1 py-2 text-xs font-extrabold text-indigo-600 border-b-2 border-indigo-600 transition";
    tabPwd.className = "flex-1 py-2 text-xs font-bold text-slate-500 hover:text-slate-800 transition";
    boxOtp.classList.remove('hidden');
    boxPwd.classList.add('hidden');
  } else {
    tabPwd.className = "flex-1 py-2 text-xs font-extrabold text-indigo-600 border-b-2 border-indigo-600 transition";
    tabOtp.className = "flex-1 py-2 text-xs font-bold text-slate-500 hover:text-slate-800 transition";
    boxPwd.classList.remove('hidden');
    boxOtp.classList.add('hidden');
  }
}

function onMobileInputChanged() {
  const inputSec = document.getElementById('otpInputSection');
  if (inputSec) inputSec.classList.add('hidden');
}

async function handleContinueMobileLogin() {
  const mobileInput = document.getElementById('otpMobileInput');
  const rawInput = mobileInput.value.trim();
  const isSa = rawInput.toUpperCase().startsWith("SA");
  const cleanDigits = isSa ? rawInput.slice(2) : rawInput;

  if (cleanDigits.length !== 10 || isNaN(cleanDigits)) {
    alert("Please enter a valid 10-digit mobile number.");
    return;
  }

  const btn = document.getElementById('btnRequestOtp');
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Checking...`;

  try {
    const res = await fetch('/api/auth/check-method', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mobile: rawInput })
    });
    const data = await res.json();
    btn.disabled = false;
    btn.innerHTML = `<i class="fa-solid fa-arrow-right mr-1"></i> Continue`;

    if (!res.ok) {
      alert(data.detail || "Verification failed");
      return;
    }

    const inputSec = document.getElementById('otpInputSection');
    const notice = document.getElementById('authMethodNotice');
    const label = document.getElementById('otpCodeLabel');
    const codeInput = document.getElementById('otpCodeInput');

    inputSec.classList.remove('hidden');
    codeInput.value = "";
    codeInput.focus();

    if (data.has_authenticator) {
      notice.className = "bg-indigo-50 p-3 rounded-xl border border-indigo-200 text-xs text-indigo-900 space-y-1";
      notice.innerHTML = `
        <div class="flex items-center space-x-1.5 font-bold text-indigo-800">
          <i class="fa-solid fa-shield-halved text-indigo-600"></i>
          <span>Google / Microsoft Authenticator</span>
        </div>
        <p class="text-[11px] text-indigo-700 leading-relaxed">
          Open <b>Google Authenticator</b> on your mobile and enter the 6-digit code for <b>Kranthi High School</b>.
        </p>
      `;
      if (label) label.innerText = "Enter 6-Digit Authenticator Code *";
    } else {
      notice.className = "bg-amber-50 p-3 rounded-xl border border-amber-200 text-xs text-amber-900 space-y-1";
      notice.innerHTML = `
        <div class="flex items-center space-x-1.5 font-bold text-amber-800">
          <i class="fa-solid fa-triangle-exclamation text-amber-600"></i>
          <span>Authenticator QR Not Yet Setup</span>
        </div>
        <p class="text-[11px] text-amber-800 leading-relaxed">
          Please ask the School Admin to open <b>Staff Management</b> and click <b>Setup QR</b> so you can scan the Authenticator on your phone.
        </p>
      `;
      if (label) label.innerText = "Enter 6-Digit Code *";
    }
  } catch (err) {
    btn.disabled = false;
    btn.innerHTML = `<i class="fa-solid fa-arrow-right mr-1"></i> Continue`;
    alert("Error communicating with server: " + err);
  }
}

async function handleRequestOtp(isFallback = false) {
  const mobileInput = document.getElementById('otpMobileInput');
  const rawInput = mobileInput.value.trim();
  const isSa = rawInput.toUpperCase().startsWith("SA");
  const cleanDigits = isSa ? rawInput.slice(2) : rawInput;

  if (cleanDigits.length !== 10 || isNaN(cleanDigits)) {
    alert("Please enter a valid 10-digit mobile number.");
    return;
  }

  try {
    const res = await fetch('/api/auth/request-otp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mobile: rawInput })
    });
    const data = await res.json();

    if (!res.ok) {
      alert(data.detail || "Failed to generate OTP");
      return;
    }

    const inputSec = document.getElementById('otpInputSection');
    const notice = document.getElementById('authMethodNotice');
    const label = document.getElementById('otpCodeLabel');
    const codeInput = document.getElementById('otpCodeInput');

    inputSec.classList.remove('hidden');
    notice.className = "bg-emerald-50 p-3 rounded-xl border border-emerald-200 text-xs text-emerald-800 space-y-2";
    notice.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="font-bold flex items-center"><i class="fa-solid fa-circle-check text-emerald-600 mr-1.5"></i> One-Time Passcode Generated</span>
        <span class="font-mono font-black text-emerald-900 bg-white px-2 py-0.5 rounded border border-emerald-200">OTP: ${data.otp_code}</span>
      </div>
      <a target="_blank" href="${data.whatsapp_url}" class="block text-center bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold py-1.5 px-3 rounded-lg text-[11px] shadow-xs transition">
        <i class="fa-brands fa-whatsapp mr-1 text-sm"></i> Send OTP to Mobile via WhatsApp (Free)
      </a>
    `;
    label.innerText = "Enter 6-Digit OTP *";
    codeInput.value = data.otp_code;
    codeInput.focus();
  } catch (err) {
    alert("Error requesting OTP: " + err);
  }
}

async function handleVerifyOtpSubmit() {
  const rawInput = document.getElementById('otpMobileInput').value.trim();
  const isSa = rawInput.toUpperCase().startsWith("SA");
  const cleanDigits = isSa ? rawInput.slice(2) : rawInput;
  const otpCode = document.getElementById('otpCodeInput').value.trim();

  if (cleanDigits.length !== 10 || isNaN(cleanDigits)) {
    alert("Please enter a valid 10-digit mobile number.");
    return;
  }
  if (!otpCode || otpCode.length !== 6) {
    alert("Please enter the 6-digit code.");
    return;
  }

  const sId = getOrCreateSessionId();

  try {
    const res = await fetch('/api/auth/verify-otp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mobile: rawInput, otp_code: otpCode, session_id: sId })
    });

    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Verification failed");
      return;
    }

    currentUser = data.user;
    if (data.session_id) sessionStorage.setItem('khs_session_id', data.session_id);
    localStorage.setItem('khs_user', JSON.stringify(currentUser));
    document.getElementById('loginModal').classList.add('hidden');
    const header = document.getElementById('appTopHeader');
    const main = document.getElementById('appMainContainer');
    if (header) header.classList.remove('hidden');
    if (main) main.classList.remove('hidden');
    applyUserRoleUI();
    resetInactivityTimer();

    // Show welcome screen with big school logo on initial login
    switchTab('welcome');

    // Reload contextual data
    loadPendingDiscounts();
    loadFeeMaster();
    loadEodReport();
    if (currentUser.role === 'T1' || currentUser.role === 'T2') {
      loadStaffUsers();
    }
  } catch (err) {
    alert("Server error verifying code: " + err);
  }
}

// ================= FRONT DESK STAFF MANAGEMENT (ADMIN) =================

async function loadStaffUsers() {
  try {
    const res = await fetch('/api/staff/list');
    const data = await res.json();

    const badge = document.getElementById('staffCountBadge');
    if (badge) {
      badge.innerText = `${data.count} / 10 Users Added`;
      if (data.count >= 10) {
        badge.className = "text-xs font-bold bg-amber-100 text-amber-800 px-3 py-1 rounded-full border border-amber-300";
      } else {
        badge.className = "text-xs font-bold bg-indigo-50 text-indigo-700 px-3 py-1 rounded-full border border-indigo-200";
      }
    }

    const tbody = document.getElementById('staffTableRows');
    if (!tbody) return;

    if (!data.staff || data.staff.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-slate-400">No front desk staff added yet. Register using the form above.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.staff.map(u => {
      const isBlocked = (u.is_active === 0);
      const statusBadge = isBlocked 
        ? `<span class="bg-rose-100 text-rose-800 text-[10px] font-extrabold px-2 py-0.5 rounded-full"><i class="fa-solid fa-ban mr-1"></i>BLOCKED</span>`
        : `<span class="bg-emerald-100 text-emerald-800 text-[10px] font-extrabold px-2 py-0.5 rounded-full"><i class="fa-solid fa-circle-check mr-1"></i>ACTIVE</span>`;
      
      const toggleBtn = isBlocked
        ? `<button onclick="toggleStaffBlock(${u.id}, true)" class="bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-300 font-bold px-2.5 py-1 rounded-lg text-xs transition"><i class="fa-solid fa-unlock mr-1"></i>Unblock</button>`
        : `<button onclick="toggleStaffBlock(${u.id}, false)" class="bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-300 font-bold px-2.5 py-1 rounded-lg text-xs transition"><i class="fa-solid fa-lock mr-1"></i>Block</button>`;

      const authBadge = u.has_authenticator
        ? `<button onclick="openAuthenticatorSetupModal(${u.id}, '${u.full_name.replace(/'/g, "\\'")}')" class="bg-purple-50 hover:bg-purple-100 text-purple-700 border border-purple-200 font-bold px-2.5 py-1 rounded-lg text-xs transition" title="View or Re-scan QR Code">
             <i class="fa-solid fa-qrcode mr-1 text-purple-600"></i> Active (View QR)
           </button>`
        : `<button onclick="openAuthenticatorSetupModal(${u.id}, '${u.full_name.replace(/'/g, "\\'")}')" class="bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold px-2.5 py-1 rounded-lg text-xs shadow-xs transition" title="Setup Authenticator App">
             <i class="fa-solid fa-qrcode mr-1"></i> Setup QR
           </button>`;

      const sessionBadge = u.is_online
        ? `<span class="inline-flex items-center text-[10px] font-extrabold text-emerald-800 bg-emerald-100 border border-emerald-300 px-2 py-0.5 rounded-full">
             <span class="w-1.5 h-1.5 rounded-full bg-emerald-600 mr-1 animate-pulse"></span> ONLINE
           </span>`
        : `<span class="inline-flex items-center text-[10px] font-bold text-slate-500 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-full">OFFLINE</span>`;

      const ipInfoHtml = u.last_ip 
        ? `<div class="text-[10px] font-mono text-indigo-700 font-bold mt-1 flex items-center">
             <i class="fa-solid fa-globe mr-1 text-indigo-500"></i> ${u.last_ip}
           </div>
           <div class="text-[10px] text-slate-500 mt-0.5">
             <i class="fa-solid fa-laptop mr-1 text-slate-400"></i> ${u.last_device || 'Unknown Device'}
           </div>`
        : `<div class="text-[10px] text-slate-400 mt-1">No IP recorded</div>`;

      return `
        <tr class="hover:bg-slate-50 transition">
          <td class="p-3">
            <div class="font-bold text-slate-900">${u.full_name}</div>
            <div class="text-[10px] text-slate-500">${u.phone || ''}</div>
          </td>
          <td class="p-3 font-mono font-bold text-indigo-900">${u.username}</td>
          <td class="p-3">
            <div>${sessionBadge}</div>
            ${ipInfoHtml}
          </td>
          <td class="p-3">${statusBadge}</td>
          <td class="p-3 text-center">${toggleBtn}</td>
          <td class="p-3 text-right space-x-1.5 whitespace-nowrap">
            ${authBadge}
            <button onclick="forceLogoutStaff(${u.id}, '${u.full_name.replace(/'/g, "\\'")}', '${u.username}')" class="bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-300 font-bold px-2.5 py-1 rounded-lg text-xs transition" title="Force Logout Active Session for this staff">
              <i class="fa-solid fa-arrow-right-from-bracket mr-1"></i> Force Logout
            </button>
            <button onclick="editStaffUser(${u.id}, '${u.full_name.replace(/'/g, "\\'")}', '${u.username}')" class="bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 font-bold px-2.5 py-1 rounded-lg text-xs transition" title="Edit Staff Name or Mobile">
              <i class="fa-solid fa-pen-to-square mr-1"></i> Edit
            </button>
            <button onclick="deleteStaffUser(${u.id}, '${u.full_name.replace(/'/g, "\\'")}')" class="bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 font-bold px-2.5 py-1 rounded-lg text-xs transition" title="Permanently Delete Staff">
              <i class="fa-solid fa-trash-can mr-1"></i> Remove
            </button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error("Error loading staff:", err);
  }
}

async function openAuthenticatorSetupModal(userId, fullName) {
  try {
    const res = await fetch(`/api/staff/${userId}/authenticator-qr`);
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Failed to load Authenticator QR code");
      return;
    }

    document.getElementById('qrStaffNameText').innerText = `Staff: ${fullName} (${data.mobile})`;
    document.getElementById('qrCodeImage').src = data.qr_image_data;
    document.getElementById('qrSecretKeyText').innerText = data.secret_key;
    document.getElementById('authenticatorQrModal').classList.remove('hidden');
  } catch (err) {
    alert("Error fetching Authenticator QR: " + err);
  }
}

function closeAuthenticatorQrModal() {
  document.getElementById('authenticatorQrModal').classList.add('hidden');
  loadStaffUsers();
}

async function handleStaffAddSubmit(e) {
  e.preventDefault();
  const nameInput = document.getElementById('newStaffName');
  const mobileInput = document.getElementById('newStaffMobile');

  const fullName = nameInput.value.trim().toUpperCase();
  const mobile = mobileInput.value.trim();

  if (!fullName) {
    alert("Please enter the staff member's full name.");
    return;
  }
  if (mobile.length !== 10) {
    alert("Please enter a valid 10-digit mobile number.");
    return;
  }

  const btn = document.getElementById('btnAddStaffBtn');
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Adding...`;

  try {
    const res = await fetch('/api/staff/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        full_name: fullName,
        mobile: mobile,
        admin_username: currentUser ? currentUser.username : 'admin'
      })
    });

    const data = await res.json();
    btn.disabled = false;
    btn.innerHTML = `<i class="fa-solid fa-plus mr-1"></i> Add Staff User`;

    if (!res.ok) {
      alert(data.detail || "Failed to add staff member.");
      return;
    }

    alert(data.message);
    nameInput.value = "";
    mobileInput.value = "";
    loadStaffUsers();
  } catch (err) {
    btn.disabled = false;
    btn.innerHTML = `<i class="fa-solid fa-plus mr-1"></i> Add Staff User`;
    alert("Server error adding staff: " + err);
  }
}

async function editStaffUser(userId, currentName, currentMobile) {
  const newName = prompt("Edit Staff Full Name:", currentName);
  if (newName === null) return;
  const trimmedName = newName.trim().toUpperCase();
  if (!trimmedName) {
    alert("Staff Full Name cannot be empty.");
    return;
  }

  const newMobile = prompt("Edit 10-Digit Mobile Number (Login Username):", currentMobile);
  if (newMobile === null) return;
  const trimmedMobile = newMobile.trim().replace(/[^0-9]/g, '');
  if (trimmedMobile.length !== 10) {
    alert("Please enter a valid 10-digit mobile number.");
    return;
  }

  try {
    const res = await fetch('/api/staff/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        full_name: trimmedName,
        mobile: trimmedMobile
      })
    });

    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Failed to update staff user");
      return;
    }

    alert(data.message);
    loadStaffUsers();
  } catch (err) {
    alert("Server error updating staff: " + err);
  }
}

async function deleteStaffUser(userId, fullName) {
  if (!confirm(`Are you sure you want to permanently remove staff member "${fullName}"? They will no longer be able to log in.`)) {
    return;
  }

  try {
    const res = await fetch('/api/staff/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId })
    });

    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Failed to remove staff user");
      return;
    }

    alert(data.message);
    loadStaffUsers();
  } catch (err) {
    alert("Server error removing staff: " + err);
  }
}

async function toggleStaffBlock(userId, unblock) {
  const actionText = unblock ? "Unblock this user so they can login and receive OTPs" : "Block this user so they will be denied login and OTPs";
  if (!confirm(`Are you sure you want to ${actionText}?`)) return;

  try {
    const res = await fetch('/api/staff/toggle-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        is_active: unblock ? 1 : 0,
        admin_username: currentUser ? currentUser.username : 'admin'
      })
    });

    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Failed to update staff access");
      return;
    }

    alert(data.message);
    loadStaffUsers();
  } catch (err) {
    alert("Server error toggling staff access: " + err);
  }
}

async function forceLogoutStaff(userId, fullName, username) {
  if (!currentUser || !['T1', 'T2'].includes(currentUser.role)) {
    return alert("Only Admin or Super Admin can force logout staff.");
  }

  if (!confirm(`Are you sure you want to FORCE LOGOUT all active sessions for "${fullName}" (${username})? They will be immediately disconnected and required to re-authenticate.`)) {
    return;
  }

  try {
    const res = await fetch('/api/staff/force-logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        operator_user: currentUser.username
      })
    });

    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Failed to force logout staff");
      return;
    }

    alert(data.message);
    loadStaffUsers();
  } catch (err) {
    alert("Server error forcing logout: " + err);
  }
}

// ================= AUDIT & SESSION ACTIVITY LOGS (ADMIN & SUPER ADMIN) =================

async function loadAuditLogs() {
  if (!currentUser) return;
  const isAdmin = (currentUser.role === 'T1' || currentUser.role === 'T2');
  if (!isAdmin) return;

  const dateInput = document.getElementById('auditDatePicker');
  let targetDate = dateInput ? dateInput.value : '';
  if (!targetDate) {
    const now = new Date();
    targetDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    if (dateInput) dateInput.value = targetDate;
  }

  const container = document.getElementById('auditSessionsContainer');
  if (!container) return;

  container.innerHTML = `
    <div class="text-center py-12 text-slate-400 text-xs">
      <i class="fa-solid fa-spinner fa-spin text-lg mb-2 text-indigo-600"></i><br>
      Fetching audit trail & session logs for ${targetDate}...
    </div>
  `;

  // Update subtitle based on role
  const subtitle = document.getElementById('auditSubtitle');
  if (subtitle) {
    if (currentUser.role === 'T1') {
      subtitle.innerText = "Super Admin View: Full transparency into sessions & transactions for Cashiers (T3) and Admin (T2)";
    } else {
      subtitle.innerText = "Admin View: Review login/logout times and transactions completed by Front Desk Cashiers (T3)";
    }
  }

  try {
    const res = await fetch(`/api/audit-logs?target_date=${targetDate}&operator_user=${encodeURIComponent(currentUser.username)}`);
    const data = await res.json();

    if (!res.ok) {
      container.innerHTML = `
        <div class="p-6 text-center text-rose-600 bg-rose-50 rounded-xl border border-rose-200 text-xs font-bold">
          <i class="fa-solid fa-triangle-exclamation mr-1.5"></i> ${data.detail || "Unable to load logs"}
        </div>
      `;
      return;
    }

    // Compute summary KPI counts
    let totalAdmissions = 0;
    let totalPayments = 0;
    let totalAmount = 0;

    data.raw_logs.forEach(l => {
      if (l.action_type === 'NEW_ADMISSION') {
        totalAdmissions++;
        totalAmount += (l.amount || 0);
      } else if (l.action_type === 'FEE_PAYMENT') {
        totalPayments++;
        totalAmount += (l.amount || 0);
      }
    });

    document.getElementById('auditTotalSessions').innerText = data.sessions.length;
    document.getElementById('auditTotalAdmissions').innerText = totalAdmissions;
    document.getElementById('auditTotalPayments').innerText = totalPayments;
    document.getElementById('auditTotalAmount').innerText = '₹ ' + Number(totalAmount).toLocaleString('en-IN');

    const notice = document.getElementById('auditTimestampNotice');
    if (notice) notice.innerText = `Showing ${data.total_logs} activities across ${data.sessions.length} sessions for ${targetDate}`;

    if (!data.sessions || data.sessions.length === 0) {
      container.innerHTML = `
        <div class="bg-slate-50 border border-dashed border-slate-200 rounded-2xl p-12 text-center">
          <div class="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400 mb-3">
            <i class="fa-solid fa-clock-rotate-left text-xl"></i>
          </div>
          <h4 class="text-sm font-bold text-slate-700">No Activity Logs Found</h4>
          <p class="text-xs text-slate-400 mt-1">There are no staff login or transaction records registered on ${targetDate}.</p>
        </div>
      `;
      return;
    }

    // Render session cards
    let html = '';
    data.sessions.forEach(sess => {
      const roleLabel = (sess.role === 'T1') ? 'Super Admin' : (sess.role === 'T2' ? 'Admin' : 'Front Desk / T3');
      const roleBadgeClass = (sess.role === 'T1')
        ? 'bg-indigo-100 text-indigo-900 border-indigo-200'
        : (sess.role === 'T2' ? 'bg-purple-100 text-purple-900 border-purple-200' : 'bg-emerald-100 text-emerald-900 border-emerald-200');

      // Format Login / Logout times
      const loginDisplay = sess.login_time 
        ? new Date(sess.login_time.replace(' ', 'T')).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })
        : 'In Progress / Prior';
      
      let logoutDisplay = '';
      if (sess.logout_time) {
        const timeStr = new Date(sess.logout_time.replace(' ', 'T')).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
        const isTimeout = sess.logout_type === 'AUTO_TIMEOUT';
        logoutDisplay = `<span class="inline-flex items-center text-xs font-bold ${isTimeout ? 'text-amber-700 bg-amber-50 border-amber-200' : 'text-slate-700 bg-slate-100 border-slate-200'} px-2 py-0.5 rounded border">
          <i class="fa-solid ${isTimeout ? 'fa-hourglass-end mr-1 text-amber-600' : 'fa-right-from-bracket mr-1 text-slate-500'}"></i>
          ${timeStr} (${isTimeout ? 'Auto-Timeout' : 'Logged Out'})
        </span>`;
      } else {
        logoutDisplay = `<span class="inline-flex items-center text-xs font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5 animate-pulse"></span>
          Session Active
        </span>`;
      }

      // Filter transaction actions inside this session (exclude LOGIN/LOGOUT for transaction list)
      const txnActions = sess.actions.filter(a => a.action_type !== 'LOGIN' && a.action_type !== 'LOGOUT' && a.action_type !== 'AUTO_TIMEOUT');

      let txnRowsHtml = '';
      if (txnActions.length === 0) {
        txnRowsHtml = `
          <div class="py-3 px-4 text-xs text-slate-400 italic bg-white rounded-lg border border-slate-100 text-center">
            No financial transactions (Admissions or Fee Payments) recorded during this session.
          </div>
        `;
      } else {
        txnRowsHtml = txnActions.map(txn => {
          const isAdmission = (txn.action_type === 'NEW_ADMISSION');
          const typeIcon = isAdmission ? 'fa-user-plus text-indigo-600 bg-indigo-50' : 'fa-receipt text-emerald-600 bg-emerald-50';
          const typeBadge = isAdmission
            ? '<span class="bg-indigo-100 text-indigo-800 text-[10px] font-extrabold px-2 py-0.5 rounded uppercase">New Admission</span>'
            : '<span class="bg-emerald-100 text-emerald-800 text-[10px] font-extrabold px-2 py-0.5 rounded uppercase">Fee Payment</span>';

          const timeFormatted = new Date(txn.timestamp.replace(' ', 'T')).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });

          return `
            <div class="flex items-center justify-between p-3 bg-white hover:bg-slate-50/80 rounded-xl border border-slate-200/80 transition text-xs">
              <div class="flex items-center space-x-3">
                <div class="w-8 h-8 rounded-lg flex items-center justify-center ${typeIcon} shrink-0">
                  <i class="fa-solid ${isAdmission ? 'fa-user-plus' : 'fa-receipt'} text-xs"></i>
                </div>
                <div>
                  <div class="flex items-center space-x-2">
                    ${typeBadge}
                    <span class="font-bold text-slate-800">${txn.action_details}</span>
                  </div>
                  <div class="text-[11px] text-slate-400 mt-0.5 flex items-center space-x-3">
                    <span><i class="fa-regular fa-clock mr-1"></i>${timeFormatted}</span>
                    ${txn.entity_id ? `<span><i class="fa-solid fa-hashtag mr-0.5"></i>Ref: ${txn.entity_id}</span>` : ''}
                  </div>
                </div>
              </div>
              <div class="text-right shrink-0">
                ${txn.amount > 0 ? `<div class="font-black text-slate-900 text-sm">₹ ${Number(txn.amount).toLocaleString('en-IN')}</div>` : '<div class="text-slate-400 font-bold">—</div>'}
              </div>
            </div>
          `;
        }).join('');
      }

      html += `
        <div class="bg-slate-50/90 border border-slate-200 rounded-2xl p-5 space-y-4 hover:border-slate-300 transition shadow-xs">
          <!-- Session Header -->
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
            <div class="flex items-center space-x-3">
              <div class="w-10 h-10 rounded-xl bg-indigo-600 text-white font-black text-sm flex items-center justify-center shadow-xs">
                ${sess.full_name ? sess.full_name.charAt(0).toUpperCase() : 'U'}
              </div>
              <div>
                <div class="flex items-center space-x-2">
                  <h4 class="font-extrabold text-slate-900 text-sm">${sess.full_name || sess.username}</h4>
                  <span class="text-[10px] font-bold px-2 py-0.5 rounded-full border ${roleBadgeClass}">${roleLabel}</span>
                  <span class="text-[11px] text-slate-400">(${sess.username})</span>
                </div>
                <div class="text-[11px] text-slate-500 mt-0.5">
                  <i class="fa-solid fa-code-branch text-slate-400 mr-1"></i>${sess.branch || 'Branch 1'}
                </div>
              </div>
            </div>

            <!-- Login / Logout times & IP / Device Tracker -->
            <div class="flex flex-wrap items-center gap-3 text-xs">
              <div class="bg-white px-3 py-1.5 rounded-xl border border-slate-200 text-left">
                <div class="text-[10px] font-bold text-slate-400 uppercase">Login Time</div>
                <div class="font-extrabold text-slate-800 flex items-center mt-0.5">
                  <i class="fa-solid fa-right-to-bracket mr-1.5 text-emerald-600"></i> ${loginDisplay}
                </div>
              </div>

              <div class="bg-white px-3 py-1.5 rounded-xl border border-slate-200 text-left">
                <div class="text-[10px] font-bold text-slate-400 uppercase">Logout Status</div>
                <div class="mt-0.5">
                  ${logoutDisplay}
                </div>
              </div>

              <div class="bg-white px-3 py-1.5 rounded-xl border border-slate-200 text-left">
                <div class="text-[10px] font-bold text-slate-400 uppercase">IP Address</div>
                <div class="font-black text-indigo-700 flex items-center mt-0.5">
                  <i class="fa-solid fa-globe mr-1.5 text-indigo-500"></i> ${sess.ip_address || '127.0.0.1 (Local)'}
                </div>
              </div>

              <div class="bg-white px-3 py-1.5 rounded-xl border border-slate-200 text-left">
                <div class="text-[10px] font-bold text-slate-400 uppercase">Device & Browser</div>
                <div class="font-bold text-slate-700 flex items-center mt-0.5">
                  <i class="fa-solid fa-laptop mr-1.5 text-slate-500"></i> ${sess.device_browser || 'Desktop • Browser'}
                </div>
              </div>
            </div>
          </div>

          <!-- Transactions Subheading -->
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-extrabold text-slate-500 uppercase tracking-wider">
                <i class="fa-solid fa-list-check mr-1 text-indigo-500"></i> Actions & Transactions (${txnActions.length})
              </span>
            </div>
            <div class="space-y-2">
              ${txnRowsHtml}
            </div>
          </div>
        </div>
      `;
    });

    container.innerHTML = html;

  } catch (err) {
    container.innerHTML = `
      <div class="p-6 text-center text-rose-600 bg-rose-50 rounded-xl border border-rose-200 text-xs font-bold">
        <i class="fa-solid fa-triangle-exclamation mr-1.5"></i> Network error fetching audit logs: ${err}
      </div>
    `;
  }
}

// ================= VISITOR & IP ACCESS TRACKER (OPTION 2) =================

let currentIpLogsData = [];

async function loadIpTrackerLogs() {
  if (!currentUser) return;
  const isAdmin = (currentUser.role === 'T1' || currentUser.role === 'T2');
  if (!isAdmin) return;

  const dateInput = document.getElementById('ipDatePicker');
  let targetDate = dateInput ? dateInput.value : '';
  if (!targetDate) {
    const now = new Date();
    targetDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    if (dateInput) dateInput.value = targetDate;
  }

  const tbody = document.getElementById('ipLogsTableBody');
  if (!tbody) return;

  tbody.innerHTML = `
    <tr>
      <td colspan="6" class="p-8 text-center text-slate-400">
        <i class="fa-solid fa-spinner fa-spin text-lg mb-2 text-indigo-600"></i><br>
        Fetching visitor & IP logs for ${targetDate}...
      </td>
    </tr>
  `;

  try {
    const res = await fetch(`/api/security/ip-logs?target_date=${targetDate}&operator_user=${encodeURIComponent(currentUser.username)}`);
    const data = await res.json();

    if (!res.ok) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="p-6 text-center text-rose-600 font-bold bg-rose-50">
            <i class="fa-solid fa-triangle-exclamation mr-1.5"></i> ${data.detail || "Unable to load IP access logs"}
          </td>
        </tr>
      `;
      return;
    }

    currentIpLogsData = data.logs || [];

    const visitsEl = document.getElementById('ipTotalVisits');
    if (visitsEl) visitsEl.innerText = data.total_visits || 0;
    const uniqEl = document.getElementById('ipUniqueCount');
    if (uniqEl) uniqEl.innerText = data.unique_ips || 0;
    const deskEl = document.getElementById('ipDesktopCount');
    if (deskEl) deskEl.innerText = data.desktop_count || 0;
    const mobEl = document.getElementById('ipMobileCount');
    if (mobEl) mobEl.innerText = data.mobile_count || 0;

    const notice = document.getElementById('ipTimestampNotice');
    if (notice) notice.innerText = `Showing ${currentIpLogsData.length} records for ${targetDate}`;

    renderIpLogsTable(currentIpLogsData);
  } catch (err) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="p-6 text-center text-rose-600 font-bold bg-rose-50">
          <i class="fa-solid fa-triangle-exclamation mr-1.5"></i> Network error: ${err.message}
        </td>
      </tr>
    `;
  }
}

function renderIpLogsTable(logs) {
  const tbody = document.getElementById('ipLogsTableBody');
  if (!tbody) return;

  if (!logs || logs.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="p-8 text-center text-slate-400">
          <i class="fa-solid fa-network-wired text-xl mb-2 text-slate-300"></i><br>
          No access or visitor activity recorded for this date.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = logs.map(row => {
    const timeFormatted = row.timestamp ? new Date(row.timestamp.replace(' ', 'T')).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }) : row.timestamp;
    
    // Status badge
    const isSuccess = (row.status_code >= 200 && row.status_code < 300);
    const isRedirect = (row.status_code >= 300 && row.status_code < 400);
    const statusBadge = isSuccess
      ? `<span class="px-2 py-0.5 rounded text-[10px] font-extrabold bg-emerald-50 text-emerald-700 border border-emerald-200">${row.status_code} OK</span>`
      : (isRedirect ? `<span class="px-2 py-0.5 rounded text-[10px] font-extrabold bg-blue-50 text-blue-700 border border-blue-200">${row.status_code}</span>`
      : `<span class="px-2 py-0.5 rounded text-[10px] font-extrabold bg-rose-50 text-rose-700 border border-rose-200">${row.status_code}</span>`);

    // Device badge
    const isMobile = (row.device_browser || '').includes('Android') || (row.device_browser || '').includes('iPhone') || (row.device_browser || '').includes('iPad');
    const deviceIcon = isMobile ? 'fa-mobile-screen text-indigo-500' : 'fa-laptop text-slate-600';

    // Meaningful action icon
    let actIcon = 'fa-arrow-pointer text-slate-400';
    const ep = row.endpoint || '';
    if (ep.includes('Login')) actIcon = 'fa-right-to-bracket text-emerald-600';
    else if (ep.includes('Failed')) actIcon = 'fa-triangle-exclamation text-rose-600';
    else if (ep.includes('Portal')) actIcon = 'fa-school text-indigo-600';
    else if (ep.includes('Receipt')) actIcon = 'fa-receipt text-blue-600';
    else if (ep.includes('Admission')) actIcon = 'fa-user-plus text-indigo-600';
    else if (ep.includes('Fee')) actIcon = 'fa-indian-rupee-sign text-emerald-600';
    else if (ep.includes('Logout')) actIcon = 'fa-right-from-bracket text-slate-500';

    return `
      <tr class="hover:bg-slate-50 transition border-b border-slate-100">
        <td class="p-3 whitespace-nowrap font-mono text-[11px] text-slate-500">
          <i class="fa-regular fa-clock mr-1 text-slate-400"></i>${timeFormatted}
        </td>
        <td class="p-3 whitespace-nowrap">
          <span class="inline-flex items-center font-mono font-bold text-indigo-700 bg-indigo-50/80 px-2.5 py-1 rounded-lg border border-indigo-100 text-xs">
            <i class="fa-solid fa-globe mr-1.5 text-indigo-500"></i>${row.ip_address}
          </span>
        </td>
        <td class="p-3 whitespace-nowrap text-slate-700">
          <span class="inline-flex items-center">
            <i class="fa-solid ${deviceIcon} mr-1.5"></i>
            <span class="font-bold">${row.device_browser || 'Unknown Device'}</span>
          </span>
        </td>
        <td class="p-3 text-xs text-slate-800">
          <span class="inline-flex items-center font-bold text-slate-800">
            <i class="fa-solid ${actIcon} mr-2"></i>
            <span>${row.endpoint}</span>
          </span>
        </td>
        <td class="p-3 whitespace-nowrap">
          <span class="inline-flex items-center text-xs font-bold text-slate-700">
            <i class="fa-solid fa-user-circle mr-1 text-slate-400"></i>${row.username || 'Visitor / Public'}
          </span>
        </td>
        <td class="p-3 text-center whitespace-nowrap">
          ${statusBadge}
        </td>
      </tr>
    `;
  }).join('');
}

function filterIpLogsTable() {
  const query = (document.getElementById('ipFilterSearch')?.value || '').toLowerCase().trim();
  if (!query) {
    renderIpLogsTable(currentIpLogsData);
    return;
  }
  const filtered = currentIpLogsData.filter(r => 
    (r.ip_address || '').toLowerCase().includes(query) ||
    (r.endpoint || '').toLowerCase().includes(query) ||
    (r.username || '').toLowerCase().includes(query) ||
    (r.device_browser || '').toLowerCase().includes(query)
  );
  renderIpLogsTable(filtered);
}

// ================= CLASS-WISE ENROLLED STUDENTS =================

let classWiseLoadedStudents = [];

async function loadClassWiseStudents() {
  const branchVal = document.getElementById('filterCwBranch') ? document.getElementById('filterCwBranch').value : 'All';
  const cname = document.getElementById('filterCwClass') ? document.getElementById('filterCwClass').value : 'All';
  const sec = document.getElementById('filterCwSection') ? document.getElementById('filterCwSection').value : 'All';
  const status = document.getElementById('filterCwStatus') ? document.getElementById('filterCwStatus').value : 'Active';

  const tbody = document.getElementById('classWiseTableRows');
  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="12" class="p-8 text-center text-slate-400"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Loading class-wise records...</td></tr>`;
  }

  try {
    const url = `/api/students/class-wise?branch=${encodeURIComponent(branchVal)}&class_name=${encodeURIComponent(cname)}&section=${encodeURIComponent(sec)}&status=${encodeURIComponent(status)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to load class-wise data");
    const data = await res.json();

    classWiseLoadedStudents = data.students || [];

    // Render Quick Class Pills
    renderClassWisePills(data.class_summaries || [], cname);

    // Render Metrics Banner
    const stats = data.stats || {};
    const isAdmin = currentUser && (currentUser.role === 'T1' || currentUser.role === 'T2');
    document.getElementById('cwStatTotal').innerText = stats.total_enrolled || 0;
    document.getElementById('cwStatActiveSub').innerText = `${stats.active_count || 0} Active students`;

    const cardAgreed = document.getElementById('cwCardAgreed');
    const cardPaid = document.getElementById('cwCardPaid');
    const cardBal = document.getElementById('cwCardBalance');
    const thAgreed = document.getElementById('thCwAgreed');
    const thPaid = document.getElementById('thCwPaid');
    const thBal = document.getElementById('thCwBalance');

    if (isAdmin) {
      document.getElementById('cwStatAgreed').innerText = `₹ ${(stats.total_agreed || 0).toLocaleString('en-IN')}`;
      document.getElementById('cwStatPaid').innerText = `₹ ${(stats.total_paid || 0).toLocaleString('en-IN')}`;
      document.getElementById('cwStatBalance').innerText = `₹ ${(stats.total_balance || 0).toLocaleString('en-IN')}`;
    }

    [cardAgreed, cardPaid, cardBal].forEach(el => {
      if (el) el.style.display = isAdmin ? '' : 'none';
    });
    [thAgreed, thPaid, thBal].forEach(el => {
      if (el) el.style.display = isAdmin ? '' : 'none';
    });

    // Render Student Table
    renderClassWiseTable(classWiseLoadedStudents);

  } catch (err) {
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="12" class="p-6 text-center text-rose-500 font-bold">Error loading students: ${err}</td></tr>`;
    }
  }
}

function renderClassWisePills(summaries, activeClass) {
  const container = document.getElementById('classWisePillsContainer');
  const banner = document.getElementById('classSummaryTotalBanner');
  if (!container) return;

  const totalAllStudents = summaries.reduce((acc, s) => acc + (s.total_students || 0), 0);
  const totalActiveStudents = summaries.reduce((acc, s) => acc + (s.active_students || 0), 0);
  if (banner) {
    banner.innerText = `Total ${totalAllStudents} Enrolled (${totalActiveStudents} Active) across ${summaries.length} Classes`;
  }

  let html = `
    <button onclick="selectClassPill('All')" class="px-3.5 py-1.5 rounded-xl text-xs font-bold transition flex items-center space-x-1.5 ${activeClass === 'All' ? 'bg-indigo-600 text-white shadow-xs' : 'bg-slate-100 hover:bg-slate-200 text-slate-700'}">
      <span>All Classes</span>
      <span class="text-[10px] font-black px-1.5 py-0.2 rounded-full ${activeClass === 'All' ? 'bg-white/25 text-white' : 'bg-slate-200 text-slate-700'}">${totalAllStudents}</span>
    </button>
  `;

  // Standard ordered class list
  const standardClasses = ['PP1', 'PP2', 'Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5', 'Class 6', 'Class 7', 'Class 8', 'Class 9', 'Class 10'];

  standardClasses.forEach(cn => {
    const s = summaries.find(item => item.class_name === cn);
    const count = s ? s.total_students : 0;
    const isSel = (activeClass === cn);

    html += `
      <button onclick="selectClassPill('${cn}')" class="px-3 py-1.5 rounded-xl text-xs font-bold transition flex items-center space-x-1.5 ${isSel ? 'bg-indigo-600 text-white shadow-xs' : (count > 0 ? 'bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200' : 'bg-slate-100 hover:bg-slate-200 text-slate-400')}">
        <span>${cn}</span>
        <span class="text-[10px] font-black px-1.5 py-0.2 rounded-full ${isSel ? 'bg-white/25 text-white' : (count > 0 ? 'bg-indigo-200/80 text-indigo-900' : 'bg-slate-200 text-slate-500')}">${count}</span>
      </button>
    `;
  });

  container.innerHTML = html;
}

function selectClassPill(className) {
  const select = document.getElementById('filterCwClass');
  if (select) {
    select.value = className;
    handleClassWiseFilterChange();
  }
}

function handleClassWiseFilterChange() {
  loadClassWiseStudents();
}

function filterClassWiseTableLocally() {
  const query = (document.getElementById('filterCwSearch').value || '').trim().toLowerCase();
  if (!query) {
    renderClassWiseTable(classWiseLoadedStudents);
    return;
  }

  const filtered = classWiseLoadedStudents.filter(s => {
    return (s.student_name && s.student_name.toLowerCase().includes(query)) ||
           (s.admission_no && s.admission_no.toLowerCase().includes(query)) ||
           (s.parent_name && s.parent_name.toLowerCase().includes(query)) ||
           (s.parent_phone && s.parent_phone.includes(query)) ||
           (s.branch && s.branch.toLowerCase().includes(query)) ||
           (s.class_name && s.class_name.toLowerCase().includes(query));
  });

  renderClassWiseTable(filtered);
}

function renderClassWiseTable(students) {
  const tbody = document.getElementById('classWiseTableRows');
  if (!tbody) return;

  if (!students || students.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="12" class="p-8 text-center text-slate-400">
          <i class="fa-solid fa-folder-open text-2xl mb-2 text-slate-300"></i>
          <p class="font-bold text-slate-600">No students found matching this criteria.</p>
          <p class="text-[11px] text-slate-400 mt-1">Try selecting 'All Classes' or 'All Admissions'.</p>
        </td>
      </tr>
    `;
    return;
  }

  const isAdmin = currentUser && (currentUser.role === 'T1' || currentUser.role === 'T2');

  tbody.innerHTML = students.map(s => {
    const isCancelled = (s.status === 'Cancelled');
    const balance = s.balance_due || 0;
    const paid = s.total_paid || 0;
    const agreed = s.final_agreed_fee || 0;
    const sBranch = s.branch || 'Branch 1';

    let balBadge = "";
    if (isCancelled) {
      balBadge = `<span class="text-slate-400 font-bold">--</span>`;
    } else if (balance <= 0) {
      balBadge = `<span class="bg-emerald-100 text-emerald-800 text-[10px] font-extrabold px-2 py-0.5 rounded-full"><i class="fa-solid fa-check-double mr-1"></i>CLEARED</span>`;
    } else {
      balBadge = `<span class="font-extrabold text-rose-700">₹ ${balance.toLocaleString('en-IN')}</span>`;
    }

    const statusBadge = isCancelled
      ? `<span class="bg-rose-100 text-rose-800 text-[10px] font-extrabold px-2 py-0.5 rounded-full whitespace-nowrap"><i class="fa-solid fa-ban mr-1"></i>Cancelled</span>`
      : `<span class="bg-emerald-100 text-emerald-800 text-[10px] font-extrabold px-2 py-0.5 rounded-full whitespace-nowrap"><i class="fa-solid fa-circle-check mr-1"></i>Active</span>`;

    const transportBadge = s.has_transport === 1
      ? `<span class="text-[9px] font-extrabold px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-800 ml-1" title="Bus: ${s.bus_route || 'Standard'}">🚌 Bus</span>`
      : "";

    const financialCells = isAdmin ? `
      <td class="p-3 text-right font-bold text-slate-800 whitespace-nowrap">₹ ${agreed.toLocaleString('en-IN')}</td>
      <td class="p-3 text-right font-bold text-emerald-700 whitespace-nowrap">₹ ${paid.toLocaleString('en-IN')}</td>
      <td class="p-3 text-right whitespace-nowrap">${balBadge}</td>
    ` : '';

    return `
      <tr class="hover:bg-slate-50 transition ${isCancelled ? 'opacity-60 bg-slate-50/50' : ''}">
        <td class="p-3 text-center font-bold text-slate-600 font-mono">${s.roll_no || '-'}</td>
        <td class="p-3 font-mono font-bold text-indigo-900 whitespace-nowrap">${s.admission_no}</td>
        <td class="p-3 font-bold text-slate-900 whitespace-nowrap">
          ${s.student_name}
          ${transportBadge}
        </td>
        <td class="p-3 whitespace-nowrap font-bold text-indigo-700">
          <span class="px-2 py-0.5 rounded-md text-[10px] ${sBranch === 'Branch 1' ? 'bg-indigo-50 text-indigo-700 border border-indigo-200' : 'bg-purple-50 text-purple-700 border border-purple-200'}">${sBranch}</span>
        </td>
        <td class="p-3 font-semibold text-slate-700 whitespace-nowrap">${s.class_name} - ${s.section}</td>
        <td class="p-3 whitespace-nowrap"><span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${s.student_type === 'Residential' ? 'bg-purple-100 text-purple-800' : 'bg-slate-100 text-slate-700'}">${s.student_type}</span></td>
        <td class="p-3 text-slate-600 whitespace-nowrap">
          <p class="font-semibold text-slate-800">${s.parent_name || '-'}</p>
          <p class="text-[11px] text-slate-500 font-mono">${s.parent_phone || '-'}</p>
        </td>
        ${financialCells}
        <td class="p-3 text-center whitespace-nowrap">${statusBadge}</td>
        <td class="p-3 text-center whitespace-nowrap space-x-1">
          <button onclick="openStudentFromClassWise('${s.admission_no}')" class="bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 font-bold px-2.5 py-1 rounded-lg text-xs transition shadow-xs" title="Open student in Fee Collection Ledger">
            <i class="fa-solid fa-cash-register mr-1"></i> Ledger / Pay
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function openStudentFromClassWise(admNo) {
  switchTab('collect');
  const input = document.getElementById('studentSearchInput');
  if (input) {
    input.value = admNo;
    performStudentSearch();
  }
}

function exportClassWiseToExcel() {
  if (!classWiseLoadedStudents || classWiseLoadedStudents.length === 0) {
    alert("No students to export in current view.");
    return;
  }

  const isAdmin = currentUser && (currentUser.role === 'T1' || currentUser.role === 'T2');

  // Convert currently loaded students to CSV formatted data
  let headers = ["Roll_No", "Admission_No", "Student_Name", "Branch", "Gender", "Class_Name", "Section", "Student_Type", "Has_Transport", "Parent_Name", "Parent_Phone"];
  if (isAdmin) {
    headers.push("Agreed_Fee", "Amount_Paid", "Balance_Due");
  }
  headers.push("Status");
  
  const rows = classWiseLoadedStudents.map(s => {
    let r = [
      `"${s.roll_no || ''}"`,
      `"${s.admission_no || ''}"`,
      `"${(s.student_name || '').replace(/"/g, '""')}"`,
      `"${s.branch || 'Branch 1'}"`,
      `"${s.gender || ''}"`,
      `"${s.class_name || ''}"`,
      `"${s.section || ''}"`,
      `"${s.student_type || ''}"`,
      `"${s.has_transport === 1 ? 'Yes' : 'No'}"`,
      `"${(s.parent_name || '').replace(/"/g, '""')}"`,
      `"${s.parent_phone || ''}"`
    ];
    if (isAdmin) {
      r.push(s.final_agreed_fee || 0, s.total_paid || 0, s.balance_due || 0);
    }
    r.push(`"${s.status || 'Active'}"`);
    return r;
  });

  const csvContent = "data:text/csv;charset=utf-8," + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  
  const cname = document.getElementById('filterCwClass') ? document.getElementById('filterCwClass').value : 'All';
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", `KHS_Students_${cname.replace(/\s+/g, '_')}_${new Date().toISOString().slice(0,10)}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// ================= GOOGLE DRIVE BACKUP SYNC =================

let cachedGDriveStatus = null;

async function openGDriveModal() {
  const modal = document.getElementById('gdriveModal');
  if (modal) modal.classList.remove('hidden');
  await loadGDriveStatus();
}

function closeGDriveModal() {
  const modal = document.getElementById('gdriveModal');
  if (modal) modal.classList.add('hidden');
}

async function loadGDriveStatus() {
  const statusCard = document.getElementById('gdriveStatusCard');
  const statusTitle = document.getElementById('gdriveStatusTitle');
  const statusBadge = document.getElementById('gdriveStatusBadge');
  const statusDesc = document.getElementById('gdriveStatusDesc');
  const syncNowContainer = document.getElementById('gdriveSyncNowContainer');
  const botEmailSec = document.getElementById('gdriveBotEmailSection');
  const botEmailText = document.getElementById('gdriveBotEmailText');
  const folderInput = document.getElementById('gdriveFolderIdInput');
  const autoSyncCheck = document.getElementById('gdriveAutoSyncCheck');
  const jsonNameText = document.getElementById('gdriveJsonNameText');

  try {
    const res = await fetch('/api/gdrive/status');
    const data = await res.json();
    cachedGDriveStatus = data;

    if (data.folder_id && folderInput) {
      folderInput.value = data.folder_id;
    }
    if (autoSyncCheck) {
      autoSyncCheck.checked = !!data.auto_sync_eod;
    }

    if (data.has_credentials_file) {
      jsonNameText.innerText = "service_account.json (Installed ✓)";
      jsonNameText.classList.add("text-emerald-700", "font-bold");
    } else {
      jsonNameText.innerText = "Upload service_account.json";
      jsonNameText.classList.remove("text-emerald-700");
    }

    if (data.service_account_email) {
      botEmailSec.classList.remove('hidden');
      botEmailText.innerText = data.service_account_email;
    } else {
      botEmailSec.classList.add('hidden');
    }

    if (data.configured) {
      statusCard.className = "p-3.5 rounded-xl border border-emerald-200 bg-emerald-50 text-xs space-y-1";
      statusTitle.innerHTML = `<i class="fa-solid fa-circle-check text-emerald-600 mr-1.5"></i> Connected & Ready`;
      statusTitle.className = "font-bold text-emerald-900 flex items-center";
      statusBadge.innerText = "ONLINE";
      statusBadge.className = "text-[10px] font-black px-2 py-0.5 rounded-full uppercase bg-emerald-200 text-emerald-800";
      statusDesc.innerText = `Google Drive folder connected (${data.folder_id}). Automated daily backup is active.`;
      syncNowContainer.classList.remove('hidden');
    } else {
      statusCard.className = "p-3.5 rounded-xl border border-amber-200 bg-amber-50 text-xs space-y-1";
      statusTitle.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-amber-600 mr-1.5"></i> Setup Pending`;
      statusTitle.className = "font-bold text-amber-900 flex items-center";
      statusBadge.innerText = "NOT READY";
      statusBadge.className = "text-[10px] font-black px-2 py-0.5 rounded-full uppercase bg-amber-200 text-amber-800";
      statusDesc.innerText = data.status_message || "Please upload service_account.json and specify your target Folder ID.";
      syncNowContainer.classList.add('hidden');
    }

  } catch (err) {
    console.error("Error loading GDrive status:", err);
    if (statusDesc) statusDesc.innerText = "Failed to connect to backend server.";
  }
}

async function uploadGDriveCredentialsFile() {
  const input = document.getElementById('gdriveJsonInput');
  if (!input.files || !input.files[0]) return;

  const file = input.files[0];
  if (!file.name.endsWith('.json')) {
    alert("Please select a valid JSON key file downloaded from Google Cloud Console.");
    input.value = "";
    return;
  }

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/gdrive/upload-credentials', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    input.value = "";

    if (!res.ok) {
      alert("Error: " + (data.detail || "Could not upload credentials"));
      return;
    }

    alert(data.message);
    await loadGDriveStatus();
  } catch (err) {
    input.value = "";
    alert("Failed to upload service account credentials: " + err);
  }
}

async function saveGDriveSettings() {
  const folderInput = document.getElementById('gdriveFolderIdInput');
  const autoSyncCheck = document.getElementById('gdriveAutoSyncCheck');
  const btn = document.getElementById('btnSaveGDriveConfig');

  const folderId = folderInput ? folderInput.value.trim() : '';
  const autoSync = autoSyncCheck ? autoSyncCheck.checked : true;

  btn.disabled = true;
  btn.innerText = "Saving...";

  try {
    const res = await fetch('/api/gdrive/configure', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_folder_id: folderId,
        auto_sync_eod: autoSync
      })
    });
    const data = await res.json();

    if (!res.ok) {
      alert("Error: " + (data.detail || "Could not save configuration"));
    } else {
      alert(data.message);
      await loadGDriveStatus();
    }
  } catch (err) {
    alert("Failed to save settings: " + err);
  } finally {
    btn.disabled = false;
    btn.innerText = "Save Settings";
  }
}

async function triggerGDriveSyncNow() {
  const btn = document.getElementById('btnSyncNowDrive');
  const originalHtml = btn.innerHTML;

  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Uploading...</span>`;

  try {
    const operator = currentUser ? currentUser.username : 'admin';
    const res = await fetch(`/api/gdrive/sync-now?operator_user=${operator}`, {
      method: 'POST'
    });
    const data = await res.json();

    if (!res.ok) {
      alert("Cloud Sync Failed: " + (data.detail || "Unknown error"));
      return;
    }

    alert(`Cloud Backup Successful!\n\nFile: ${data.file_name}\nUploaded to Folder: ${data.folder_id}\nDrive File ID: ${data.drive_file_id}\n\nYour school database snapshot is safely secured in Google Drive.`);
  } catch (err) {
    alert("Sync error: " + err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

function copyGDriveBotEmail() {
  const email = document.getElementById('gdriveBotEmailText').innerText;
  if (!email || email === '--') return;
  navigator.clipboard.writeText(email);
  alert("Service Account Bot Email copied to clipboard!\n\nPaste this in Google Drive 'Share' dialog with Editor permission.");
}

// ================= MULTI-BRANCH CLOUD SYNC =================

let cloudSyncAutoTimer = null;

async function openCloudSyncModal() {
  const modal = document.getElementById('cloudSyncModal');
  if (modal) modal.classList.remove('hidden');
  await loadCloudSyncStatus();
}

function closeCloudSyncModal() {
  const modal = document.getElementById('cloudSyncModal');
  if (modal) modal.classList.add('hidden');
}

async function loadCloudSyncStatus() {
  const card = document.getElementById('cloudSyncStatusCard');
  const title = document.getElementById('cloudSyncStatusTitle');
  const badge = document.getElementById('cloudSyncStatusBadge');
  const desc = document.getElementById('cloudSyncStatusDesc');
  const urlInput = document.getElementById('cloudSyncDbUrlInput');
  const branchSelect = document.getElementById('cloudSyncBranchSelect');
  const checkEnabled = document.getElementById('cloudSyncEnabledCheck');
  const pendingCount = document.getElementById('cloudSyncPendingCount');
  const syncedCount = document.getElementById('cloudSyncSyncedCount');

  try {
    const res = await fetch('/api/cloud-sync/status');
    const data = await res.json();

    if (data.db_url && urlInput) urlInput.value = data.db_url;
    if (data.branch && branchSelect) branchSelect.value = data.branch;
    if (checkEnabled) checkEnabled.checked = !!data.enabled;
    if (pendingCount) pendingCount.innerText = data.pending_outbox_count || 0;
    if (syncedCount) syncedCount.innerText = data.synced_total_count || 0;

    if (data.enabled && data.db_url && data.has_token) {
      card.className = "p-3.5 rounded-xl border border-purple-200 bg-purple-50 text-xs space-y-1";
      title.innerHTML = `<i class="fa-solid fa-cloud-check text-purple-600 mr-1.5"></i> Connected & Syncing in Real-Time`;
      title.className = "font-bold text-purple-900 flex items-center";
      badge.innerText = "ACTIVE";
      badge.className = "text-[10px] font-black px-2 py-0.5 rounded-full uppercase bg-purple-200 text-purple-800";
      desc.innerText = `Branch: ${data.branch}. Changes are synced to central cloud in real time. ${data.pending_outbox_count} pending offline.`;
    } else {
      card.className = "p-3.5 rounded-xl border border-slate-200 bg-slate-50 text-xs space-y-1";
      title.innerHTML = `<i class="fa-solid fa-circle-info text-slate-500 mr-1.5"></i> Cloud Sync Disabled or Not Configured`;
      title.className = "font-bold text-slate-700 flex items-center";
      badge.innerText = "STANDALONE";
      badge.className = "text-[10px] font-black px-2 py-0.5 rounded-full uppercase bg-slate-200 text-slate-700";
      desc.innerText = `Operating in local offline mode. Enter your Turso cloud database URL and token to enable live sync.`;
    }
  } catch (err) {
    console.error("Error loading cloud sync status:", err);
  }
}

async function saveCloudSyncSettings() {
  const urlInput = document.getElementById('cloudSyncDbUrlInput');
  const tokenInput = document.getElementById('cloudSyncTokenInput');
  const branchSelect = document.getElementById('cloudSyncBranchSelect');
  const enabledCheck = document.getElementById('cloudSyncEnabledCheck');
  const btn = document.getElementById('btnSaveCloudSync');

  const operator = currentUser ? currentUser.username : 'admin';
  btn.disabled = true;
  btn.innerText = "Saving...";

  try {
    const res = await fetch(`/api/cloud-sync/configure?operator_user=${operator}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enabled: enabledCheck ? enabledCheck.checked : true,
        db_url: urlInput ? urlInput.value.trim() : '',
        auth_token: tokenInput ? tokenInput.value.trim() : '',
        branch: branchSelect ? branchSelect.value : 'Branch 1',
        auto_sync_interval_seconds: 30
      })
    });
    const data = await res.json();
    alert(data.message);
    await loadCloudSyncStatus();
  } catch (err) {
    alert("Error saving cloud settings: " + err);
  } finally {
    btn.disabled = false;
    btn.innerText = "Save Settings";
  }
}

async function testCloudSyncConnection() {
  const btn = document.getElementById('btnTestCloudSync');
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Testing...</span>`;

  try {
    const operator = currentUser ? currentUser.username : 'admin';
    const res = await fetch(`/api/cloud-sync/test?operator_user=${operator}`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) {
      alert("Connection Failed: " + (data.detail || "Could not reach cloud database."));
    } else {
      alert("Success! " + data.message);
    }
  } catch (err) {
    alert("Test error: " + err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

async function triggerManualCloudSync() {
  const btn = document.getElementById('btnSyncNowCloud');
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Syncing...</span>`;

  try {
    const operator = currentUser ? currentUser.username : 'admin';
    const res = await fetch(`/api/cloud-sync/sync-now?operator_user=${operator}`, { method: 'POST' });
    const data = await res.json();
    if (data.status === 'success') {
      alert(`Sync Complete! ${data.synced} transactions sent to Cloud Database.`);
    } else if (data.status === 'up_to_date') {
      alert("Local database is already fully synced with Cloud!");
    } else {
      alert("Sync Notice: " + (data.message || data.error || JSON.stringify(data)));
    }
    await loadCloudSyncStatus();
  } catch (err) {
    alert("Sync error: " + err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

// Background auto-sync loop & online event listener (ensures offline items push automatically on reconnection)
window.addEventListener('online', async () => {
  console.log("[KHS Sync] Internet connection detected. Pushing outbox...");
  try {
    const operator = currentUser ? currentUser.username : 'system_online';
    await fetch(`/api/cloud-sync/sync-now?operator_user=${operator}`, { method: 'POST' });
    await loadCloudSyncStatus();
  } catch (e) {
    console.warn("[KHS Sync] Online reconnect sync attempt failed:", e);
  }
});

// Periodic background sync ping every 25 seconds
setInterval(async () => {
  if (navigator.onLine) {
    try {
      const operator = currentUser ? currentUser.username : 'daemon';
      await fetch(`/api/cloud-sync/sync-now?operator_user=${operator}`, { method: 'POST' });
      // Update badge if modal is open or for real-time awareness
      const modal = document.getElementById('cloudSyncModal');
      if (modal && !modal.classList.contains('hidden')) {
        await loadCloudSyncStatus();
      }
    } catch (e) {
      // Silent catch during periodic sync
    }
  }
}, 25000);


