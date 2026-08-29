package com.melamoud.tvtracker.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
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
import com.melamoud.tvtracker.data.api.dto.ListMembershipDto
import com.melamoud.tvtracker.data.api.dto.ServiceLinkDto

@Composable
fun ConfirmDialog(
    title: String,
    message: String,
    confirmLabel: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(message) },
        confirmButton = { TextButton(onClick = onConfirm) { Text(confirmLabel) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RateDialog(
    current: Int?,
    onSave: (Int?) -> Unit,
    onDismiss: () -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    var value by remember { mutableStateOf(current) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Rate") },
        text = {
            ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
                OutlinedTextField(
                    value = value?.toString() ?: "Clear rating",
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("1–10") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                    modifier = Modifier.menuAnchor().fillMaxWidth(),
                )
                ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                    DropdownMenuItem(text = { Text("Clear rating") }, onClick = {
                        value = null
                        expanded = false
                    })
                    (1..10).forEach { score ->
                        DropdownMenuItem(text = { Text(score.toString()) }, onClick = {
                            value = score
                            expanded = false
                        })
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = { onSave(value) }) { Text("Save") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
fun ListsDialog(
    title: String,
    lists: List<ListMembershipDto>,
    defaults: List<String>,
    onApply: (List<String>) -> Unit,
    onDismiss: () -> Unit,
) {
    var selected by remember(title, lists) {
        mutableStateOf(lists.filter { it.selected || it.onList }.map { it.id }.toSet())
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title.ifBlank { "Set lists" }) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                lists.forEach { lst ->
                    androidx.compose.foundation.layout.Row {
                        Checkbox(
                            checked = lst.id in selected,
                            onCheckedChange = { on ->
                                selected = if (on) selected + lst.id else selected - lst.id
                            },
                        )
                        Text(lst.name, modifier = Modifier.align(androidx.compose.ui.Alignment.CenterVertically))
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = { onApply(selected.toList()) }) { Text("Save") } },
        dismissButton = {
            Column {
                TextButton(onClick = { selected = defaults.toSet() }) { Text("Apply my defaults") }
                TextButton(onClick = { selected = emptySet() }) { Text("Remove from all") }
                TextButton(onClick = onDismiss) { Text("Cancel") }
            }
        },
    )
}

@Composable
fun FoundOnDialog(
    selected: List<String>,
    choices: List<String>,
    choiceLinks: List<ServiceLinkDto> = emptyList(),
    onApply: (List<String>) -> Unit,
    onDismiss: () -> Unit,
) {
    val uriHandler = LocalUriHandler.current
    val linkByLabel = remember(choiceLinks) {
        choiceLinks.associate { it.label.lowercase() to it.url }
    }
    val chosen = selected.map { it.lowercase() }.toSet()
    var checked by remember {
        mutableStateOf(choices.filter { it.lowercase() in chosen }.toSet())
    }
    val extraInitial = selected.filter { label ->
        choices.none { it.equals(label, ignoreCase = true) }
    }.joinToString(", ")
    var other by remember { mutableStateOf(extraInitial) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Where did you find it?") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                choices.forEach { name ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Row(
                            modifier = Modifier.weight(1f),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Checkbox(
                                checked = name in checked,
                                onCheckedChange = { on ->
                                    checked = if (on) checked + name else checked - name
                                },
                            )
                            Text(name)
                        }
                        val href = linkByLabel[name.lowercase()]
                        if (!href.isNullOrBlank()) {
                            TextButton(
                                onClick = {
                                    try {
                                        uriHandler.openUri(href)
                                    } catch (_: Exception) {
                                    }
                                },
                            ) { Text("Search") }
                        }
                    }
                }
                OutlinedTextField(
                    value = other,
                    onValueChange = { other = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Other") },
                    placeholder = { Text("Comma-separated") },
                    singleLine = true,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val extras = other.split(',').map { it.trim() }.filter { it.isNotEmpty() }
                onApply((checked.toList() + extras).distinctBy { it.lowercase() })
            }) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
fun ReviewDialog(
    loading: Boolean,
    error: String?,
    comment: String,
    spoiler: Boolean,
    onSave: (String, Boolean) -> Unit,
    onDismiss: () -> Unit,
) {
    var text by remember(comment, loading) { mutableStateOf(comment) }
    var markSpoiler by remember(spoiler, loading) { mutableStateOf(spoiler) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Write review") },
        text = {
            Column {
                if (loading) {
                    Text("Loading your Trakt review…")
                } else if (error != null) {
                    Text(error)
                } else {
                    OutlinedTextField(
                        value = text,
                        onValueChange = { text = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Review") },
                        minLines = 4,
                    )
                    androidx.compose.foundation.layout.Row {
                        Checkbox(checked = markSpoiler, onCheckedChange = { markSpoiler = it })
                        Text("Spoiler", modifier = Modifier.align(androidx.compose.ui.Alignment.CenterVertically))
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onSave(text.trim(), markSpoiler) },
                enabled = !loading && text.trim().isNotEmpty(),
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
