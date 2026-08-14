package com.melamoud.tvtracker.ui.search

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.MediaItemDto
import com.melamoud.tvtracker.data.repo.CatalogRepository
import com.melamoud.tvtracker.ui.media.ListsDialogState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class SearchUiState(
    val query: String = "",
    val type: String = "both",
    val hideWatched: Boolean = true,
    val hideLists: Boolean = true,
    val loading: Boolean = false,
    val error: String? = null,
    val items: List<MediaItemDto> = emptyList(),
    val page: Int = 1,
    val pages: Int = 1,
    val total: Int = 0,
    val listsDialog: ListsDialogState? = null,
    val rateTarget: MediaItemDto? = null,
    val watchConfirm: MediaItemDto? = null,
)

class SearchViewModel(
    private val repo: CatalogRepository,
    private val onUnread: (Int) -> Unit,
) : ViewModel() {
    private val _state = MutableStateFlow(SearchUiState())
    val state: StateFlow<SearchUiState> = _state.asStateFlow()

    fun onQuery(value: String) { _state.value = _state.value.copy(query = value) }

    fun reloadFromServer() {
        if (_state.value.query.trim().length >= 2) search()
    }

    fun search() {
        val q = _state.value.query.trim()
        if (q.length < 2) {
            _state.value = _state.value.copy(items = emptyList(), error = null, total = 0)
            return
        }
        viewModelScope.launch {
            val s = _state.value
            _state.value = s.copy(loading = true, error = null, page = 1)
            load(s.copy(page = 1))
        }
    }

    fun setType(type: String) { _state.value = _state.value.copy(type = type); if (_state.value.query.length >= 2) search() }
    fun setHideWatched(value: Boolean) { _state.value = _state.value.copy(hideWatched = value); if (_state.value.query.length >= 2) search() }
    fun setHideLists(value: Boolean) { _state.value = _state.value.copy(hideLists = value); if (_state.value.query.length >= 2) search() }

    private suspend fun load(s: SearchUiState) {
        val result = repo.search(s.query.trim(), s.type, s.page, s.hideWatched, s.hideLists)
        _state.value = result.fold(
            onSuccess = {
                s.copy(
                    loading = false,
                    items = it.items,
                    page = it.page,
                    pages = it.pages,
                    total = it.total,
                    hideWatched = it.hideWatched,
                    hideLists = it.hideLists,
                    error = it.fetchError,
                )
            },
            onFailure = { s.copy(loading = false, error = it.message) },
        )
    }

    fun openLists(item: MediaItemDto) {
        viewModelScope.launch {
            repo.listsGet(item.mediaType ?: "movie", item.traktId).onSuccess {
                _state.value = _state.value.copy(listsDialog = ListsDialogState(item, it.lists, it.defaults))
            }
        }
    }
    fun dismissLists() { _state.value = _state.value.copy(listsDialog = null) }
    fun applyLists(selected: List<String>) {
        val dialog = _state.value.listsDialog ?: return
        _state.value = _state.value.copy(listsDialog = null)
        viewModelScope.launch {
            repo.listsSet(dialog.item.mediaType ?: "movie", dialog.item.traktId, selected)
            search()
        }
    }

    fun confirmWatch(item: MediaItemDto) { _state.value = _state.value.copy(watchConfirm = item) }
    fun dismissWatch() { _state.value = _state.value.copy(watchConfirm = null) }
    fun applyWatch() {
        val item = _state.value.watchConfirm ?: return
        _state.value = _state.value.copy(watchConfirm = null)
        viewModelScope.launch {
            repo.watched(item.mediaType ?: "movie", item.traktId, !item.watched)
            onUnread(repo.unreadAlerts())
            search()
        }
    }

    fun openRate(item: MediaItemDto) { _state.value = _state.value.copy(rateTarget = item) }
    fun dismissRate() { _state.value = _state.value.copy(rateTarget = null) }
    fun applyRate(score: Int?) {
        val item = _state.value.rateTarget ?: return
        _state.value = _state.value.copy(rateTarget = null)
        viewModelScope.launch {
            repo.rating(item.mediaType ?: "movie", item.traktId, score)
            search()
        }
    }

    fun favorite(item: MediaItemDto) {
        viewModelScope.launch {
            repo.favorite(item.mediaType ?: "movie", item.traktId, !item.favorited)
            search()
        }
    }

    fun pin(item: MediaItemDto) {
        viewModelScope.launch {
            repo.pin(item.mediaType ?: "movie", item.traktId, !item.pinned)
            search()
        }
    }

    companion object {
        fun factory(repo: CatalogRepository, onUnread: (Int) -> Unit) = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = SearchViewModel(repo, onUnread) as T
        }
    }
}
