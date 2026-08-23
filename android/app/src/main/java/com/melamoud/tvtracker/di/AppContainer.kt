package com.melamoud.tvtracker.di

import android.content.Context
import android.util.Log
import coil.ImageLoader
import com.melamoud.tvtracker.BuildConfig
import com.melamoud.tvtracker.data.api.AuthInterceptor
import com.melamoud.tvtracker.data.api.AuthLog
import com.melamoud.tvtracker.data.api.PersistentCookieJar
import com.melamoud.tvtracker.data.api.SessionCaptureInterceptor
import com.melamoud.tvtracker.data.api.TvTrackerApi
import com.melamoud.tvtracker.data.api.buildSslConfig
import com.melamoud.tvtracker.data.auth.SessionStore
import com.melamoud.tvtracker.data.repo.AuthRepository
import com.melamoud.tvtracker.data.repo.CatalogRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

data class ActorSearchRequest(val traktId: Int, val name: String)

data class PendingOpen(
    val dest: String,
    val mediaType: String? = null,
    val traktId: Int? = null,
)

class AppContainer(context: Context) {
    val baseUrl: String = BuildConfig.BASE_URL.trimEnd('/')
    val sessionStore = SessionStore(context)
    val cookieJar = PersistentCookieJar(context)

    val okHttpClient: OkHttpClient = run {
        val ssl = buildSslConfig(context, "tvtracker.melamoud.com")
        OkHttpClient.Builder()
            .cookieJar(cookieJar)
            .sslSocketFactory(ssl.socketFactory, ssl.trustManager)
            .hostnameVerifier(ssl.hostnameVerifier)
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(90, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .addInterceptor(AuthInterceptor(sessionStore))
            .addInterceptor(SessionCaptureInterceptor(sessionStore))
            .addInterceptor(
                HttpLoggingInterceptor { message ->
                    Log.i(AuthLog.HTTP_TAG, message)
                }.apply {
                    level = if (BuildConfig.DEBUG) {
                        HttpLoggingInterceptor.Level.BASIC
                    } else {
                        HttpLoggingInterceptor.Level.HEADERS
                    }
                }
            )
            .build()
    }

    val imageLoader: ImageLoader = ImageLoader.Builder(context)
        .okHttpClient(okHttpClient)
        .crossfade(true)
        .build()

    private val api: TvTrackerApi = Retrofit.Builder()
        .baseUrl("$baseUrl/")
        .client(okHttpClient)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
        .create(TvTrackerApi::class.java)

    val authRepository = AuthRepository(api, sessionStore, cookieJar)
    val catalogRepository = CatalogRepository(api)

    private val _unreadAlerts = MutableStateFlow(0)
    val unreadAlerts: StateFlow<Int> = _unreadAlerts.asStateFlow()

    fun setUnreadAlerts(count: Int) {
        _unreadAlerts.value = count.coerceAtLeast(0)
    }

    private val _pendingActorSearch = MutableStateFlow<ActorSearchRequest?>(null)
    val pendingActorSearch: StateFlow<ActorSearchRequest?> = _pendingActorSearch.asStateFlow()

    fun requestActorSearch(traktId: Int, name: String) {
        _pendingActorSearch.value = ActorSearchRequest(traktId, name)
    }

    fun consumePendingActorSearch() {
        _pendingActorSearch.value = null
    }

    private val _pendingOpen = MutableStateFlow<PendingOpen?>(null)
    val pendingOpen: StateFlow<PendingOpen?> = _pendingOpen.asStateFlow()

    fun requestOpen(dest: String, mediaType: String? = null, traktId: Int? = null) {
        _pendingOpen.value = PendingOpen(dest, mediaType, traktId)
    }

    fun consumePendingOpen() {
        _pendingOpen.value = null
    }
}
