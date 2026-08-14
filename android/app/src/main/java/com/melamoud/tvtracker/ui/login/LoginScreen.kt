package com.melamoud.tvtracker.ui.login

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Tv
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.melamoud.tvtracker.R
import com.melamoud.tvtracker.ui.theme.Background
import com.melamoud.tvtracker.ui.theme.Danger
import com.melamoud.tvtracker.ui.theme.Primary
import com.melamoud.tvtracker.ui.theme.TextMuted

@Composable
fun LoginScreen(
    viewModel: LoginViewModel,
    onOpenUrl: (String) -> Unit,
    onLoggedIn: (String, Int) -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(state.loggedIn, state.username, state.unreadAlerts) {
        if (state.loggedIn) onLoggedIn(state.username.orEmpty(), state.unreadAlerts)
    }
    LaunchedEffect(state.authorizeUrl) {
        val url = state.authorizeUrl ?: return@LaunchedEffect
        onOpenUrl(url)
        viewModel.consumeAuthorizeUrl()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Background)
            .systemBarsPadding()
            .verticalScroll(rememberScrollState()),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(Primary)
                .padding(horizontal = 24.dp, vertical = 28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(Icons.Default.Tv, contentDescription = null, tint = Background, modifier = Modifier.size(40.dp))
            Spacer(Modifier.height(8.dp))
            Text(
                stringResource(R.string.login_title),
                color = Background,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center,
            )
            Text(
                stringResource(R.string.login_subtitle),
                color = Background.copy(alpha = 0.85f),
                style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center,
            )
        }

        Card(
            modifier = Modifier.padding(20.dp).fillMaxWidth(),
            elevation = CardDefaults.cardElevation(8.dp),
            shape = RoundedCornerShape(8.dp),
        ) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.login_help), color = TextMuted, style = MaterialTheme.typography.bodyMedium)
                state.error?.let {
                    Surface(color = Danger.copy(alpha = 0.12f), shape = RoundedCornerShape(6.dp), modifier = Modifier.fillMaxWidth()) {
                        Text(it, color = Danger, modifier = Modifier.padding(12.dp))
                    }
                }
                Button(
                    onClick = viewModel::startLogin,
                    enabled = !state.loading,
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Primary),
                ) {
                    if (state.loading) {
                        CircularProgressIndicator(color = Background, modifier = Modifier.size(22.dp), strokeWidth = 2.dp)
                    } else {
                        Text(stringResource(R.string.login_with_trakt))
                    }
                }
            }
        }
    }
}
