package com.melamoud.tvtracker.ui.media

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.FilterListDto
import com.melamoud.tvtracker.data.api.dto.ListMembershipDto
import com.melamoud.tvtracker.data.api.dto.MediaItemDto
import com.melamoud.tvtracker.data.api.dto.ServiceLinkDto
import com.melamoud.tvtracker.data.repo.CatalogRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class MyMediaUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val items: List<MediaItemDto> = emptyList(),
    val filter: String = "lists",
    val avail: String = "",
    val display: String = "",
    val query: String = "",
    val page: Int = 1,
    val pages: Int = 1,
    val total: Int = 0,
    val filterLists: List<FilterListDto> = emptyList(),
    val listsDialog: ListsDialogState? = null,
    val foundOnDialog: FoundOnDialogState? = null,
    val foundOnChoices: List<String> = emptyList(),
    val rateTarget: MediaItemDto? = null,
    val watchConfirm: MediaItemDto? = null,
)

data class ListsDialogState(
    val item: MediaItemDto,
    val lists: List<ListMembershipDto>,
    val defaults: List<String>,
)

data class FoundOnDialogState(
    val item: MediaItemDto,
    val choices: List<String>,
    val choiceLinks: List<ServiceLinkDto> = emptyList(),
)

class MyMediaViewModel(
    private val kind: String,
    private val repo: CatalogRepository,
    private val onUnread: (Int) -> Unit,
) : ViewModel() {
    private val _state = MutableStateFlow(MyMediaUiState())
    val state: StateFlow<MyMediaUiState> = _state.asStateFlow()
    private val mediaType = if (kind == "shows") "show" else "movie"
    private var loadSeq = 0
    private var persistFilter = false
    private var persistAvail = false
    private var persistDisplay = false

    fun reload(lists: List<String>? = null) {
        val seq = ++loadSeq
        viewModelScope.launch {
            val s = _state.value
            _state.value = s.copy(loading = true, error = null)
            val result = repo.myMedia(
                kind = kind,
                filter = s.filter.takeIf { persistFilter },
                avail = s.avail.takeIf { persistAvail },
                query = s.query,
                display = s.display.takeIf { persistDisplay && it.isNotBlank() },
                page = s.page,
                refresh = false,
                lists = lists,
            )
            if (seq != loadSeq) return@launch
            _state.value = result.fold(
                onSuccess = {
                    _state.value.copy(
                        loading = false,
                        error = null,
                        items = it.items,
                        filter = it.filter ?: _state.value.filter,
                        avail = it.avail.orEmpty(),
                        display = it.display ?: _state.value.display,
                        page = it.page,
                        pages = it.pages,
                        total = it.total,
                        filterLists = it.filterLists,
                        foundOnChoices = it.foundOnChoices.ifEmpty { _state.value.foundOnChoices },
                    )
                },
                onFailure = { _state.value.copy(loading = false, error = it.message) },
            )
        }
    }

    fun setFilter(value: String) {
        persistFilter = true
        _state.value = _state.value.copy(filter = value, page = 1)
        reload()
    }
    fun setAvail(value: String) {
        persistAvail = true
        _state.value = _state.value.copy(avail = value, page = 1)
        reload()
    }
    fun setDisplay(value: String) {
        persistDisplay = true
        _state.value = _state.value.copy(display = value, page = 1)
        reload()
    }
    fun setQuery(value: String) { _state.value = _state.value.copy(query = value) }
    fun applyQuery() { _state.value = _state.value.copy(page = 1); reload() }
    fun setPage(page: Int) { _state.value = _state.value.copy(page = page); reload() }
    fun toggleList(id: String) {
        val selected = _state.value.filterLists.filter { it.selected }.map { it.id }.toMutableSet()
        if (id in selected) selected.remove(id) else selected.add(id)
        _state.value = _state.value.copy(page = 1)
        reload(lists = selected.toList())
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
                    MyMediaViewModel(kind, repo, onUnread) as T
            }
    }
}
