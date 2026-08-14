package com.melamoud.tvtracker.ui.login

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.melamoud.tvtracker.data.repo.AuthRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class LoginUiState(
    val loading: Boolean = false,
    val error: String? = null,
    val authorizeUrl: String? = null,
    val loggedIn: Boolean = false,
    val username: String? = null,
    val unreadAlerts: Int = 0,
)

class LoginViewModel(
    private val auth: AuthRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    fun startLogin() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null, authorizeUrl = null)
            val result = auth.startLogin()
            _state.value = result.fold(
                onSuccess = { _state.value.copy(loading = false, authorizeUrl = it) },
                onFailure = { _state.value.copy(loading = false, error = it.message) },
            )
        }
    }

    fun consumeAuthorizeUrl() {
        _state.value = _state.value.copy(authorizeUrl = null)
    }

    fun complete(token: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            val result = auth.completeLogin(token)
            _state.value = result.fold(
                onSuccess = {
                    _state.value.copy(
                        loading = false,
                        loggedIn = true,
                        username = it.username,
                        unreadAlerts = it.unreadAlerts,
                    )
                },
                onFailure = { _state.value.copy(loading = false, error = it.message) },
            )
        }
    }

    companion object {
        fun factory(auth: AuthRepository) = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = LoginViewModel(auth) as T
        }
    }
}
