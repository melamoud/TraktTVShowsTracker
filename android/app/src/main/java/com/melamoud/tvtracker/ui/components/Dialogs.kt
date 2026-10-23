package com.melamoud.tvtracker.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.melamoud.tvtracker.data.api.dto.FeedbackResponse
import com.melamoud.tvtracker.data.api.dto.ListMembershipDto
import com.melamoud.tvtracker.data.api.dto.ServiceLinkDto
import kotlinx.coroutines.launch

@Composable
fun ConfirmDialog(
    title: String,
    message: String,
    confirmLabel: String,
    destructive: Boolean = false,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(message) },
        confirmButton = {
            TextButton(onClick = onConfirm) {
                Text(confirmLabel, color = if (destructive) com.melamoud.tvtracker.ui.theme.Danger else androidx.compose.material3.LocalContentColor.current)
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
fun PageJumpDialog(
    current: Int,
    pages: Int,
    onConfirm: (Int) -> Unit,
    onDismiss: () -> Unit,
) {
    var text by remember { mutableStateOf(current.toString()) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Go to page") },
        text = {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it.filter { c -> c.isDigit() } },
                label = { Text("1–$pages") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Number,
                    imeAction = ImeAction.Go,
                ),
                keyboardActions = KeyboardActions(onGo = {
                    text.toIntOrNull()?.coerceIn(1, pages)?.let(onConfirm)
                }),
                modifier = Modifier.fillMaxWidth(),
            )
        },
        confirmButton = {
            TextButton(onClick = {
                text.toIntOrNull()?.coerceIn(1, pages)?.let(onConfirm)
            }) { Text("Go") }
        },
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

data class FeedbackDraft(
    val rating: Int?,
    val ratingChanged: Boolean,
    val comment: String?,
    val spoiler: Boolean,
    val commentId: Int?,
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FeedbackDialog(
    title: String,
    load: suspend () -> FeedbackResponse,
    save: suspend (FeedbackDraft) -> Unit,
    onSaved: () -> Unit,
    onDismiss: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var loading by remember { mutableStateOf(true) }
    var saving by remember { mutableStateOf(false) }
    var formError by remember { mutableStateOf<String?>(null) }
    var rating by remember { mutableStateOf<Int?>(null) }
    var initialRating by remember { mutableStateOf<Int?>(null) }
    var comment by remember { mutableStateOf("") }
    var initialComment by remember { mutableStateOf("") }
    var spoiler by remember { mutableStateOf(false) }
    var initialSpoiler by remember { mutableStateOf(false) }
    var commentId by remember { mutableStateOf<Int?>(null) }
    var expanded by remember { mutableStateOf(false) }

    LaunchedEffect(title) {
        loading = true
        formError = null
        try {
            val fb = load()
            rating = fb.rating
            initialRating = fb.rating
            comment = fb.comment.orEmpty()
            initialComment = fb.comment.orEmpty()
            spoiler = fb.spoiler
            initialSpoiler = fb.spoiler
            commentId = fb.commentId
        } catch (err: Exception) {
            formError = err.message ?: "Could not load your Trakt rating/review."
        } finally {
            loading = false
        }
    }

    AlertDialog(
        onDismissRequest = { if (!saving) onDismiss() },
        title = { Text("Feedback") },
        text = {
            if (loading) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(if (title.isBlank()) "Loading your Trakt rating and review…" else "Loading $title…")
                    CircularProgressIndicator()
                }
            } else {
                Column(
                    Modifier.verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    if (title.isNotBlank()) Text(title)
                    Text("Rating and optional review for this title. A review needs at least 5 words.")
                    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
                        OutlinedTextField(
                            value = rating?.toString() ?: "No rating",
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Rating 1–10") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                            modifier = Modifier.menuAnchor().fillMaxWidth(),
                        )
                        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                            DropdownMenuItem(text = { Text("No rating") }, onClick = {
                                rating = null
                                expanded = false
                            })
                            (1..10).forEach { score ->
                                DropdownMenuItem(text = { Text(score.toString()) }, onClick = {
                                    rating = score
                                    expanded = false
                                })
                            }
                        }
                    }
                    OutlinedTextField(
                        value = comment,
                        onValueChange = { comment = it },
                        label = { Text("Review (optional)") },
                        modifier = Modifier.fillMaxWidth().height(120.dp),
                        maxLines = 5,
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = spoiler, onCheckedChange = { spoiler = it })
                        Text("Spoiler")
                    }
                    formError?.let { Text(it) }
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = !loading && !saving,
                onClick = {
                    val text = comment.trim()
                    val words = text.split(Regex("\\s+")).filter { it.isNotBlank() }
                    if (text.isNotEmpty() && words.size < 5) {
                        formError = "Reviews need at least 5 words (or leave the review empty)."
                        return@TextButton
                    }
                    if (text.isEmpty() && initialComment.isNotBlank()) {
                        formError = "Leave the existing review, or replace it with at least 5 words."
                        return@TextButton
                    }
                    val ratingChanged = rating != initialRating
                    val commentChanged = text != initialComment.trim() || spoiler != initialSpoiler
                    val writeComment = text.isNotEmpty() && commentChanged
                    if (!ratingChanged && !writeComment) {
                        formError = "Change the rating or write a review."
                        return@TextButton
                    }
                    formError = null
                    saving = true
                    scope.launch {
                        try {
                            save(
                                FeedbackDraft(
                                    rating = rating,
                                    ratingChanged = ratingChanged,
                                    comment = if (writeComment) text else null,
                                    spoiler = spoiler,
                                    commentId = commentId,
                                ),
                            )
                            onSaved()
                        } catch (err: Exception) {
                            formError = err.message ?: "Could not save to Trakt."
                            saving = false
                        }
                    }
                },
            ) { Text(if (saving) "Saving…" else "Save") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !saving) { Text("Cancel") }
        },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReviewDialog(
    currentRating: Int?,
    currentComment: String?,
    onSave: (Int?, String, Boolean) -> Unit,
    onDismiss: () -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    var rating by remember { mutableStateOf(currentRating) }
    var comment by remember { mutableStateOf(currentComment.orEmpty()) }
    var spoiler by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Rate / Review") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
                    OutlinedTextField(
                        value = rating?.toString() ?: "Clear rating",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Rating 1–10") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                        modifier = Modifier.menuAnchor().fillMaxWidth(),
                    )
                    ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                        DropdownMenuItem(text = { Text("Clear rating") }, onClick = {
                            rating = null
                            expanded = false
                        })
                        (1..10).forEach { score ->
                            DropdownMenuItem(text = { Text(score.toString()) }, onClick = {
                                rating = score
                                expanded = false
                            })
                        }
                    }
                }
                OutlinedTextField(
                    value = comment,
                    onValueChange = { comment = it },
                    label = { Text("Review (optional)") },
                    modifier = Modifier.fillMaxWidth().height(120.dp),
                    maxLines = 5,
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = spoiler, onCheckedChange = { spoiler = it })
                    Text("Spoiler")
                }
            }
        },
        confirmButton = { TextButton(onClick = { onSave(rating, comment, spoiler) }) { Text("Save") } },
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
