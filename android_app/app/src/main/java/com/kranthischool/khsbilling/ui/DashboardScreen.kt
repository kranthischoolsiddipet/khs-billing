package com.kranthischool.khsbilling.ui

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.kranthischool.khsbilling.data.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    onSelectStudent: (Int) -> Unit,
    onNavigateApprovals: () -> Unit,
    onNavigateEnrolledStudents: () -> Unit,
    onNavigateEodReports: () -> Unit,
    onNavigateStaffList: () -> Unit,
    onLogout: () -> Unit
) {
    val context = LocalContext.current
    val sessionManager = remember { SessionManager(context) }
    val scope = rememberCoroutineScope()

    val isAdmin = remember { sessionManager.isAdmin() }
    val roleDisplay = remember { sessionManager.getDisplayRoleName() }
    val userName = remember { sessionManager.getUserFullName() ?: roleDisplay }

    var searchQuery by remember { mutableStateOf("") }
    var studentsList by remember { mutableStateOf<List<Student>>(emptyList()) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    // Notifications state
    var notificationsList by remember { mutableStateOf<List<NotificationItem>>(emptyList()) }
    var showNotificationDialog by remember { mutableStateOf(false) }

    // New Admission state (Front Desk)
    var showAdmitDialog by remember { mutableStateOf(false) }
    var isSubmittingAdmit by remember { mutableStateOf(false) }
    var admitAdmNo by remember { mutableStateOf("") }
    var admitName by remember { mutableStateOf("") }
    var admitClass by remember { mutableStateOf("Class 1") }
    var admitSection by remember { mutableStateOf("A") }
    var admitType by remember { mutableStateOf("Day Scholar") }
    var admitParentName by remember { mutableStateOf("") }
    var admitParentPhone by remember { mutableStateOf("") }
    var admitInitialPayment by remember { mutableStateOf("") }

    // Change PIN Dialog state
    var showChangePinDialog by remember { mutableStateOf(false) }
    var currentPinInput by remember { mutableStateOf("") }
    var newPinInput by remember { mutableStateOf("") }
    var isChangingPin by remember { mutableStateOf(false) }

    fun doSearch(query: String) {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val api = ApiClient.getService(context)
                val res = api.searchStudents(query)
                if (res.isSuccessful) {
                    studentsList = res.body() ?: emptyList()
                } else {
                    errorMessage = "Error loading students (${res.code()})"
                }
            } catch (e: Exception) {
                errorMessage = "Network error: ${e.localizedMessage}"
            } finally {
                isLoading = false
            }
        }
    }

    fun fetchNotifications() {
        if (!isAdmin) return
        scope.launch {
            try {
                val api = ApiClient.getService(context)
                val res = api.getNotificationsFeed(30)
                if (res.isSuccessful && res.body() != null) {
                    notificationsList = res.body()?.notifications ?: emptyList()
                }
            } catch (_: Exception) {}
        }
    }

    LaunchedEffect(Unit) {
        doSearch("")
        if (isAdmin) {
            fetchNotifications()
            while (true) {
                delay(20_000)
                fetchNotifications()
            }
        }
    }

    Scaffold(
        containerColor = Color(0xFFF8FAFC),
        topBar = {
            Surface(
                color = Color.White,
                shadowElevation = 2.dp
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .statusBarsPadding()
                        .padding(horizontal = 16.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(40.dp)
                                .clip(RoundedCornerShape(10.dp))
                                .background(Brush.linearGradient(listOf(Color(0xFF4338CA), Color(0xFF6366F1)))),
                            contentAlignment = Alignment.Center
                        ) {
                            Text("KHS", fontWeight = FontWeight.ExtraBold, color = Color.White, fontSize = 13.sp)
                        }

                        Spacer(modifier = Modifier.width(12.dp))

                        Column {
                            Text(
                                text = "Kranthi High School",
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Bold,
                                color = Color(0xFF0F172A)
                            )
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Surface(
                                    shape = RoundedCornerShape(4.dp),
                                    color = if (isAdmin) Color(0xFFEEF2FF) else Color(0xFFECFDF5)
                                ) {
                                    Text(
                                        text = roleDisplay,
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = if (isAdmin) Color(0xFF4338CA) else Color(0xFF047857),
                                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                    )
                                }
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = "v1.4.0",
                                    fontSize = 11.sp,
                                    color = Color(0xFF94A3B8)
                                )
                            }
                        }
                    }

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        if (isAdmin) {
                            IconButton(onClick = {
                                fetchNotifications()
                                showNotificationDialog = true
                            }) {
                                BadgedBox(
                                    badge = {
                                        if (notificationsList.isNotEmpty()) {
                                            Badge(containerColor = Color(0xFFDC2626)) { Text(notificationsList.size.toString()) }
                                        }
                                    }
                                ) {
                                    Icon(Icons.Default.Notifications, contentDescription = "Activity Feed", tint = Color(0xFF334155))
                                }
                            }
                            IconButton(onClick = { showChangePinDialog = true }) {
                                Icon(Icons.Default.Lock, contentDescription = "Change PIN", tint = Color(0xFF334155))
                            }
                        }
                        IconButton(onClick = { doSearch(searchQuery) }) {
                            Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = Color(0xFF334155))
                        }
                        IconButton(onClick = {
                            sessionManager.clearSession()
                            onLogout()
                        }) {
                            Icon(Icons.AutoMirrored.Filled.ExitToApp, contentDescription = "Logout", tint = Color(0xFFDC2626))
                        }
                    }
                }
            }
        },
        floatingActionButton = {
            if (!isAdmin) {
                ExtendedFloatingActionButton(
                    onClick = {
                        admitAdmNo = "KHS-${System.currentTimeMillis().toString().takeLast(5)}"
                        admitName = ""
                        admitParentName = ""
                        admitParentPhone = ""
                        admitInitialPayment = ""
                        showAdmitDialog = true
                    },
                    icon = { Icon(Icons.Default.PersonAdd, contentDescription = "New Admission") },
                    text = { Text("New Admission", fontWeight = FontWeight.Bold) },
                    containerColor = Color(0xFF4338CA),
                    contentColor = Color.White,
                    shape = RoundedCornerShape(16.dp)
                )
            }
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(16.dp)
        ) {
            // ADMIN 5-OPTION MODERN COMMAND CENTER
            if (isAdmin) {
                Text(
                    text = "MANAGEMENT HUB",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF64748B),
                    letterSpacing = 1.sp,
                    modifier = Modifier.padding(bottom = 12.dp)
                )

                // 2 x 2 Grid
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    ModernAdminCard(
                        title = "Enrolled Students",
                        subtitle = "Full Directory",
                        icon = Icons.Default.Groups,
                        iconTint = Color(0xFF2563EB),
                        iconBg = Color(0xFFEFF6FF),
                        modifier = Modifier.weight(1f),
                        onClick = onNavigateEnrolledStudents
                    )
                    ModernAdminCard(
                        title = "Approvals",
                        subtitle = "Concessions",
                        icon = Icons.Default.FactCheck,
                        iconTint = Color(0xFFD97706),
                        iconBg = Color(0xFFFEF3C7),
                        modifier = Modifier.weight(1f),
                        onClick = onNavigateApprovals
                    )
                }

                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 14.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    ModernAdminCard(
                        title = "EOD Reports",
                        subtitle = "Daily Collection",
                        icon = Icons.Default.Assessment,
                        iconTint = Color(0xFF059669),
                        iconBg = Color(0xFFECFDF5),
                        modifier = Modifier.weight(1f),
                        onClick = onNavigateEodReports
                    )
                    ModernAdminCard(
                        title = "Staff & Cashiers",
                        subtitle = "Counter Accounts",
                        icon = Icons.Default.Badge,
                        iconTint = Color(0xFF7C3AED),
                        iconBg = Color(0xFFF5F3FF),
                        modifier = Modifier.weight(1f),
                        onClick = onNavigateStaffList
                    )
                }

                // Section Divider with Label
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "FEE COLLECTION",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF64748B),
                        letterSpacing = 1.sp
                    )
                    Spacer(modifier = Modifier.width(10.dp))
                    HorizontalDivider(modifier = Modifier.weight(1f), color = Color(0xFFE2E8F0))
                }
            }

            // Modern Search Bar
            Surface(
                shape = RoundedCornerShape(14.dp),
                color = Color.White,
                shadowElevation = 2.dp,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 12.dp)
            ) {
                OutlinedTextField(
                    value = searchQuery,
                    onValueChange = {
                        searchQuery = it
                        if (it.length >= 2 || it.isEmpty()) {
                            doSearch(it)
                        }
                    },
                    placeholder = { Text("Search by Student Name, Class, Adm No...", fontSize = 14.sp, color = Color(0xFF94A3B8)) },
                    leadingIcon = { Icon(Icons.Default.Search, contentDescription = "Search", tint = Color(0xFF4338CA)) },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Color(0xFF4338CA),
                        unfocusedBorderColor = Color(0xFFE2E8F0),
                        focusedContainerColor = Color.White,
                        unfocusedContainerColor = Color.White
                    )
                )
            }

            // Student List Stream
            if (isLoading) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Color(0xFF4338CA))
                }
            } else if (errorMessage != null) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(errorMessage ?: "", color = Color(0xFFDC2626), fontSize = 14.sp)
                }
            } else if (studentsList.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.School, contentDescription = null, tint = Color(0xFFCBD5E1), modifier = Modifier.size(56.dp))
                        Spacer(modifier = Modifier.height(10.dp))
                        Text("No students found.", color = Color(0xFF94A3B8), fontSize = 14.sp)
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(studentsList) { student ->
                        ModernStudentCard(student = student, onClick = { onSelectStudent(student.id) })
                    }
                }
            }
        }
    }

    // --- NOTIFICATIONS FEED DIALOG ---
    if (showNotificationDialog && isAdmin) {
        AlertDialog(
            onDismissRequest = { showNotificationDialog = false },
            title = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(36.dp)
                            .background(Color(0xFFEEF2FF), shape = RoundedCornerShape(8.dp)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(Icons.Default.Notifications, contentDescription = null, tint = Color(0xFF4338CA), modifier = Modifier.size(20.dp))
                    }
                    Spacer(modifier = Modifier.width(10.dp))
                    Text("Admin Activity Feed", fontSize = 18.sp, fontWeight = FontWeight.Bold)
                }
            },
            text = {
                if (notificationsList.isEmpty()) {
                    Text("No recent alerts or actions.", color = Color.Gray)
                } else {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 420.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(notificationsList) { item ->
                            val iconColor = when (item.type) {
                                "APPROVAL" -> Color(0xFFD97706)
                                "NEW_ADMISSION" -> Color(0xFF059669)
                                else -> Color(0xFF2563EB)
                            }
                            val iconBg = when (item.type) {
                                "APPROVAL" -> Color(0xFFFEF3C7)
                                "NEW_ADMISSION" -> Color(0xFFECFDF5)
                                else -> Color(0xFFEFF6FF)
                            }

                            Surface(
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(10.dp),
                                color = Color(0xFFF8FAFC),
                                border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE2E8F0))
                            ) {
                                Row(
                                    modifier = Modifier.padding(12.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Box(
                                        modifier = Modifier
                                            .size(32.dp)
                                            .background(iconBg, shape = CircleShape),
                                        contentAlignment = Alignment.Center
                                    ) {
                                        Icon(
                                            when (item.type) {
                                                "APPROVAL" -> Icons.Default.Warning
                                                "NEW_ADMISSION" -> Icons.Default.CheckCircle
                                                else -> Icons.Default.Receipt
                                            },
                                            contentDescription = null,
                                            tint = iconColor,
                                            modifier = Modifier.size(18.dp)
                                        )
                                    }
                                    Spacer(modifier = Modifier.width(12.dp))
                                    Column {
                                        Text(item.title, fontWeight = FontWeight.Bold, fontSize = 13.sp, color = Color(0xFF0F172A))
                                        Text(item.body, fontSize = 12.sp, color = Color(0xFF475569))
                                        if (!item.time.isNullOrBlank()) {
                                            Text(item.time, fontSize = 10.sp, color = Color(0xFF94A3B8), modifier = Modifier.padding(top = 2.dp))
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { showNotificationDialog = false }) {
                    Text("Close", fontWeight = FontWeight.Bold, color = Color(0xFF4338CA))
                }
            }
        )
    }

    // --- FRONT DESK: NEW ADMISSION DIALOG ---
    if (showAdmitDialog && !isAdmin) {
        AlertDialog(
            onDismissRequest = { if (!isSubmittingAdmit) showAdmitDialog = false },
            title = { Text("New Student Admission", fontWeight = FontWeight.Bold) },
            text = {
                LazyColumn(
                    modifier = Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    item {
                        OutlinedTextField(
                            value = admitAdmNo,
                            onValueChange = { admitAdmNo = it },
                            label = { Text("Admission No.") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                    item {
                        OutlinedTextField(
                            value = admitName,
                            onValueChange = { admitName = it },
                            label = { Text("Student Full Name *") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                    item {
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedTextField(
                                value = admitClass,
                                onValueChange = { admitClass = it },
                                label = { Text("Class") },
                                modifier = Modifier.weight(1f)
                            )
                            OutlinedTextField(
                                value = admitSection,
                                onValueChange = { admitSection = it },
                                label = { Text("Sec") },
                                modifier = Modifier.weight(0.7f)
                            )
                        }
                    }
                    item {
                        OutlinedTextField(
                            value = admitType,
                            onValueChange = { admitType = it },
                            label = { Text("Type (Day Scholar / Residential)") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                    item {
                        OutlinedTextField(
                            value = admitParentName,
                            onValueChange = { admitParentName = it },
                            label = { Text("Parent / Guardian Name *") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                    item {
                        OutlinedTextField(
                            value = admitParentPhone,
                            onValueChange = { if (it.length <= 10) admitParentPhone = it },
                            label = { Text("Parent Phone (10-digit) *") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                    item {
                        OutlinedTextField(
                            value = admitInitialPayment,
                            onValueChange = { admitInitialPayment = it },
                            label = { Text("Initial Fee Deposit (₹, optional)") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        if (admitName.isBlank() || admitParentName.isBlank() || admitParentPhone.length < 10) {
                            Toast.makeText(context, "Please enter student name, parent name & 10-digit phone", Toast.LENGTH_SHORT).show()
                            return@Button
                        }
                        isSubmittingAdmit = true
                        scope.launch {
                            try {
                                val api = ApiClient.getService(context)
                                val initialPay = admitInitialPayment.toDoubleOrNull() ?: 0.0
                                val req = StudentAdmissionSubmitRequest(
                                    admission_no = admitAdmNo.trim(),
                                    student_name = admitName.trim(),
                                    class_name = admitClass.trim(),
                                    section = admitSection.trim(),
                                    student_type = admitType.trim(),
                                    parent_name = admitParentName.trim(),
                                    parent_phone = admitParentPhone.trim(),
                                    initial_payment_amount = initialPay
                                )
                                val res = api.admitStudent(req)
                                if (res.isSuccessful && res.body()?.isSuccessful() == true) {
                                    Toast.makeText(context, "Student admitted successfully!", Toast.LENGTH_LONG).show()
                                    showAdmitDialog = false
                                    doSearch("")
                                } else {
                                    Toast.makeText(context, res.body()?.message ?: "Admission failed (${res.code()})", Toast.LENGTH_SHORT).show()
                                }
                            } catch (e: Exception) {
                                Toast.makeText(context, "Error: ${e.localizedMessage}", Toast.LENGTH_SHORT).show()
                            } finally {
                                isSubmittingAdmit = false
                            }
                        }
                    },
                    enabled = !isSubmittingAdmit,
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF4338CA))
                ) {
                    if (isSubmittingAdmit) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp, color = Color.White)
                    } else {
                        Text("Admit Student")
                    }
                }
            },
            dismissButton = {
                TextButton(onClick = { showAdmitDialog = false }, enabled = !isSubmittingAdmit) {
                    Text("Cancel")
                }
            }
        )
    }

    // --- CHANGE ADMIN PIN DIALOG ---
    if (showChangePinDialog && isAdmin) {
        AlertDialog(
            onDismissRequest = { if (!isChangingPin) showChangePinDialog = false },
            title = { Text("Change Admin PIN", fontWeight = FontWeight.Bold) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Update your 6-digit PIN used to log into KHS Billing.", fontSize = 13.sp, color = Color.Gray)
                    OutlinedTextField(
                        value = currentPinInput,
                        onValueChange = { currentPinInput = it },
                        label = { Text("Current PIN") },
                        placeholder = { Text("Default: 123456") },
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = newPinInput,
                        onValueChange = { if (it.length <= 8) newPinInput = it },
                        label = { Text("New 6-Digit PIN") },
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        if (newPinInput.length < 4 || !newPinInput.all { it.isDigit() }) {
                            Toast.makeText(context, "New PIN must be 4 to 8 digits", Toast.LENGTH_SHORT).show()
                            return@Button
                        }
                        isChangingPin = true
                        scope.launch {
                            try {
                                val api = ApiClient.getService(context)
                                val req = ChangePinRequest(
                                    old_pin = currentPinInput.trim(),
                                    new_pin = newPinInput.trim()
                                )
                                val res = api.changePin(req)
                                if (res.isSuccessful && res.body()?.success == true) {
                                    Toast.makeText(context, "PIN updated successfully!", Toast.LENGTH_LONG).show()
                                    showChangePinDialog = false
                                    currentPinInput = ""
                                    newPinInput = ""
                                } else {
                                    Toast.makeText(context, res.body()?.message ?: "Failed to update PIN", Toast.LENGTH_SHORT).show()
                                }
                            } catch (e: Exception) {
                                Toast.makeText(context, "Error: ${e.localizedMessage}", Toast.LENGTH_SHORT).show()
                            } finally {
                                isChangingPin = false
                            }
                        }
                    },
                    enabled = !isChangingPin,
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF4338CA))
                ) {
                    if (isChangingPin) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp, color = Color.White)
                    } else {
                        Text("Update PIN")
                    }
                }
            },
            dismissButton = {
                TextButton(onClick = { showChangePinDialog = false }, enabled = !isChangingPin) {
                    Text("Cancel")
                }
            }
        )
    }
}

@Composable
fun ModernAdminCard(
    title: String,
    subtitle: String,
    icon: ImageVector,
    iconTint: Color,
    iconBg: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Surface(
        modifier = modifier
            .height(96.dp)
            .clickable { onClick() },
        shape = RoundedCornerShape(16.dp),
        color = Color.White,
        shadowElevation = 2.dp,
        border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFF1F5F9))
    ) {
        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(44.dp)
                    .background(iconBg, shape = RoundedCornerShape(12.dp)),
                contentAlignment = Alignment.Center
            ) {
                Icon(icon, contentDescription = null, tint = iconTint, modifier = Modifier.size(24.dp))
            }
            Spacer(modifier = Modifier.width(12.dp))
            Column {
                Text(title, fontWeight = FontWeight.Bold, fontSize = 13.sp, color = Color(0xFF0F172A), lineHeight = 16.sp)
                Text(subtitle, fontSize = 11.sp, color = Color(0xFF64748B), modifier = Modifier.padding(top = 2.dp))
            }
        }
    }
}

@Composable
fun ModernStudentCard(
    student: Student,
    onClick: () -> Unit
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() },
        shape = RoundedCornerShape(14.dp),
        color = Color.White,
        shadowElevation = 2.dp,
        border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFF1F5F9))
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
                Box(
                    modifier = Modifier
                        .size(42.dp)
                        .background(Color(0xFFEEF2FF), shape = CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        student.getDisplayName().take(1).uppercase(),
                        fontWeight = FontWeight.Bold,
                        fontSize = 17.sp,
                        color = Color(0xFF4338CA)
                    )
                }

                Spacer(modifier = Modifier.width(12.dp))

                Column {
                    Text(
                        text = student.getDisplayName(),
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF0F172A)
                    )
                    Text(
                        text = "Class ${student.getEffectiveClass()} • Adm: ${student.admission_no ?: student.student_id ?: "N/A"}",
                        fontSize = 12.sp,
                        color = Color(0xFF64748B)
                    )
                    val phoneNum = student.getEffectivePhone()
                    if (!phoneNum.isNullOrBlank()) {
                        Text(
                            text = "Ph: $phoneNum",
                            fontSize = 11.sp,
                            color = Color(0xFF94A3B8)
                        )
                    }
                }
            }

            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = "DUE BALANCE",
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF94A3B8),
                    letterSpacing = 0.5.sp
                )
                Text(
                    text = "₹ ${student.balance.toInt()}",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = if (student.balance > 0) Color(0xFFDC2626) else Color(0xFF059669)
                )
            }
        }
    }
}
