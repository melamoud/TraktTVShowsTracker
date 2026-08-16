package com.melamoud.tvtracker.ui.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.CastMemberDto
import com.melamoud.tvtracker.data.api.dto.FeedbackResponse
import com.melamoud.tvtracker.data.api.dto.MediaDetailResponse
import com.melamoud.tvtracker.data.api.dto.MediaItemDto
import com.melamoud.tvtracker.data.repo.CatalogRepository
import com.melamoud.tvtracker.ui.media.ListsDialogState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class ReviewDialogState(
    val loading: Boolean = false,
    val error: String? = null,
    val comment: String = "",
    val spoiler: Boolean = false,
    val commentId: Int? = null,
)

data class DetailUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val detail: MediaDetailResponse? = null,
    val showAllCast: Boolean = false,
    val listsDialog: ListsDialogState? = null,
    val rateOpen: Boolean = false,
    val watchConfirm: Boolean = false,
    val foundOnOpen: Boolean = false,
    val review: ReviewDialogState? = null,
)

class DetailViewModel(
    private val mediaType: String,
    private val traktId: Int,
    private val repo: CatalogRepository,
    private val onUnread: (Int) -> Unit,
) : ViewModel() {
    private val _state = MutableStateFlow(DetailUiState())
    val state: StateFlow<DetailUiState> = _state.asStateFlow()

    val item: MediaItemDto? get() = _state.value.detail?.item

    fun reload() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            val result = repo.catalogDetail(mediaType, traktId)
            _state.value = result.fold(
                onSuccess = { _state.value.copy(loading = false, detail = it, error = null) },
                onFailure = { _state.value.copy(loading = false, error = it.message) },
            )
        }
    }

    fun toggleCast() {
        _state.value = _state.value.copy(showAllCast = !_state.value.showAllCast)
    }

    fun confirmWatch() { _state.value = _state.value.copy(watchConfirm = true) }
    fun dismissWatch() { _state.value = _state.value.copy(watchConfirm = false) }
    fun applyWatch() {
        val current = item ?: return
        _state.value = _state.value.copy(watchConfirm = false)
        viewModelScope.launch {
            repo.watched(mediaType, traktId, !current.watched)
            onUnread(repo.unreadAlerts())
            reload()
        }
    }

    fun openRate() { _state.value = _state.value.copy(rateOpen = true) }
    fun dismissRate() { _state.value = _state.value.copy(rateOpen = false) }
    fun applyRate(score: Int?) {
        _state.value = _state.value.copy(rateOpen = false)
        viewModelScope.launch {
            repo.rating(mediaType, traktId, score)
            reload()
        }
    }

    fun favorite() {
        val current = item ?: return
        viewModelScope.launch {
            repo.favorite(mediaType, traktId, !current.favorited)
            reload()
        }
    }

    fun openLists() {
        viewModelScope.launch {
            repo.listsGet(mediaType, traktId).onSuccess {
                val current = item ?: return@onSuccess
                _state.value = _state.value.copy(
                    listsDialog = ListsDialogState(current, it.lists, it.defaults),
                )
            }
        }
    }
    fun dismissLists() { _state.value = _state.value.copy(listsDialog = null) }
    fun applyLists(selected: List<String>) {
        _state.value = _state.value.copy(listsDialog = null)
        viewModelScope.launch {
            repo.listsSet(mediaType, traktId, selected)
            reload()
        }
    }

    fun openFoundOn() { _state.value = _state.value.copy(foundOnOpen = true) }
    fun dismissFoundOn() { _state.value = _state.value.copy(foundOnOpen = false) }
    fun applyFoundOn(labels: List<String>) {
        _state.value = _state.value.copy(foundOnOpen = false)
        viewModelScope.launch {
            repo.foundOn(mediaType, traktId, labels)
            reload()
        }
    }

    fun openReview() {
        _state.value = _state.value.copy(review = ReviewDialogState(loading = true))
        viewModelScope.launch {
            val result = repo.feedback(mediaType, traktId)
            _state.value = result.fold(
                onSuccess = { fb: FeedbackResponse ->
                    _state.value.copy(
                        review = ReviewDialogState(
                            loading = false,
                            comment = fb.comment.orEmpty(),
                            spoiler = fb.spoiler,
                            commentId = fb.commentId,
                        ),
                    )
                },
                onFailure = {
                    _state.value.copy(
                        review = ReviewDialogState(loading = false, error = it.message),
                    )
                },
            )
        }
    }
    fun dismissReview() { _state.value = _state.value.copy(review = null) }
    fun applyReview(text: String, spoiler: Boolean) {
        val commentId = _state.value.review?.commentId
        _state.value = _state.value.copy(review = null)
        viewModelScope.launch {
            repo.comment(mediaType, traktId, text, spoiler, commentId)
            reload()
        }
    }

    fun toggleFavoriteActor(actor: CastMemberDto) {
        viewModelScope.launch {
            repo.favoriteActor(actor.traktId, !actor.favorited)
            reload()
        }
    }

    companion object {
        fun factory(mediaType: String, traktId: Int, repo: CatalogRepository, onUnread: (Int) -> Unit) =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    DetailViewModel(mediaType, traktId, repo, onUnread) as T
            }
    }
}
