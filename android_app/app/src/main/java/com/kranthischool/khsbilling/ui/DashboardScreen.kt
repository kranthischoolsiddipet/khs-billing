package com.kranthischool.khsbilling.ui

import android.widget.Toast
import androidx.compose.foundation.background
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

    // Notifications state (for Admin)
    var notificationsList by remember { mutableStateOf<List<NotificationItem>>(emptyList()) }
    var showNotificationDialog by remember { mutableStateOf(false) }

    // New Admission state (for Front Desk)
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
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = "Kranthi High School",
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = "$userName • $roleDisplay",
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                },
                actions = {
                    if (isAdmin) {
                        IconButton(onClick = {
                            fetchNotifications()
                            showNotificationDialog = true
                        }) {
                            BadgedBox(
                                badge = {
                                    if (notificationsList.isNotEmpty()) {
                                        Badge { Text(notificationsList.size.toString()) }
                                    }
                                }
                            ) {
                                Icon(Icons.Default.Notifications, contentDescription = "Activity Feed")
                            }
                        }
                        IconButton(onClick = { showChangePinDialog = true }) {
                            Icon(Icons.Default.Lock, contentDescription = "Change PIN")
                        }
                    }
                    IconButton(onClick = { doSearch(searchQuery) }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                    IconButton(onClick = {
                        sessionManager.clearSession()
                        onLogout()
                    }) {
                        Icon(Icons.AutoMirrored.Filled.ExitToApp, contentDescription = "Logout")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant
                )
            )
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
                    icon = { Icon(Icons.Default.Add, contentDescription = "New Admission") },
                    text = { Text("New Admission", fontWeight = FontWeight.Bold) },
                    containerColor = MaterialTheme.colorScheme.primary,
                    contentColor = MaterialTheme.colorScheme.onPrimary
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
            // ADMIN MENU DASHBOARD (5 Clear Options)
            if (isAdmin) {
                Text(
                    text = "Administrator Controls",
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(bottom = 10.dp)
                )

                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 10.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    AdminMenuCard(
                        title = "Enrolled Students",
                        subtitle = "View all records",
                        icon = Icons.Default.Groups,
                        color = Color(0xFF2563EB),
                        modifier = Modifier.weight(1f),
                        onClick = onNavigateEnrolledStudents
                    )
                    AdminMenuCard(
                        title = "Approvals",
                        subtitle = "Concessions & Changes",
                        icon = Icons.Default.FactCheck,
                        color = Color(0xFFD97706),
                        modifier = Modifier.weight(1f),
                        onClick = onNavigateApprovals
                    )
                }

                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 10.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    AdminMenuCard(
                        title = "EOD Reports",
                        subtitle = "Daily Collection",
                        icon = Icons.Default.Assessment,
                        color = Color(0xFF059669),
                        modifier = Modifier.weight(1f),
                        onClick = onNavigateEodReports
                    )
                    AdminMenuCard(
                        title = "Staff & Cashiers",
                        subtitle = "Accounts & Activity",
                        icon = Icons.Default.Badge,
                        color = Color(0xFF7C3AED),
                        modifier = Modifier.weight(1f),
                        onClick = onNavigateStaffList
                    )
                }

                Spacer(modifier = Modifier.height(4.dp))
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                Spacer(modifier = Modifier.height(10.dp))

                Text(
                    text = "Fee Collection & Quick Search",
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
            }

            // Search Bar for Fee Collection (Used by both Admin & Front Desk)
            OutlinedTextField(
                value = searchQuery,
                onValueChange = {
                    searchQuery = it
                    if (it.length >= 2 || it.isEmpty()) {
                        doSearch(it)
                    }
                },
                placeholder = { Text("Search Student to Collect Fee...") },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = "Search") },
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                singleLine = true
            )

            Spacer(modifier = Modifier.height(12.dp))

            if (isLoading) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else if (errorMessage != null) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(errorMessage ?: "", color = MaterialTheme.colorScheme.error)
                }
            } else if (studentsList.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No students found.", color = Color.Gray)
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(studentsList) { student ->
                        StudentCard(student = student, onClick = { onSelectStudent(student.id) })
                    }
                }
            }
        }
    }

    // --- ADMIN NOTIFICATIONS FEED DIALOG ---
    if (showNotificationDialog && isAdmin) {
        AlertDialog(
            onDismissRequest = { showNotificationDialog = false },
            title = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Notifications, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Admin Activity Feed")
                }
            },
            text = {
                if (notificationsList.isEmpty()) {
                    Text("No recent notifications.", color = Color.Gray)
                } else {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 400.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(notificationsList) { item ->
                            val iconVector = when (item.type) {
                                "APPROVAL" -> Icons.Default.Warning
                                "NEW_ADMISSION" -> Icons.Default.CheckCircle
                                else -> Icons.Default.Info
                            }
                            val iconColor = when (item.type) {
                                "APPROVAL" -> Color(0xFFD97706)
                                "NEW_ADMISSION" -> Color(0xFF059669)
                                else -> MaterialTheme.colorScheme.primary
                            }

                            Card(
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(8.dp),
                                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))
                            ) {
                                Row(
                                    modifier = Modifier.padding(10.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(iconVector, contentDescription = null, tint = iconColor, modifier = Modifier.size(24.dp))
                                    Spacer(modifier = Modifier.width(10.dp))
                                    Column {
                                        Text(item.title, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                                        Text(item.body, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurface)
                                        if (!item.time.isNullOrBlank()) {
                                            Text(item.time, fontSize = 10.sp, color = Color.Gray)
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
                    Text("Close")
                }
            }
        )
    }

    // --- FRONT DESK: NEW ADMISSION DIALOG ---
    if (showAdmitDialog && !isAdmin) {
        AlertDialog(
            onDismissRequest = { if (!isSubmittingAdmit) showAdmitDialog = false },
            title = { Text("New Student Admission") },
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
                            Toast.makeText(context, "Please fill required details and valid 10-digit phone", Toast.LENGTH_SHORT).show()
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
                    enabled = !isSubmittingAdmit
                ) {
                    if (isSubmittingAdmit) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
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
            title = { Text("Change Admin PIN") },
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
                    enabled = !isChangingPin
                ) {
                    if (isChangingPin) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
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
fun AdminMenuCard(
    title: String,
    subtitle: String,
    icon: ImageVector,
    color: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Card(
        modifier = modifier
            .height(90.dp)
            .clickable { onClick() },
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .background(color.copy(alpha = 0.12f), shape = RoundedCornerShape(8.dp)),
                contentAlignment = Alignment.Center
            ) {
                Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(24.dp))
            }
            Spacer(modifier = Modifier.width(10.dp))
            Column {
                Text(title, fontWeight = FontWeight.Bold, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurface)
                Text(subtitle, fontSize = 11.sp, color = Color.Gray)
            }
        }
    }
}

@Composable
fun StudentCard(
    student: Student,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() },
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = student.getDisplayName(),
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Text(
                    text = "Class: ${student.getEffectiveClass()} • Adm: ${student.admission_no ?: student.student_id ?: "N/A"}",
                    fontSize = 13.sp,
                    color = Color.Gray
                )
                val phoneNum = student.getEffectivePhone()
                if (!phoneNum.isNullOrBlank()) {
                    Text(
                        text = "Ph: $phoneNum",
                        fontSize = 12.sp,
                        color = Color.Gray
                    )
                }
            }

            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = "Due Balance",
                    fontSize = 11.sp,
                    color = Color.Gray
                )
                Text(
                    text = "₹ ${student.balance.toInt()}",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                    color = if (student.balance > 0) Color(0xFFDC2626) else Color(0xFF059669)
                )
            }
        }
    }
}
