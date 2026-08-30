package com.melamoud.tvtracker

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.core.view.WindowCompat
import com.melamoud.tvtracker.ui.nav.AppNav
import com.melamoud.tvtracker.ui.theme.TvTrackerTheme
import com.melamoud.tvtracker.widget.TrackerWidgetProvider
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private var oauthTokenState = mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        handleDeepLink(intent)
        val container = TvTrackerApp.from(this).container

        setContent {
            TvTrackerTheme {
                val scope = rememberCoroutineScope()
                var checking by remember { mutableStateOf(true) }
                var loggedIn by remember { mutableStateOf(false) }
                var username by remember { mutableStateOf<String?>(null) }
                var isAdmin by remember { mutableStateOf(false) }
                val oauthToken by oauthTokenState

                LaunchedEffect(Unit) {
                    val user = container.authRepository.restoreSession()
                    loggedIn = user != null
                    username = user?.username
                    isAdmin = user?.isAdmin ?: false
                    container.setUnreadAlerts(user?.unreadAlerts ?: 0)
                    if (user != null) TrackerWidgetProvider.requestRefresh(this@MainActivity)
                    checking = false
                }

                if (!checking) {
                    AppNav(
                        container = container,
                        loggedIn = loggedIn,
                        username = username,
                        isAdmin = isAdmin,
                        onOpenLoginUrl = ::openCustomTab,
                        onOauthToken = oauthToken,
                        onOauthConsumed = { oauthTokenState.value = null },
                        onLoggedIn = { name, admin, unreadCount ->
                            loggedIn = true
                            username = name
                            isAdmin = admin
                            container.setUnreadAlerts(unreadCount)
                            TrackerWidgetProvider.requestRefresh(this@MainActivity)
                        },
                        onLogout = {
                            scope.launch {
                                container.authRepository.logout()
                                loggedIn = false
                                username = null
                                isAdmin = false
                                container.setUnreadAlerts(0)
                            }
                        },
                    )
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleDeepLink(intent)
    }

    private fun handleDeepLink(intent: Intent?) {
        val data = intent?.data ?: return
        if (data.scheme != "tvtracker") return
        if (data.host == "oauth") {
            val token = data.getQueryParameter("token")
            if (!token.isNullOrBlank()) {
                oauthTokenState.value = token
            }
            return
        }
        if (data.host != "open") return
        val parts = data.pathSegments
        val dest = parts.getOrNull(0) ?: return
        val container = TvTrackerApp.from(this).container
        when (dest) {
            "detail" -> {
                val mediaType = parts.getOrNull(1)
                val traktId = parts.getOrNull(2)?.toIntOrNull()
                if (mediaType != null && traktId != null) {
                    container.requestOpen("detail", mediaType, traktId)
                }
            }
            "progress" -> {
                val traktId = parts.getOrNull(1)?.toIntOrNull()
                if (traktId != null) container.requestOpen("progress", "show", traktId)
            }
            "shows", "movies", "alerts", "search" -> container.requestOpen(dest)
        }
    }

    private fun openCustomTab(url: String) {
        CustomTabsIntent.Builder().build().launchUrl(this, Uri.parse(url))
    }
}
