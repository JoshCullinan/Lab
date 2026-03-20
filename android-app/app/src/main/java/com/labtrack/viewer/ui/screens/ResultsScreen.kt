package com.labtrack.viewer.ui.screens

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.labtrack.viewer.data.models.PatientResult
import com.labtrack.viewer.ui.components.LoadingOverlay
import com.labtrack.viewer.ui.components.PatientHeaderCard
import com.labtrack.viewer.ui.components.ResultsTable
import com.labtrack.viewer.viewmodel.SearchViewModel
import com.labtrack.viewer.viewmodel.UiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ResultsScreen(
    searchViewModel: SearchViewModel,
    onBack: () -> Unit
) {
    val searchState by searchViewModel.searchState.collectAsState()
    val multiResultsState by searchViewModel.multiResultsState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Results") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back")
                    }
                }
            )
        }
    ) { padding ->
        when {
            // Multiple results (recent, load-all)
            multiResultsState is UiState.Success -> {
                val results = (multiResultsState as UiState.Success<List<PatientResult>>).data
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                ) {
                    items(results) { result ->
                        PatientHeaderCard(
                            result = result,
                            modifier = Modifier.padding(16.dp)
                        )
                        ResultsTable(
                            tests = result.tests,
                            specimenId = result.specimenId
                        )
                        HorizontalDivider(
                            modifier = Modifier.padding(vertical = 16.dp),
                            thickness = 2.dp
                        )
                    }
                }
            }

            // Single result
            searchState is UiState.Success -> {
                val result = (searchState as UiState.Success<PatientResult?>).data
                if (result != null) {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding)
                    ) {
                        item {
                            PatientHeaderCard(
                                result = result,
                                modifier = Modifier.padding(16.dp)
                            )
                        }
                        item {
                            ResultsTable(
                                tests = result.tests,
                                specimenId = result.specimenId
                            )
                        }
                    }
                } else {
                    Text(
                        "No results found.",
                        modifier = Modifier.padding(padding).padding(16.dp),
                        style = MaterialTheme.typography.bodyLarge
                    )
                }
            }

            searchState is UiState.Loading || multiResultsState is UiState.Loading -> {
                LoadingOverlay("Loading results...")
            }

            searchState is UiState.Error -> {
                Text(
                    "Error: ${(searchState as UiState.Error).message}",
                    modifier = Modifier.padding(padding).padding(16.dp),
                    color = MaterialTheme.colorScheme.error
                )
            }

            else -> {
                Text(
                    "No data.",
                    modifier = Modifier.padding(padding).padding(16.dp)
                )
            }
        }
    }
}
