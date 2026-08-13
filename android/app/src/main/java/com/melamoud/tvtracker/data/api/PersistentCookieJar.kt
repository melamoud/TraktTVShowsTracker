package com.melamoud.tvtracker.data.api

import android.content.Context
import android.content.SharedPreferences
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl

class PersistentCookieJar(context: Context) : CookieJar {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("tvtracker_cookies", Context.MODE_PRIVATE)
    private val lock = Any()

    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        synchronized(lock) {
            val stored = loadAll().toMutableMap()
            cookies.forEach { cookie ->
                val key = "${cookie.domain}|${cookie.path}|${cookie.name}"
                if (cookie.expiresAt < System.currentTimeMillis()) {
                    stored.remove(key)
                } else {
                    stored[key] = cookie.toString()
                }
            }
            prefs.edit().putStringSet("cookies", stored.values.toSet()).apply()
        }
    }

    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        synchronized(lock) {
            val now = System.currentTimeMillis()
            val valid = mutableListOf<Cookie>()
            val kept = mutableMapOf<String, String>()
            loadAll().forEach { (key, value) ->
                val cookie = Cookie.parse(url, value) ?: return@forEach
                if (cookie.expiresAt < now) return@forEach
                if (cookie.matches(url)) {
                    valid += cookie
                }
                kept[key] = value
            }
            prefs.edit().putStringSet("cookies", kept.values.toSet()).apply()
            return valid
        }
    }

    fun clear() {
        synchronized(lock) {
            prefs.edit().remove("cookies").apply()
        }
    }

    private fun loadAll(): Map<String, String> {
        val out = mutableMapOf<String, String>()
        prefs.getStringSet("cookies", emptySet())?.forEach { raw ->
            val dummy = HttpUrl.Builder().scheme("https").host("tvtracker.melamoud.com").build()
            val cookie = Cookie.parse(dummy, raw) ?: return@forEach
            val key = "${cookie.domain}|${cookie.path}|${cookie.name}"
            out[key] = raw
        }
        return out
    }
}
