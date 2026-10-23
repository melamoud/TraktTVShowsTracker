package com.melamoud.tvtracker.ui.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.AlertCounts
import com.melamoud.tvtracker.data.api.dto.CastMemberDto
import com.melamoud.tvtracker.data.api.dto.FeedbackResponse
import com.melamoud.tvtracker.data.api.dto.MediaDetailResponse
import com.melamoud.tvtracker.data.api.dto.MediaItemDto
import com.melamoud.tvtracker.data.repo.CatalogRepository
import com.melamoud.tvtracker.ui.components.FeedbackDraft
import com.melamoud.tvtracker.ui.media.ListsDialogState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class DetailUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val detail: MediaDetailResponse? = null,
    val showAllCast: Boolean = false,
    val listsDialog: ListsDialogState? = null,
    val rateOpen: Boolean = false,
    val watchConfirm: Boolean = false,
    val foundOnOpen: Boolean = false,
    val feedbackOpen: Boolean = false,
)

class DetailViewModel(
    private val mediaType: String,
    private val traktId: Int,
    private val repo: CatalogRepository,
    private val onUnread: (AlertCounts) -> Unit,
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
            onUnread(repo.alertCounts())
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

    fun hideRecommendation() {
        viewModelScope.launch {
            repo.hideRecommendation(mediaType, traktId)
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

    fun openFoundOn() {
        val current = item
        if (current == null) return
        if (current.foundOnChoiceLinks.isNotEmpty()) {
            _state.value = _state.value.copy(foundOnOpen = true)
            return
        }
        viewModelScope.launch {
            repo.foundOnChoices(current.title, current.year).onSuccess { resp ->
                val detail = _state.value.detail
                val media = detail?.item
                _state.value = _state.value.copy(
                    foundOnOpen = true,
                    detail = if (detail != null && media != null && resp.choiceLinks.isNotEmpty()) {
                        detail.copy(item = media.copy(foundOnChoiceLinks = resp.choiceLinks))
                    } else {
                        detail
                    },
                )
            }
        }
    }
    fun dismissFoundOn() { _state.value = _state.value.copy(foundOnOpen = false) }
    fun applyFoundOn(labels: List<String>) {
        _state.value = _state.value.copy(foundOnOpen = false)
        viewModelScope.launch {
            repo.foundOn(mediaType, traktId, labels)
            reload()
        }
    }

    fun openFeedback() { _state.value = _state.value.copy(feedbackOpen = true) }
    fun dismissFeedback() { _state.value = _state.value.copy(feedbackOpen = false) }
    fun feedbackSaved() {
        _state.value = _state.value.copy(feedbackOpen = false)
        reload()
    }
    suspend fun loadFeedback(): FeedbackResponse = repo.feedback(mediaType, traktId).getOrThrow()
    suspend fun saveFeedback(draft: FeedbackDraft) {
        if (draft.ratingChanged) repo.rating(mediaType, traktId, draft.rating).getOrThrow()
        val text = draft.comment?.trim().orEmpty()
        if (text.isNotEmpty()) repo.comment(mediaType, traktId, text, draft.spoiler, draft.commentId).getOrThrow()
    }

    fun toggleFavoriteActor(actor: CastMemberDto) {
        viewModelScope.launch {
            repo.favoriteActor(actor.traktId, !actor.favorited)
            reload()
        }
    }

    companion object {
        fun factory(mediaType: String, traktId: Int, repo: CatalogRepository, onUnread: (AlertCounts) -> Unit) =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    DetailViewModel(mediaType, traktId, repo, onUnread) as T
            }
    }
}
