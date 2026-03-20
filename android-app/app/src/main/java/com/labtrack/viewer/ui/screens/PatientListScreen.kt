package com.labtrack.viewer.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.labtrack.viewer.data.models.PatientSearchHit
import com.labtrack.viewer.viewmodel.SearchViewModel
import com.labtrack.viewer.viewmodel.UiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PatientListScreen(
    searchViewModel: SearchViewModel,
    onPatientSelected: (PatientSearchHit) -> Unit,
    onPatientFolderSelected: (PatientSearchHit) -> Unit,
    onBack: () -> Unit
) {
    val patientListState by searchViewModel.patientListState.collectAsState()
    val isFolderMode by searchViewModel.isFolderMode.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Patient Search Results") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back")
                    }
                }
            )
        }
    ) { padding ->
        when (val state = patientListState) {
            is UiState.Success -> {
                val patients = state.data
                if (patients.isEmpty()) {
                    Text(
                        "No patients found.",
                        modifier = Modifier.padding(padding).padding(16.dp),
                        style = MaterialTheme.typography.bodyLarge
                    )
                } else {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding)
                    ) {
                        itemsIndexed(patients) { index, hit ->
                            PatientCard(
                                index = index + 1,
                                hit = hit,
                                onClick = {
                                    if (isFolderMode) onPatientFolderSelected(hit)
                                    else onPatientSelected(hit)
                                }
                            )
                        }
                    }
                }
            }
            else -> {
                Text(
                    "Loading...",
                    modifier = Modifier.padding(padding).padding(16.dp)
                )
            }
        }
    }
}

@Composable
private fun PatientCard(index: Int, hit: PatientSearchHit, onClick: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp)
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Row(modifier = Modifier.padding(16.dp)) {
            Text(
                text = "$index.",
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(end = 12.dp),
                color = MaterialTheme.colorScheme.primary
            )
            Column {
                Text(
                    text = "${hit.surname}, ${hit.givenName}",
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text("MRN: ${hit.mrn}", style = MaterialTheme.typography.bodySmall)
                Text("DOB: ${hit.dob}", style = MaterialTheme.typography.bodySmall)
                if (hit.episode.isNotBlank()) {
                    Text("Episode: ${hit.episode}", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}
