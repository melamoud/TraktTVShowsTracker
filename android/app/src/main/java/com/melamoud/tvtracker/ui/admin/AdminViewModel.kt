package com.melamoud.tvtracker.ui.admin

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.AdminStatsDto
import com.melamoud.tvtracker.data.api.dto.AdminUserDto
import com.melamoud.tvtracker.data.repo.CatalogRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class AdminUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val stats: AdminStatsDto = AdminStatsDto(),
    val users: List<AdminUserDto> = emptyList(),
    val scheduler: String = "",
    val actionBusy: Boolean = false,
    val actionMessage: String? = null,
)

class AdminViewModel(private val repo: CatalogRepository) : ViewModel() {
    private val _state = MutableStateFlow(AdminUiState())
    val state: StateFlow<AdminUiState> = _state.asStateFlow()

    init { load() }

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            val statsResult = repo.adminDashboard()
            val usersResult = repo.adminUsers()
            val schedulerResult = repo.adminScheduler()
            _state.value = _state.value.copy(
                loading = false,
                stats = statsResult.getOrNull()?.stats ?: AdminStatsDto(),
                users = usersResult.getOrNull()?.users ?: emptyList(),
                scheduler = schedulerResult.getOrNull()?.status?.let { formatStatus(it) } ?: "",
                error = sequenceOf(statsResult, usersResult, schedulerResult)
                    .mapNotNull { it.exceptionOrNull()?.message }
                    .firstOrNull(),
            )
        }
    }

    private fun run(action: suspend () -> Result<*>, ok: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(actionBusy = true, actionMessage = null)
            action().fold(
                onSuccess = { _state.value = _state.value.copy(actionBusy = false, actionMessage = ok) },
                onFailure = { _state.value = _state.value.copy(actionBusy = false, actionMessage = it.message) },
            )
            load()
        }
    }

    fun runReleaseCheck() = run({ repo.adminRunReleaseCheck() }, "Release check finished")
    fun toggleActive(userId: Int) = run({ repo.adminToggleActive(userId) }, "Active flag toggled")
    fun toggleAdmin(userId: Int) = run({ repo.adminToggleAdmin(userId) }, "Admin flag toggled")
    fun revokeSessions(userId: Int) = run({ repo.adminRevokeSessions(userId) }, "Sessions revoked")
    fun deleteLocal(userId: Int) = run({ repo.adminDeleteLocal(userId) }, "User deleted")
    fun dismissAction() { _state.value = _state.value.copy(actionMessage = null) }

    companion object {
        fun factory(repo: CatalogRepository) = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = AdminViewModel(repo) as T
        }
    }
}

private fun formatStatus(status: Map<String, Any>): String {
    return status.entries.joinToString("\n") { "${it.key}: ${it.value}" }
}
