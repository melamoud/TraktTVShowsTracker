package com.melamoud.tvtracker.ui.progress

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.AlertCounts
import com.melamoud.tvtracker.data.api.dto.EpisodeDto
import com.melamoud.tvtracker.data.api.dto.FeedbackResponse
import com.melamoud.tvtracker.data.api.dto.ProgressResponse
import com.melamoud.tvtracker.data.repo.CatalogRepository
import com.melamoud.tvtracker.ui.components.FeedbackDraft
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class EpisodeReviewTarget(
    val episode: EpisodeDto,
    val season: Int,
)

data class ProgressUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val data: ProgressResponse? = null,
    val busy: Boolean = false,
    val reviewTarget: EpisodeReviewTarget? = null,
)

class ProgressViewModel(
    private val traktId: Int,
    private val repo: CatalogRepository,
    private val onUnread: (AlertCounts) -> Unit,
) : ViewModel() {
    private val _state = MutableStateFlow(ProgressUiState())
    val state: StateFlow<ProgressUiState> = _state.asStateFlow()

    fun reload() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            val result = repo.progress(traktId, refresh = false)
            _state.value = result.fold(
                onSuccess = { _state.value.copy(loading = false, data = it) },
                onFailure = { _state.value.copy(loading = false, error = it.message) },
            )
        }
    }

    fun toggleEpisode(ep: EpisodeDto, season: Int) {
        val ids = episodeIds(ep)
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true)
            repo.episodeWatched(ids, traktId, season, ep.number, !ep.watched)
            onUnread(repo.alertCounts())
            _state.value = _state.value.copy(busy = false)
            reload()
        }
    }

    fun toggleSeason(season: Int, watched: Boolean) {
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true)
            repo.seasonWatched(traktId, season, watched)
            onUnread(repo.alertCounts())
            _state.value = _state.value.copy(busy = false)
            reload()
        }
    }

    fun refreshFromTrakt() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            val result = repo.progress(traktId, refresh = true)
            _state.value = result.fold(
                onSuccess = { _state.value.copy(loading = false, data = it) },
                onFailure = { _state.value.copy(loading = false, error = it.message) },
            )
        }
    }

    fun markSeriesWatched() {
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true, error = null)
            val marked = repo.watched("show", traktId, true)
            marked.onFailure {
                _state.value = _state.value.copy(busy = false, error = it.message)
            }
            if (marked.isFailure) return@launch
            onUnread(repo.alertCounts())
            _state.value = _state.value.copy(busy = false)
            reload()
        }
    }

    fun openReview(ep: EpisodeDto, season: Int) {
        _state.value = _state.value.copy(reviewTarget = EpisodeReviewTarget(ep, season))
    }
    fun dismissReview() { _state.value = _state.value.copy(reviewTarget = null) }

    suspend fun loadEpisodeFeedback(target: EpisodeReviewTarget): FeedbackResponse {
        val id = target.episode.traktId ?: throw IllegalStateException("This episode has no Trakt id yet.")
        return repo.feedback("episode", id).getOrThrow()
    }

    suspend fun saveEpisodeFeedback(target: EpisodeReviewTarget, draft: FeedbackDraft) {
        val ep = target.episode
        val id = ep.traktId ?: return
        if (draft.ratingChanged) repo.rating("episode", id, draft.rating).getOrThrow()
        val text = draft.comment?.trim().orEmpty()
        if (text.isNotEmpty()) repo.comment("episode", id, text, draft.spoiler, draft.commentId).getOrThrow()
        if (draft.markWatched && !ep.watched) {
            repo.episodeWatched(episodeIds(ep), traktId, target.season, ep.number, true).getOrThrow()
        }
    }

    fun episodeFeedbackSaved() {
        _state.value = _state.value.copy(reviewTarget = null)
        onUnreadLaunch()
        reload()
    }

    private fun onUnreadLaunch() {
        viewModelScope.launch { onUnread(repo.alertCounts()) }
    }

    private fun episodeIds(ep: EpisodeDto): Map<String, Any> {
        val ids = linkedMapOf<String, Any>()
        ep.ids?.trakt?.let { ids["trakt"] = it }
        ep.ids?.tvdb?.let { ids["tvdb"] = it }
        ep.ids?.tmdb?.let { ids["tmdb"] = it }
        ep.ids?.imdb?.let { ids["imdb"] = it }
        if (ids.isEmpty() && ep.traktId != null) ids["trakt"] = ep.traktId
        return ids
    }

    companion object {
        fun factory(traktId: Int, repo: CatalogRepository, onUnread: (AlertCounts) -> Unit) =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    ProgressViewModel(traktId, repo, onUnread) as T
            }
    }
}
