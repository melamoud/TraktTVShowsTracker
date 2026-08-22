package com.melamoud.tvtracker.ui.alerts

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.AlertEntryDto
import com.melamoud.tvtracker.data.api.dto.AlertItemDto
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

    companion object {
        fun factory(repo: CatalogRepository, onUnread: (Int) -> Unit) = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = AlertsViewModel(repo, onUnread) as T
        }
    }
}

private fun fallbackEntries(items: List<AlertItemDto>): List<AlertEntryDto> =
    items.map { AlertEntryDto(kind = "single", item = it) }
