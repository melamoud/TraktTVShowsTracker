package com.melamoud.tvtracker.ui.preferences

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.AlertPrefsDto
import com.melamoud.tvtracker.data.api.dto.CustomServiceDto
import com.melamoud.tvtracker.data.api.dto.FavoriteActorDto
import com.melamoud.tvtracker.data.api.dto.PreferencesSaveRequest
import com.melamoud.tvtracker.data.api.dto.StreamingServiceDto
import com.melamoud.tvtracker.data.repo.CatalogRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class PreferencesUiState(
    val loading: Boolean = false,
    val saving: Boolean = false,
    val error: String? = null,
    val saveError: String? = null,
    val saved: Boolean = false,
    val defaults: List<StreamingServiceDto> = emptyList(),
    val customs: List<CustomServiceDto> = emptyList(),
    val commonGenres: List<String> = emptyList(),
    val genres: List<String> = emptyList(),
    val keywords: List<String> = emptyList(),
    val excludedGenres: List<String> = emptyList(),
    val alerts: AlertPrefsDto = AlertPrefsDto(),
    val favoriteActors: List<FavoriteActorDto> = emptyList(),
    val prefsReminderDisabled: Boolean = false,
    val actorBusy: Boolean = false,
)

class PreferencesViewModel(
    private val repo: CatalogRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(PreferencesUiState())
    val state: StateFlow<PreferencesUiState> = _state.asStateFlow()

    init { load() }

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null, saved = false)
            repo.preferences().fold(
                onSuccess = {
                    _state.value = _state.value.copy(
                        loading = false,
                        error = null,
                        defaults = it.defaults,
                        customs = it.customs,
                        commonGenres = it.commonGenres,
                        genres = it.genres,
                        keywords = it.keywords,
                        excludedGenres = it.excludedGenres,
                        alerts = it.alerts ?: AlertPrefsDto(),
                        favoriteActors = it.favoriteActors,
                        prefsReminderDisabled = it.prefsReminderDisabled,
                    )
                },
                onFailure = { _state.value = _state.value.copy(loading = false, error = it.message) },
            )
        }
    }

    fun toggleService(id: Int) {
        val current = _state.value.defaults.find { it.id == id }?.selected ?: false
        _state.value = _state.value.copy(
            defaults = _state.value.defaults.map {
                if (it.id == id) it.copy(selected = !current) else it
            },
            saved = false,
        )
    }

    fun addCustom(name: String, url: String, searchTemplate: String, note: String) {
        val trimmed = name.trim()
        if (trimmed.isEmpty()) return
        _state.value = _state.value.copy(
            customs = _state.value.customs + CustomServiceDto(
                name = trimmed,
                url = url.trim().ifEmpty { null },
                searchTemplate = searchTemplate.trim().ifEmpty { null },
                note = note.trim().ifEmpty { null },
            ),
            saved = false,
        )
    }

    fun removeCustom(id: Int) {
        _state.value = _state.value.copy(
            customs = _state.value.customs.filter { it.id != id },
            saved = false,
        )
    }

    fun toggleGenre(genre: String) {
        val g = genre.trim().lowercase()
        val current = _state.value.genres.map { it.lowercase() }.toSet()
        _state.value = _state.value.copy(
            genres = if (g in current) _state.value.genres.filter { it.lowercase() != g } else _state.value.genres + genre.trim(),
            saved = false,
        )
    }

    fun addGenre(genre: String) {
        val g = genre.trim()
        if (g.isEmpty()) return
        val current = _state.value.genres.map { it.lowercase() }.toSet()
        if (g.lowercase() !in current) {
            _state.value = _state.value.copy(
                genres = _state.value.genres + g,
                saved = false,
            )
        }
    }

    fun removeGenre(genre: String) {
        _state.value = _state.value.copy(
            genres = _state.value.genres.filter { it.lowercase() != genre.lowercase() },
            saved = false,
        )
    }

    fun setKeywords(text: String) {
        _state.value = _state.value.copy(
            keywords = text.split(',').map { it.trim() }.filter { it.isNotEmpty() },
            saved = false,
        )
    }

    fun removeKeyword(keyword: String) {
        _state.value = _state.value.copy(
            keywords = _state.value.keywords.filter { it.lowercase() != keyword.lowercase() },
            saved = false,
        )
    }

    fun toggleExcludedGenre(genre: String) {
        val g = genre.trim().lowercase()
        val current = _state.value.excludedGenres.map { it.lowercase() }.toSet()
        _state.value = _state.value.copy(
            excludedGenres = if (g in current) {
                _state.value.excludedGenres.filter { it.lowercase() != g }
            } else {
                _state.value.excludedGenres + genre.trim()
            },
            saved = false,
        )
    }

    fun addExcludedGenre(genre: String) {
        val g = genre.trim()
        if (g.isEmpty()) return
        val current = _state.value.excludedGenres.map { it.lowercase() }.toSet()
        if (g.lowercase() !in current) {
            _state.value = _state.value.copy(
                excludedGenres = _state.value.excludedGenres + g,
                saved = false,
            )
        }
    }

    fun removeExcludedGenre(genre: String) {
        _state.value = _state.value.copy(
            excludedGenres = _state.value.excludedGenres.filter { it.lowercase() != genre.lowercase() },
            saved = false,
        )
    }

    fun setAlert(key: String, value: Boolean) {
        val current = _state.value.alerts
        val updated = when (key) {
            "release_day" -> current.copy(releaseDay = value)
            "new_streaming" -> current.copy(newStreaming = value)
            "episode_aired" -> current.copy(episodeAired = value)
            "list_add" -> current.copy(listAdd = value)
            "season_streaming" -> current.copy(seasonStreaming = value)
            "favorite_actor" -> current.copy(favoriteActor = value)
            "favorite_actor_match_only" -> current.copy(favoriteActorMatchOnly = value)
            "new_user_login" -> current.copy(newUserLogin = value)
            else -> current
        }
        _state.value = _state.value.copy(alerts = updated, saved = false)
    }

    fun setPrefsReminderDisabled(value: Boolean) {
        _state.value = _state.value.copy(prefsReminderDisabled = value, saved = false)
    }

    fun removeFavoriteActor(traktId: Int) {
        viewModelScope.launch {
            _state.value = _state.value.copy(actorBusy = true)
            repo.favoriteActor(traktId, false).onSuccess {
                _state.value = _state.value.copy(
                    favoriteActors = _state.value.favoriteActors.filter { it.traktId != traktId },
                    actorBusy = false,
                    saved = false,
                )
            }.onFailure {
                _state.value = _state.value.copy(actorBusy = false, saveError = it.message)
            }
        }
    }

    fun save() {
        viewModelScope.launch {
            val s = _state.value
            _state.value = s.copy(saving = true, saveError = null, saved = false)
            val body = PreferencesSaveRequest(
                serviceIds = s.defaults.filter { it.selected }.map { it.id },
                removeCustomIds = emptyList(),
                customServices = s.customs,
                genres = s.genres,
                keywords = s.keywords,
                excludedGenres = s.excludedGenres,
                alerts = s.alerts,
                removeFavoriteActorIds = emptyList(),
                prefsReminderDisabled = s.prefsReminderDisabled,
            )
            repo.savePreferences(body).fold(
                onSuccess = { _state.value = _state.value.copy(saving = false, saveError = null, saved = true) },
                onFailure = { _state.value = _state.value.copy(saving = false, saveError = it.message, saved = false) },
            )
        }
    }

    companion object {
        fun factory(repo: CatalogRepository) = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T =
                PreferencesViewModel(repo) as T
        }
    }
}
