package com.kranthischool.khsbilling.ui

import android.widget.Toast
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExitToApp
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.kranthischool.khsbilling.data.ApiClient
import com.kranthischool.khsbilling.data.ChangePinRequest
import com.kranthischool.khsbilling.data.SessionManager
import com.kranthischool.khsbilling.data.Student
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    onSelectStudent: (Int) -> Unit,
    onNavigateApprovals: () -> Unit,
    onLogout: () -> Unit
) {
    val context = LocalContext.current
    val sessionManager = remember { SessionManager(context) }
    val scope = rememberCoroutineScope()

    val userRole = remember { sessionManager.getUserRole() ?: "T3" }
    val userName = remember { sessionManager.getUserFullName() ?: "Staff" }

    var searchQuery by remember { mutableStateOf("") }
    var studentsList by remember { mutableStateOf<List<Student>>(emptyList()) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

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

    LaunchedEffect(Unit) {
        doSearch("")
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
                            text = "$userName • Role: $userRole",
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                },
                actions = {
                    IconButton(onClick = { showChangePinDialog = true }) {
                        Icon(Icons.Default.Lock, contentDescription = "Change PIN")
                    }
                    IconButton(onClick = { doSearch(searchQuery) }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                    IconButton(onClick = {
                        sessionManager.clearSession()
                        onLogout()
                    }) {
                        Icon(Icons.Default.ExitToApp, contentDescription = "Logout")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant
                )
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(16.dp)
        ) {
            // Admin Action Ribbon (T1 / T2)
            if (userRole == "T1" || userRole == "T2" || userRole == "SUPER_ADMIN" || userRole == "ADMIN") {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 12.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column {
                            Text(
                                "Approvals Desk",
                                fontWeight = FontWeight.Bold,
                                fontSize = 15.sp,
                                color = MaterialTheme.colorScheme.onPrimaryContainer
                            )
                            Text(
                                "Review fee concessions & changes",
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f)
                            )
                        }
                        Button(
                            onClick = onNavigateApprovals,
                            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
                        ) {
                            Text("Open", fontSize = 13.sp)
                        }
                    }
                }
            }

            // Search Bar
            OutlinedTextField(
                value = searchQuery,
                onValueChange = {
                    searchQuery = it
                    if (it.length >= 2 || it.isEmpty()) {
                        doSearch(it)
                    }
                },
                placeholder = { Text("Search by Name, Roll/Admission No...") },
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

    if (showChangePinDialog) {
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
