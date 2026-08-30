package com.melamoud.tvtracker.ui.latest

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.MediaItemDto
import com.melamoud.tvtracker.data.api.dto.ReviewMarkerDto
import com.melamoud.tvtracker.data.repo.CatalogRepository
import com.melamoud.tvtracker.ui.media.FoundOnDialogState
import com.melamoud.tvtracker.ui.media.ListsDialogState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class LatestMediaUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val items: List<MediaItemDto> = emptyList(),
    val query: String = "",
    val avail: String = "",
    val hideWatched: Boolean = true,
    val hideLists: Boolean = true,
    val matchOnly: Boolean = false,
    val recentYears: Boolean = true,
    val perPage: Int = 50,
    val page: Int = 1,
    val pages: Int = 1,
    val total: Int = 0,
    val marker: ReviewMarkerDto? = null,
    val markerPage: Int? = null,
    val hasMoreOlder: Boolean = false,
    val foundOnChoices: List<String> = emptyList(),
    val listsDialog: ListsDialogState? = null,
    val foundOnDialog: FoundOnDialogState? = null,
    val rateTarget: MediaItemDto? = null,
    val watchConfirm: MediaItemDto? = null,
)

class LatestMediaViewModel(
    private val kind: String,
    private val repo: CatalogRepository,
    private val onUnread: (Int) -> Unit,
) : ViewModel() {
    private val mediaType = if (kind == "shows") "show" else "movie"
    private val _state = MutableStateFlow(LatestMediaUiState())
    val state: StateFlow<LatestMediaUiState> = _state.asStateFlow()
    private var loadSeq = 0

    init { reload() }

    fun reload(loadOlder: Boolean = false) {
        val seq = ++loadSeq
        viewModelScope.launch {
            val s = _state.value
            _state.value = s.copy(loading = true, error = null)
            val result = repo.latestMedia(
                kind = kind,
                query = s.query,
                page = s.page,
                avail = s.avail,
                hideWatched = s.hideWatched,
                hideLists = s.hideLists,
                matchOnly = s.matchOnly,
                recentYears = s.recentYears,
                perPage = s.perPage,
                loadOlder = loadOlder,
            )
            if (seq != loadSeq) return@launch
            _state.value = result.fold(
                onSuccess = {
                    _state.value.copy(
                        loading = false,
                        error = null,
                        items = it.items,
                        page = it.page,
                        pages = it.pages,
                        perPage = it.perPage,
                        total = it.total,
                        marker = it.marker,
                        markerPage = it.markerPage,
                        hasMoreOlder = it.hasMoreOlder,
                        foundOnChoices = it.foundOnChoices.ifEmpty { _state.value.foundOnChoices },
                    )
                },
                onFailure = { _state.value.copy(loading = false, error = it.message) },
            )
        }
    }

    fun setQuery(value: String) { _state.value = _state.value.copy(query = value) }
    fun applyQuery() { _state.value = _state.value.copy(page = 1); reload() }
    fun setPage(page: Int) { _state.value = _state.value.copy(page = page); reload() }

    fun setAvail(value: String) {
        _state.value = _state.value.copy(avail = value, page = 1)
        reload()
    }

    fun setHideWatched(value: Boolean) {
        _state.value = _state.value.copy(hideWatched = value, page = 1)
        reload()
    }

    fun setHideLists(value: Boolean) {
        _state.value = _state.value.copy(hideLists = value, page = 1)
        reload()
    }

    fun setMatchOnly(value: Boolean) {
        _state.value = _state.value.copy(matchOnly = value, page = 1)
        reload()
    }

    fun setRecentYears(value: Boolean) {
        _state.value = _state.value.copy(recentYears = value, page = 1)
        reload()
    }

    fun setPerPage(value: Int) {
        _state.value = _state.value.copy(perPage = value, page = 1)
        reload()
    }

    fun syncCatalog() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            repo.syncCatalog(mediaType).onSuccess {
                reload()
            }.onFailure { err ->
                _state.value = _state.value.copy(loading = false, error = err.message)
            }
        }
    }

    fun reviewMarkerSet(item: MediaItemDto) {
        viewModelScope.launch {
            repo.reviewMarkerSet(mediaType, item.traktId).onSuccess { reload() }
        }
    }

    fun reviewMarkerClear() {
        viewModelScope.launch {
            repo.reviewMarkerClear(mediaType).onSuccess { reload() }
        }
    }

    fun reviewMarkerCaughtUp() {
        viewModelScope.launch {
            repo.reviewMarkerCaughtUp(mediaType).onSuccess { reload() }
        }
    }

    fun hideRecommendation(item: MediaItemDto) {
        viewModelScope.launch {
            repo.hideRecommendation(mediaType, item.traktId).onSuccess { reload() }
        }
    }

    fun pin(item: MediaItemDto) {
        viewModelScope.launch {
            repo.pin(mediaType, item.traktId, !item.pinned)
            reload()
        }
    }

    fun confirmWatch(item: MediaItemDto) { _state.value = _state.value.copy(watchConfirm = item) }
    fun dismissWatch() { _state.value = _state.value.copy(watchConfirm = null) }
    fun applyWatch() {
        val item = _state.value.watchConfirm ?: return
        _state.value = _state.value.copy(watchConfirm = null)
        viewModelScope.launch {
            repo.watched(mediaType, item.traktId, !item.watched)
            onUnread(repo.unreadAlerts())
            reload()
        }
    }

    fun openRate(item: MediaItemDto) { _state.value = _state.value.copy(rateTarget = item) }
    fun dismissRate() { _state.value = _state.value.copy(rateTarget = null) }
    fun applyRate(score: Int?) {
        val item = _state.value.rateTarget ?: return
        _state.value = _state.value.copy(rateTarget = null)
        viewModelScope.launch {
            repo.rating(mediaType, item.traktId, score)
            reload()
        }
    }

    fun favorite(item: MediaItemDto) {
        viewModelScope.launch {
            repo.favorite(mediaType, item.traktId, !item.favorited)
            reload()
        }
    }

    fun openLists(item: MediaItemDto) {
        viewModelScope.launch {
            repo.listsGet(mediaType, item.traktId).onSuccess {
                _state.value = _state.value.copy(
                    listsDialog = ListsDialogState(item, it.lists, it.defaults),
                )
            }
        }
    }

    fun dismissLists() { _state.value = _state.value.copy(listsDialog = null) }
    fun applyLists(selected: List<String>) {
        val dialog = _state.value.listsDialog ?: return
        _state.value = _state.value.copy(listsDialog = null)
        viewModelScope.launch {
            repo.listsSet(mediaType, dialog.item.traktId, selected)
            reload()
        }
    }

    fun openFoundOn(item: MediaItemDto) {
        val cached = _state.value.foundOnChoices
        val links = item.foundOnChoiceLinks
        if (cached.isNotEmpty() && links.isNotEmpty()) {
            _state.value = _state.value.copy(foundOnDialog = FoundOnDialogState(item, cached, links))
            return
        }
        viewModelScope.launch {
            repo.foundOnChoices(item.title, item.year).onSuccess {
                _state.value = _state.value.copy(
                    foundOnChoices = it.choices.ifEmpty { cached },
                    foundOnDialog = FoundOnDialogState(
                        item,
                        it.choices.ifEmpty { cached },
                        it.choiceLinks.ifEmpty { links },
                    ),
                )
            }
        }
    }

    fun dismissFoundOn() { _state.value = _state.value.copy(foundOnDialog = null) }
    fun applyFoundOn(labels: List<String>) {
        val dialog = _state.value.foundOnDialog ?: return
        _state.value = _state.value.copy(foundOnDialog = null)
        viewModelScope.launch {
            repo.foundOn(mediaType, dialog.item.traktId, labels)
            reload()
        }
    }

    companion object {
        fun factory(kind: String, repo: CatalogRepository, onUnread: (Int) -> Unit) =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    LatestMediaViewModel(kind, repo, onUnread) as T
            }
    }
}
