package com.kranthischool.khsbilling.ui

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.kranthischool.khsbilling.data.ActionDiscountRequest
import com.kranthischool.khsbilling.data.ApiClient
import com.kranthischool.khsbilling.data.PendingDiscount
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AdminApprovalsScreen(
    onNavigateBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var pendingList by remember { mutableStateOf<List<PendingDiscount>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    // Dialog state for approving or rejecting
    var selectedDiscount by remember { mutableStateOf<PendingDiscount?>(null) }
    var actionType by remember { mutableStateOf<String?>(null) } // "APPROVE" or "REJECT"
    var remarks by remember { mutableStateOf("") }
    var isSubmitting by remember { mutableStateOf(false) }

    fun loadPending() {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val api = ApiClient.getService(context)
                val res = api.getPendingDiscounts()
                if (res.isSuccessful) {
                    pendingList = res.body() ?: emptyList()
                } else {
                    errorMessage = "Failed to load requests (${res.code()})"
                }
            } catch (e: Exception) {
                errorMessage = "Network error: ${e.localizedMessage}"
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(Unit) {
        loadPending()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Approvals Desk") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { loadPending() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(16.dp)
        ) {
            if (isLoading) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else if (errorMessage != null) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(errorMessage ?: "", color = MaterialTheme.colorScheme.error)
                }
            } else if (pendingList.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No pending discount or approval requests.", color = Color.Gray)
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(pendingList) { item ->
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp),
                            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = item.student_name ?: "Student #${item.student_id}",
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 16.sp
                                    )
                                    Text(
                                        text = "₹ ${item.amount.toInt()}",
                                        fontWeight = FontWeight.ExtraBold,
                                        fontSize = 16.sp,
                                        color = MaterialTheme.colorScheme.primary
                                    )
                                }

                                Text(
                                    text = "Class: ${item.class_name ?: "N/A"} • Concession: ${item.discount_type ?: "Special"}",
                                    fontSize = 13.sp,
                                    color = Color.Gray,
                                    modifier = Modifier.padding(top = 2.dp)
                                )

                                if (!item.reason.isNullOrBlank()) {
                                    Text(
                                        text = "Reason: ${item.reason}",
                                        fontSize = 13.sp,
                                        modifier = Modifier.padding(top = 6.dp)
                                    )
                                }

                                if (!item.requested_by.isNullOrBlank()) {
                                    Text(
                                        text = "Requested by: ${item.requested_by}",
                                        fontSize = 11.sp,
                                        color = Color.Gray,
                                        modifier = Modifier.padding(top = 4.dp)
                                    )
                                }

                                Divider(modifier = Modifier.padding(vertical = 12.dp))

                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.End,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    OutlinedButton(
                                        onClick = {
                                            selectedDiscount = item
                                            actionType = "REJECT"
                                            remarks = ""
                                        },
                                        colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFDC2626)),
                                        modifier = Modifier.padding(end = 8.dp)
                                    ) {
                                        Text("Reject")
                                    }

                                    Button(
                                        onClick = {
                                            selectedDiscount = item
                                            actionType = "APPROVE"
                                            remarks = ""
                                        },
                                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF059669))
                                    ) {
                                        Text("Approve")
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Approve / Reject Dialog
    if (selectedDiscount != null && actionType != null) {
        val isApprove = actionType == "APPROVE"
        AlertDialog(
            onDismissRequest = { if (!isSubmitting) selectedDiscount = null },
            title = {
                Text(if (isApprove) "Approve Concession" else "Reject Concession")
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Student: ${selectedDiscount!!.student_name}")
                    Text("Amount: ₹ ${selectedDiscount!!.amount.toInt()}")
                    OutlinedTextField(
                        value = remarks,
                        onValueChange = { remarks = it },
                        label = { Text("Admin Remarks / Reason") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        isSubmitting = true
                        scope.launch {
                            try {
                                val api = ApiClient.getService(context)
                                val req = ActionDiscountRequest(
                                    discount_id = selectedDiscount!!.id,
                                    action = actionType!!,
                                    remarks = remarks.ifBlank { null }
                                )
                                val res = api.actionDiscount(req)
                                if (res.isSuccessful && res.body()?.success == true) {
                                    Toast.makeText(context, "Concession ${actionType!!.lowercase()}d successfully", Toast.LENGTH_SHORT).show()
                                    selectedDiscount = null
                                    loadPending()
                                } else {
                                    Toast.makeText(context, "Action failed: ${res.body()?.message ?: res.message()}", Toast.LENGTH_SHORT).show()
                                }
                            } catch (e: Exception) {
                                Toast.makeText(context, "Error: ${e.localizedMessage}", Toast.LENGTH_SHORT).show()
                            } finally {
                                isSubmitting = false
                            }
                        }
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isApprove) Color(0xFF059669) else Color(0xFFDC2626)
                    ),
                    enabled = !isSubmitting
                ) {
                    if (isSubmitting) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                    } else {
                        Text(if (isApprove) "Confirm Approval" else "Confirm Rejection")
                    }
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { selectedDiscount = null },
                    enabled = !isSubmitting
                ) {
                    Text("Cancel")
                }
            }
        )
    }
}
