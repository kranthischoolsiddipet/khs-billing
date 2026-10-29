package com.kranthischool.khsbilling.data

import android.content.Context
import android.content.SharedPreferences

class SessionManager(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("khs_session_prefs", Context.MODE_PRIVATE)

    companion object {
        private const val KEY_TOKEN = "auth_token"
        private const val KEY_USER_ID = "user_id"
        private const val KEY_USERNAME = "username"
        private const val KEY_FULL_NAME = "full_name"
        private const val KEY_ROLE = "role"
        private const val KEY_MOBILE = "mobile"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_PRINTER_MAC = "printer_mac_address"

        // Default to cloud Render URL; can be toggled to local dev server
        const val DEFAULT_CLOUD_URL = "https://khs-billing.onrender.com"
        const val DEFAULT_LOCAL_URL = "http://10.0.2.2:8000" // For Android Emulator
    }

    fun saveSession(token: String, user: UserProfile) {
        prefs.edit().apply {
            putString(KEY_TOKEN, token)
            user.id?.let { putInt(KEY_USER_ID, it) }
            putString(KEY_USERNAME, user.username)
            putString(KEY_FULL_NAME, user.full_name)
            putString(KEY_ROLE, user.role)
            putString(KEY_MOBILE, user.mobile)
            apply()
        }
    }

    fun getToken(): String? = prefs.getString(KEY_TOKEN, null)

    fun getUserRole(): String? = prefs.getString(KEY_ROLE, null)

    fun getUserFullName(): String? = prefs.getString(KEY_FULL_NAME, null)

    fun isLoggedIn(): Boolean = !getToken().isNullOrBlank()

    fun clearSession() {
        prefs.edit().apply {
            remove(KEY_TOKEN)
            remove(KEY_USER_ID)
            remove(KEY_USERNAME)
            remove(KEY_FULL_NAME)
            remove(KEY_ROLE)
            remove(KEY_MOBILE)
            apply()
        }
    }

    var baseUrl: String
        get() = prefs.getString(KEY_BASE_URL, DEFAULT_CLOUD_URL) ?: DEFAULT_CLOUD_URL
        set(value) = prefs.edit().putString(KEY_BASE_URL, value.trimEnd('/')).apply()

    var savedPrinterMac: String?
        get() = prefs.getString(KEY_PRINTER_MAC, null)
        set(value) = prefs.edit().putString(KEY_PRINTER_MAC, value).apply()
}
