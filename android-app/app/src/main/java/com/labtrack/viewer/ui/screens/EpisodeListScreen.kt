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
import androidx.compose.material3.Button
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
import com.labtrack.viewer.data.models.EpisodeData
import com.labtrack.viewer.data.models.EpisodeRow
import com.labtrack.viewer.ui.components.PatientHeaderCard
import com.labtrack.viewer.data.models.PatientResult
import com.labtrack.viewer.viewmodel.SearchViewModel
import com.labtrack.viewer.viewmodel.UiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EpisodeListScreen(
    searchViewModel: SearchViewModel,
    onEpisodeSelected: (Int) -> Unit,
    onLoadAll: () -> Unit,
    onBack: () -> Unit
) {
    val episodeListState by searchViewModel.episodeListState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Lab Episodes") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back")
                    }
                }
            )
        }
    ) { padding ->
        when (val state = episodeListState) {
            is UiState.Success -> {
                val data = state.data
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                ) {
                    // Patient header
                    item {
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(16.dp),
                            colors = CardDefaults.cardColors(
                                containerColor = MaterialTheme.colorScheme.surfaceVariant
                            )
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text("Patient: ${data.patientName}", fontWeight = FontWeight.Bold)
                                Text("MRN: ${data.patientId}")
                                Text("DOB: ${data.dob}")
                            }
                        }
                    }

                    // Load all button
                    item {
                        Button(
                            onClick = onLoadAll,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 16.dp, vertical = 8.dp)
                        ) {
                            Text("Load All Episodes")
                        }
                    }

                    // Episode rows
                    itemsIndexed(data.rows) { index, row ->
                        EpisodeCard(
                            index = index + 1,
                            row = row,
                            onClick = { onEpisodeSelected(row.rowIndex) }
                        )
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
private fun EpisodeCard(index: Int, row: EpisodeRow, onClick: () -> Unit) {
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
                    text = row.episodeNumber.ifBlank { "Episode ${row.rowIndex}" },
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(4.dp))
                if (row.doctor.isNotBlank()) {
                    Text("Doctor: ${row.doctor}", style = MaterialTheme.typography.bodySmall)
                }
                Text("Collected: ${row.collectionDatetime}", style = MaterialTheme.typography.bodySmall)
                val testNames = row.clickable.joinToString(", ") { it.text }
                if (testNames.isNotBlank()) {
                    Text("Tests: $testNames", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}
