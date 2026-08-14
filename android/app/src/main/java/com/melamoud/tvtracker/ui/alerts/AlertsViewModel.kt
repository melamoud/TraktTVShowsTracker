package com.melamoud.tvtracker.ui.alerts

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
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
    val unreadCount: Int = 0,
    val hideRead: Boolean = true,
)

class AlertsViewModel(
    private val repo: CatalogRepository,
    private val onUnread: (Int) -> Unit,
) : ViewModel() {
    private val _state = MutableStateFlow(AlertsUiState())
    val state: StateFlow<AlertsUiState> = _state.asStateFlow()

    fun reload() {
        viewModelScope.launch {
            val s = _state.value
            _state.value = s.copy(loading = true, error = null)
            val result = repo.alerts(s.hideRead)
            _state.value = result.fold(
                onSuccess = {
                    onUnread(it.unreadCount)
                    s.copy(loading = false, items = it.items, unreadCount = it.unreadCount, hideRead = it.hideRead)
                },
                onFailure = { s.copy(loading = false, error = it.message) },
            )
        }
    }

    fun setHideRead(value: Boolean) {
        _state.value = _state.value.copy(hideRead = value)
        reload()
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

    companion object {
        fun factory(repo: CatalogRepository, onUnread: (Int) -> Unit) = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = AlertsViewModel(repo, onUnread) as T
        }
    }
}
