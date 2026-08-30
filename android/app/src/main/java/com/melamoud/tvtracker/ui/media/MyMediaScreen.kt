package com.melamoud.tvtracker.ui.media

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
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
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
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
import com.melamoud.tvtracker.ui.components.MoreFiltersButton
import com.melamoud.tvtracker.ui.components.RateDialog
import com.melamoud.tvtracker.ui.components.ReloadOnResume
import com.melamoud.tvtracker.ui.components.ServerRefreshBox
import com.melamoud.tvtracker.ui.theme.Danger
import com.melamoud.tvtracker.ui.theme.SurfaceAlt
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
        val advancedCount = (if (state.perPage != 50) 1 else 0) +
            (if (state.year.isNotBlank()) 1 else 0) +
            state.genres.size
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
            MoreFiltersButton(advancedCount) {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    PerPageSection(state.perPage) { viewModel.setPerPage(it) }
                    YearSection(state.year) { viewModel.setYear(it) }
                    GenreSection(state.genres, state.genreChoices) { viewModel.toggleGenre(it) }
                    TextButton(onClick = viewModel::refreshFromTrakt) {
                        Icon(Icons.Default.Refresh, contentDescription = null)
                        Text("Refresh Trakt", modifier = Modifier.padding(start = 8.dp))
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
                displayMode in setOf("daily", "weekly", "monthly") -> CalendarGridView(
                    calendar = state.calendar,
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
private fun CalendarGridView(
    calendar: com.melamoud.tvtracker.data.api.dto.CalendarDto?,
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
    var selectedDay by remember { mutableStateOf<com.melamoud.tvtracker.data.api.dto.CalendarDayDto?>(null) }
    Column(Modifier.fillMaxSize().padding(12.dp)) {
        Row(Modifier.fillMaxWidth()) {
            calendar.weekdays.forEach { dayName ->
                Text(
                    dayName.take(1),
                    modifier = Modifier.weight(1f),
                    textAlign = TextAlign.Center,
                    color = TextMuted,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
        LazyVerticalGrid(
            columns = GridCells.Fixed(7),
            modifier = Modifier.weight(1f),
        ) {
            items(calendar.days, key = { it.date ?: it.hashCode() }) { day ->
                CalendarDayCell(day, onClick = { if (day.events.isNotEmpty()) selectedDay = day })
            }
        }
    }
    selectedDay?.let { day ->
        DayEventsDialog(day, onOpen) { selectedDay = null }
    }
}

@Composable
private fun CalendarDayCell(
    day: com.melamoud.tvtracker.data.api.dto.CalendarDayDto,
    onClick: () -> Unit,
) {
    val eventCount = day.events.size
    Box(
        modifier = Modifier
            .padding(2.dp)
            .aspectRatio(1f)
            .clip(RoundedCornerShape(4.dp))
            .background(
                if (day.isToday) MaterialTheme.colorScheme.primaryContainer
                else if (day.inMonth) SurfaceAlt
                else androidx.compose.ui.graphics.Color.Transparent
            )
            .clickable(enabled = eventCount > 0, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                day.date?.substringAfterLast("-") ?: "",
                color = if (day.isToday) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                fontWeight = if (day.isToday) FontWeight.Bold else FontWeight.Normal,
                style = MaterialTheme.typography.bodySmall,
            )
            if (eventCount > 0) {
                Text(
                    "$eventCount",
                    color = MaterialTheme.colorScheme.primary,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }
}

@Composable
private fun DayEventsDialog(
    day: com.melamoud.tvtracker.data.api.dto.CalendarDayDto,
    onOpen: (String, Int) -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(day.date ?: "Events") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                if (day.events.isEmpty()) {
                    Text("No events", color = TextMuted)
                } else {
                    day.events.forEach { ev ->
                        TextButton(
                            onClick = {
                                onDismiss()
                                onOpen(ev.mediaType ?: "show", ev.traktId)
                            },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text("${ev.title} ${ev.label?.let { "($it)" } ?: ""}")
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Close") } },
    )
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
        TextButton(onClick = { onChange(text) }, modifier = Modifier.align(Alignment.End)) { Text("Apply") }
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
