package com.kranthischool.khsbilling.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.kranthischool.khsbilling.R
import com.kranthischool.khsbilling.data.ApiClient
import com.kranthischool.khsbilling.data.LoginRequest
import com.kranthischool.khsbilling.data.SessionManager
import com.kranthischool.khsbilling.data.VerifyOtpRequest
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(
    onLoginSuccess: () -> Unit
) {
    val context = LocalContext.current
    val sessionManager = remember { SessionManager(context) }
    val scope = rememberCoroutineScope()
    val scrollState = rememberScrollState()

    // Login mode toggle: 0 = Front Desk / Cashier, 1 = Admin / Management
    var selectedRoleTab by remember { mutableStateOf(1) } // Default to Admin as requested

    // Admin fields
    var adminPin by remember { mutableStateOf("") }

    // Front Desk fields
    var frontdeskMobile by remember { mutableStateOf("") }
    var frontdeskOtp by remember { mutableStateOf("") }

    var serverUrl by remember { mutableStateOf(sessionManager.baseUrl) }
    var showServerSettings by remember { mutableStateOf(false) }

    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(scrollState)
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // School Logo
            Image(
                painter = painterResource(id = R.drawable.khs_logo),
                contentDescription = "KHS Logo",
                modifier = Modifier
                    .size(90.dp)
                    .padding(bottom = 12.dp)
            )

            Text(
                text = "KRANTHI HIGH SCHOOL",
                fontSize = 20.sp,
                fontWeight = FontWeight.ExtraBold,
                color = MaterialTheme.colorScheme.primary
            )
            Text(
                text = "Billing & Receipt System",
                fontSize = 13.sp,
                color = Color.Gray,
                modifier = Modifier.padding(bottom = 20.dp)
            )

            // Role Selector Tab (Front Desk vs Admin)
            TabRow(
                selectedTabIndex = selectedRoleTab,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp),
                containerColor = MaterialTheme.colorScheme.surfaceVariant
            ) {
                Tab(
                    selected = selectedRoleTab == 0,
                    onClick = {
                        selectedRoleTab = 0
                        errorMessage = null
                    },
                    text = { Text("Front Desk", fontWeight = if (selectedRoleTab == 0) FontWeight.Bold else FontWeight.Normal) }
                )
                Tab(
                    selected = selectedRoleTab == 1,
                    onClick = {
                        selectedRoleTab = 1
                        errorMessage = null
                    },
                    text = { Text("Admin (PIN)", fontWeight = if (selectedRoleTab == 1) FontWeight.Bold else FontWeight.Normal) }
                )
            }

            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    if (selectedRoleTab == 1) {
                        // ADMIN LOGIN
                        Text(
                            text = "Admin Access",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(bottom = 8.dp)
                        )
                        Text(
                            text = "Enter 6-digit Secret PIN",
                            fontSize = 13.sp,
                            color = Color.Gray,
                            modifier = Modifier.padding(bottom = 16.dp)
                        )

                        OutlinedTextField(
                            value = adminPin,
                            onValueChange = { if (it.length <= 8) adminPin = it },
                            label = { Text("6-Digit Admin PIN") },
                            placeholder = { Text("Enter 6-digit PIN") },
                            visualTransformation = PasswordVisualTransformation(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                    } else {
                        // FRONT DESK LOGIN
                        Text(
                            text = "Front Desk Access",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(bottom = 8.dp)
                        )
                        Text(
                            text = "Enter Registered Mobile & OTP",
                            fontSize = 13.sp,
                            color = Color.Gray,
                            modifier = Modifier.padding(bottom = 16.dp)
                        )

                        OutlinedTextField(
                            value = frontdeskMobile,
                            onValueChange = { frontdeskMobile = it },
                            label = { Text("Registered Mobile Number") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )

                        Spacer(modifier = Modifier.height(12.dp))

                        OutlinedTextField(
                            value = frontdeskOtp,
                            onValueChange = { frontdeskOtp = it },
                            label = { Text("Authenticator Code / PIN") },
                            visualTransformation = PasswordVisualTransformation(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }

                    if (errorMessage != null) {
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            text = errorMessage ?: "",
                            color = MaterialTheme.colorScheme.error,
                            fontSize = 13.sp
                        )
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    Button(
                        onClick = {
                            isLoading = true
                            errorMessage = null
                            scope.launch {
                                try {
                                    val api = ApiClient.getService(context)
                                    if (selectedRoleTab == 1) {
                                        // Admin Login using PIN (T1/T2)
                                        if (adminPin.isBlank()) {
                                            errorMessage = "Please enter Admin PIN"
                                            isLoading = false
                                            return@launch
                                        }
                                        val req = LoginRequest(
                                            username = "admin",
                                            mobile = "admin",
                                            pin = adminPin.trim(),
                                            password = adminPin.trim()
                                        )
                                        val response = api.login(req)
                                        val body = response.body()
                                        if (response.isSuccessful && body != null && body.isSuccessful()) {
                                            val token = body.getAuthToken()
                                            val user = body.user ?: com.kranthischool.khsbilling.data.UserProfile(
                                                username = "admin",
                                                full_name = "Administrator",
                                                role = "ADMIN"
                                            )
                                            sessionManager.saveSession(token, user)
                                            onLoginSuccess()
                                        } else {
                                            errorMessage = body?.message
                                                ?: "Invalid Admin PIN. Please check your PIN."
                                        }
                                    } else {
                                        // Front Desk Login using Mobile & PIN (or OTP)
                                        if (frontdeskMobile.isBlank() || frontdeskOtp.isBlank()) {
                                            errorMessage = "Please enter Mobile number and PIN / Code"
                                            isLoading = false
                                            return@launch
                                        }

                                        // Try primary password/PIN login endpoint first
                                        val loginReq = LoginRequest(
                                            username = frontdeskMobile.trim(),
                                            mobile = frontdeskMobile.trim(),
                                            password = frontdeskOtp.trim(),
                                            pin = frontdeskOtp.trim()
                                        )
                                        val loginRes = api.login(loginReq)
                                        val loginBody = loginRes.body()

                                        if (loginRes.isSuccessful && loginBody != null && loginBody.isSuccessful()) {
                                            val token = loginBody.getAuthToken()
                                            val user = loginBody.user ?: com.kranthischool.khsbilling.data.UserProfile(
                                                username = frontdeskMobile.trim(),
                                                full_name = "Front Desk",
                                                role = "FRONTDESK"
                                            )
                                            sessionManager.saveSession(token, user)
                                            onLoginSuccess()
                                        } else {
                                            // Fallback to verify-otp endpoint if standard login didn't match
                                            val otpReq = VerifyOtpRequest(
                                                mobile = frontdeskMobile.trim(),
                                                otp_code = frontdeskOtp.trim()
                                            )
                                            val otpRes = api.verifyOtp(otpReq)
                                            val otpBody = otpRes.body()
                                            if (otpRes.isSuccessful && otpBody != null && otpBody.isSuccessful()) {
                                                val token = otpBody.getAuthToken()
                                                val user = otpBody.user ?: com.kranthischool.khsbilling.data.UserProfile(
                                                    username = frontdeskMobile.trim(),
                                                    full_name = "Front Desk",
                                                    role = "FRONTDESK"
                                                )
                                                sessionManager.saveSession(token, user)
                                                onLoginSuccess()
                                            } else {
                                                errorMessage = otpBody?.message ?: loginBody?.message
                                                    ?: "Invalid Mobile Number or PIN."
                                            }
                                        }
                                    }
                                } catch (e: Exception) {
                                    errorMessage = "Connection error: ${e.localizedMessage}"
                                } finally {
                                    isLoading = false
                                }
                            }
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(50.dp),
                        shape = RoundedCornerShape(10.dp),
                        enabled = !isLoading
                    ) {
                        if (isLoading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(24.dp),
                                color = MaterialTheme.colorScheme.onPrimary,
                                strokeWidth = 2.dp
                            )
                        } else {
                            Text(
                                if (selectedRoleTab == 1) "Sign In as Admin" else "Sign In as Front Desk",
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            TextButton(onClick = { showServerSettings = !showServerSettings }) {
                Text(
                    text = if (showServerSettings) "Hide Server Settings" else "⚙️ Change Server Address",
                    fontSize = 12.sp,
                    color = Color.Gray
                )
            }

            if (showServerSettings) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Text("Backend Server Address:", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                        Spacer(modifier = Modifier.height(6.dp))
                        OutlinedTextField(
                            value = serverUrl,
                            onValueChange = { serverUrl = it },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(
                                onClick = {
                                    serverUrl = SessionManager.DEFAULT_CLOUD_URL
                                    sessionManager.baseUrl = serverUrl
                                    ApiClient.resetClient()
                                },
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("Cloud (Render)", fontSize = 11.sp)
                            }
                            OutlinedButton(
                                onClick = {
                                    serverUrl = "http://192.168.0.165:8000"
                                    sessionManager.baseUrl = serverUrl
                                    ApiClient.resetClient()
                                },
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("Local Wi-Fi PC", fontSize = 11.sp)
                            }
                        }
                    }
                }
            }
        }
    }
}
