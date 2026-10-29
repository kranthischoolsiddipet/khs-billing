package com.kranthischool.khsbilling.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.FilterList
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.kranthischool.khsbilling.data.*
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EnrolledStudentsScreen(
    onSelectStudent: (Int) -> Unit,
    onNavigateBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var selectedClass by remember { mutableStateOf("All") }
    var selectedBranch by remember { mutableStateOf("All") }
    var selectedStatus by remember { mutableStateOf("Active") }
    var searchQuery by remember { mutableStateOf("") }

    var classWiseData by remember { mutableStateOf<ClassWiseResponse?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    fun loadData() {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val api = ApiClient.getService(context)
                val cFilter = if (selectedClass == "All") null else selectedClass
                val bFilter = if (selectedBranch == "All") null else selectedBranch
                val sFilter = if (selectedStatus == "All") null else if (selectedStatus == "Active") "Active" else "Cancelled"
                
                val res = api.getStudentsClassWise(className = cFilter, branch = bFilter, status = sFilter)
                if (res.isSuccessful) {
                    classWiseData = res.body()
                } else {
                    errorMessage = "Failed to load directory (${res.code()})"
                }
            } catch (e: Exception) {
                errorMessage = "Network error: ${e.localizedMessage}"
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(selectedClass, selectedBranch, selectedStatus) {
        loadData()
    }

    // Filter students by local search query
    val allStudents = classWiseData?.students ?: emptyList()
    val filteredStudents = remember(allStudents, searchQuery) {
        if (searchQuery.isBlank()) allStudents
        else {
            val q = searchQuery.trim().lowercase()
            allStudents.filter { s ->
                s.getDisplayName().lowercase().contains(q) ||
                (s.admission_no ?: "").lowercase().contains(q) ||
                (s.class_name ?: "").lowercase().contains(q) ||
                (s.getEffectivePhone() ?: "").contains(q)
            }
        }
    }

    val stats = classWiseData?.stats
    val classSummaries = classWiseData?.class_summaries ?: emptyList()

    Scaffold(
        containerColor = Color(0xFFF8FAFC),
        topBar = {
            Surface(color = Color.White, shadowElevation = 2.dp) {
                TopAppBar(
                    title = {
                        Column {
                            Text("Enrolled Students", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = Color(0xFF0F172A))
                            Text(
                                "Total ${stats?.total_enrolled ?: allStudents.size} Enrolled (${stats?.active_count ?: 0} Active)",
                                fontSize = 12.sp,
                                color = Color(0xFF64748B)
                            )
                        }
                    },
                    navigationIcon = {
                        IconButton(onClick = onNavigateBack) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = Color(0xFF0F172A))
                        }
                    },
                    actions = {
                        IconButton(onClick = { loadData() }) {
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
        ) {
            // 1. HORIZONTAL CLASS FILTER PILLS (Matching Web Portal)
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Color.White)
                    .padding(vertical = 10.dp)
            ) {
                Text(
                    text = "SELECT CLASS TO FILTER",
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF64748B),
                    letterSpacing = 1.sp,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                )

                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState())
                        .padding(horizontal = 16.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    val allCount = stats?.total_enrolled ?: allStudents.size
                    ClassFilterChip(
                        label = "All Classes",
                        count = allCount,
                        isSelected = selectedClass == "All",
                        onClick = { selectedClass = "All" }
                    )

                    val standardClasses = listOf("PP1", "PP2", "Class 1", "Class 2", "Class 3", "Class 4", "Class 5", "Class 6", "Class 7", "Class 8", "Class 9", "Class 10")
                    standardClasses.forEach { cls ->
                        val summary = classSummaries.find { it.class_name.equals(cls, ignoreCase = true) }
                        val cnt = summary?.total_students ?: 0
                        ClassFilterChip(
                            label = cls,
                            count = cnt,
                            isSelected = selectedClass.equals(cls, ignoreCase = true),
                            onClick = { selectedClass = cls }
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // 2. FINANCIAL STATS CARDS (Enrolled, Agreed Annual Fee, Collected, Balance)
            Column(modifier = Modifier.padding(horizontal = 16.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    MetricCard(
                        title = "TOTAL ENROLLED",
                        mainValue = "${stats?.active_count ?: 0}",
                        subText = "${stats?.total_enrolled ?: 0} Records",
                        valueColor = Color(0xFF2563EB),
                        bgColor = Color(0xFFEFF6FF),
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        title = "AGREED ANNUAL FEE",
                        mainValue = "₹ ${(stats?.total_agreed ?: 0.0).toInt()}",
                        subText = "Tuition & Transport",
                        valueColor = Color(0xFF0F172A),
                        bgColor = Color.White,
                        modifier = Modifier.weight(1.3f)
                    )
                }

                Spacer(modifier = Modifier.height(10.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    MetricCard(
                        title = "TOTAL COLLECTED",
                        mainValue = "₹ ${(stats?.total_paid ?: 0.0).toInt()}",
                        subText = "Cleared via receipts",
                        valueColor = Color(0xFF059669),
                        bgColor = Color(0xFFECFDF5),
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        title = "REMAINING BALANCE",
                        mainValue = "₹ ${(stats?.total_balance ?: 0.0).toInt()}",
                        subText = "Pending collection",
                        valueColor = Color(0xFFDC2626),
                        bgColor = Color(0xFFFEF2F2),
                        modifier = Modifier.weight(1f)
                    )
                }

                Spacer(modifier = Modifier.height(14.dp))

                // 3. SEARCH WITHIN RESULTS
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = Color.White,
                    shadowElevation = 1.dp
                ) {
                    OutlinedTextField(
                        value = searchQuery,
                        onValueChange = { searchQuery = it },
                        placeholder = { Text("Search within results (Name, Adm No, Phone)...", fontSize = 13.sp, color = Color(0xFF94A3B8)) },
                        leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = Color(0xFF4338CA)) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Color(0xFF4338CA),
                            unfocusedBorderColor = Color(0xFFE2E8F0),
                            focusedContainerColor = Color.White,
                            unfocusedContainerColor = Color.White
                        )
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // 4. STUDENT LIST
            if (isLoading) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Color(0xFF4338CA))
                }
            } else if (errorMessage != null) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(errorMessage ?: "", color = Color(0xFFDC2626))
                }
            } else if (filteredStudents.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No students found in this filter.", color = Color.Gray, fontSize = 14.sp)
                }
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(filteredStudents) { student ->
                        ModernStudentCard(student = student, onClick = { onSelectStudent(student.id) })
                    }
                    item {
                        Spacer(modifier = Modifier.height(16.dp))
                    }
                }
            }
        }
    }
}

@Composable
fun ClassFilterChip(
    label: String,
    count: Int,
    isSelected: Boolean,
    onClick: () -> Unit
) {
    Surface(
        shape = RoundedCornerShape(20.dp),
        color = if (isSelected) Color(0xFF4338CA) else Color(0xFFF1F5F9),
        modifier = Modifier.clickable { onClick() }
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = label,
                fontSize = 12.sp,
                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                color = if (isSelected) Color.White else Color(0xFF334155)
            )
            Spacer(modifier = Modifier.width(6.dp))
            Surface(
                shape = CircleShape,
                color = if (isSelected) Color.White.copy(alpha = 0.25f) else Color(0xFFE2E8F0)
            ) {
                Text(
                    text = "$count",
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = if (isSelected) Color.White else Color(0xFF64748B),
                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                )
            }
        }
    }
}

@Composable
fun MetricCard(
    title: String,
    mainValue: String,
    subText: String,
    valueColor: Color,
    bgColor: Color,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier.height(86.dp),
        shape = RoundedCornerShape(12.dp),
        color = bgColor,
        shadowElevation = 1.dp,
        border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE2E8F0))
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 12.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                text = title,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF64748B),
                letterSpacing = 0.5.sp
            )
            Text(
                text = mainValue,
                fontSize = 17.sp,
                fontWeight = FontWeight.ExtraBold,
                color = valueColor,
                modifier = Modifier.padding(vertical = 2.dp)
            )
            Text(
                text = subText,
                fontSize = 10.sp,
                color = Color(0xFF94A3B8)
            )
        }
    }
}
