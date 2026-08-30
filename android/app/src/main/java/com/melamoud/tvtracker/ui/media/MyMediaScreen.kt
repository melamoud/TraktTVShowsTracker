package com.melamoud.tvtracker.ui.media

import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.NavigateBefore
import androidx.compose.material.icons.automirrored.filled.NavigateNext
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import com.melamoud.tvtracker.R
import com.melamoud.tvtracker.data.api.absoluteUrl
import com.melamoud.tvtracker.data.api.dto.FilterListDto
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
fun MyMediaScreen(
    viewModel: MyMediaViewModel,
    baseUrl: String,
    isShows: Boolean,
    onProgress: (Int) -> Unit,
    onOpenDetail: (String, Int) -> Unit,
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
    val displayMode = state.display.ifBlank { "list" }
    val viewLabel = when (displayMode) {
        "newest_aired" -> "Newest"
        "daily" -> "Daily"
        "weekly" -> "Weekly"
        "monthly" -> "Monthly"
        else -> "List"
    }
    val perPageLabel = "${state.perPage}/pg"
    val listsSelected = state.filterLists.count { it.selected }
    val listsLabel = if (listsSelected == 0) "Lists" else "Lists ($listsSelected)"
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
                FilterMenuButton(listsLabel) { dismiss ->
                    state.filterLists.forEach { lst ->
                        CheckMenuItem(lst.name, lst.selected) { viewModel.toggleList(lst.id) }
                    }
                    TextButton(onClick = { dismiss(); viewModel.showCreateList() }) { Text("Manage lists…") }
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
                listOf(
                    "list" to "List",
                    "newest_aired" to "Newest aired",
                    "daily" to "Daily",
                    "weekly" to "Weekly",
                    "monthly" to "Monthly",
                ).forEach { (id, label) ->
                    CheckMenuItem(label, displayMode == id) {
                        viewModel.setDisplay(id)
                        dismiss()
                    }
                }
            }
            FilterMenuButton(perPageLabel) { dismiss ->
                listOf(10, 50, 100).forEach { n ->
                    CheckMenuItem("$n / page", state.perPage == n) {
                        viewModel.setPerPage(n)
                        dismiss()
                    }
                }
            }
        }
        if (displayMode in setOf("daily", "weekly", "monthly")) {
            CalendarHeader(state, viewModel)
        } else {
            Text(
                "${state.total} titles · page ${state.page}/${state.pages}",
                color = TextMuted,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )
        }
        ServerRefreshBox(
            isRefreshing = state.loading && state.items.isNotEmpty(),
            onRefresh = viewModel::reload,
            modifier = Modifier.weight(1f),
        ) {
            when {
                state.loading && state.items.isEmpty() && state.calendar == null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                state.error != null && state.items.isEmpty() && state.calendar == null -> Text(state.error ?: "", color = Danger, modifier = Modifier.padding(16.dp))
                displayMode in setOf("daily", "weekly", "monthly") -> CalendarListView(
                    calendar = state.calendar,
                    baseUrl = baseUrl,
                    onOpen = onOpenDetail,
                )
                state.items.isEmpty() -> Text(stringResource(R.string.empty_list), color = TextMuted, modifier = Modifier.padding(24.dp))
                else -> LazyColumn(contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(state.items, key = { "${it.mediaType}-${it.traktId}" }) { item ->
                        MediaCard(
                            item = item,
                            baseUrl = baseUrl,
                            showProgress = isShows,
                            showNewestAired = displayMode == "newest_aired",
                            onPin = { viewModel.pin(item) },
                            onLists = { viewModel.openLists(item) },
                            onFoundOn = { viewModel.openFoundOn(item) },
                            onWatched = { viewModel.confirmWatch(item) },
                            onRate = { viewModel.openRate(item) },
                            onFavorite = { viewModel.favorite(item) },
                            onProgress = if (isShows) ({ onProgress(item.traktId) }) else null,
                            onOpen = {
                                onOpenDetail(item.mediaType ?: if (isShows) "show" else "movie", item.traktId)
                            },
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
    if (state.listCreateDialog) {
        ListsManagementDialog(
            lists = state.filterLists,
            busy = state.listActionBusy,
            message = state.listActionMessage,
            onCreate = viewModel::createList,
            onDelete = viewModel::confirmDeleteList,
            onDismiss = viewModel::dismissCreateList,
        )
    }
    state.listDeleteConfirm?.let { list ->
        ConfirmDialog(
            title = "Delete list?",
            message = "Delete \"${list.name}\" from Trakt? This cannot be undone.",
            confirmLabel = "Delete",
            destructive = true,
            onConfirm = viewModel::deleteList,
            onDismiss = viewModel::dismissDeleteList,
        )
    }
}

@Composable
private fun ListsManagementDialog(
    lists: List<FilterListDto>,
    busy: Boolean,
    message: String?,
    onCreate: (String) -> Unit,
    onDelete: (FilterListDto) -> Unit,
    onDismiss: () -> Unit,
) {
    var newName by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Manage lists") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(
                    value = newName,
                    onValueChange = { newName = it },
                    label = { Text("New list name") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    enabled = !busy,
                )
                TextButton(
                    onClick = { onCreate(newName); newName = "" },
                    enabled = newName.isNotBlank() && !busy,
                    modifier = Modifier.align(Alignment.End),
                ) { Text("Create list") }
                message?.let {
                    Text(it, color = Danger, modifier = Modifier.padding(vertical = 4.dp))
                }
                lists.forEach { lst ->
                    Row(
                        Modifier.fillMaxWidth().padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text(lst.name, modifier = Modifier.weight(1f))
                        if (lst.kind != "watchlist") {
                            TextButton(
                                onClick = { onDelete(lst) },
                                enabled = !busy,
                            ) { Text("Delete", color = Danger) }
                        }
                    }
                }
                if (busy) {
                    CircularProgressIndicator(modifier = Modifier.padding(top = 8.dp).align(Alignment.CenterHorizontally))
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Done") } },
    )
}

private fun statusChoices(isShows: Boolean): List<Pair<String, String>> {
    return if (isShows) {
        listOf("lists" to "Both", "watched" to "Watched", "unwatched_episodes" to "Unwatched eps")
    } else {
        listOf("lists" to "Both", "watched" to "Watched", "unwatched" to "Unwatched")
    }
}

@Composable
private fun CalendarHeader(state: MyMediaUiState, viewModel: MyMediaViewModel) {
    val calendar = state.calendar ?: return
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = { viewModel.setCalDate(calendar.prevAnchor) }) {
            Icon(Icons.AutoMirrored.Filled.NavigateBefore, contentDescription = "Previous")
        }
        TextButton(
            onClick = { viewModel.setCalDate(calendar.today) },
            enabled = calendar.today != null && calendar.anchor != calendar.today,
        ) { Text("Today") }
        Text(
            calendar.label,
            modifier = Modifier.weight(1f),
            color = TextMuted,
        )
        IconButton(onClick = { viewModel.setCalDate(calendar.nextAnchor) }) {
            Icon(Icons.AutoMirrored.Filled.NavigateNext, contentDescription = "Next")
        }
    }
}

@Composable
private fun CalendarListView(
    calendar: com.melamoud.tvtracker.data.api.dto.CalendarDto?,
    baseUrl: String,
    onOpen: (String, Int) -> Unit,
) {
    if (calendar == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        return
    }
    val allEvents = remember(calendar) { calendar.days.flatMap { it.events } }
    if (allEvents.isEmpty()) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("Nothing airing or releasing in this period.", color = TextMuted)
        }
        return
    }
    LazyColumn(contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        calendar.days.forEach { day ->
            if (day.events.isEmpty()) return@forEach
            item(key = "header-${day.date}") {
                Text(
                    day.date ?: "",
                    color = TextMuted,
                    modifier = Modifier.padding(top = 8.dp, bottom = 4.dp),
                )
            }
            items(day.events, key = { "${day.date}-${it.traktId}-${it.label}" }) { ev ->
                CalendarEventCard(ev, baseUrl, onOpen)
            }
        }
    }
}

@Composable
private fun CalendarEventCard(
    event: com.melamoud.tvtracker.data.api.dto.CalendarEventDto,
    baseUrl: String,
    onOpen: (String, Int) -> Unit,
) {
    Card(
        onClick = { onOpen(event.mediaType ?: "show", event.traktId) },
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            Modifier.padding(8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            AsyncImage(
                model = absoluteUrl(baseUrl, event.posterUrl),
                contentDescription = event.title,
                modifier = Modifier.width(40.dp).height(60.dp),
            )
            Column(Modifier.weight(1f)) {
                Text(event.title, maxLines = 2)
                event.label?.let { Text(it, color = TextMuted, maxLines = 1) }
            }
        }
    }
}
