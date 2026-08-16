package com.melamoud.tvtracker.ui.alerts

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import com.melamoud.tvtracker.R
import com.melamoud.tvtracker.data.api.absoluteUrl
import com.melamoud.tvtracker.data.api.dto.AlertItemDto
import com.melamoud.tvtracker.ui.components.ReloadOnResume
import com.melamoud.tvtracker.ui.components.ServerRefreshBox
import com.melamoud.tvtracker.ui.components.ServiceLinksLine
import com.melamoud.tvtracker.ui.theme.AccentGold
import com.melamoud.tvtracker.ui.theme.SurfaceAlt
import com.melamoud.tvtracker.ui.theme.TextMuted

@Composable
fun AlertsScreen(
    viewModel: AlertsViewModel,
    baseUrl: String,
    onProgress: (Int) -> Unit,
    onOpenDetail: (String, Int) -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    ReloadOnResume(viewModel::reload)
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FilterChip(
                selected = state.hideRead,
                onClick = { viewModel.setHideRead(!state.hideRead) },
                label = { Text(if (state.hideRead) "Hide read" else "Show read") },
            )
            TextButton(onClick = viewModel::readAll) { Text("Mark all read") }
            Text("${state.unreadCount} unread", color = TextMuted, modifier = Modifier.weight(1f))
            IconButton(onClick = viewModel::reload) {
                Icon(Icons.Default.Refresh, contentDescription = stringResource(R.string.refresh))
            }
        }
        ServerRefreshBox(
            isRefreshing = state.loading && state.items.isNotEmpty(),
            onRefresh = viewModel::reload,
            modifier = Modifier.weight(1f),
        ) {
            when {
                state.loading && state.items.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                state.error != null && state.items.isEmpty() -> Text(state.error ?: "", modifier = Modifier.padding(16.dp))
                state.items.isEmpty() -> Text(stringResource(R.string.empty_alerts), color = TextMuted, modifier = Modifier.padding(24.dp))
                else -> LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    items(state.items, key = { it.id }) { item ->
                        Card(
                            colors = CardDefaults.cardColors(containerColor = SurfaceAlt),
                            modifier = Modifier
                                .alpha(if (item.isRead) 0.55f else 1f)
                                .then(
                                    if (item.mediaType != null && item.traktId != null) {
                                        Modifier.clickable { onOpenDetail(item.mediaType, item.traktId) }
                                    } else Modifier
                                ),
                        ) {
                            Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                AsyncImage(
                                    model = absoluteUrl(baseUrl, item.posterUrl),
                                    contentDescription = item.title,
                                    contentScale = ContentScale.Crop,
                                    modifier = Modifier.width(64.dp).height(96.dp).clip(RoundedCornerShape(6.dp)),
                                )
                                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                    Text(item.typeLabel.orEmpty(), color = AccentGold, style = MaterialTheme.typography.labelMedium)
                                    Text(
                                        item.mediaTitle?.takeIf { it.isNotBlank() } ?: item.title,
                                        fontWeight = FontWeight.SemiBold,
                                    )
                                    if (!item.message.isNullOrBlank()) {
                                        Text(item.message, color = TextMuted, style = MaterialTheme.typography.bodySmall)
                                    }
                                    lastAiredLine(item)?.let { line ->
                                        Text(line, color = AccentGold, style = MaterialTheme.typography.bodySmall)
                                    }
                                    if (item.foundOn.isNotEmpty() || item.foundOnLinks.isNotEmpty()) {
                                        ServiceLinksLine(
                                            prefix = "Found on:",
                                            links = item.foundOnLinks,
                                            fallbackLabels = item.foundOn,
                                        )
                                    }
                                    if (item.myProviders.isNotEmpty() || item.myProviderLinks.isNotEmpty()) {
                                        ServiceLinksLine(
                                            prefix = "Plays on your services:",
                                            links = item.myProviderLinks,
                                            fallbackLabels = item.myProviders,
                                        )
                                    }
                                    if (item.otherProviders.isNotEmpty() || item.otherProviderLinks.isNotEmpty()) {
                                        ServiceLinksLine(
                                            prefix = if (item.myProviders.isNotEmpty()) "Also streaming:" else "Streaming:",
                                            links = item.otherProviderLinks,
                                            fallbackLabels = item.otherProviders,
                                            color = TextMuted,
                                        )
                                    }
                                    item.createdAt?.let { Text(it, color = TextMuted, style = MaterialTheme.typography.bodySmall) }
                                    Row {
                                        TextButton(onClick = { viewModel.toggleRead(item) }) {
                                            Text(if (item.isRead) "Mark unread" else "Mark read")
                                        }
                                        if (item.mediaType == "show" && item.traktId != null) {
                                            OutlinedButton(onClick = { onProgress(item.traktId) }) { Text("Progress") }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun lastAiredLine(item: AlertItemDto): String? {
    val day = item.lastEpisodeAiredAt?.take(10)?.takeIf { it.length == 10 }
    val label = item.lastEpisodeLabel?.takeIf { it.isNotBlank() }
    if (day == null && label == null) return null
    return listOfNotNull("Latest aired", label, day).joinToString(" · ")
}
