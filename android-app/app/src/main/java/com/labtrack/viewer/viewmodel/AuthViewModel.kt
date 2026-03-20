package com.labtrack.viewer.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.labtrack.viewer.data.repository.AuthRepository
import com.labtrack.viewer.domain.auth.AuthManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import javax.inject.Inject

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authRepo: AuthRepository,
    private val authManager: AuthManager
) : ViewModel() {

    private val _loginState = MutableStateFlow<UiState<Boolean>>(UiState.Idle)
    val loginState: StateFlow<UiState<Boolean>> = _loginState.asStateFlow()

    fun hasCredentials(): Boolean = authRepo.hasCredentials()

    fun login(username: String, password: String) {
        viewModelScope.launch {
            _loginState.value = UiState.Loading
            try {
                // Save credentials on IO thread (EncryptedSharedPreferences does disk I/O)
                withContext(Dispatchers.IO) {
                    authRepo.saveCredentials(username, password)
                }

                // WebView login (internally dispatches to Main for WebView ops)
                authManager.login()

                _loginState.value = UiState.Success(true)
            } catch (e: Exception) {
                withContext(Dispatchers.IO) {
                    authRepo.clearCredentials()
                }
                _loginState.value = UiState.Error(
                    e.message ?: "Login failed. Check your credentials and try again."
                )
            }
        }
    }

    fun clearSession() {
        viewModelScope.launch {
            authManager.clearSession()
            _loginState.value = UiState.Idle
        }
    }

    fun resetLoginState() {
        _loginState.value = UiState.Idle
    }
}
