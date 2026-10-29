package com.kranthischool.khsbilling.data

import com.google.gson.annotations.SerializedName

data class LoginRequest(
    val username: String? = null,
    val mobile: String? = null,
    val pin: String? = null,
    val password: String? = null,
    val totp_code: String? = null
)

data class LoginResponse(
    val status: String? = null,
    val success: Boolean = false,
    val message: String? = null,
    val token: String? = null,
    val session_token: String? = null,
    val user: UserProfile? = null,
    val requires_totp: Boolean = false,
    val requires_pin_setup: Boolean = false
) {
    fun isSuccessful(): Boolean = success || status == "success"
    fun getAuthToken(): String = token ?: session_token ?: ""
}

data class UserProfile(
    val id: Int? = null,
    val username: String? = null,
    val full_name: String? = null,
    val role: String? = null,
    val mobile: String? = null,
    val status: String? = null
)

data class Student(
    val id: Int,
    val student_id: String? = null,
    val admission_no: String? = null,
    @SerializedName("student_name") val raw_name: String? = null,
    val name: String? = null,
    val class_name: String? = null,
    @SerializedName("class") val standard: String? = null,
    val section: String? = null,
    val student_type: String? = null,
    val admission_type: String? = null,
    @SerializedName("parent_name") val parent_name: String? = null,
    val father_name: String? = null,
    val mother_name: String? = null,
    @SerializedName("parent_phone") val parent_phone: String? = null,
    val phone: String? = null,
    @SerializedName("standard_fee") val total_fee: Double = 0.0,
    @SerializedName("total_paid") val paid_fee: Double = 0.0,
    @SerializedName("balance_due") val balance: Double = 0.0,
    @SerializedName("discount_amount") val discount: Double = 0.0,
    val status: String? = null
) {
    fun getDisplayName(): String = raw_name ?: name ?: "Unnamed Student"
    fun getEffectivePhone(): String? = parent_phone ?: phone
    fun getEffectiveClass(): String = class_name ?: standard ?: "N/A"
}

data class StatementResponse(
    val student: Student,
    val fee_summary: FeeSummary? = null,
    val payments: List<PaymentItem> = emptyList(),
    val discounts: List<DiscountItem> = emptyList()
)

data class FeeSummary(
    val total_fee: Double = 0.0,
    val discount: Double = 0.0,
    val net_fee: Double = 0.0,
    val paid_fee: Double = 0.0,
    val balance: Double = 0.0
)

data class PaymentItem(
    val id: Int? = null,
    val receipt_no: String? = null,
    val amount: Double = 0.0,
    val payment_mode: String? = null,
    val reference_no: String? = null,
    val payment_date: String? = null,
    val collected_by: String? = null,
    val remarks: String? = null
)

data class DiscountItem(
    val id: Int? = null,
    val discount_type: String? = null,
    val amount: Double = 0.0,
    val status: String? = null,
    val requested_by: String? = null,
    val approved_by: String? = null,
    val reason: String? = null,
    val date: String? = null
)

data class FeeStructure(
    val id: Int? = null,
    val class_name: String,
    val admission_type: String,
    val tuition_fee: Double = 0.0,
    val term_fee: Double = 0.0,
    val exam_fee: Double = 0.0,
    val transport_fee: Double = 0.0,
    val total_fee: Double = 0.0
)

data class CollectPaymentRequest(
    val student_id: Int,
    val amount: Double,
    val payment_mode: String = "CASH",
    val reference_no: String? = null,
    val remarks: String? = null
)

data class PaymentResponse(
    val success: Boolean,
    val message: String? = null,
    val receipt_no: String? = null,
    val payment_id: Int? = null,
    val balance_remaining: Double = 0.0
)

data class PendingDiscount(
    val id: Int,
    val student_id: Int,
    val student_name: String? = null,
    val class_name: String? = null,
    val discount_type: String? = null,
    val amount: Double = 0.0,
    val reason: String? = null,
    val requested_by: String? = null,
    val created_at: String? = null,
    val status: String? = null
)

data class ActionDiscountRequest(
    val discount_id: Int,
    val action: String, // "APPROVE" or "REJECT"
    val remarks: String? = null
)

data class ChangePinRequest(
    val old_pin: String,
    val new_pin: String
)

data class VerifyOtpRequest(
    val mobile: String,
    val otp_code: String
)

data class GenericResponse(
    val success: Boolean,
    val message: String? = null
)
