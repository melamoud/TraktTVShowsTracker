package com.melamoud.tvtracker.ui.media

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
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.melamoud.tvtracker.R
import com.melamoud.tvtracker.ui.components.CheckMenuItem
import com.melamoud.tvtracker.ui.components.ConfirmDialog
import com.melamoud.tvtracker.ui.components.FilterMenuButton
import com.melamoud.tvtracker.ui.components.ListsDialog
import com.melamoud.tvtracker.ui.components.MediaCard
import com.melamoud.tvtracker.ui.components.RateDialog
import com.melamoud.tvtracker.ui.theme.Danger
import com.melamoud.tvtracker.ui.theme.TextMuted

@Composable
fun MyMediaScreen(
    viewModel: MyMediaViewModel,
    baseUrl: String,
    isShows: Boolean,
    onProgress: (Int) -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val statusOptions = statusChoices(isShows)
    val statusLabel = statusOptions.firstOrNull { it.first == state.filter }?.second ?: "Status"
    val availLabel = when (state.avail) {
        "upcoming" -> "Upcoming"
        "theater" -> "Theater"
        "streaming" -> "Streaming"
        else -> "Avail"
    }
    val viewLabel = if (state.display == "newest_aired") "Newest" else "List"
    val listsSelected = state.filterLists.count { it.selected }
    val listsLabel = if (listsSelected == 0) "Lists" else "Lists ($listsSelected)"

    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = state.query,
            onValueChange = viewModel::setQuery,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
            placeholder = { Text(stringResource(R.string.list_search_hint)) },
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
            trailingIcon = {
                IconButton(onClick = { viewModel.reload(refresh = true) }) {
                    Icon(Icons.Default.Refresh, contentDescription = stringResource(R.string.refresh))
                }
            },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { viewModel.applyQuery() }),
        )
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FilterMenuButton(statusLabel) { dismiss ->
                statusOptions.forEach { (id, label) ->
                    CheckMenuItem(label, state.filter == id) {
                        viewModel.setFilter(id)
                        dismiss()
                    }
                }
            }
            if (state.filterLists.isNotEmpty()) {
                FilterMenuButton(listsLabel) { _ ->
                    state.filterLists.forEach { lst ->
                        CheckMenuItem(lst.name, lst.selected) { viewModel.toggleList(lst.id) }
                    }
                }
            }
            FilterMenuButton(availLabel) { dismiss ->
                listOf("" to "Any", "upcoming" to "Upcoming", "theater" to "Theater", "streaming" to "Streaming")
                    .forEach { (id, label) ->
                        CheckMenuItem(label, state.avail == id) {
                            viewModel.setAvail(id)
                            dismiss()
                        }
                    }
            }
            FilterMenuButton(viewLabel) { dismiss ->
                CheckMenuItem("List", state.display == "list") {
                    viewModel.setDisplay("list")
                    dismiss()
                }
                CheckMenuItem("Newest aired", state.display == "newest_aired") {
                    viewModel.setDisplay("newest_aired")
                    dismiss()
                }
            }
        }
        Text(
            "${state.total} titles · page ${state.page}/${state.pages}",
            color = TextMuted,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
        )
        when {
            state.loading && state.items.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            state.error != null && state.items.isEmpty() -> Text(state.error ?: "", color = Danger, modifier = Modifier.padding(16.dp))
            state.items.isEmpty() -> Text(stringResource(R.string.empty_list), color = TextMuted, modifier = Modifier.padding(24.dp))
            else -> LazyColumn(contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(state.items, key = { "${it.mediaType}-${it.traktId}" }) { item ->
                    MediaCard(
                        item = item,
                        baseUrl = baseUrl,
                        showProgress = isShows,
                        onPin = { viewModel.pin(item) },
                        onLists = { viewModel.openLists(item) },
                        onWatched = { viewModel.confirmWatch(item) },
                        onRate = { viewModel.openRate(item) },
                        onFavorite = { viewModel.favorite(item) },
                        onProgress = if (isShows) ({ onProgress(item.traktId) }) else null,
                    )
                }
                if (state.pages > 1) {
                    item {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            TextButton(onClick = { viewModel.setPage(state.page - 1) }, enabled = state.page > 1) { Text("Previous") }
                            TextButton(onClick = { viewModel.setPage(state.page + 1) }, enabled = state.page < state.pages) { Text("Next") }
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
}

private fun statusChoices(isShows: Boolean): List<Pair<String, String>> {
    return if (isShows) {
        listOf("lists" to "Both", "watched" to "Watched", "unwatched_episodes" to "Unwatched eps")
    } else {
        listOf("lists" to "Both", "watched" to "Watched", "unwatched" to "Unwatched")
    }
}
