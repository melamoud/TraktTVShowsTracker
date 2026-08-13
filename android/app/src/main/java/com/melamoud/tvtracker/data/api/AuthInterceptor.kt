package com.melamoud.tvtracker.data.api

import com.melamoud.tvtracker.data.auth.SessionStore
import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.Response

class AuthInterceptor(
    private val sessionStore: SessionStore,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        val builder = original.newBuilder()
            .header("Accept", "application/json")
            .header("X-Requested-With", "XMLHttpRequest")
            .header("X-TVTracker-Client", "android")

        val method = original.method
        if (method != "GET" && method != "HEAD") {
            val csrf = runBlocking { sessionStore.csrfToken() }
            if (!csrf.isNullOrBlank()) {
                builder.header("X-CSRFToken", csrf)
            }
        }
        return chain.proceed(builder.build())
    }
}

class SessionCaptureInterceptor(
    private val sessionStore: SessionStore,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val response = chain.proceed(chain.request())
        if (response.code == 401) {
            runBlocking { sessionStore.clear() }
        }
        return response
    }
}

fun absoluteUrl(baseUrl: String, path: String?): String? {
    if (path.isNullOrBlank()) return null
    if (path.startsWith("http://") || path.startsWith("https://")) return path
    return baseUrl.trimEnd('/') + if (path.startsWith("/")) path else "/$path"
}
