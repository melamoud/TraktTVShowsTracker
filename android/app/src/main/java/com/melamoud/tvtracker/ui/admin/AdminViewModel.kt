package com.melamoud.tvtracker.ui.admin

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.api.dto.AdminSchedulerSaveRequest
import com.melamoud.tvtracker.data.api.dto.AdminServiceSuggestionDto
import com.melamoud.tvtracker.data.api.dto.AdminStatsDto
import com.melamoud.tvtracker.data.api.dto.AdminStreamingServiceActionRequest
import com.melamoud.tvtracker.data.api.dto.AdminStreamingServiceDto
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
    val services: List<AdminStreamingServiceDto> = emptyList(),
    val pendingSuggestions: List<AdminServiceSuggestionDto> = emptyList(),
    val scheduler: String = "",
    val schedulerConfig: Map<String, Any>? = null,
    val schedulerRunning: Boolean = false,
    val actionBusy: Boolean = false,
    val actionMessage: String? = null,
    val addServiceDialog: Boolean = false,
    val newServiceName: String = "",
    val newServiceUrl: String = "",
    val newServiceNote: String = "",
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
            val servicesResult = repo.adminStreamingServices()
            val schedulerStatus = schedulerResult.getOrNull()?.status
            val config = schedulerStatus?.get("config") as? Map<String, Any>
            _state.value = _state.value.copy(
                loading = false,
                stats = statsResult.getOrNull()?.stats ?: AdminStatsDto(),
                users = usersResult.getOrNull()?.users ?: emptyList(),
                services = servicesResult.getOrNull()?.services ?: emptyList(),
                pendingSuggestions = servicesResult.getOrNull()?.pending ?: emptyList(),
                scheduler = schedulerStatus?.let { formatStatus(it) } ?: "",
                schedulerConfig = config,
                schedulerRunning = schedulerStatus?.get("running") as? Boolean ?: false,
                error = sequenceOf(statsResult, usersResult, schedulerResult, servicesResult)
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

    fun showAddServiceDialog() { _state.value = _state.value.copy(addServiceDialog = true) }
    fun dismissAddServiceDialog() { _state.value = _state.value.copy(addServiceDialog = false) }
    fun setNewServiceName(value: String) { _state.value = _state.value.copy(newServiceName = value) }
    fun setNewServiceUrl(value: String) { _state.value = _state.value.copy(newServiceUrl = value) }
    fun setNewServiceNote(value: String) { _state.value = _state.value.copy(newServiceNote = value) }
    fun addService() = run({
        repo.adminStreamingServicesAction(
            AdminStreamingServiceActionRequest(
                action = "add",
                name = _state.value.newServiceName,
                url = _state.value.newServiceUrl,
                note = _state.value.newServiceNote,
            )
        )
    }, "Service added")

    fun approveSuggestion(id: Int) = run({
        repo.adminStreamingServicesAction(AdminStreamingServiceActionRequest(action = "approve", suggestionId = id))
    }, "Suggestion approved")

    fun rejectSuggestion(id: Int) = run({
        repo.adminStreamingServicesAction(AdminStreamingServiceActionRequest(action = "reject", suggestionId = id))
    }, "Suggestion rejected")

    fun setSchedulerConfig(key: String, value: Any) {
        val config = _state.value.schedulerConfig?.toMutableMap() ?: mutableMapOf()
        config[key] = value
        _state.value = _state.value.copy(schedulerConfig = config)
    }

    fun saveScheduler() {
        val config = _state.value.schedulerConfig ?: return
        viewModelScope.launch {
            _state.value = _state.value.copy(actionBusy = true, actionMessage = null)
            val body = AdminSchedulerSaveRequest(
                catalogSyncEnabled = config["catalog_sync_enabled"] as? Boolean ?: false,
                catalogSyncMode = config["catalog_sync_mode"] as? String ?: "interval",
                catalogSyncIntervalMinutes = (config["catalog_sync_interval_minutes"] as? Number)?.toInt() ?: 60,
                catalogSyncCronTime = config["catalog_sync_cron_time"] as? String ?: "08:00",
                mediaAlertsEnabled = config["media_alerts_enabled"] as? Boolean ?: false,
                mediaAlertsMode = config["media_alerts_mode"] as? String ?: "interval",
                mediaAlertsIntervalHours = (config["media_alerts_interval_hours"] as? Number)?.toDouble() ?: 4.0,
                mediaAlertsCronTime = config["media_alerts_cron_time"] as? String ?: "08:00",
                mediaAlertsTimezone = config["media_alerts_timezone"] as? String ?: "America/New_York",
                traktReadCacheHours = (config["trakt_read_cache_hours"] as? Number)?.toDouble() ?: 2.0,
            )
            repo.adminSchedulerSave(body).fold(
                onSuccess = { _state.value = _state.value.copy(actionBusy = false, actionMessage = it.message) },
                onFailure = { _state.value = _state.value.copy(actionBusy = false, actionMessage = it.message) },
            )
            load()
        }
    }

    fun resetScheduler() = run({
        repo.adminSchedulerSave(AdminSchedulerSaveRequest(action = "reset"))
    }, "Scheduler reset")

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
