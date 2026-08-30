package com.melamoud.tvtracker.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import com.melamoud.tvtracker.ui.theme.Danger
import com.melamoud.tvtracker.ui.theme.Ok
import com.melamoud.tvtracker.ui.theme.Primary
import com.melamoud.tvtracker.ui.theme.Surface
import com.melamoud.tvtracker.ui.theme.SurfaceAlt
import com.melamoud.tvtracker.ui.theme.TextMuted

@Composable
fun MediaCard(
    item: MediaItemDto,
    baseUrl: String,
    showProgress: Boolean,
    showNewestAired: Boolean = false,
    showPin: Boolean = true,
    setListsInline: Boolean = false,
    watchInOverflow: Boolean = false,
    hideRecommendationInline: Boolean = false,
    onPin: () -> Unit,
    onLists: () -> Unit,
    onFoundOn: () -> Unit,
    onWatched: () -> Unit,
    onRate: () -> Unit,
    onFavorite: () -> Unit,
    onProgress: (() -> Unit)? = null,
    onReviewMarker: (() -> Unit)? = null,
    onHideRecommendation: (() -> Unit)? = null,
    onImdb: (() -> Unit)? = null,
    onTrailer: (() -> Unit)? = null,
    onTrakt: (() -> Unit)? = null,
    onOpen: (() -> Unit)? = null,
) {
    var menuOpen by remember { mutableStateOf(false) }
    Card(
        modifier = Modifier.fillMaxWidth().then(
            if (onOpen != null) Modifier.clickable(onClick = onOpen) else Modifier
        ),
        colors = CardDefaults.cardColors(
            containerColor = if (item.olderThanMarker) Surface else SurfaceAlt,
        ),
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
                    val progressBits = buildList {
                        if (aired != null && done != null) add("$done/$aired eps")
                        nextEpisodeLine(item)?.let { add(it) }
                    }
                    if (progressBits.isNotEmpty()) {
                        Text(progressBits.joinToString(" · "), color = Ok, style = MaterialTheme.typography.bodySmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    }
                }
                if (showNewestAired) {
                    val newestLine = newestAiredLine(item)
                    if (newestLine != null) {
                        Text(newestLine, color = AccentGold, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                if (item.foundOn.isNotEmpty() || item.foundOnLinks.isNotEmpty()) {
                    ServiceLinksLine(
                        prefix = "Found on:",
                        links = item.foundOnLinks,
                        fallbackLabels = item.foundOn,
                    )
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
                if (item.myProviders.isNotEmpty() || item.myProviderLinks.isNotEmpty()) {
                    ServiceLinksLine(
                        prefix = "On your services:",
                        links = item.myProviderLinks,
                        fallbackLabels = item.myProviders,
                    )
                } else if (item.otherProviders.isNotEmpty() || item.otherProviderLinks.isNotEmpty()) {
                    ServiceLinksLine(
                        prefix = "Streaming:",
                        links = item.otherProviderLinks.take(3),
                        fallbackLabels = item.otherProviders.take(3),
                        color = TextMuted,
                    )
                }
                Row(
                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    if (setListsInline) {
                        OutlinedButton(
                            onClick = onLists,
                            contentPadding = PaddingValues(horizontal = 10.dp),
                            modifier = Modifier.height(32.dp),
                        ) { Text("Set lists") }
                    }
                    if (onProgress != null) {
                        OutlinedButton(
                            onClick = onProgress,
                            contentPadding = PaddingValues(horizontal = 10.dp),
                            modifier = Modifier.height(32.dp),
                        ) { Text("Progress", color = AccentGold) }
                    }
                    if (!watchInOverflow) {
                        OutlinedButton(
                            onClick = onWatched,
                            contentPadding = PaddingValues(horizontal = 10.dp),
                            modifier = Modifier.height(32.dp),
                        ) { Text(if (item.watched) "Unwatch" else "Watch") }
                    }
                    if (hideRecommendationInline && onHideRecommendation != null) {
                        OutlinedButton(
                            onClick = onHideRecommendation,
                            contentPadding = PaddingValues(horizontal = 10.dp),
                            modifier = Modifier.height(32.dp),
                        ) { Text("Hide", color = Danger) }
                    }
                    IconButton(onClick = { menuOpen = true }, modifier = Modifier.height(32.dp)) {
                        Icon(Icons.Default.MoreVert, contentDescription = "More")
                    }
                    DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                        if (watchInOverflow) {
                            DropdownMenuItem(
                                text = { Text(if (item.watched) "Unwatch" else "Watch") },
                                onClick = { menuOpen = false; onWatched() },
                            )
                        }
                        if (showPin) {
                            DropdownMenuItem(
                                text = { Text(if (item.pinned) "Unpin" else "Pin") },
                                onClick = { menuOpen = false; onPin() },
                            )
                        }
                        if (!setListsInline) {
                            DropdownMenuItem(
                                text = { Text("Set lists…") },
                                onClick = { menuOpen = false; onLists() },
                            )
                        }
                        DropdownMenuItem(
                            text = { Text("Found on…") },
                            onClick = { menuOpen = false; onFoundOn() },
                        )
                        DropdownMenuItem(
                            text = { Text(if (item.rating != null) "Rate ${item.rating}/10" else "Rate…") },
                            onClick = { menuOpen = false; onRate() },
                        )
                        DropdownMenuItem(
                            text = { Text(if (item.favorited) "Unfavorite" else "Favorite") },
                            onClick = { menuOpen = false; onFavorite() },
                        )
                        if (onReviewMarker != null) {
                            DropdownMenuItem(
                                text = { Text("Reviewed older than this") },
                                onClick = { menuOpen = false; onReviewMarker() },
                            )
                        }
                        if (onHideRecommendation != null && !hideRecommendationInline) {
                            DropdownMenuItem(
                                text = { Text("Hide recommendation") },
                                onClick = { menuOpen = false; onHideRecommendation() },
                            )
                        }
                        if (onImdb != null) {
                            DropdownMenuItem(
                                text = { Text("IMDb") },
                                onClick = { menuOpen = false; onImdb() },
                            )
                        }
                        if (onTrailer != null) {
                            DropdownMenuItem(
                                text = { Text("Trailer") },
                                onClick = { menuOpen = false; onTrailer() },
                            )
                        }
                        if (onTrakt != null) {
                            DropdownMenuItem(
                                text = { Text("Trakt") },
                                onClick = { menuOpen = false; onTrakt() },
                            )
                        }
                    }
                }
            }
        }
    }
}

private fun dayPrefix(raw: String?): String? =
    raw?.take(10)?.takeIf { it.length == 10 }

private fun nextEpisodeLine(item: MediaItemDto): String? {
    val next = item.nextEp
    val label = next?.label
        ?: item.nextEpisodeSeason?.let { s ->
            item.nextEpisodeNumber?.let { e -> "S${s}E${e}" }
        }
        ?: return null
    val title = next?.title ?: item.nextEpisodeTitle
    val day = dayPrefix(next?.date)
    return buildString {
        append("Next: ")
        append(label)
        if (!title.isNullOrBlank()) append(" — ").append(title)
        if (day != null) append(" · ").append(day)
    }
}

private fun newestAiredLine(item: MediaItemDto): String? {
    return if (item.mediaType == "movie") {
        dayPrefix(item.avail?.releasedAt)?.let { "Released: $it" }
    } else {
        val aired = dayPrefix(item.lastEpisodeAiredAt) ?: return null
        listOfNotNull("Latest aired: $aired", item.lastEpisodeLabel).joinToString(" · ")
    }
}
