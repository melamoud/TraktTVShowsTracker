package com.melamoud.tvtracker.data.api

import android.util.Log
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLHandshakeException
import javax.net.ssl.SSLPeerUnverifiedException
import retrofit2.HttpException

object AuthLog {
    const val TAG = "TVTrackerAuth"
    const val HTTP_TAG = "TVTrackerHttp"

    fun i(message: String) = Log.i(TAG, message)
    fun w(message: String) = Log.w(TAG, message)
    fun e(message: String, error: Throwable? = null) = Log.e(TAG, message, error)

    fun userMessage(error: Throwable, body: String? = null): String {
        return when (error) {
            is HttpException -> httpMessage(error, body)
            is SSLHandshakeException, is SSLPeerUnverifiedException ->
                "Cannot complete a secure connection to the server (TLS). ${error.message ?: ""}".trim()
            is UnknownHostException ->
                "Cannot resolve tvtracker.melamoud.com. Check DNS / Wi-Fi."
            is SocketTimeoutException ->
                "Timed out reaching the server on port 8300."
            is ConnectException ->
                "Cannot connect to https://tvtracker.melamoud.com:8300"
            else -> {
                val cause = error.cause
                if (cause != null && cause !== error) {
                    "${error.javaClass.simpleName}: ${error.message ?: "Request failed"} (${cause.javaClass.simpleName}: ${cause.message})"
                } else {
                    "${error.javaClass.simpleName}: ${error.message ?: "Request failed"}"
                }
            }
        }
    }

    private fun httpMessage(error: HttpException, body: String?): String {
        val text = body.orEmpty()
        val looksHtml = text.contains("<html", ignoreCase = true) || text.contains("Page Not Found", ignoreCase = true)
        return when {
            error.code() == 404 || looksHtml ->
                "Server does not have /api/v1 yet (HTTP ${error.code()}). Restart the Flask server, then try again."
            error.code() == 401 ->
                "Login required. Sign in with Trakt again."
            error.code() == 429 ->
                "Trakt is rate-limiting right now. Wait a few seconds and retry."
            else ->
                "Request failed (HTTP ${error.code()}). ${text.take(180).ifBlank { error.message() }}"
        }
    }
}
