package com.melamoud.tvtracker.ui.preferences

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import com.melamoud.tvtracker.R
import com.melamoud.tvtracker.data.api.absoluteUrl
import com.melamoud.tvtracker.ui.theme.Danger
import com.melamoud.tvtracker.ui.theme.Ok
import com.melamoud.tvtracker.ui.theme.SurfaceAlt
import com.melamoud.tvtracker.ui.theme.TextMuted

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PreferencesScreen(
    viewModel: PreferencesViewModel,
    baseUrl: String,
    onHelp: () -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    if (state.loading && state.defaults.isEmpty()) {
        Column(
            Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) { CircularProgressIndicator() }
        return
    }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        state.error?.let { Text(it, color = Danger) }
        state.saveError?.let { Text(it, color = Danger) }
        if (state.saved) {
            Text("Preferences saved", color = Ok)
        }

        ExpandableSection("Streaming services") {
            Text("Select the services you subscribe to:", color = TextMuted, style = MaterialTheme.typography.bodySmall)
            state.defaults.forEach { svc ->
                Row(
                    Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(
                        checked = svc.selected,
                        onCheckedChange = { viewModel.toggleService(svc.id) },
                    )
                    Text(svc.name)
                }
            }
            if (state.customs.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text("Custom services:", color = TextMuted, style = MaterialTheme.typography.bodySmall)
                state.customs.forEach { custom ->
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text(custom.name)
                        IconButton(onClick = { viewModel.removeCustom(custom.id) }) {
                            Icon(Icons.Default.Delete, contentDescription = "Remove", tint = Danger)
                        }
                    }
                }
            }
            AddCustomServiceDialog(onAdd = { name, url, template, note ->
                viewModel.addCustom(name, url, template, note)
            })
        }

        ExpandableSection("Genres") {
            Text("Tap to like or dislike. Liked genres make Latest/Recommendations match.", color = TextMuted, style = MaterialTheme.typography.bodySmall)
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                state.commonGenres.forEach { genre ->
                    val selected = state.genres.map { it.lowercase() }.contains(genre.lowercase())
                    FilterChip(
                        selected = selected,
                        onClick = { viewModel.toggleGenre(genre) },
                        label = { Text(genre) },
                    )
                }
            }
            AddTagRow(
                placeholder = "Add genre…",
                onAdd = viewModel::addGenre,
            )
            if (state.genres.isNotEmpty()) {
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    state.genres.forEach { genre ->
                        InputChipWithRemove(label = genre, onRemove = { viewModel.removeGenre(genre) })
                    }
                }
            }
        }

        ExpandableSection("Keywords") {
            Text("Comma-separated keywords that should count as a match.", color = TextMuted, style = MaterialTheme.typography.bodySmall)
            OutlinedTextField(
                value = state.keywords.joinToString(", "),
                onValueChange = viewModel::setKeywords,
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("e.g. superhero, time travel, zombie") },
                singleLine = true,
            )
            if (state.keywords.isNotEmpty()) {
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    state.keywords.forEach { keyword ->
                        InputChipWithRemove(label = keyword, onRemove = { viewModel.removeKeyword(keyword) })
                    }
                }
            }
        }

        ExpandableSection("Excluded genres") {
            Text("Titles with these genres are hidden everywhere.", color = TextMuted, style = MaterialTheme.typography.bodySmall)
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                state.commonGenres.forEach { genre ->
                    val selected = state.excludedGenres.map { it.lowercase() }.contains(genre.lowercase())
                    FilterChip(
                        selected = selected,
                        onClick = { viewModel.toggleExcludedGenre(genre) },
                        label = { Text(genre) },
                    )
                }
            }
            AddTagRow(
                placeholder = "Add excluded genre…",
                onAdd = viewModel::addExcludedGenre,
            )
            if (state.excludedGenres.isNotEmpty()) {
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    state.excludedGenres.forEach { genre ->
                        InputChipWithRemove(label = genre, onRemove = { viewModel.removeExcludedGenre(genre) })
                    }
                }
            }
        }

        ExpandableSection("Alerts") {
            Text("Choose which in-app notifications you receive.", color = TextMuted, style = MaterialTheme.typography.bodySmall)
            AlertToggle("Release day reminders", "release_day", state.alerts.releaseDay, viewModel::setAlert)
            AlertToggle("New streaming availability", "new_streaming", state.alerts.newStreaming, viewModel::setAlert)
            AlertToggle("New episode aired", "episode_aired", state.alerts.episodeAired, viewModel::setAlert)
            AlertToggle("Title added to a list", "list_add", state.alerts.listAdd, viewModel::setAlert)
            AlertToggle("Season now streaming", "season_streaming", state.alerts.seasonStreaming, viewModel::setAlert)
            AlertToggle("Favorite actor appearance", "favorite_actor", state.alerts.favoriteActor, viewModel::setAlert)
            AlertToggle("Only when actor title matches prefs", "favorite_actor_match_only", state.alerts.favoriteActorMatchOnly, viewModel::setAlert)
        }

        ExpandableSection("Favorite actors") {
            Text("Actors marked as favorite on title detail pages. Tap to remove.", color = TextMuted, style = MaterialTheme.typography.bodySmall)
            if (state.favoriteActors.isEmpty()) {
                Text("No favorite actors yet. Add them from a title's cast list.", color = TextMuted)
            } else {
                state.favoriteActors.forEach { actor ->
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        AsyncImage(
                            model = absoluteUrl(baseUrl, actor.headshotUrl),
                            contentDescription = actor.name,
                            modifier = Modifier.size(40.dp),
                        )
                        Text(actor.name, modifier = Modifier.weight(1f))
                        IconButton(
                            onClick = { viewModel.removeFavoriteActor(actor.traktId) },
                            enabled = !state.actorBusy,
                        ) {
                            Icon(Icons.Default.Delete, contentDescription = "Remove", tint = Danger)
                        }
                    }
                }
            }
        }

        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("Disable preferences reminder", style = MaterialTheme.typography.bodyMedium)
            Checkbox(
                checked = state.prefsReminderDisabled,
                onCheckedChange = viewModel::setPrefsReminderDisabled,
            )
        }

        Button(
            onClick = viewModel::save,
            enabled = !state.saving,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.saving) {
                CircularProgressIndicator(modifier = Modifier.height(18.dp))
            } else {
                Text(stringResource(R.string.save))
            }
        }
        OutlinedButton(
            onClick = onHelp,
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Help") }
    }
}

@Composable
private fun ExpandableSection(title: String, content: @Composable () -> Unit) {
    var expanded by remember { mutableStateOf(true) }
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = SurfaceAlt),
    ) {
        Column(Modifier.padding(12.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(title, style = MaterialTheme.typography.titleSmall)
                IconButton(onClick = { expanded = !expanded }) {
                    Icon(
                        if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = if (expanded) "Collapse" else "Expand",
                    )
                }
            }
            if (expanded) {
                Spacer(Modifier.height(8.dp))
                content()
            }
        }
    }
}

@Composable
private fun AddTagRow(placeholder: String, onAdd: (String) -> Unit) {
    var text by remember { mutableStateOf("") }
    Row(
        Modifier.fillMaxWidth().padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        OutlinedTextField(
            value = text,
            onValueChange = { text = it },
            modifier = Modifier.weight(1f),
            placeholder = { Text(placeholder) },
            singleLine = true,
        )
        OutlinedButton(
            onClick = {
                onAdd(text)
                text = ""
            },
            enabled = text.isNotBlank(),
        ) { Icon(Icons.Default.Add, contentDescription = "Add") }
    }
}

@Composable
private fun InputChipWithRemove(label: String, onRemove: () -> Unit) {
    FilterChip(
        selected = true,
        onClick = onRemove,
        label = { Text(label) },
        trailingIcon = { Icon(Icons.Default.Close, contentDescription = "Remove", modifier = Modifier.height(16.dp)) },
    )
}

@Composable
private fun AddCustomServiceDialog(onAdd: (String, String, String, String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var url by remember { mutableStateOf("") }
    var template by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }

    OutlinedButton(
        onClick = { open = true },
        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
    ) { Text("Add custom service") }

    if (open) {
        AlertDialog(
            onDismissRequest = { open = false },
            title = { Text("Custom service") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") }, singleLine = true)
                    OutlinedTextField(value = url, onValueChange = { url = it }, label = { Text("URL (optional)") }, singleLine = true)
                    OutlinedTextField(value = template, onValueChange = { template = it }, label = { Text("Search template (optional)") }, singleLine = true)
                    OutlinedTextField(value = note, onValueChange = { note = it }, label = { Text("Note (optional)") }, singleLine = true)
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        onAdd(name, url, template, note)
                        name = ""
                        url = ""
                        template = ""
                        note = ""
                        open = false
                    },
                    enabled = name.isNotBlank(),
                ) { Text("Add") }
            },
            dismissButton = { TextButton(onClick = { open = false }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun AlertToggle(label: String, key: String, checked: Boolean, onToggle: (String, Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Checkbox(
            checked = checked,
            onCheckedChange = { onToggle(key, it) },
        )
    }
}
