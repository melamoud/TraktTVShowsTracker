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
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private var oauthTokenState = mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        handleOauthIntent(intent)
        val container = TvTrackerApp.from(this).container

        setContent {
            TvTrackerTheme {
                val scope = rememberCoroutineScope()
                var checking by remember { mutableStateOf(true) }
                var loggedIn by remember { mutableStateOf(false) }
                var username by remember { mutableStateOf<String?>(null) }
                val oauthToken by oauthTokenState

                LaunchedEffect(Unit) {
                    val user = container.authRepository.restoreSession()
                    loggedIn = user != null
                    username = user?.username
                    container.setUnreadAlerts(user?.unreadAlerts ?: 0)
                    checking = false
                }

                if (!checking) {
                    AppNav(
                        container = container,
                        loggedIn = loggedIn,
                        username = username,
                        onOpenLoginUrl = ::openCustomTab,
                        onOauthToken = oauthToken,
                        onOauthConsumed = { oauthTokenState.value = null },
                        onLoggedIn = { name, unreadCount ->
                            loggedIn = true
                            username = name
                            container.setUnreadAlerts(unreadCount)
                        },
                        onLogout = {
                            scope.launch {
                                container.authRepository.logout()
                                loggedIn = false
                                username = null
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
        handleOauthIntent(intent)
    }

    private fun handleOauthIntent(intent: Intent?) {
        val data = intent?.data ?: return
        if (data.scheme == "tvtracker" && data.host == "oauth") {
            val token = data.getQueryParameter("token")
            if (!token.isNullOrBlank()) {
                oauthTokenState.value = token
            }
        }
    }

    private fun openCustomTab(url: String) {
        CustomTabsIntent.Builder().build().launchUrl(this, Uri.parse(url))
    }
}
