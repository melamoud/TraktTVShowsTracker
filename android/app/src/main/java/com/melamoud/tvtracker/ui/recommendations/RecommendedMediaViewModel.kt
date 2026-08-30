package com.melamoud.tvtracker.ui.recommendations

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.CategoryDto
import com.melamoud.tvtracker.data.api.dto.MediaItemDto
import com.melamoud.tvtracker.data.repo.CatalogRepository
import com.melamoud.tvtracker.ui.media.FoundOnDialogState
import com.melamoud.tvtracker.ui.media.ListsDialogState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class RecommendedMediaUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val items: List<MediaItemDto> = emptyList(),
    val query: String = "",
    val avail: String = "",
    val category: String = "all",
    val categories: List<CategoryDto> = emptyList(),
    val hideWatched: Boolean = true,
    val hideWishlist: Boolean = true,
    val onMyServices: Boolean = false,
    val matchOnly: Boolean = false,
    val hasMatchPrefs: Boolean = false,
    val userServiceNames: List<String> = emptyList(),
    val perPage: Int = 50,
    val page: Int = 1,
    val pages: Int = 1,
    val total: Int = 0,
    val foundOnChoices: List<String> = emptyList(),
    val refresh: Boolean = false,
    val year: String = "",
    val genres: List<String> = emptyList(),
    val genreChoices: List<String> = emptyList(),
    val listsDialog: ListsDialogState? = null,
    val foundOnDialog: FoundOnDialogState? = null,
    val rateTarget: MediaItemDto? = null,
    val watchConfirm: MediaItemDto? = null,
)

class RecommendedMediaViewModel(
    private val kind: String,
    private val repo: CatalogRepository,
    private val onUnread: (Int) -> Unit,
) : ViewModel() {
    private val mediaType = if (kind == "shows") "show" else "movie"
    private val _state = MutableStateFlow(RecommendedMediaUiState())
    val state: StateFlow<RecommendedMediaUiState> = _state.asStateFlow()
    private var loadSeq = 0

    init { reload() }

    fun reload() {
        val seq = ++loadSeq
        viewModelScope.launch {
            val s = _state.value
            _state.value = s.copy(loading = true, error = null)
            val result = repo.recommendations(
                kind = kind,
                query = s.query,
                page = s.page,
                avail = s.avail,
                category = s.category,
                hideWatched = s.hideWatched,
                hideWishlist = s.hideWishlist,
                onMyServices = s.onMyServices,
                matchOnly = s.matchOnly,
                perPage = s.perPage,
                refresh = s.refresh,
                year = s.year,
                genres = s.genres,
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
                        categories = it.categories,
                        category = it.category,
                        hideWatched = it.hideWatched,
                        hideWishlist = it.hideWishlist,
                        onMyServices = it.onMyServices,
                        matchOnly = it.matchOnly,
                        hasMatchPrefs = it.hasMatchPrefs,
                        userServiceNames = it.userServiceNames,
                        foundOnChoices = it.foundOnChoices.ifEmpty { _state.value.foundOnChoices },
                        year = it.year ?: s.year,
                        genres = it.genres.ifEmpty { s.genres },
                        genreChoices = it.genreChoices.ifEmpty { s.genreChoices },
                        refresh = false,
                    )
                },
                onFailure = { _state.value.copy(loading = false, error = it.message) },
            )
        }
    }

    fun setQuery(value: String) { _state.value = _state.value.copy(query = value) }
    fun applyQuery() { _state.value = _state.value.copy(page = 1); reload() }
    fun setPage(page: Int) { _state.value = _state.value.copy(page = page); reload() }

    fun setCategory(value: String) {
        _state.value = _state.value.copy(category = value, page = 1)
        reload()
    }

    fun setAvail(value: String) {
        _state.value = _state.value.copy(avail = value, page = 1)
        reload()
    }

    fun setHideWatched(value: Boolean) {
        _state.value = _state.value.copy(hideWatched = value, page = 1)
        reload()
    }

    fun setHideWishlist(value: Boolean) {
        _state.value = _state.value.copy(hideWishlist = value, page = 1)
        reload()
    }

    fun setOnMyServices(value: Boolean) {
        _state.value = _state.value.copy(onMyServices = value, page = 1)
        reload()
    }

    fun setMatchOnly(value: Boolean) {
        _state.value = _state.value.copy(matchOnly = value, page = 1)
        reload()
    }

    fun setPerPage(value: Int) {
        _state.value = _state.value.copy(perPage = value, page = 1)
        reload()
    }

    fun setRefresh() {
        _state.value = _state.value.copy(refresh = true, page = 1)
        reload()
    }

    fun setYear(value: String) {
        _state.value = _state.value.copy(year = value.trim(), page = 1)
        reload()
    }

    fun toggleGenre(genre: String) {
        val g = genre.trim()
        val current = _state.value.genres.toSet()
        _state.value = _state.value.copy(
            genres = if (g in current) _state.value.genres.filter { it != g } else _state.value.genres + g,
            page = 1,
        )
        reload()
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

    fun hideRecommendation(item: MediaItemDto) {
        viewModelScope.launch {
            repo.hideRecommendation(mediaType, item.traktId).onSuccess { reload() }
        }
    }

    companion object {
        fun factory(kind: String, repo: CatalogRepository, onUnread: (Int) -> Unit) =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    RecommendedMediaViewModel(kind, repo, onUnread) as T
            }
    }
}
