package com.kranthischool.khsbilling.ui

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Print
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.kranthischool.khsbilling.data.*
import com.kranthischool.khsbilling.printer.EscPosPrinterHelper
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StudentLedgerScreen(
    studentId: Int,
    onNavigateBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val sessionManager = remember { SessionManager(context) }
    val printerHelper = remember { EscPosPrinterHelper(context) }

    var statement by remember { mutableStateOf<StatementResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    // Payment Collection Dialog state
    var showPaymentDialog by remember { mutableStateOf(false) }
    var paymentAmount by remember { mutableStateOf("") }
    var paymentMode by remember { mutableStateOf("CASH") }
    var paymentRemarks by remember { mutableStateOf("") }
    var isSubmittingPayment by remember { mutableStateOf(false) }

    // Bluetooth Printer Picker Dialog state
    var showPrinterDialog by remember { mutableStateOf(false) }
    var lastReceiptToPrint by remember { mutableStateOf<PaymentItem?>(null) }

    fun loadLedger() {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val api = ApiClient.getService(context)
                val res = api.getStudentStatement(studentId)
                if (res.isSuccessful && res.body() != null) {
                    statement = res.body()
                } else {
                    errorMessage = "Failed to load statement (${res.code()})"
                }
            } catch (e: Exception) {
                errorMessage = "Network error: ${e.localizedMessage}"
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(studentId) {
        loadLedger()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(statement?.student?.name ?: "Student Ledger") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
            )
        },
        bottomBar = {
            if (statement != null) {
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shadowElevation = 8.dp
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Button(
                            onClick = {
                                paymentAmount = statement!!.student.balance.toInt().toString()
                                showPaymentDialog = true
                            },
                            modifier = Modifier
                                .weight(1f)
                                .height(48.dp),
                            shape = RoundedCornerShape(10.dp)
                        ) {
                            Text("Collect Fee", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    ) { innerPadding ->
        if (isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else if (errorMessage != null) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding),
                contentAlignment = Alignment.Center
            ) {
                Text(errorMessage ?: "", color = MaterialTheme.colorScheme.error)
            }
        } else if (statement != null) {
            val s = statement!!.student
            val summary = statement!!.fee_summary ?: FeeSummary(
                total_fee = s.total_fee,
                discount = s.discount,
                net_fee = s.total_fee - s.discount,
                paid_fee = s.paid_fee,
                balance = s.balance
            )

            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Fee Summary Card
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(14.dp),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text(
                                text = s.name,
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.onPrimaryContainer
                            )
                            Text(
                                text = "Class: ${s.getEffectiveClass()} • Adm: ${s.admission_no ?: s.student_id ?: "N/A"}",
                                fontSize = 13.sp,
                                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f)
                            )
                            if (!s.phone.isNullOrBlank()) {
                                Text(
                                    text = "Mobile: ${s.phone}",
                                    fontSize = 12.sp,
                                    color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f)
                                )
                            }

                            Divider(
                                modifier = Modifier.padding(vertical = 12.dp),
                                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.2f)
                            )

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Column {
                                    Text("Standard Fee", fontSize = 11.sp)
                                    Text("₹ ${summary.total_fee.toInt()}", fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                                }
                                Column {
                                    Text("Concession", fontSize = 11.sp)
                                    Text("₹ ${summary.discount.toInt()}", fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                                }
                                Column {
                                    Text("Paid Amount", fontSize = 11.sp)
                                    Text("₹ ${summary.paid_fee.toInt()}", fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = Color(0xFF047857))
                                }
                                Column {
                                    Text("Balance Due", fontSize = 11.sp)
                                    Text(
                                        "₹ ${summary.balance.toInt()}",
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 14.sp,
                                        color = if (summary.balance > 0) Color(0xFFDC2626) else Color(0xFF047857)
                                    )
                                }
                            }
                        }
                    }
                }

                // Receipts History Header
                item {
                    Text(
                        text = "Payment History (${statement!!.payments.size})",
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp
                    )
                }

                // Receipts List
                if (statement!!.payments.isEmpty()) {
                    item {
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
                        ) {
                            Box(modifier = Modifier.padding(20.dp).fillMaxWidth(), contentAlignment = Alignment.Center) {
                                Text("No payment installments recorded yet.", color = Color.Gray, fontSize = 13.sp)
                            }
                        }
                    }
                } else {
                    items(statement!!.payments) { payment ->
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(10.dp),
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(14.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = "Receipt #${payment.receipt_no ?: payment.id}",
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 14.sp
                                    )
                                    Text(
                                        text = "${payment.payment_date ?: "N/A"} • ${payment.payment_mode ?: "CASH"}",
                                        fontSize = 12.sp,
                                        color = Color.Gray
                                    )
                                    if (!payment.collected_by.isNullOrBlank()) {
                                        Text(
                                            text = "By: ${payment.collected_by}",
                                            fontSize = 11.sp,
                                            color = Color.Gray
                                        )
                                    }
                                }

                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(
                                        text = "₹ ${payment.amount.toInt()}",
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 16.sp,
                                        color = Color(0xFF047857),
                                        modifier = Modifier.padding(end = 8.dp)
                                    )

                                    // Print Thermal Receipt Button
                                    IconButton(onClick = {
                                        lastReceiptToPrint = payment
                                        showPrinterDialog = true
                                    }) {
                                        Icon(
                                            Icons.Default.Print,
                                            contentDescription = "Print Slip",
                                            tint = MaterialTheme.colorScheme.primary
                                        )
                                    }

                                    // WhatsApp Share Button
                                    IconButton(onClick = {
                                        val phone = s.phone ?: ""
                                        val cleanPhone = phone.replace(Regex("[^0-9]"), "").let {
                                            if (it.length == 10) "91$it" else it
                                        }
                                        val receiptMsg = """
                                            *KRANTHI HIGH SCHOOL - SIDDIPET*
                                            Fee Receipt: ${payment.receipt_no ?: payment.id}
                                            Student: ${s.name} (${s.getEffectiveClass()})
                                            Date: ${payment.payment_date ?: ""}
                                            Amount Paid: ₹ ${payment.amount.toInt()}
                                            Mode: ${payment.payment_mode ?: "CASH"}
                                            Remaining Balance: ₹ ${summary.balance.toInt()}
                                            View Online: ${sessionManager.baseUrl}/receipt.html?receipt_no=${payment.receipt_no}
                                        """.trimIndent()

                                        try {
                                            val uri = Uri.parse("https://api.whatsapp.com/send?phone=$cleanPhone&text=${Uri.encode(receiptMsg)}")
                                            val intent = Intent(Intent.ACTION_VIEW, uri)
                                            context.startActivity(intent)
                                        } catch (e: Exception) {
                                            Toast.makeText(context, "Could not open WhatsApp: ${e.message}", Toast.LENGTH_SHORT).show()
                                        }
                                    }) {
                                        Icon(
                                            Icons.Default.Share,
                                            contentDescription = "Share WhatsApp",
                                            tint = Color(0xFF25D366)
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Payment Collection Dialog
    if (showPaymentDialog && statement != null) {
        AlertDialog(
            onDismissRequest = { if (!isSubmittingPayment) showPaymentDialog = false },
            title = { Text("Collect Payment") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Student: ${statement!!.student.name}")
                    OutlinedTextField(
                        value = paymentAmount,
                        onValueChange = { paymentAmount = it },
                        label = { Text("Amount (₹)") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    // Mode Selection
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf("CASH", "UPI", "BANK_TRANSFER").forEach { mode ->
                            FilterChip(
                                selected = paymentMode == mode,
                                onClick = { paymentMode = mode },
                                label = { Text(mode, fontSize = 11.sp) }
                            )
                        }
                    }

                    OutlinedTextField(
                        value = paymentRemarks,
                        onValueChange = { paymentRemarks = it },
                        label = { Text("Remarks (Optional)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        val amount = paymentAmount.toDoubleOrNull()
                        if (amount == null || amount <= 0) {
                            Toast.makeText(context, "Enter valid positive amount", Toast.LENGTH_SHORT).show()
                            return@Button
                        }
                        isSubmittingPayment = true
                        scope.launch {
                            try {
                                val api = ApiClient.getService(context)
                                val req = CollectPaymentRequest(
                                    student_id = studentId,
                                    amount = amount,
                                    payment_mode = paymentMode,
                                    remarks = paymentRemarks.ifBlank { null }
                                )
                                val res = api.collectPayment(req)
                                if (res.isSuccessful && res.body()?.success == true) {
                                    Toast.makeText(context, "Payment collected: ${res.body()?.receipt_no}", Toast.LENGTH_LONG).show()
                                    showPaymentDialog = false
                                    loadLedger()
                                } else {
                                    Toast.makeText(context, "Failed: ${res.body()?.message ?: res.message()}", Toast.LENGTH_SHORT).show()
                                }
                            } catch (e: Exception) {
                                Toast.makeText(context, "Error: ${e.localizedMessage}", Toast.LENGTH_SHORT).show()
                            } finally {
                                isSubmittingPayment = false
                            }
                        }
                    },
                    enabled = !isSubmittingPayment
                ) {
                    if (isSubmittingPayment) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                    } else {
                        Text("Confirm & Save")
                    }
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { showPaymentDialog = false },
                    enabled = !isSubmittingPayment
                ) {
                    Text("Cancel")
                }
            }
        )
    }

    // Bluetooth Thermal Printer Selection Dialog
    if (showPrinterDialog && lastReceiptToPrint != null) {
        val pairedDevices = remember { printerHelper.getPairedPrinters() }

        AlertDialog(
            onDismissRequest = { showPrinterDialog = false },
            title = { Text("Select Thermal Printer") },
            text = {
                Column(modifier = Modifier.fillMaxWidth()) {
                    if (pairedDevices.isEmpty()) {
                        Text(
                            "No paired Bluetooth printers found.\nPlease pair your 58mm/80mm Bluetooth printer in Android Settings first.",
                            fontSize = 13.sp,
                            color = Color.Gray
                        )
                    } else {
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            items(pairedDevices) { device ->
                                Card(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable {
                                            showPrinterDialog = false
                                            sessionManager.savedPrinterMac = device.address

                                            scope.launch {
                                                Toast.makeText(context, "Printing to ${device.name ?: device.address}...", Toast.LENGTH_SHORT).show()
                                                val s = statement!!.student
                                                val res = printerHelper.printFeeReceipt(
                                                    deviceAddress = device.address,
                                                    receiptNo = lastReceiptToPrint!!.receipt_no ?: "REC-${lastReceiptToPrint!!.id}",
                                                    date = lastReceiptToPrint!!.payment_date ?: SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date()),
                                                    studentName = s.name,
                                                    studentClass = s.getEffectiveClass(),
                                                    studentId = s.admission_no ?: s.student_id ?: s.id.toString(),
                                                    amountPaid = lastReceiptToPrint!!.amount,
                                                    balanceRemaining = statement!!.fee_summary?.balance ?: s.balance,
                                                    paymentMode = lastReceiptToPrint!!.payment_mode ?: "CASH",
                                                    collectedBy = lastReceiptToPrint!!.collected_by ?: sessionManager.getUserFullName() ?: "Staff"
                                                )
                                                if (res.isSuccess) {
                                                    Toast.makeText(context, "Slip printed successfully!", Toast.LENGTH_SHORT).show()
                                                } else {
                                                    Toast.makeText(context, "Print failed: ${res.exceptionOrNull()?.message}", Toast.LENGTH_LONG).show()
                                                }
                                            }
                                        },
                                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
                                ) {
                                    Column(modifier = Modifier.padding(12.dp)) {
                                        Text(device.name ?: "Unknown Printer", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                                        Text(device.address, fontSize = 11.sp, color = Color.Gray)
                                    }
                                }
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { showPrinterDialog = false }) {
                    Text("Close")
                }
            }
        )
    }
}
