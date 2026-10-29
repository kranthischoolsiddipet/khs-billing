package com.kranthischool.khsbilling.data

import android.content.Context
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Response
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {
    private var retrofit: Retrofit? = null
    private var cachedBaseUrl: String? = null

    class AuthInterceptor(private val sessionManager: SessionManager) : Interceptor {
        override fun intercept(chain: Interceptor.Chain): Response {
            val original = chain.request()
            val token = sessionManager.getToken()

            val requestBuilder = original.newBuilder()
            if (!token.isNullOrBlank()) {
                requestBuilder.header("Authorization", "Bearer $token")
            }
            requestBuilder.header("Accept", "application/json")
            requestBuilder.header("Content-Type", "application/json")

            return chain.proceed(requestBuilder.build())
        }
    }

    fun getService(context: Context): KhsApiService {
        val sessionManager = SessionManager(context)
        val currentBaseUrl = sessionManager.baseUrl.let { if (it.endsWith("/")) it else "$it/" }

        if (retrofit == null || cachedBaseUrl != currentBaseUrl) {
            val logging = HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BODY
            }

            val okHttpClient = OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)
                .addInterceptor(AuthInterceptor(sessionManager))
                .addInterceptor(logging)
                .build()

            retrofit = Retrofit.Builder()
                .baseUrl(currentBaseUrl)
                .client(okHttpClient)
                .addConverterFactory(GsonConverterFactory.create())
                .build()

            cachedBaseUrl = currentBaseUrl
        }

        return retrofit!!.create(KhsApiService::class.java)
    }

    fun resetClient() {
        retrofit = null
        cachedBaseUrl = null
    }
}
