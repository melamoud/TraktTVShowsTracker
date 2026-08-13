package com.melamoud.tvtracker.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.melamoud.tvtracker.data.api.absoluteUrl
import com.melamoud.tvtracker.data.api.dto.MediaItemDto
import com.melamoud.tvtracker.ui.theme.AccentGold
import com.melamoud.tvtracker.ui.theme.Ok
import com.melamoud.tvtracker.ui.theme.Primary
import com.melamoud.tvtracker.ui.theme.SurfaceAlt
import com.melamoud.tvtracker.ui.theme.TextMuted

@Composable
fun MediaCard(
    item: MediaItemDto,
    baseUrl: String,
    showProgress: Boolean,
    onPin: () -> Unit,
    onLists: () -> Unit,
    onWatched: () -> Unit,
    onRate: () -> Unit,
    onFavorite: () -> Unit,
    onProgress: (() -> Unit)? = null,
) {
    var menuOpen by remember { mutableStateOf(false) }
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = SurfaceAlt),
        shape = RoundedCornerShape(10.dp),
    ) {
        Row(Modifier.padding(10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            AsyncImage(
                model = absoluteUrl(baseUrl, item.posterUrl),
                contentDescription = item.title,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .width(64.dp)
                    .height(96.dp)
                    .clip(RoundedCornerShape(6.dp))
                    .background(MaterialTheme.colorScheme.surface),
            )
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    listOfNotNull(item.title, item.year?.toString()).joinToString(" · "),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                val meta = buildList {
                    if (item.listNames.isNotEmpty()) add(item.listNames.joinToString(", "))
                    if (item.watched) add("Watched")
                    item.rating?.let { add("$it/10") }
                    if (item.favorited) add("Favorite")
                    if (item.pinned) add("Pinned")
                    item.availChips.forEach { chip -> add(chip.label ?: chip.kind.orEmpty()) }
                }.filter { it.isNotBlank() }
                if (meta.isNotEmpty()) {
                    Text(
                        meta.joinToString(" · "),
                        color = Primary,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (showProgress) {
                    val aired = item.episodesAired
                    val done = item.episodesCompleted
                    val next = item.nextEp
                    val progressBits = buildList {
                        if (aired != null && done != null) add("$done/$aired eps")
                        if (next != null) {
                            add(listOfNotNull(next.label, next.title).joinToString(" "))
                        } else if (item.nextEpisodeSeason != null && item.nextEpisodeNumber != null) {
                            add("S${item.nextEpisodeSeason}E${item.nextEpisodeNumber}")
                        }
                    }
                    if (progressBits.isNotEmpty()) {
                        Text(progressBits.joinToString(" · "), color = Ok, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                if (!item.overview.isNullOrBlank()) {
                    Text(
                        item.overview,
                        color = TextMuted,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                val providers = item.myProviders.ifEmpty { item.otherProviders.take(3) }
                if (providers.isNotEmpty()) {
                    Text(
                        (if (item.myProviders.isNotEmpty()) "On your services: " else "Streaming: ") +
                            providers.joinToString(),
                        color = if (item.myProviders.isNotEmpty()) Primary else TextMuted,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Row(
                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    if (onProgress != null) {
                        OutlinedButton(
                            onClick = onProgress,
                            contentPadding = PaddingValues(horizontal = 10.dp),
                            modifier = Modifier.height(32.dp),
                        ) { Text("Progress", color = AccentGold) }
                    }
                    OutlinedButton(
                        onClick = onWatched,
                        contentPadding = PaddingValues(horizontal = 10.dp),
                        modifier = Modifier.height(32.dp),
                    ) { Text(if (item.watched) "Unwatch" else "Watch") }
                    IconButton(onClick = { menuOpen = true }, modifier = Modifier.height(32.dp)) {
                        Icon(Icons.Default.MoreVert, contentDescription = "More")
                    }
                    DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                        DropdownMenuItem(
                            text = { Text(if (item.pinned) "Unpin" else "Pin") },
                            onClick = { menuOpen = false; onPin() },
                        )
                        DropdownMenuItem(
                            text = { Text("Set lists…") },
                            onClick = { menuOpen = false; onLists() },
                        )
                        DropdownMenuItem(
                            text = { Text(if (item.rating != null) "Rate ${item.rating}/10" else "Rate…") },
                            onClick = { menuOpen = false; onRate() },
                        )
                        DropdownMenuItem(
                            text = { Text(if (item.favorited) "Unfavorite" else "Favorite") },
                            onClick = { menuOpen = false; onFavorite() },
                        )
                    }
                }
            }
        }
    }
}
