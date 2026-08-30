package com.melamoud.tvtracker.ui.detail

import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import com.melamoud.tvtracker.R
import com.melamoud.tvtracker.data.api.absoluteUrl
import com.melamoud.tvtracker.data.api.dto.CastMemberDto
import com.melamoud.tvtracker.data.api.dto.MediaDetailResponse
import com.melamoud.tvtracker.data.api.dto.MediaItemDto
import com.melamoud.tvtracker.ui.components.ConfirmDialog
import com.melamoud.tvtracker.ui.components.FoundOnDialog
import com.melamoud.tvtracker.ui.components.ListsDialog
import com.melamoud.tvtracker.ui.components.RateDialog
import com.melamoud.tvtracker.ui.components.ReloadOnResume
import com.melamoud.tvtracker.ui.components.ReviewDialog
import com.melamoud.tvtracker.ui.components.ServerRefreshBox
import com.melamoud.tvtracker.ui.components.ServiceLinksLine
import com.melamoud.tvtracker.ui.theme.AccentGold
import com.melamoud.tvtracker.ui.theme.Ok
import com.melamoud.tvtracker.ui.theme.Primary
import com.melamoud.tvtracker.ui.theme.SurfaceAlt
import com.melamoud.tvtracker.ui.theme.TextMuted

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun DetailScreen(
    viewModel: DetailViewModel,
    baseUrl: String,
    onBack: () -> Unit,
    onProgress: (Int) -> Unit,
    onActorTitles: (Int, String) -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val detail = state.detail
    val item = detail?.item
    ReloadOnResume(viewModel::reload)
    val uriHandler = LocalUriHandler.current

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text(item?.title ?: "Title") },
            navigationIcon = {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                }
            },
            actions = {
                IconButton(onClick = viewModel::reload) {
                    Icon(Icons.Default.Refresh, contentDescription = stringResource(R.string.refresh))
                }
            },
        )
        ServerRefreshBox(
            isRefreshing = state.loading && detail != null,
            onRefresh = viewModel::reload,
            modifier = Modifier.weight(1f),
        ) {
            when {
                state.loading && detail == null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
                state.error != null && detail == null -> Column(
                    Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(state.error ?: "")
                    OutlinedButton(onClick = viewModel::reload) { Text("Retry") }
                }
                detail != null && item != null -> LazyColumn(
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    item {
                        DetailHero(item, detail, baseUrl)
                    }
                    item {
                        DetailActions(
                            item = item,
                            mediaType = item.mediaType,
                            traktUrl = detail.traktUrl,
                            imdbUrl = detail.imdbUrl,
                            homepage = detail.homepage,
                            onLists = viewModel::openLists,
                            onRate = viewModel::openRate,
                            onFavorite = viewModel::favorite,
                            onReview = viewModel::openReview,
                            onWatch = viewModel::confirmWatch,
                            onFoundOn = viewModel::openFoundOn,
                            onHideRecommendation = viewModel::hideRecommendation,
                            onProgress = {
                                if (item.mediaType == "show") onProgress(item.traktId)
                            },
                            onOpenUrl = { url ->
                                try {
                                    uriHandler.openUri(url)
                                } catch (_: Exception) {
                                }
                            },
                        )
                    }
                    if (detail.cast.isNotEmpty()) {
                        val limit = detail.mainCastLimit
                        val visible = if (state.showAllCast) detail.cast else detail.cast.take(limit)
                        item {
                            Text("Cast", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        }
                        items(visible, key = { it.traktId }) { actor ->
                            CastRow(
                                actor = actor,
                                baseUrl = baseUrl,
                                onFavorite = { viewModel.toggleFavoriteActor(actor) },
                                onTitles = { onActorTitles(actor.traktId, actor.name) },
                            )
                        }
                        if (detail.cast.size > limit) {
                            item {
                                TextButton(onClick = viewModel::toggleCast) {
                                    Text(
                                        if (state.showAllCast) "Show fewer"
                                        else "Show all ${detail.cast.size} actors",
                                    )
                                }
                            }
                        }
                        item {
                            Text(
                                "Favorite actors are saved in Preferences (local — not Trakt favorites).",
                                color = TextMuted,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }
            }
        }
    }

    if (state.watchConfirm && item != null) {
        ConfirmDialog(
            title = if (item.watched) "Unwatch?" else "Mark watched?",
            message = if (item.mediaType == "show" && !item.watched) {
                "This marks all aired episodes of ${item.title} watched on Trakt."
            } else {
                "${item.title} will sync to Trakt."
            },
            confirmLabel = if (item.watched) "Unwatch" else "Mark watched",
            onConfirm = viewModel::applyWatch,
            onDismiss = viewModel::dismissWatch,
        )
    }
    if (state.rateOpen && item != null) {
        RateDialog(current = item.rating, onSave = viewModel::applyRate, onDismiss = viewModel::dismissRate)
    }
    state.listsDialog?.let { dialog ->
        ListsDialog(
            title = dialog.item.title,
            lists = dialog.lists,
            defaults = dialog.defaults,
            onApply = viewModel::applyLists,
            onDismiss = viewModel::dismissLists,
        )
    }
    if (state.foundOnOpen && detail != null && item != null) {
        FoundOnDialog(
            selected = item.foundOn,
            choices = detail.foundOnChoices,
            choiceLinks = item.foundOnChoiceLinks,
            onApply = viewModel::applyFoundOn,
            onDismiss = viewModel::dismissFoundOn,
        )
    }
    state.review?.let { review ->
        ReviewDialog(
            loading = review.loading,
            error = review.error,
            comment = review.comment,
            spoiler = review.spoiler,
            onSave = viewModel::applyReview,
            onDismiss = viewModel::dismissReview,
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DetailHero(item: MediaItemDto, detail: MediaDetailResponse, baseUrl: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        AsyncImage(
            model = absoluteUrl(baseUrl, item.posterUrl),
            contentDescription = item.title,
            contentScale = ContentScale.Crop,
            modifier = Modifier
                .width(120.dp)
                .height(180.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(MaterialTheme.colorScheme.surface),
        )
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                listOfNotNull(item.title, item.year?.toString()?.let { "($it)" }).joinToString(" "),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
            )
            val meta = buildList {
                detail.traktListedAt?.take(10)?.let { add("Trakt DB: $it") }
                detail.releasedAt?.take(10)?.let { add("Released: $it") }
                item.network?.takeIf { it.isNotBlank() }?.let { add(it) }
                item.runtime?.let { add("$it min") }
            }
            if (meta.isNotEmpty()) {
                Text(meta.joinToString(" · "), color = TextMuted, style = MaterialTheme.typography.bodySmall)
            }
            if (item.genres.isNotEmpty()) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    item.genres.forEach { g -> TagChip(g) }
                }
            }
        }
    }
    if (!item.overview.isNullOrBlank()) {
        Text(item.overview, style = MaterialTheme.typography.bodyMedium)
    } else {
        Text("No description available from Trakt yet.", color = TextMuted)
    }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        val match = detail.match
        if (match?.matched == true) TagChip("Preference match", gold = true)
        match?.genres.orEmpty().forEach { TagChip(it, gold = true) }
        match?.keywords.orEmpty().forEach { TagChip(it, gold = true) }
        if (item.onWatchlist) TagChip("Watchlist")
        item.listNames.forEach { TagChip(it) }
        if (item.watched) TagChip("Watched", ok = true)
        item.rating?.let { TagChip("$it/10") }
        if (item.favorited) TagChip("Favorite", gold = true)
    }
    if (item.myProviders.isNotEmpty() || item.myProviderLinks.isNotEmpty()) {
        ServiceLinksLine(
            prefix = "Plays on your services:",
            links = item.myProviderLinks,
            fallbackLabels = item.myProviders,
        )
    }
    val otherPrefix = if (item.myProviders.isNotEmpty()) "Also streaming:" else "Streaming:"
    if (item.otherProviders.isNotEmpty() || item.otherProviderLinks.isNotEmpty()) {
        ServiceLinksLine(
            prefix = otherPrefix,
            links = item.otherProviderLinks,
            fallbackLabels = item.otherProviders,
            color = TextMuted,
        )
    } else if (item.myProviders.isEmpty()) {
        Text("No subscription streaming listed", color = TextMuted, style = MaterialTheme.typography.bodySmall)
    }
    if (item.foundOn.isNotEmpty() || item.foundOnLinks.isNotEmpty()) {
        ServiceLinksLine(
            prefix = "Found on:",
            links = item.foundOnLinks,
            fallbackLabels = item.foundOn,
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DetailActions(
    item: MediaItemDto,
    mediaType: String?,
    traktUrl: String?,
    imdbUrl: String?,
    homepage: String?,
    onLists: () -> Unit,
    onRate: () -> Unit,
    onFavorite: () -> Unit,
    onReview: () -> Unit,
    onWatch: () -> Unit,
    onFoundOn: () -> Unit,
    onHideRecommendation: () -> Unit,
    onProgress: () -> Unit,
    onOpenUrl: (String) -> Unit,
) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        ActionBtn("Set lists…", onClick = onLists)
        ActionBtn(if (item.rating != null) "Rate ${item.rating}/10" else "Rate…", onClick = onRate)
        ActionBtn(if (item.favorited) "Unfavorite" else "Favorite", onClick = onFavorite)
        ActionBtn("Write review…", onClick = onReview)
        ActionBtn(if (item.watched) "Unwatch" else "Mark watched", onClick = onWatch)
        ActionBtn("Found on…", onClick = onFoundOn)
        ActionBtn("Hide recommendation", onClick = onHideRecommendation)
        if (mediaType == "show") {
            ActionBtn("Series progress", primary = true, onClick = onProgress)
        }
        imdbUrl?.let { url -> ActionBtn("IMDb") { onOpenUrl(url) } }
        item.trailerUrl?.takeIf { it.isNotBlank() }?.let { url -> ActionBtn("Trailer") { onOpenUrl(url) } }
        homepage?.takeIf { it.isNotBlank() }?.let { url -> ActionBtn("Homepage") { onOpenUrl(url) } }
        traktUrl?.let { url -> ActionBtn("Trakt") { onOpenUrl(url) } }
    }
}

@Composable
private fun ActionBtn(label: String, primary: Boolean = false, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        contentPadding = PaddingValues(horizontal = 12.dp),
        modifier = Modifier.height(36.dp),
    ) {
        Text(label, color = if (primary) AccentGold else Primary)
    }
}

@Composable
private fun TagChip(label: String, gold: Boolean = false, ok: Boolean = false) {
    val color = when {
        gold -> AccentGold
        ok -> Ok
        else -> Primary
    }
    Text(
        label,
        color = color,
        style = MaterialTheme.typography.labelMedium,
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(color.copy(alpha = 0.14f))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    )
}

@Composable
private fun CastRow(
    actor: CastMemberDto,
    baseUrl: String,
    onFavorite: () -> Unit,
    onTitles: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val headshot = absoluteUrl(baseUrl, actor.headshotUrl)
        if (headshot != null) {
            AsyncImage(
                model = headshot,
                contentDescription = actor.name,
                contentScale = ContentScale.Crop,
                modifier = Modifier.size(40.dp).clip(CircleShape),
            )
        } else {
            Box(
                Modifier.size(40.dp).clip(CircleShape).background(SurfaceAlt),
                contentAlignment = Alignment.Center,
            ) {
                Text(actor.name.take(1).uppercase(), color = Primary, fontWeight = FontWeight.SemiBold)
            }
        }
        Column(Modifier.weight(1f)) {
            Text(actor.name, fontWeight = FontWeight.SemiBold)
            if (actor.characters.isNotEmpty()) {
                Text(actor.characters.joinToString(), color = TextMuted, style = MaterialTheme.typography.bodySmall)
            }
            actor.episodeCount?.let {
                Text("$it ep${if (it == 1) "" else "s"}", color = TextMuted, style = MaterialTheme.typography.bodySmall)
            }
        }
        TextButton(onClick = onFavorite) {
            Text(if (actor.favorited) "★ Favorite" else "☆ Favorite", color = if (actor.favorited) AccentGold else Primary)
        }
        TextButton(onClick = onTitles) { Text("Titles") }
    }
}
