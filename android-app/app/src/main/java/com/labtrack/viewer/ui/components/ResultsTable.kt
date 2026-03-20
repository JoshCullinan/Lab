package com.labtrack.viewer.ui.components

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.labtrack.viewer.data.models.TestResult

/**
 * LazyColumn with color-coded test results — matching CLI display.py table.
 */
@Composable
fun ResultsTable(
    tests: List<TestResult>,
    specimenId: String,
    modifier: Modifier = Modifier
) {
    val regularTests = tests.filter { it.testName != "Culture Report" }
    val cultureReports = tests.filter { it.testName == "Culture Report" }

    Column(modifier = modifier.fillMaxWidth()) {
        if (regularTests.isNotEmpty()) {
            Text(
                text = "Results - $specimenId",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
            )

            // Header row
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("Test", Modifier.weight(3f), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
                Text("Value", Modifier.weight(1.5f), fontWeight = FontWeight.Bold, textAlign = TextAlign.End, style = MaterialTheme.typography.bodySmall)
                Text("Unit", Modifier.weight(1.5f), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(start = 8.dp))
                Text("Ref", Modifier.weight(1.5f), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
                Text("", Modifier.width(40.dp), style = MaterialTheme.typography.bodySmall)
            }
            HorizontalDivider()

            regularTests.forEach { test ->
                ResultRow(test)
                HorizontalDivider(thickness = 0.5.dp, color = MaterialTheme.colorScheme.outlineVariant)
            }
        }

        // Culture reports as cards
        cultureReports.forEach { cr ->
            Spacer(modifier = Modifier.height(8.dp))
            CultureReportCard(cr)
        }
    }
}

@Composable
private fun ResultRow(test: TestResult) {
    val valueColor = flagValueColor(test.flag)

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = test.testName,
            modifier = Modifier.weight(3f),
            style = MaterialTheme.typography.bodyMedium
        )
        Text(
            text = test.value,
            modifier = Modifier.weight(1.5f),
            textAlign = TextAlign.End,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = if (test.flag != null) FontWeight.Bold else FontWeight.Normal,
            color = valueColor
        )
        Text(
            text = test.unit,
            modifier = Modifier.weight(1.5f).padding(start = 8.dp),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = test.referenceRange,
            modifier = Modifier.weight(1.5f),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        FlagBadge(
            flag = test.flag,
            modifier = Modifier.width(40.dp)
        )
    }
}

@Composable
private fun CultureReportCard(test: TestResult) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = "Culture Report",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = test.value,
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}
