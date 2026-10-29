package com.kranthischool.khsbilling.ui

import android.app.DatePickerDialog
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.DateRange
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
import com.kranthischool.khsbilling.data.ApiClient
import com.kranthischool.khsbilling.data.EodReportResponse
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EodReportScreen(
    onNavigateBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val calendar = remember { Calendar.getInstance() }
    val dateFormatter = remember { SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()) }
    val displayFormatter = remember { SimpleDateFormat("EEE, dd MMM yyyy", Locale.getDefault()) }

    var selectedDateString by remember { mutableStateOf(dateFormatter.format(calendar.time)) }
    var eodData by remember { mutableStateOf<EodReportResponse?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    fun loadEod(date: String) {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val api = ApiClient.getService(context)
                val res = api.getEodReport(date, "All")
                if (res.isSuccessful) {
                    eodData = res.body()
                } else {
                    errorMessage = "Failed to load EOD Report (${res.code()})"
                }
            } catch (e: Exception) {
                errorMessage = "Network error: ${e.localizedMessage}"
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(selectedDateString) {
        loadEod(selectedDateString)
    }

    fun pickDate() {
        val y = calendar.get(Calendar.YEAR)
        val m = calendar.get(Calendar.MONTH)
        val d = calendar.get(Calendar.DAY_OF_MONTH)

        DatePickerDialog(context, { _, year, month, dayOfMonth ->
            calendar.set(year, month, dayOfMonth)
            selectedDateString = dateFormatter.format(calendar.time)
        }, y, m, d).show()
    }

    fun stepDay(offset: Int) {
        calendar.add(Calendar.DAY_OF_MONTH, offset)
        selectedDateString = dateFormatter.format(calendar.time)
    }

    Scaffold(
        containerColor = Color(0xFFF8FAFC),
        topBar = {
            Surface(color = Color.White, shadowElevation = 2.dp) {
                TopAppBar(
                    title = {
                        Column {
                            Text("EOD & Receipts", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Color(0xFF0F172A))
                            Text("Day-Wise Collection Reports", fontSize = 12.sp, color = Color(0xFF64748B))
                        }
                    },
                    navigationIcon = {
                        IconButton(onClick = onNavigateBack) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = Color(0xFF0F172A))
                        }
                    },
                    actions = {
                        IconButton(onClick = { loadEod(selectedDateString) }) {
                            Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = Color(0xFF4338CA))
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White)
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
            // DATE PICKER STRIP
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                color = Color.White,
                shadowElevation = 2.dp,
                border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE2E8F0))
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 8.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    IconButton(onClick = { stepDay(-1) }) {
                        Icon(Icons.Default.ChevronLeft, contentDescription = "Previous Day", tint = Color(0xFF4338CA))
                    }

                    Row(
                        modifier = Modifier
                            .clickable { pickDate() }
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.CalendarMonth, contentDescription = null, tint = Color(0xFF4338CA), modifier = Modifier.size(20.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = displayFormatter.format(calendar.time),
                                fontWeight = FontWeight.Bold,
                                fontSize = 15.sp,
                                color = Color(0xFF0F172A)
                            )
                            Text(
                                text = "Tap to pick date",
                                fontSize = 11.sp,
                                color = Color(0xFF64748B)
                            )
                        }
                    }

                    IconButton(onClick = { stepDay(1) }) {
                        Icon(Icons.Default.ChevronRight, contentDescription = "Next Day", tint = Color(0xFF4338CA))
                    }
                }
            }

            Spacer(modifier = Modifier.height(14.dp))

            if (isLoading) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Color(0xFF4338CA))
                }
            } else if (errorMessage != null) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(errorMessage ?: "", color = Color(0xFFDC2626))
                }
            } else if (eodData != null) {
                val data = eodData!!

                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    // Summary Banner Card
                    item {
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(16.dp),
                            color = Color(0xFF4338CA),
                            shadowElevation = 3.dp
                        ) {
                            Column(modifier = Modifier.padding(18.dp)) {
                                Text(
                                    text = "COLLECTION ON $selectedDateString",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = Color.White.copy(alpha = 0.8f),
                                    letterSpacing = 1.sp
                                )
                                Text(
                                    text = "₹ ${data.total_amount.toInt()}",
                                    fontSize = 32.sp,
                                    fontWeight = FontWeight.ExtraBold,
                                    color = Color.White,
                                    modifier = Modifier.padding(vertical = 4.dp)
                                )
                                Text(
                                    text = "${data.total_receipts} Receipts Issued • All Branches",
                                    fontSize = 13.sp,
                                    color = Color.White.copy(alpha = 0.9f)
                                )

                                Spacer(modifier = Modifier.height(14.dp))
                                HorizontalDivider(color = Color.White.copy(alpha = 0.2f))
                                Spacer(modifier = Modifier.height(12.dp))

                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Column {
                                        Text("Cash", fontSize = 11.sp, color = Color.White.copy(alpha = 0.7f))
                                        Text("₹ ${data.cash_total.toInt()}", fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color.White)
                                    }
                                    Column {
                                        Text("UPI", fontSize = 11.sp, color = Color.White.copy(alpha = 0.7f))
                                        Text("₹ ${data.upi_total.toInt()}", fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color.White)
                                    }
                                    Column {
                                        Text("Bank / Cheque", fontSize = 11.sp, color = Color.White.copy(alpha = 0.7f))
                                        Text("₹ ${data.bank_total.toInt()}", fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color.White)
                                    }
                                }
                            }
                        }
                    }

                    // Itemized Receipts List Header
                    item {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(top = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                "Day Receipts (${data.transactions.size})",
                                fontWeight = FontWeight.Bold,
                                fontSize = 15.sp,
                                color = Color(0xFF0F172A)
                            )
                            Surface(
                                shape = RoundedCornerShape(6.dp),
                                color = Color(0xFFEFF6FF)
                            ) {
                                Text(
                                    "Date: $selectedDateString",
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = Color(0xFF2563EB)
                                )
                            }
                        }
                    }

                    if (data.transactions.isEmpty()) {
                        item {
                            Surface(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 24.dp),
                                shape = RoundedCornerShape(12.dp),
                                color = Color.White,
                                border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE2E8F0))
                            ) {
                                Box(
                                    modifier = Modifier.padding(32.dp),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                        Icon(Icons.Default.DateRange, contentDescription = null, tint = Color(0xFFCBD5E1), modifier = Modifier.size(48.dp))
                                        Spacer(modifier = Modifier.height(8.dp))
                                        Text("No receipts issued on this date.", color = Color(0xFF94A3B8), fontSize = 14.sp)
                                    }
                                }
                            }
                        }
                    } else {
                        items(data.transactions) { tx ->
                            Surface(
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(12.dp),
                                color = Color.White,
                                shadowElevation = 1.dp,
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
                                                .size(40.dp)
                                                .background(Color(0xFFECFDF5), shape = CircleShape),
                                            contentAlignment = Alignment.Center
                                        ) {
                                            Text("₹", fontWeight = FontWeight.Bold, color = Color(0xFF059669), fontSize = 18.sp)
                                        }

                                        Spacer(modifier = Modifier.width(12.dp))

                                        Column {
                                            Text(
                                                tx.student_name ?: "Student",
                                                fontWeight = FontWeight.Bold,
                                                fontSize = 15.sp,
                                                color = Color(0xFF0F172A)
                                            )
                                            Text(
                                                "Receipt: ${tx.receipt_no ?: "N/A"} • Class ${tx.class_name ?: "N/A"}",
                                                fontSize = 12.sp,
                                                color = Color(0xFF64748B)
                                            )
                                            Text(
                                                "Collected by: ${tx.collected_by ?: "Staff"} (${tx.payment_mode})",
                                                fontSize = 11.sp,
                                                color = Color(0xFF4338CA),
                                                modifier = Modifier.padding(top = 2.dp)
                                            )
                                        }
                                    }

                                    Column(horizontalAlignment = Alignment.End) {
                                        Text(
                                            "₹ ${tx.amount_paid.toInt()}",
                                            fontWeight = FontWeight.ExtraBold,
                                            fontSize = 17.sp,
                                            color = Color(0xFF059669)
                                        )
                                        Surface(
                                            shape = RoundedCornerShape(4.dp),
                                            color = Color(0xFFF1F5F9),
                                            modifier = Modifier.padding(top = 4.dp)
                                        ) {
                                            Text(
                                                tx.payment_mode ?: "CASH",
                                                fontSize = 10.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = Color(0xFF475569),
                                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
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
    }
}
