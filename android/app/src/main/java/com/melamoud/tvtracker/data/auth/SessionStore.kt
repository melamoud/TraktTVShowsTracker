package com.melamoud.tvtracker.data.auth

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "tvtracker_session")

class SessionStore(private val context: Context) {
    private val usernameKey = stringPreferencesKey("username")
    private val csrfKey = stringPreferencesKey("csrf_token")

    val username: Flow<String?> = context.dataStore.data.map { it[usernameKey] }

    suspend fun username(): String? = context.dataStore.data.first()[usernameKey]

    suspend fun csrfToken(): String? = context.dataStore.data.first()[csrfKey]

    suspend fun isLoggedIn(): Boolean = !username().isNullOrBlank()

    suspend fun save(username: String, csrfToken: String?) {
        context.dataStore.edit { prefs ->
            prefs[usernameKey] = username
            if (csrfToken.isNullOrBlank()) {
                prefs.remove(csrfKey)
            } else {
                prefs[csrfKey] = csrfToken
            }
        }
    }

    suspend fun clear() {
        context.dataStore.edit { it.clear() }
    }
}
