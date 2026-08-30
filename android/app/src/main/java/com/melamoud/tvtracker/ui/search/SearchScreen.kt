package com.melamoud.tvtracker.ui.search

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.melamoud.tvtracker.R
import com.melamoud.tvtracker.di.ActorSearchRequest
import com.melamoud.tvtracker.ui.components.CheckMenuItem
import com.melamoud.tvtracker.ui.components.ConfirmDialog
import com.melamoud.tvtracker.ui.components.FilterMenuButton
import com.melamoud.tvtracker.ui.components.FoundOnDialog
import com.melamoud.tvtracker.ui.components.ListsDialog
import com.melamoud.tvtracker.ui.components.MediaCard
import com.melamoud.tvtracker.ui.components.RateDialog
import com.melamoud.tvtracker.ui.components.ReloadOnResume
import com.melamoud.tvtracker.ui.components.ServerRefreshBox
import com.melamoud.tvtracker.ui.theme.Danger
import com.melamoud.tvtracker.ui.theme.TextMuted

@Composable
fun SearchScreen(
    viewModel: SearchViewModel,
    baseUrl: String,
    pendingActor: ActorSearchRequest?,
    onConsumeActor: () -> Unit,
    onProgress: (Int) -> Unit,
    onOpenDetail: (String, Int) -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(pendingActor) {
        if (pendingActor != null) {
            viewModel.searchActor(pendingActor.traktId, pendingActor.name)
            onConsumeActor()
        }
    }
    val typeLabel = when (state.type) {
        "movie" -> "Movies"
        "show" -> "Shows"
        else -> "Type"
    }
    val filterCount = listOf(state.hideWatched, state.hideLists).count { it } +
        (if (state.year.isNotBlank()) 1 else 0) + state.genres.size
    val filtersLabel = if (filterCount == 0) "Filters" else "Filters ($filterCount)"
    ReloadOnResume(viewModel::reloadFromServer)

    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = state.query,
            onValueChange = viewModel::onQuery,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
            placeholder = { Text(stringResource(R.string.search_hint)) },
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
            trailingIcon = {
                IconButton(onClick = viewModel::reloadFromServer) {
                    Icon(Icons.Default.Refresh, contentDescription = stringResource(R.string.refresh))
                }
            },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { viewModel.search() }),
        )
        if (state.actorName.isBlank()) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = state.actorSearchQuery,
                    onValueChange = viewModel::onActorQueryChange,
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("Search actor…") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { viewModel.searchActors() }),
                )
                IconButton(onClick = viewModel::searchActors) {
                    Icon(Icons.Default.Search, contentDescription = "Search actors")
                }
            }
            if (state.actorSearchResults.isNotEmpty()) {
                Row(
                    Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    state.actorSearchResults.forEach { person ->
                        FilterChip(
                            selected = false,
                            onClick = { viewModel.selectActor(person) },
                            label = { Text(person.name) },
                        )
                    }
                }
            }
            if (state.actorSearchLoading) {
                CircularProgressIndicator(modifier = Modifier.padding(horizontal = 16.dp))
            }
        }
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (state.actorName.isNotBlank()) {
                FilterChip(
                    selected = true,
                    onClick = viewModel::clearActor,
                    label = { Text("Actor: ${state.actorName}") },
                )
            }
            FilterMenuButton(typeLabel) { _ ->
                CheckMenuItem("Movies", state.type == "both" || state.type == "movie") {
                    viewModel.setType(
                        when (state.type) {
                            "both" -> "show"
                            "show" -> "both"
                            else -> "both"
                        }
                    )
                }
                CheckMenuItem("Shows", state.type == "both" || state.type == "show") {
                    viewModel.setType(
                        when (state.type) {
                            "both" -> "movie"
                            "movie" -> "both"
                            else -> "both"
                        }
                    )
                }
            }
            FilterMenuButton(filtersLabel) { _ ->
                CheckMenuItem("Not watched", state.hideWatched) { viewModel.setHideWatched(!state.hideWatched) }
                CheckMenuItem("Not in lists", state.hideLists) { viewModel.setHideLists(!state.hideLists) }
                OutlinedTextField(
                    value = state.year,
                    onValueChange = viewModel::setYear,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 4.dp),
                    label = { Text("Year or range") },
                    placeholder = { Text("2018 or 2015-2020") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { viewModel.applyYear() }),
                )
                state.genreChoices.forEach { label ->
                    CheckMenuItem(label.replaceFirstChar { it.uppercase() }, label in state.genres) {
                        viewModel.toggleGenre(label)
                    }
                }
            }
            OutlinedButton(
                onClick = viewModel::refreshFromTrakt,
                enabled = !state.loading && canSearch(state),
            ) { Text("Refresh Trakt") }
        }
        Text(
            "${state.total} results · page ${state.page}/${state.pages}",
            color = TextMuted,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
        )
        ServerRefreshBox(
            isRefreshing = state.loading && state.items.isNotEmpty(),
            onRefresh = viewModel::reloadFromServer,
            modifier = Modifier.weight(1f),
        ) {
            when {
                state.loading && state.items.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                state.error != null && state.items.isEmpty() -> Text(state.error ?: "", color = Danger, modifier = Modifier.padding(16.dp))
                state.items.isEmpty() -> Text(
                    if (state.actorId != null) "No titles found for this actor."
                    else stringResource(R.string.empty_search),
                    color = TextMuted,
                    modifier = Modifier.padding(24.dp),
                )
                else -> LazyColumn(contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(state.items, key = { "${it.mediaType}-${it.traktId}" }) { item ->
                        MediaCard(
                            item = item,
                            baseUrl = baseUrl,
                            showProgress = item.mediaType == "show",
                            onPin = { viewModel.pin(item) },
                            onLists = { viewModel.openLists(item) },
                            onFoundOn = { viewModel.openFoundOn(item) },
                            onWatched = { viewModel.confirmWatch(item) },
                            onRate = { viewModel.openRate(item) },
                            onFavorite = { viewModel.favorite(item) },
                            onProgress = if (item.mediaType == "show") ({ onProgress(item.traktId) }) else null,
                            onOpen = {
                                item.mediaType?.let { onOpenDetail(it, item.traktId) }
                            },
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
            message = item.title,
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

private fun canSearch(state: SearchUiState): Boolean =
    state.query.trim().length >= 2 || state.actorId != null
