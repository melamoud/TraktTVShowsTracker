package com.melamoud.tvtracker.ui.alerts

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.PushPin
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.outlined.PushPin
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import com.melamoud.tvtracker.R
import com.melamoud.tvtracker.data.api.absoluteUrl
import com.melamoud.tvtracker.data.api.dto.AlertEntryDto
import com.melamoud.tvtracker.data.api.dto.AlertItemDto
import com.melamoud.tvtracker.ui.components.ReloadOnResume
import com.melamoud.tvtracker.ui.components.ServerRefreshBox
import com.melamoud.tvtracker.ui.components.ServiceLinksLine
import com.melamoud.tvtracker.ui.theme.AccentGold
import com.melamoud.tvtracker.ui.theme.SurfaceAlt
import com.melamoud.tvtracker.ui.theme.TextMuted

@OptIn(ExperimentalLayoutApi::class)
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
            Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FilterChip(
                selected = state.hideRead,
                onClick = { viewModel.setHideRead(!state.hideRead) },
                label = { Text(if (state.hideRead) "Hide read" else "Show read") },
            )
            FilterChip(
                selected = state.sort == "desc",
                onClick = { viewModel.setSort(if (state.sort == "desc") "asc" else "desc") },
                label = { Text(if (state.sort == "desc") "Newest first" else "Oldest first") },
            )
            FilterChip(
                selected = state.groupShows,
                onClick = { viewModel.setGroupShows(!state.groupShows) },
                label = { Text(if (state.groupShows) "Grouped by show" else "One row each") },
            )
            TextButton(onClick = viewModel::readAll) { Text("Mark all read") }
            Text("${state.unreadCount} unread", color = TextMuted)
            IconButton(onClick = viewModel::reload) {
                Icon(Icons.Default.Refresh, contentDescription = stringResource(R.string.refresh))
            }
        }
        ServerRefreshBox(
            isRefreshing = state.loading && state.entries.isNotEmpty(),
            onRefresh = viewModel::reload,
            modifier = Modifier.weight(1f),
        ) {
            when {
                state.loading && state.entries.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                state.error != null && state.entries.isEmpty() -> Text(state.error ?: "", modifier = Modifier.padding(16.dp))
                state.entries.isEmpty() -> Text(stringResource(R.string.empty_alerts), color = TextMuted, modifier = Modifier.padding(24.dp))
                else -> LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    state.entries.forEach { entry ->
                        if (entry.kind == "group") {
                            val key = "show-${entry.traktId}"
                            val expanded = key in state.expandedKeys
                            item(key = key) {
                                AlertGroupCard(
                                    entry = entry,
                                    baseUrl = baseUrl,
                                    expanded = expanded,
                                    onToggle = { viewModel.toggleExpanded(key) },
                                    onPin = {
                                        val id = entry.traktId ?: return@AlertGroupCard
                                        viewModel.pin("show", id, !entry.alertsPinned)
                                    },
                                    onProgress = { entry.traktId?.let(onProgress) },
                                    onOpenDetail = { entry.traktId?.let { onOpenDetail("show", it) } },
                                )
                            }
                            if (expanded) {
                                items(entry.items, key = { "child-${it.id}" }) { item ->
                                    AlertItemCard(
                                        item = item,
                                        baseUrl = baseUrl,
                                        nested = true,
                                        onProgress = onProgress,
                                        onOpenDetail = onOpenDetail,
                                        onToggleRead = { viewModel.toggleRead(item) },
                                        onPin = {
                                            val mt = item.mediaType
                                            val id = item.traktId
                                            if (mt != null && id != null) {
                                                viewModel.pin(mt, id, !item.alertsPinned)
                                            }
                                        },
                                    )
                                }
                            }
                        } else {
                            val single = entry.item ?: return@forEach
                            item(key = "n-${single.id}") {
                                AlertItemCard(
                                    item = single,
                                    baseUrl = baseUrl,
                                    nested = false,
                                    onProgress = onProgress,
                                    onOpenDetail = onOpenDetail,
                                    onToggleRead = { viewModel.toggleRead(single) },
                                    onPin = {
                                        val mt = single.mediaType
                                        val id = single.traktId
                                        if (mt != null && id != null) {
                                            viewModel.pin(mt, id, !single.alertsPinned)
                                        }
                                    },
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun AlertGroupCard(
    entry: AlertEntryDto,
    baseUrl: String,
    expanded: Boolean,
    onToggle: () -> Unit,
    onPin: () -> Unit,
    onProgress: () -> Unit,
    onOpenDetail: () -> Unit,
) {
    val dimmed = entry.unreadCount == 0
    Card(
        colors = CardDefaults.cardColors(containerColor = SurfaceAlt),
        modifier = Modifier
            .alpha(if (dimmed) 0.55f else 1f)
            .clickable(onClick = onToggle),
    ) {
        Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            AlertPoster(baseUrl, entry.posterUrl, entry.title ?: "", entry.kindLabel ?: "Show")
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        entry.title ?: "Show",
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier
                            .weight(1f, fill = false)
                            .clickable(onClick = onOpenDetail),
                    )
                    if (entry.episodeCodes.isNotEmpty()) {
                        Text(
                            entry.episodeCodes.joinToString(" · "),
                            color = AccentGold,
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.titleSmall,
                        )
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (entry.unreadCount > 0) {
                        Text("${entry.unreadCount} unread", color = AccentGold, style = MaterialTheme.typography.labelMedium)
                    }
                    Text(
                        if (expanded) "Tap to hide ${entry.items.size} alerts" else "Tap to show ${entry.items.size} alerts",
                        color = TextMuted,
                        style = MaterialTheme.typography.labelMedium,
                    )
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedButton(onClick = onToggle) {
                        Icon(
                            if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                            contentDescription = null,
                        )
                        Text(if (expanded) "Hide alerts" else "Show ${entry.items.size} alerts")
                    }
                    OutlinedButton(onClick = onProgress) { Text("Progress") }
                    TextButton(onClick = onPin) {
                        Icon(
                            if (entry.alertsPinned) Icons.Filled.PushPin else Icons.Outlined.PushPin,
                            contentDescription = if (entry.alertsPinned) "Unpin" else "Pin",
                            modifier = Modifier.padding(end = 4.dp),
                        )
                        Text(if (entry.alertsPinned) "Unpin" else "Pin")
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AlertItemCard(
    item: AlertItemDto,
    baseUrl: String,
    nested: Boolean,
    onProgress: (Int) -> Unit,
    onOpenDetail: (String, Int) -> Unit,
    onToggleRead: () -> Unit,
    onPin: () -> Unit,
) {
    val title = item.displayTitle?.takeIf { it.isNotBlank() }
        ?: listOfNotNull(
            item.mediaTitle?.takeIf { it.isNotBlank() } ?: item.title.takeIf { it.isNotBlank() },
            item.episodeCode?.takeIf { it.isNotBlank() },
        ).joinToString(" ").ifBlank { item.title }
    Card(
        colors = CardDefaults.cardColors(containerColor = SurfaceAlt),
        modifier = Modifier
            .padding(start = if (nested) 20.dp else 0.dp)
            .alpha(if (item.isRead) 0.55f else 1f)
            .then(
                if (item.mediaType != null && item.traktId != null) {
                    Modifier.clickable { onOpenDetail(item.mediaType, item.traktId) }
                } else Modifier
            ),
    ) {
        Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            if (!nested) {
                AlertPoster(baseUrl, item.posterUrl, title, item.kindLabel)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(title, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f, fill = false))
                    if (!item.episodeCode.isNullOrBlank() && title.contains(item.episodeCode).not()) {
                        Text(item.episodeCode, color = AccentGold, fontWeight = FontWeight.Bold)
                    }
                    if (!item.typeLabel.isNullOrBlank()) {
                        Text(item.typeLabel, color = AccentGold, style = MaterialTheme.typography.labelMedium)
                    }
                }
                val headline = item.headline?.takeIf { it.isNotBlank() }
                if (headline != null) {
                    Text(headline, color = TextMuted, style = MaterialTheme.typography.bodySmall)
                }
                if (item.otherProviders.isNotEmpty() || item.otherProviderLinks.isNotEmpty()) {
                    ServiceLinksLine(
                        prefix = if (item.myProviders.isNotEmpty()) "Also streaming:" else "Streaming:",
                        links = item.otherProviderLinks,
                        fallbackLabels = item.otherProviders,
                        color = TextMuted,
                    )
                }
                if (
                    item.foundOn.isNotEmpty() || item.foundOnLinks.isNotEmpty() ||
                    item.myProviders.isNotEmpty() || item.myProviderLinks.isNotEmpty()
                ) {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        if (item.myProviders.isNotEmpty() || item.myProviderLinks.isNotEmpty()) {
                            ServiceLinksLine(
                                prefix = "Plays on your services:",
                                links = item.myProviderLinks,
                                fallbackLabels = item.myProviders,
                            )
                        }
                        if (item.foundOn.isNotEmpty() || item.foundOnLinks.isNotEmpty()) {
                            ServiceLinksLine(
                                prefix = "Found on:",
                                links = item.foundOnLinks,
                                fallbackLabels = item.foundOn,
                            )
                        }
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = onToggleRead) {
                        Text(if (item.isRead) "Mark unread" else "Mark read")
                    }
                    if (item.mediaType == "show" && item.traktId != null) {
                        OutlinedButton(onClick = { onProgress(item.traktId) }) { Text("Progress") }
                    }
                    if (item.mediaType != null && item.traktId != null) {
                        TextButton(onClick = onPin) {
                            Icon(
                                if (item.alertsPinned) Icons.Filled.PushPin else Icons.Outlined.PushPin,
                                contentDescription = if (item.alertsPinned) "Unpin" else "Pin",
                                modifier = Modifier.padding(end = 4.dp),
                            )
                            Text(if (item.alertsPinned) "Unpin" else "Pin")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun AlertPoster(
    baseUrl: String,
    posterUrl: String?,
    title: String,
    kindLabel: String?,
) {
    Box {
        AsyncImage(
            model = absoluteUrl(baseUrl, posterUrl),
            contentDescription = title,
            contentScale = ContentScale.Crop,
            modifier = Modifier
                .width(64.dp)
                .height(96.dp)
                .clip(RoundedCornerShape(6.dp)),
        )
        if (!kindLabel.isNullOrBlank()) {
            Text(
                kindLabel,
                color = Color.White,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
                modifier = Modifier
                    .padding(4.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(Color(0xCC0B1220))
                    .padding(horizontal = 5.dp, vertical = 2.dp),
            )
        }
    }
}
