package com.melamoud.tvtracker.ui.progress

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.EpisodeDto
import com.melamoud.tvtracker.data.api.dto.ProgressResponse
import com.melamoud.tvtracker.data.repo.CatalogRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class ProgressUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val data: ProgressResponse? = null,
    val busy: Boolean = false,
)

class ProgressViewModel(
    private val traktId: Int,
    private val repo: CatalogRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(ProgressUiState())
    val state: StateFlow<ProgressUiState> = _state.asStateFlow()

    init { reload() }

    fun reload(refresh: Boolean = false) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            val result = repo.progress(traktId, refresh)
            _state.value = result.fold(
                onSuccess = { _state.value.copy(loading = false, data = it) },
                onFailure = { _state.value.copy(loading = false, error = it.message) },
            )
        }
    }

    fun toggleEpisode(ep: EpisodeDto, season: Int) {
        val ids = linkedMapOf<String, Any>()
        ep.ids?.trakt?.let { ids["trakt"] = it }
        ep.ids?.tvdb?.let { ids["tvdb"] = it }
        ep.ids?.tmdb?.let { ids["tmdb"] = it }
        ep.ids?.imdb?.let { ids["imdb"] = it }
        if (ids.isEmpty() && ep.traktId != null) ids["trakt"] = ep.traktId
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true)
            repo.episodeWatched(ids, traktId, season, ep.number, !ep.watched)
            _state.value = _state.value.copy(busy = false)
            reload()
        }
    }

    fun toggleSeason(season: Int, watched: Boolean) {
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true)
            repo.seasonWatched(traktId, season, watched)
            _state.value = _state.value.copy(busy = false)
            reload()
        }
    }

    companion object {
        fun factory(traktId: Int, repo: CatalogRepository) = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = ProgressViewModel(traktId, repo) as T
        }
    }
}
