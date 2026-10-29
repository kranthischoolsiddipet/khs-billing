package com.kranthischool.khsbilling.data

import retrofit2.Response
import retrofit2.http.*

interface KhsApiService {

    @POST("/api/auth/login")
    suspend fun login(@Body req: LoginRequest): Response<LoginResponse>

    @GET("/api/auth/me")
    suspend fun getCurrentUser(): Response<UserProfile>

    @GET("/api/students/search")
    suspend fun searchStudents(
        @Query("query") query: String,
        @Query("class_name") className: String? = null
    ): Response<List<Student>>

    @GET("/api/students/{id}/statement")
    suspend fun getStudentStatement(@Path("id") id: Int): Response<StatementResponse>

    @POST("/api/payments/collect")
    suspend fun collectPayment(@Body req: CollectPaymentRequest): Response<PaymentResponse>

    @GET("/api/fee-structures")
    suspend fun getFeeStructures(): Response<List<FeeStructure>>

    @GET("/api/discounts/pending")
    suspend fun getPendingDiscounts(): Response<List<PendingDiscount>>

    @POST("/api/discounts/action")
    suspend fun actionDiscount(@Body req: ActionDiscountRequest): Response<GenericResponse>

    @POST("/api/auth/verify-otp")
    suspend fun verifyOtp(@Body req: VerifyOtpRequest): Response<LoginResponse>

    @POST("/api/auth/change-pin")
    suspend fun changePin(@Body req: ChangePinRequest): Response<GenericResponse>

    @POST("/api/students/admit")
    suspend fun admitStudent(@Body req: StudentAdmissionSubmitRequest): Response<GenericResponse>

    @GET("/api/notifications/feed")
    suspend fun getNotificationsFeed(@Query("limit") limit: Int = 30): Response<NotificationFeedResponse>

    @GET("/api/reports/eod")
    suspend fun getEodReport(
        @Query("target_date") targetDate: String? = null,
        @Query("branch") branch: String? = "All"
    ): Response<EodReportResponse>

    @GET("/api/staff/list")
    suspend fun getStaffList(): Response<StaffListResponse>

    @POST("/api/devices/register")
    suspend fun registerDeviceToken(
        @Query("token") token: String,
        @Query("platform") platform: String = "android"
    ): Response<GenericResponse>
}
