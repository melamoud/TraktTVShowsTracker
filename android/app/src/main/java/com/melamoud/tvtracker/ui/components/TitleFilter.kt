package com.melamoud.tvtracker.ui.components

import com.melamoud.tvtracker.data.api.dto.AlertEntryDto
import com.melamoud.tvtracker.data.api.dto.AlertItemDto
import com.melamoud.tvtracker.data.api.dto.CalendarDto
import com.melamoud.tvtracker.data.api.dto.MediaItemDto
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Case-insensitive title (or year) match. Empty text matches everything. */
fun MediaItemDto.matchesTitleQuery(raw: String): Boolean {
    val needle = raw.trim()
    if (needle.isEmpty()) return true
    if (title.contains(needle, ignoreCase = true)) return true
    val yearText = year?.toString().orEmpty()
    return yearText.isNotEmpty() && needle in yearText
}

fun List<MediaItemDto>.filterByTitle(raw: String): List<MediaItemDto> {
    val needle = raw.trim()
    if (needle.isEmpty()) return this
    return filter { it.matchesTitleQuery(needle) }
}

private fun AlertItemDto.matchesTitleQuery(raw: String): Boolean {
    val needle = raw.trim()
    if (needle.isEmpty()) return true
    return listOf(displayTitle, mediaTitle, title, episodeName, headline).any {
        !it.isNullOrBlank() && it.contains(needle, ignoreCase = true)
    }
}

/** Keep a show group when its title matches, otherwise only the matching alerts. */
fun List<AlertEntryDto>.filterAlertsByTitle(raw: String): List<AlertEntryDto> {
    val needle = raw.trim()
    if (needle.isEmpty()) return this
    return mapNotNull { entry ->
        if (entry.kind == "group") {
            if (entry.title?.contains(needle, ignoreCase = true) == true) {
                entry
            } else {
                val kids = entry.items.filter { it.matchesTitleQuery(needle) }
                if (kids.isEmpty()) null
                else entry.copy(
                    items = kids,
                    unreadCount = kids.count { !it.isRead },
                    newCount = kids.count { it.isNew },
                )
            }
        } else if (entry.item?.matchesTitleQuery(needle) == true) {
            entry
        } else {
            null
        }
    }
}

/** Calendar already holds the whole period, so a title filter covers every day. */
fun CalendarDto.filteredByTitle(raw: String): CalendarDto {
    val needle = raw.trim()
    if (needle.isEmpty()) return this
    return copy(
        days = days.map { day ->
            day.copy(events = day.events.filter { it.title.contains(needle, ignoreCase = true) })
        },
    )
}

/**
 * Reloads the full list once the typed text has settled.
 * One character filters the rows already on screen; two or more ask the server
 * so matches on other pages show up. Clearing the box reloads the unfiltered list.
 */
class DebouncedTitleQuery(
    private val scope: CoroutineScope,
    private val onApply: () -> Unit,
) {
    private var job: Job? = null
    private var applied: String = ""

    fun onChange(raw: String) {
        job?.cancel()
        job = scope.launch {
            delay(160)
            val normalized = normalize(raw)
            if (normalized == applied) return@launch
            applied = normalized
            onApply()
        }
    }

    fun applyNow(raw: String) {
        job?.cancel()
        applied = normalize(raw)
        onApply()
    }

    private fun normalize(raw: String): String {
        val text = raw.trim()
        return if (text.length >= 2) text else ""
    }
}
