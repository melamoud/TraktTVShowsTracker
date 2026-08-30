package com.melamoud.tvtracker.ui.alerts

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.AlertEntryDto
import com.melamoud.tvtracker.data.api.dto.AlertItemDto
import com.melamoud.tvtracker.data.api.dto.MediaItemDto
import com.melamoud.tvtracker.ui.media.FoundOnDialogState
import com.melamoud.tvtracker.ui.media.ListsDialogState
import com.melamoud.tvtracker.data.repo.CatalogRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class AlertsUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val items: List<AlertItemDto> = emptyList(),
    val entries: List<AlertEntryDto> = emptyList(),
    val unreadCount: Int = 0,
    val hideRead: Boolean = true,
    val sort: String = "desc",
    val groupShows: Boolean = true,
    val expandedKeys: Set<String> = emptySet(),
    val foundOnChoices: List<String> = emptyList(),
    val rateTarget: AlertItemDto? = null,
    val listsDialog: ListsDialogState? = null,
    val foundOnDialog: FoundOnDialogState? = null,
    val watchConfirm: AlertItemDto? = null,
)

class AlertsViewModel(
    private val repo: CatalogRepository,
    private val onUnread: (Int) -> Unit,
) : ViewModel() {
    private val _state = MutableStateFlow(AlertsUiState())
    val state: StateFlow<AlertsUiState> = _state.asStateFlow()
    private var persistHideRead = false
    private var persistSort = false
    private var persistGroup = false

    fun reload() {
        viewModelScope.launch {
            val s = _state.value
            _state.value = s.copy(loading = true, error = null)
            val result = repo.alerts(
                hideRead = s.hideRead.takeIf { persistHideRead },
                sort = s.sort.takeIf { persistSort },
                groupShows = s.groupShows.takeIf { persistGroup },
            )
            _state.value = result.fold(
                onSuccess = {
                    onUnread(it.unreadCount)
                    s.copy(
                        loading = false,
                        items = it.items,
                        entries = it.entries.ifEmpty { fallbackEntries(it.items) },
                        unreadCount = it.unreadCount,
                        hideRead = it.hideRead,
                        sort = it.sort,
                        groupShows = it.groupShows,
                    )
                },
                onFailure = { s.copy(loading = false, error = it.message) },
            )
        }
    }

    fun setHideRead(value: Boolean) {
        persistHideRead = true
        _state.value = _state.value.copy(hideRead = value)
        reload()
    }

    fun setSort(value: String) {
        persistSort = true
        _state.value = _state.value.copy(sort = value)
        reload()
    }

    fun setGroupShows(value: Boolean) {
        persistGroup = true
        _state.value = _state.value.copy(groupShows = value)
        reload()
    }

    fun toggleExpanded(key: String) {
        val cur = _state.value.expandedKeys
        _state.value = _state.value.copy(
            expandedKeys = if (key in cur) cur - key else cur + key,
        )
    }

    fun toggleRead(item: AlertItemDto) {
        viewModelScope.launch {
            repo.alertRead(item.id, !item.isRead)
            reload()
        }
    }

    fun readAll() {
        viewModelScope.launch {
            repo.alertsReadAll()
            reload()
        }
    }

    fun pin(mediaType: String, traktId: Int, pin: Boolean) {
        viewModelScope.launch {
            repo.alertsPin(mediaType, traktId, pin)
            reload()
        }
    }

    fun runReleaseCheck() {
        viewModelScope.launch {
            repo.adminRunReleaseCheck()
            reload()
        }
    }

    fun confirmWatch(item: AlertItemDto) { _state.value = _state.value.copy(watchConfirm = item) }
    fun dismissWatch() { _state.value = _state.value.copy(watchConfirm = null) }
    fun applyWatch() {
        val item = _state.value.watchConfirm ?: return
        _state.value = _state.value.copy(watchConfirm = null)
        val mt = item.mediaType ?: return
        val tid = item.traktId ?: return
        viewModelScope.launch {
            repo.watched(mt, tid, true)
            onUnread(repo.unreadAlerts())
            reload()
        }
    }

    fun openRate(item: AlertItemDto) { _state.value = _state.value.copy(rateTarget = item) }
    fun dismissRate() { _state.value = _state.value.copy(rateTarget = null) }
    fun applyRate(score: Int?) {
        val item = _state.value.rateTarget ?: return
        _state.value = _state.value.copy(rateTarget = null)
        val mt = item.mediaType ?: return
        val tid = item.traktId ?: return
        viewModelScope.launch {
            repo.rating(mt, tid, score)
            reload()
        }
    }

    fun openLists(item: AlertItemDto) {
        val mt = item.mediaType ?: return
        val tid = item.traktId ?: return
        viewModelScope.launch {
            repo.listsGet(mt, tid).onSuccess {
                _state.value = _state.value.copy(
                    listsDialog = ListsDialogState(
                        MediaItemDto(
                            mediaType = mt,
                            traktId = tid,
                            title = item.mediaTitle ?: item.title,
                            year = item.year,
                        ),
                        it.lists,
                        it.defaults,
                    ),
                )
            }
        }
    }
    fun dismissLists() { _state.value = _state.value.copy(listsDialog = null) }
    fun applyLists(selected: List<String>) {
        val dialog = _state.value.listsDialog ?: return
        _state.value = _state.value.copy(listsDialog = null)
        viewModelScope.launch {
            repo.listsSet(dialog.item.mediaType ?: "movie", dialog.item.traktId, selected)
            reload()
        }
    }

    fun openFoundOn(item: AlertItemDto) {
        val choices = item.foundOn
        val links = item.foundOnLinks
        _state.value = _state.value.copy(
            foundOnDialog = FoundOnDialogState(
                MediaItemDto(
                    mediaType = item.mediaType ?: "movie",
                    traktId = item.traktId ?: 0,
                    title = item.mediaTitle ?: item.title,
                    year = item.year,
                    foundOn = item.foundOn,
                    foundOnChoiceLinks = item.foundOnLinks,
                ),
                choices = choices.ifEmpty { _state.value.foundOnChoices },
                choiceLinks = links,
            ),
        )
        if (_state.value.foundOnChoices.isEmpty()) {
            viewModelScope.launch {
                repo.foundOnChoices(item.mediaTitle ?: item.title, item.year).onSuccess {
                    _state.value = _state.value.copy(foundOnChoices = it.choices)
                }
            }
        }
    }
    fun dismissFoundOn() { _state.value = _state.value.copy(foundOnDialog = null) }
    fun applyFoundOn(labels: List<String>) {
        val dialog = _state.value.foundOnDialog ?: return
        val item = dialog.item
        _state.value = _state.value.copy(foundOnDialog = null)
        viewModelScope.launch {
            repo.foundOn(item.mediaType ?: "movie", item.traktId, labels)
            reload()
        }
    }

    companion object {
        fun factory(repo: CatalogRepository, onUnread: (Int) -> Unit) = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = AlertsViewModel(repo, onUnread) as T
        }
    }
}

private fun fallbackEntries(items: List<AlertItemDto>): List<AlertEntryDto> =
    items.map { AlertEntryDto(kind = "single", item = it) }
