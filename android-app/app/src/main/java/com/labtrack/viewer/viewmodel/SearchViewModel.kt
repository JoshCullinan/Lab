package com.labtrack.viewer.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.labtrack.viewer.data.models.EpisodeData
import com.labtrack.viewer.data.models.PatientResult
import com.labtrack.viewer.data.models.PatientSearchHit
import com.labtrack.viewer.domain.auth.AuthManager
import com.labtrack.viewer.domain.auth.withAuthRetry
import com.labtrack.viewer.domain.results.ResultsManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SearchViewModel @Inject constructor(
    private val resultsManager: ResultsManager,
    private val authManager: AuthManager
) : ViewModel() {

    // Single result state (specimen, episode, hospital-mrn, patient-open)
    private val _searchState = MutableStateFlow<UiState<PatientResult?>>(UiState.Idle)
    val searchState: StateFlow<UiState<PatientResult?>> = _searchState.asStateFlow()

    // Patient list state (name search, folder search)
    private val _patientListState = MutableStateFlow<UiState<List<PatientSearchHit>>>(UiState.Idle)
    val patientListState: StateFlow<UiState<List<PatientSearchHit>>> = _patientListState.asStateFlow()

    // Episode list state (folder flow)
    private val _episodeListState = MutableStateFlow<UiState<EpisodeData>>(UiState.Idle)
    val episodeListState: StateFlow<UiState<EpisodeData>> = _episodeListState.asStateFlow()

    // Multi-results state (recent, load-all)
    private val _multiResultsState = MutableStateFlow<UiState<List<PatientResult>>>(UiState.Idle)
    val multiResultsState: StateFlow<UiState<List<PatientResult>>> = _multiResultsState.asStateFlow()

    // Track whether the current patient list came from folder mode
    private val _isFolderMode = MutableStateFlow(false)
    val isFolderMode: StateFlow<Boolean> = _isFolderMode.asStateFlow()

    // Cached episode data for loading individual episodes
    private var currentEpisodeData: EpisodeData? = null

    // ── State management ────────────────────────────────────────────────────

    /** Reset all result states. Call before starting a new search. */
    private fun resetResultStates() {
        _searchState.value = UiState.Idle
        _multiResultsState.value = UiState.Idle
    }

    /** Called when navigating back to HomeScreen to prevent re-navigation loops. */
    fun onReturnToHome() {
        _searchState.value = UiState.Idle
        _patientListState.value = UiState.Idle
        _episodeListState.value = UiState.Idle
        _multiResultsState.value = UiState.Idle
    }

    // ── Search methods ──────────────────────────────────────────────────────

    fun searchBySpecimen(specimenId: String) {
        _isFolderMode.value = false
        resetResultStates()
        viewModelScope.launch {
            _searchState.value = UiState.Loading
            try {
                val result = withAuthRetry(authManager) {
                    resultsManager.searchBySpecimen(specimenId)
                }
                _searchState.value = UiState.Success(result)
            } catch (e: Exception) {
                _searchState.value = UiState.Error(e.message ?: "Search failed")
            }
        }
    }

    fun searchByEpisode(episodeId: String) {
        _isFolderMode.value = false
        resetResultStates()
        viewModelScope.launch {
            _searchState.value = UiState.Loading
            try {
                val result = withAuthRetry(authManager) {
                    resultsManager.searchByEpisode(episodeId)
                }
                _searchState.value = UiState.Success(result)
            } catch (e: Exception) {
                _searchState.value = UiState.Error(e.message ?: "Search failed")
            }
        }
    }

    fun searchByHospitalMrn(hospitalMrn: String) {
        _isFolderMode.value = false
        resetResultStates()
        viewModelScope.launch {
            _searchState.value = UiState.Loading
            try {
                val result = withAuthRetry(authManager) {
                    resultsManager.searchByHospitalMrn(hospitalMrn)
                }
                _searchState.value = UiState.Success(result)
            } catch (e: Exception) {
                _searchState.value = UiState.Error(e.message ?: "Search failed")
            }
        }
    }

    fun searchByName(surname: String, givenName: String) {
        _isFolderMode.value = false
        resetResultStates()
        viewModelScope.launch {
            _patientListState.value = UiState.Loading
            try {
                val hits = withAuthRetry(authManager) {
                    resultsManager.searchByName(surname, givenName)
                }
                _patientListState.value = UiState.Success(hits)
            } catch (e: Exception) {
                _patientListState.value = UiState.Error(e.message ?: "Search failed")
            }
        }
    }

    fun searchByFolder(folderNumber: String) {
        _isFolderMode.value = true
        resetResultStates()
        viewModelScope.launch {
            _patientListState.value = UiState.Loading
            try {
                val patients = withAuthRetry(authManager) {
                    resultsManager.searchPatientsByHospitalMrn(folderNumber)
                }
                _patientListState.value = UiState.Success(patients)
            } catch (e: Exception) {
                _patientListState.value = UiState.Error(e.message ?: "Search failed")
            }
        }
    }

    fun openPatient(hit: PatientSearchHit) {
        resetResultStates()
        viewModelScope.launch {
            _searchState.value = UiState.Loading
            try {
                val result = withAuthRetry(authManager) {
                    resultsManager.openPatientByHit(hit, "${hit.surname}, ${hit.givenName}")
                }
                _searchState.value = UiState.Success(result)
            } catch (e: Exception) {
                _searchState.value = UiState.Error(e.message ?: "Failed to load patient")
            }
        }
    }

    fun listEpisodes(hit: PatientSearchHit) {
        viewModelScope.launch {
            _episodeListState.value = UiState.Loading
            try {
                val data = resultsManager.listEpisodesForPatient(hit.rowIndex)
                if (data != null) {
                    currentEpisodeData = data
                    _episodeListState.value = UiState.Success(data)
                } else {
                    _episodeListState.value = UiState.Error("Failed to load episodes")
                }
            } catch (e: Exception) {
                _episodeListState.value = UiState.Error(e.message ?: "Failed to load episodes")
            }
        }
    }

    fun loadEpisodeResults(rowIndex: Int) {
        val episodeData = currentEpisodeData
        if (episodeData == null) {
            _searchState.value = UiState.Error("Episode data not loaded")
            return
        }
        resetResultStates()
        viewModelScope.launch {
            _searchState.value = UiState.Loading
            try {
                val result = withAuthRetry(authManager) {
                    resultsManager.loadEpisodeResults(rowIndex, episodeData)
                }
                _searchState.value = UiState.Success(result)
            } catch (e: Exception) {
                _searchState.value = UiState.Error(e.message ?: "Failed to load results")
            }
        }
    }

    fun loadAllEpisodeResults() {
        val episodeData = currentEpisodeData
        if (episodeData == null) {
            _multiResultsState.value = UiState.Error("Episode data not loaded")
            return
        }
        resetResultStates()
        viewModelScope.launch {
            _multiResultsState.value = UiState.Loading
            try {
                val allResults = mutableListOf<PatientResult>()
                for (row in episodeData.rows) {
                    val result = withAuthRetry(authManager) {
                        resultsManager.loadEpisodeResults(row.rowIndex, episodeData)
                    }
                    if (result != null) allResults.add(result)
                }
                _multiResultsState.value = UiState.Success(allResults)
            } catch (e: Exception) {
                _multiResultsState.value = UiState.Error(e.message ?: "Failed to load all episodes")
            }
        }
    }

    fun getRecentResults() {
        resetResultStates()
        viewModelScope.launch {
            _multiResultsState.value = UiState.Loading
            try {
                // Recent results would require worklist support — placeholder
                _multiResultsState.value = UiState.Success(emptyList())
            } catch (e: Exception) {
                _multiResultsState.value = UiState.Error(e.message ?: "Failed to load recent results")
            }
        }
    }
}
