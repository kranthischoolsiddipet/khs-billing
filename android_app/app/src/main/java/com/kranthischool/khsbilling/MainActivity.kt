package com.kranthischool.khsbilling

import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.activity.compose.setContent
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.kranthischool.khsbilling.data.SessionManager
import com.kranthischool.khsbilling.ui.AdminApprovalsScreen
import com.kranthischool.khsbilling.ui.DashboardScreen
import com.kranthischool.khsbilling.ui.LoginScreen
import com.kranthischool.khsbilling.ui.StudentLedgerScreen
import com.kranthischool.khsbilling.ui.theme.KhsBillingTheme

class MainActivity : FragmentActivity() {

    private lateinit var sessionManager: SessionManager
    private var isAppLocked = mutableStateOf(false)
    private var lastBackgroundTime: Long = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        sessionManager = SessionManager(this)

        val startDestination = if (sessionManager.isLoggedIn()) "dashboard" else "login"

        // If already logged in, prompt device authentication on cold start
        if (sessionManager.isLoggedIn()) {
            isAppLocked.value = true
        }

        setContent {
            KhsBillingTheme {
                val locked by isAppLocked

                if (locked && sessionManager.isLoggedIn()) {
                    DeviceLockOverlay(
                        onUnlockRequest = { promptDeviceUnlock() }
                    )
                } else {
                    AppNavigation(
                        startDestination = startDestination,
                        onLogoutAction = {
                            isAppLocked.value = false
                        }
                    )
                }
            }
        }

        if (sessionManager.isLoggedIn()) {
            promptDeviceUnlock()
        }
    }

    override fun onPause() {
        super.onPause()
        lastBackgroundTime = System.currentTimeMillis()
    }

    override fun onResume() {
        super.onResume()
        // If app was sent to background for more than 45 seconds and user is logged in, lock screen
        if (sessionManager.isLoggedIn() && lastBackgroundTime > 0) {
            val elapsed = System.currentTimeMillis() - lastBackgroundTime
            if (elapsed > 45_000) {
                isAppLocked.value = true
                promptDeviceUnlock()
            }
        }
    }

    private fun promptDeviceUnlock() {
        val executor = ContextCompat.getMainExecutor(this)
        val biometricPrompt = BiometricPrompt(
            this,
            executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    super.onAuthenticationSucceeded(result)
                    isAppLocked.value = false
                }

                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    super.onAuthenticationError(errorCode, errString)
                    // If user cancelled, app stays locked with prompt button
                    if (errorCode != BiometricPrompt.ERROR_USER_CANCELED && errorCode != BiometricPrompt.ERROR_NEGATIVE_BUTTON) {
                        Toast.makeText(this@MainActivity, "$errString", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )

        // Support both Biometric (Fingerprint/Face) and Phone's Screen Lock PIN / Pattern
        val authenticators = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            BiometricManager.Authenticators.BIOMETRIC_STRONG or BiometricManager.Authenticators.DEVICE_CREDENTIAL
        } else {
            BiometricManager.Authenticators.BIOMETRIC_WEAK or BiometricManager.Authenticators.DEVICE_CREDENTIAL
        }

        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Kranthi High School")
            .setSubtitle("Confirm your Phone PIN, Pattern or Fingerprint to unlock")
            .setAllowedAuthenticators(authenticators)
            .build()

        try {
            biometricPrompt.authenticate(promptInfo)
        } catch (e: Exception) {
            // Fallback if device has no secure lock set up
            isAppLocked.value = false
        }
    }
}

@Composable
fun DeviceLockOverlay(onUnlockRequest: () -> Unit) {
    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Box(
                modifier = Modifier
                    .size(90.dp)
                    .background(MaterialTheme.colorScheme.primaryContainer, shape = CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.Lock,
                    contentDescription = "Locked",
                    modifier = Modifier.size(48.dp),
                    tint = MaterialTheme.colorScheme.primary
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            Text(
                text = "KHS Billing Locked",
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onBackground
            )

            Text(
                text = "Use your device PIN, Pattern, or Fingerprint to resume counter billing.",
                fontSize = 14.sp,
                color = Color.Gray,
                modifier = Modifier.padding(top = 8.dp, bottom = 32.dp),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center
            )

            Button(
                onClick = onUnlockRequest,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp),
                shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)
            ) {
                Text("Unlock App", fontSize = 16.sp, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
fun AppNavigation(
    startDestination: String,
    onLogoutAction: () -> Unit
) {
    val navController = rememberNavController()

    NavHost(
        navController = navController,
        startDestination = startDestination
    ) {
        composable("login") {
            LoginScreen(
                onLoginSuccess = {
                    navController.navigate("dashboard") {
                        popUpTo("login") { inclusive = true }
                    }
                }
            )
        }

        composable("dashboard") {
            DashboardScreen(
                onSelectStudent = { studentId ->
                    navController.navigate("student_ledger/$studentId")
                },
                onNavigateApprovals = {
                    navController.navigate("admin_approvals")
                },
                onLogout = {
                    onLogoutAction()
                    navController.navigate("login") {
                        popUpTo("dashboard") { inclusive = true }
                    }
                }
            )
        }

        composable(
            route = "student_ledger/{studentId}",
            arguments = listOf(navArgument("studentId") { type = NavType.IntType })
        ) { backStackEntry ->
            val studentId = backStackEntry.arguments?.getInt("studentId") ?: 0
            StudentLedgerScreen(
                studentId = studentId,
                onNavigateBack = {
                    navController.popBackStack()
                }
            )
        }

        composable("admin_approvals") {
            AdminApprovalsScreen(
                onNavigateBack = {
                    navController.popBackStack()
                }
            )
        }
    }
}
