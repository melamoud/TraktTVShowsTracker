package com.melamoud.tvtracker.ui.admin

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.melamoud.tvtracker.data.api.dto.AdminUserDto
import com.melamoud.tvtracker.ui.theme.SurfaceAlt
import com.melamoud.tvtracker.ui.theme.TextMuted

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AdminScreen(viewModel: AdminViewModel, onBack: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var confirmDelete by remember { mutableStateOf<AdminUserDto?>(null) }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(title = { Text("Admin") }, navigationIcon = { TextButton(onClick = onBack) { Text("Back") } })
        LazyColumn(
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            modifier = Modifier.fillMaxSize(),
        ) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = SurfaceAlt),
                ) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("Dashboard", style = MaterialTheme.typography.titleMedium)
                        StatRow("Users", state.stats.users.toString())
                        StatRow("Active users", state.stats.activeUsers.toString())
                        StatRow("Pending suggestions", state.stats.pendingSuggestions.toString())
                        StatRow("Services", state.stats.services.toString())
                        StatRow("Alert events", state.stats.alertEvents.toString())
                        StatRow("TMDB configured", if (state.stats.tmdbConfigured) "Yes" else "No")
                    }
                }
            }
            item {
                Button(
                    onClick = viewModel::runReleaseCheck,
                    enabled = !state.actionBusy,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Run release check now") }
            }
            item {
                if (state.scheduler.isNotBlank()) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = SurfaceAlt),
                    ) {
                        Column(Modifier.padding(12.dp).verticalScroll(rememberScrollState())) {
                            Text("Scheduler", style = MaterialTheme.typography.titleMedium)
                            Text(state.scheduler, color = TextMuted, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
            item { Text("Users", style = MaterialTheme.typography.titleMedium) }
            items(state.users, key = { it.id }) { user ->
                UserCard(
                    user = user,
                    busy = state.actionBusy,
                    onToggleActive = { viewModel.toggleActive(user.id) },
                    onToggleAdmin = { viewModel.toggleAdmin(user.id) },
                    onRevoke = { viewModel.revokeSessions(user.id) },
                    onDelete = { confirmDelete = user },
                )
            }
            if (state.loading && state.users.isEmpty()) {
                item { CircularProgressIndicator(modifier = Modifier.padding(24.dp).align(Alignment.CenterHorizontally)) }
            }
            state.error?.let { item { Text(it, color = androidx.compose.ui.graphics.Color.Red, modifier = Modifier.padding(12.dp)) } }
            state.actionMessage?.let { item { Text(it, modifier = Modifier.padding(12.dp)) } }
        }
    }

    confirmDelete?.let { user ->
        AlertDialog(
            onDismissRequest = { confirmDelete = null },
            title = { Text("Delete ${user.username}?") },
            text = { Text("This removes local data only. The Trakt account is unchanged.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmDelete = null
                        viewModel.deleteLocal(user.id)
                    },
                ) { Text("Delete", color = androidx.compose.ui.graphics.Color.Red) }
            },
            dismissButton = { TextButton(onClick = { confirmDelete = null }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun StatRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = TextMuted)
        Text(value)
    }
}

@Composable
private fun UserCard(
    user: AdminUserDto,
    busy: Boolean,
    onToggleActive: () -> Unit,
    onToggleAdmin: () -> Unit,
    onRevoke: () -> Unit,
    onDelete: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(user.username, style = MaterialTheme.typography.titleSmall)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = user.isActiveAccount, enabled = !busy, onCheckedChange = { onToggleActive() })
                Text("Active", modifier = Modifier.weight(1f))
                Checkbox(checked = user.isAdmin, enabled = !busy, onCheckedChange = { onToggleAdmin() })
                Text("Admin")
            }
            HorizontalDivider()
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = onRevoke, enabled = !busy) { Text("Revoke sessions") }
                OutlinedButton(onClick = onDelete, enabled = !busy) { Text("Delete local") }
            }
        }
    }
}
