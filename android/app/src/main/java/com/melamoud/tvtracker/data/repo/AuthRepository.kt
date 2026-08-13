package com.melamoud.tvtracker.data.repo

import com.google.gson.Gson
import com.melamoud.tvtracker.data.api.AuthLog
import com.melamoud.tvtracker.data.api.PersistentCookieJar
import com.melamoud.tvtracker.data.api.TvTrackerApi
import com.melamoud.tvtracker.data.api.dto.AuthCompleteRequest
import com.melamoud.tvtracker.data.api.dto.MeResponse
import com.melamoud.tvtracker.data.api.dto.UserDto
import com.melamoud.tvtracker.data.auth.SessionStore
import retrofit2.HttpException

class AuthRepository(
    private val api: TvTrackerApi,
    private val sessionStore: SessionStore,
    private val cookieJar: PersistentCookieJar,
) {
    suspend fun restoreSession(): UserDto? {
        if (!sessionStore.isLoggedIn()) return null
        return try {
            val me = api.me()
            val user = me.user
            if (me.success && user != null) {
                sessionStore.save(user.username, user.csrfToken)
                user
            } else {
                cookieJar.clear()
                sessionStore.clear()
                null
            }
        } catch (_: Exception) {
            cookieJar.clear()
            sessionStore.clear()
            null
        }
    }

    suspend fun startLogin(): Result<String> {
        return try {
            val resp = api.authStart()
            val url = resp.authorizeUrl
            if (resp.success && !url.isNullOrBlank()) {
                Result.success(url)
            } else {
                Result.failure(IllegalStateException(resp.message ?: "Could not start Trakt login"))
            }
        } catch (e: Exception) {
            AuthLog.e("auth start failed", e)
            Result.failure(IllegalStateException(AuthLog.userMessage(e)))
        }
    }

    suspend fun completeLogin(token: String): Result<UserDto> {
        AuthLog.i("auth complete token_len=${token.length}")
        return try {
            val response = api.authComplete(AuthCompleteRequest(token))
            val user = response.user
            if (response.success && user != null) {
                sessionStore.save(user.username, user.csrfToken)
                AuthLog.i("login success username='${user.username}' id=${user.id}")
                Result.success(user)
            } else {
                Result.failure(IllegalStateException(response.message ?: "Login failed"))
            }
        } catch (e: HttpException) {
            val raw = try { e.response()?.errorBody()?.string() } catch (_: Exception) { null }
            val parsed = try {
                raw?.let { Gson().fromJson(it, MeResponse::class.java)?.message }
            } catch (_: Exception) { null }
            Result.failure(IllegalStateException(parsed ?: AuthLog.userMessage(e, raw)))
        } catch (e: Exception) {
            AuthLog.e("auth complete failed", e)
            Result.failure(IllegalStateException(AuthLog.userMessage(e)))
        }
    }

    suspend fun logout() {
        try {
            api.logout()
        } catch (_: Exception) {
        }
        cookieJar.clear()
        sessionStore.clear()
    }
}
