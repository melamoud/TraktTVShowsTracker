package com.melamoud.tvtracker.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
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

@OptIn(ExperimentalLayoutApi::class)
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
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = SurfaceAlt),
        shape = RoundedCornerShape(12.dp),
    ) {
        Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            AsyncImage(
                model = absoluteUrl(baseUrl, item.posterUrl),
                contentDescription = item.title,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .width(84.dp)
                    .height(126.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(MaterialTheme.colorScheme.surface),
            )
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    listOfNotNull(item.title, item.year?.toString()).joinToString(" · "),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                if (item.listNames.isNotEmpty()) {
                    Text(item.listNames.joinToString(" · "), color = Primary, style = MaterialTheme.typography.bodySmall)
                }
                if (showProgress) {
                    val aired = item.episodesAired
                    val done = item.episodesCompleted
                    if (aired != null && done != null) {
                        Text("$done / $aired episodes watched", color = Ok, style = MaterialTheme.typography.bodySmall)
                    }
                    val next = item.nextEp
                    if (next != null) {
                        val line = listOfNotNull(
                            next.label?.let { "Next: $it" },
                            next.title,
                            next.date,
                        ).joinToString(" · ")
                        if (line.isNotBlank()) {
                            Text(line, color = TextMuted, style = MaterialTheme.typography.bodySmall)
                        }
                    } else if (item.nextEpisodeSeason != null && item.nextEpisodeNumber != null) {
                        Text(
                            "Next: S${item.nextEpisodeSeason}E${item.nextEpisodeNumber}" +
                                (item.nextEpisodeTitle?.let { " — $it" } ?: ""),
                            color = TextMuted,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
                if (!item.overview.isNullOrBlank()) {
                    Text(
                        item.overview,
                        color = TextMuted,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    item.availChips.forEach { chip ->
                        AssistChip(onClick = {}, label = { Text(chip.label ?: chip.kind.orEmpty()) })
                    }
                    if (item.watched) AssistChip(onClick = {}, label = { Text("Watched") })
                    if (item.favorited) AssistChip(onClick = {}, label = { Text("Favorite") })
                    item.rating?.let { AssistChip(onClick = {}, label = { Text("$it/10") }) }
                    if (item.pinned) AssistChip(onClick = {}, label = { Text("Pinned") })
                }
                if (item.myProviders.isNotEmpty()) {
                    Text("On your services: ${item.myProviders.joinToString()}", color = Primary, style = MaterialTheme.typography.bodySmall)
                } else if (item.otherProviders.isNotEmpty()) {
                    Text("Streaming: ${item.otherProviders.take(4).joinToString()}", color = TextMuted, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        FlowRow(
            modifier = Modifier.padding(start = 8.dp, end = 8.dp, bottom = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            TextButton(onClick = onPin) { Text(if (item.pinned) "Unpin" else "Pin") }
            TextButton(onClick = onLists) { Text("Set lists…") }
            TextButton(onClick = onWatched) { Text(if (item.watched) "Unwatch" else "Mark watched") }
            TextButton(onClick = onRate) { Text(if (item.rating != null) "Rate ${item.rating}" else "Rate…") }
            TextButton(onClick = onFavorite) { Text(if (item.favorited) "Unfavorite" else "Favorite") }
            if (onProgress != null) {
                OutlinedButton(onClick = onProgress) { Text("Progress", color = AccentGold) }
            }
        }
    }
}
