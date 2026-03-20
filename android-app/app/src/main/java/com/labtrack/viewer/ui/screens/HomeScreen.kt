package com.labtrack.viewer.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.labtrack.viewer.ui.components.LoadingOverlay
import com.labtrack.viewer.viewmodel.SearchViewModel
import com.labtrack.viewer.viewmodel.UiState

enum class SearchMode(val label: String) {
    SPECIMEN("Specimen"),
    EPISODE("Episode"),
    NAME("Name"),
    HOSPITAL_MRN("Hospital MRN"),
    FOLDER("Folder"),
    RECENT("Recent")
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    searchViewModel: SearchViewModel,
    onScanClick: () -> Unit,
    onPatientListReady: () -> Unit,
    onResultsReady: () -> Unit,
    onEpisodeListReady: () -> Unit,
    onClearSession: () -> Unit
) {
    var selectedTab by rememberSaveable { mutableIntStateOf(0) }
    var searchInput by rememberSaveable { mutableStateOf("") }
    var nameInput by rememberSaveable { mutableStateOf("") }

    val searchState by searchViewModel.searchState.collectAsState()
    val patientListState by searchViewModel.patientListState.collectAsState()
    val episodeListState by searchViewModel.episodeListState.collectAsState()
    val multiResultsState by searchViewModel.multiResultsState.collectAsState()

    val snackbarHostState = remember { SnackbarHostState() }

    // Reset stale state when returning to this screen
    LaunchedEffect(Unit) {
        searchViewModel.onReturnToHome()
    }

    // Navigate on NEW state transitions only (key = state identity, not just type)
    // By resetting to Idle in onReturnToHome(), the LaunchedEffect won't re-fire
    // on back navigation since the state will be Idle, not Success.
    LaunchedEffect(searchState) {
        when (searchState) {
            is UiState.Success -> onResultsReady()
            is UiState.Error -> snackbarHostState.showSnackbar(
                (searchState as UiState.Error).message
            )
            else -> {}
        }
    }
    LaunchedEffect(patientListState) {
        if (patientListState is UiState.Success) onPatientListReady()
    }
    LaunchedEffect(episodeListState) {
        if (episodeListState is UiState.Success) onEpisodeListReady()
    }
    LaunchedEffect(multiResultsState) {
        when (multiResultsState) {
            is UiState.Success -> onResultsReady()
            is UiState.Error -> snackbarHostState.showSnackbar(
                (multiResultsState as UiState.Error).message
            )
            else -> {}
        }
    }

    val modes = SearchMode.entries.toTypedArray()
    val isLoading = searchState is UiState.Loading
            || patientListState is UiState.Loading
            || episodeListState is UiState.Loading
            || multiResultsState is UiState.Loading

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("LabTrack Viewer") },
                actions = {
                    IconButton(onClick = onScanClick) {
                        Icon(Icons.Default.CameraAlt, contentDescription = "Scan barcode")
                    }
                    TextButton(onClick = onClearSession) {
                        Text("Logout")
                    }
                }
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
        ) {
            ScrollableTabRow(selectedTabIndex = selectedTab) {
                modes.forEachIndexed { index, mode ->
                    Tab(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        text = { Text(mode.label) }
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            Column(modifier = Modifier.padding(horizontal = 16.dp)) {
                when (modes[selectedTab]) {
                    SearchMode.SPECIMEN -> {
                        OutlinedTextField(
                            value = searchInput,
                            onValueChange = { searchInput = it },
                            label = { Text("Specimen ID") },
                            singleLine = true,
                            enabled = !isLoading,
                            modifier = Modifier.fillMaxWidth(),
                            trailingIcon = {
                                IconButton(onClick = onScanClick) {
                                    Icon(Icons.Default.CameraAlt, "Scan")
                                }
                            }
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        SearchButton("Search", isLoading) {
                            searchViewModel.searchBySpecimen(searchInput.trim())
                        }
                    }

                    SearchMode.EPISODE -> {
                        OutlinedTextField(
                            value = searchInput,
                            onValueChange = { searchInput = it },
                            label = { Text("Episode Number") },
                            singleLine = true,
                            enabled = !isLoading,
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        SearchButton("Search", isLoading) {
                            searchViewModel.searchByEpisode(searchInput.trim())
                        }
                    }

                    SearchMode.NAME -> {
                        OutlinedTextField(
                            value = searchInput,
                            onValueChange = { searchInput = it },
                            label = { Text("Surname") },
                            singleLine = true,
                            enabled = !isLoading,
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedTextField(
                            value = nameInput,
                            onValueChange = { nameInput = it },
                            label = { Text("Given Name (optional)") },
                            singleLine = true,
                            enabled = !isLoading,
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        SearchButton("Search", isLoading) {
                            searchViewModel.searchByName(searchInput.trim(), nameInput.trim())
                        }
                    }

                    SearchMode.HOSPITAL_MRN -> {
                        OutlinedTextField(
                            value = searchInput,
                            onValueChange = { searchInput = it },
                            label = { Text("Hospital MRN") },
                            singleLine = true,
                            enabled = !isLoading,
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        SearchButton("Search", isLoading) {
                            searchViewModel.searchByHospitalMrn(searchInput.trim())
                        }
                    }

                    SearchMode.FOLDER -> {
                        OutlinedTextField(
                            value = searchInput,
                            onValueChange = { searchInput = it },
                            label = { Text("Hospital Folder Number") },
                            singleLine = true,
                            enabled = !isLoading,
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        SearchButton("Search", isLoading) {
                            searchViewModel.searchByFolder(searchInput.trim())
                        }
                    }

                    SearchMode.RECENT -> {
                        Text(
                            "Fetch most recent results from worklist.",
                            style = MaterialTheme.typography.bodyMedium
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        SearchButton("Load Recent", isLoading) {
                            searchViewModel.getRecentResults()
                        }
                    }
                }
            }

            if (isLoading) {
                Spacer(modifier = Modifier.height(32.dp))
                LoadingOverlay("Searching...")
            }
        }
    }
}

@Composable
private fun SearchButton(text: String, isLoading: Boolean, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        enabled = !isLoading
    ) {
        Icon(Icons.Default.Search, contentDescription = null)
        Spacer(modifier = Modifier.width(8.dp))
        Text(text)
    }
}
