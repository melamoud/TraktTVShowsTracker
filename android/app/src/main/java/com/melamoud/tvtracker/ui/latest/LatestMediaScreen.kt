package com.melamoud.tvtracker.ui.latest

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.melamoud.tvtracker.R
import com.melamoud.tvtracker.ui.components.CheckMenuItem
import com.melamoud.tvtracker.ui.components.ConfirmDialog
import com.melamoud.tvtracker.ui.components.FilterMenuButton
import com.melamoud.tvtracker.ui.components.FoundOnDialog
import com.melamoud.tvtracker.ui.components.ListsDialog
import com.melamoud.tvtracker.ui.components.MediaCard
import com.melamoud.tvtracker.ui.components.MoreFiltersButton
import com.melamoud.tvtracker.ui.components.RateDialog
import com.melamoud.tvtracker.ui.components.ReloadOnResume
import com.melamoud.tvtracker.ui.components.ServerRefreshBox
import com.melamoud.tvtracker.ui.theme.Danger
import com.melamoud.tvtracker.ui.theme.TextMuted

@Composable
fun LatestMediaScreen(
    viewModel: LatestMediaViewModel,
    baseUrl: String,
    isShows: Boolean,
    onOpenDetail: (String, Int) -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val availLabel = when (state.avail) {
        "upcoming" -> "Upcoming"
        "theater" -> "Theater"
        "streaming" -> "Streaming"
        else -> "Avail"
    }
    ReloadOnResume(viewModel::reload)

    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = state.query,
            onValueChange = viewModel::setQuery,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
            placeholder = { Text(stringResource(R.string.list_search_hint)) },
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
            trailingIcon = {
                IconButton(onClick = viewModel::reload) {
                    Icon(Icons.Default.Refresh, contentDescription = stringResource(R.string.refresh))
                }
            },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { viewModel.applyQuery() }),
        )
        val advancedCount = (if (state.perPage != 50) 1 else 0) +
            (if (state.year.isNotBlank()) 1 else 0) +
            state.genres.size
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FilterMenuButton(availLabel) { dismiss ->
                listOf("" to "Any", "upcoming" to "Upcoming", "theater" to "Theater", "streaming" to "Streaming")
                    .forEach { (id, label) ->
                        CheckMenuItem(label, state.avail == id) {
                            viewModel.setAvail(id)
                            dismiss()
                        }
                    }
            }
            BooleanFilterButton("Match only", state.matchOnly) { viewModel.setMatchOnly(it) }
            BooleanFilterButton("Recent years", state.recentYears) { viewModel.setRecentYears(it) }
            BooleanFilterButton("Hide watched", state.hideWatched) { viewModel.setHideWatched(it) }
            BooleanFilterButton("Hide lists", state.hideLists) { viewModel.setHideLists(it) }
            LatestActionsMenu(
                hasMarker = state.marker != null,
                hasMoreOlder = state.hasMoreOlder,
                markerPage = state.markerPage,
                onSync = viewModel::syncCatalog,
                onCaughtUp = viewModel::reviewMarkerCaughtUp,
                onClearMarker = viewModel::reviewMarkerClear,
                onLoadOlder = { viewModel.reload(loadOlder = true) },
                onJumpToMarker = viewModel::jumpToMarker,
            )
            MoreFiltersButton(advancedCount) {
                PerPageSection(state.perPage) { viewModel.setPerPage(it) }
                YearSection(state.year) { viewModel.setYear(it) }
                GenreSection(state.genres, state.genreChoices) { viewModel.toggleGenre(it) }
            }
        }
        state.marker?.let { marker ->
            Text(
                "Reviewed up to: ${marker.title}",
                color = TextMuted,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )
        }
        Text(
            "${state.total} titles · page ${state.page}/${state.pages}",
            color = TextMuted,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
        )
        ServerRefreshBox(
            isRefreshing = state.loading && state.items.isNotEmpty(),
            onRefresh = { viewModel.reload() },
            modifier = Modifier.weight(1f),
        ) {
            when {
                state.loading && state.items.isEmpty() ->
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                state.error != null && state.items.isEmpty() ->
                    Text(state.error ?: "", color = Danger, modifier = Modifier.padding(16.dp))
                state.items.isEmpty() ->
                    Text(stringResource(R.string.empty_list), color = TextMuted, modifier = Modifier.padding(24.dp))
                else -> LazyColumn(
                    contentPadding = PaddingValues(12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(state.items, key = { "${it.mediaType}-${it.traktId}" }) { item ->
                        val uriHandler = LocalUriHandler.current
                        val mt = item.mediaType ?: if (isShows) "show" else "movie"
                        MediaCard(
                            item = item,
                            baseUrl = baseUrl,
                            showProgress = isShows,
                            showPin = false,
                            setListsInline = true,
                            watchInOverflow = true,
                            hideRecommendationInline = true,
                            onPin = { viewModel.pin(item) },
                            onLists = { viewModel.openLists(item) },
                            onFoundOn = { viewModel.openFoundOn(item) },
                            onWatched = { viewModel.confirmWatch(item) },
                            onRate = { viewModel.openRate(item) },
                            onFavorite = { viewModel.favorite(item) },
                            onReviewMarker = { viewModel.reviewMarkerSet(item) },
                            onHideRecommendation = { viewModel.hideRecommendation(item) },
                            onImdb = item.imdbId?.let { { uriHandler.openUri("https://www.imdb.com/title/$it/") } },
                            onTrailer = item.trailerUrl?.let { { uriHandler.openUri(it) } },
                            onTrakt = { uriHandler.openUri("https://trakt.tv/${mt}s/${item.slug ?: item.traktId}") },
                            onOpen = { onOpenDetail(mt, item.traktId) },
                        )
                    }
                    if (state.pages > 1) {
                        item {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                TextButton(
                                    onClick = { viewModel.setPage(state.page - 1) },
                                    enabled = state.page > 1,
                                ) { Text("Previous") }
                                TextButton(
                                    onClick = { viewModel.setPage(state.page + 1) },
                                    enabled = state.page < state.pages,
                                ) { Text("Next") }
                            }
                        }
                    }
                }
            }
        }
    }
    state.watchConfirm?.let { item ->
        ConfirmDialog(
            title = if (item.watched) "Unwatch?" else "Mark watched?",
            message = if (isShows && !item.watched) {
                "This marks all aired episodes of ${item.title} watched on Trakt."
            } else {
                "${item.title} will sync to Trakt."
            },
            confirmLabel = if (item.watched) "Unwatch" else "Mark watched",
            onConfirm = viewModel::applyWatch,
            onDismiss = viewModel::dismissWatch,
        )
    }
    state.rateTarget?.let { item ->
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
    state.foundOnDialog?.let { dialog ->
        FoundOnDialog(
            selected = dialog.item.foundOn,
            choices = dialog.choices,
            choiceLinks = dialog.choiceLinks.ifEmpty { dialog.item.foundOnChoiceLinks },
            onApply = viewModel::applyFoundOn,
            onDismiss = viewModel::dismissFoundOn,
        )
    }
}

@Composable
private fun BooleanFilterButton(
    label: String,
    value: Boolean,
    onChange: (Boolean) -> Unit,
) {
    FilterMenuButton(if (value) "$label ✓" else label) { dismiss ->
        CheckMenuItem("On", value) { onChange(true); dismiss() }
        CheckMenuItem("Off", !value) { onChange(false); dismiss() }
    }
}

@Composable
private fun LatestActionsMenu(
    hasMarker: Boolean,
    hasMoreOlder: Boolean,
    markerPage: Int?,
    onSync: () -> Unit,
    onCaughtUp: () -> Unit,
    onClearMarker: () -> Unit,
    onLoadOlder: () -> Unit,
    onJumpToMarker: () -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        IconButton(onClick = { expanded = true }) {
            Icon(Icons.Default.MoreVert, contentDescription = stringResource(R.string.more))
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            DropdownMenuItem(
                text = { Text(stringResource(R.string.sync_catalog)) },
                onClick = { expanded = false; onSync() },
            )
            DropdownMenuItem(
                text = { Text("Load older catalog") },
                onClick = { expanded = false; onLoadOlder() },
                enabled = hasMoreOlder,
            )
            markerPage?.let { page ->
                DropdownMenuItem(
                    text = { Text("Jump to marker (page $page)") },
                    onClick = { expanded = false; onJumpToMarker() },
                )
            }
            DropdownMenuItem(
                text = { Text(stringResource(R.string.review_marker_caught_up)) },
                onClick = { expanded = false; onCaughtUp() },
            )
            if (hasMarker) {
                DropdownMenuItem(
                    text = { Text(stringResource(R.string.review_marker_clear)) },
                    onClick = { expanded = false; onClearMarker() },
                )
            }
        }
    }
}

@Composable
private fun PerPageSection(
    value: Int,
    onChange: (Int) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("Per page", style = MaterialTheme.typography.labelMedium, color = TextMuted)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(10, 50, 100).forEach { size ->
                FilterChip(
                    selected = value == size,
                    onClick = { onChange(size) },
                    label = { Text(size.toString()) },
                )
            }
        }
    }
}

@Composable
private fun YearSection(
    value: String,
    onChange: (String) -> Unit,
) {
    var text by remember(value) { mutableStateOf(value) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("Year", style = MaterialTheme.typography.labelMedium, color = TextMuted)
        OutlinedTextField(
            value = text,
            onValueChange = { text = it },
            label = { Text("Year or range") },
            placeholder = { Text("2018 or 2015-2020") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { onChange(text) }),
        )
        TextButton(onClick = { onChange(text) }, modifier = Modifier.align(Alignment.End)) {
            Text("Apply")
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun GenreSection(
    selected: List<String>,
    choices: List<String>,
    onToggle: (String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("Genres", style = MaterialTheme.typography.labelMedium, color = TextMuted)
        if (choices.isEmpty()) {
            Text("No genres available", color = TextMuted)
        } else {
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                choices.forEach { genre ->
                    val active = selected.contains(genre)
                    FilterChip(
                        selected = active,
                        onClick = { onToggle(genre) },
                        label = { Text(genre.replaceFirstChar { it.uppercase() }) },
                    )
                }
            }
        }
    }
}
