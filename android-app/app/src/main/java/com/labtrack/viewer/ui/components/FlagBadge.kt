package com.labtrack.viewer.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.labtrack.viewer.ui.theme.FlagCritical
import com.labtrack.viewer.ui.theme.FlagHigh
import com.labtrack.viewer.ui.theme.FlagPending

/**
 * Colored flag badge matching CLI display.py flag formatting.
 */
@Composable
fun FlagBadge(flag: String?, modifier: Modifier = Modifier) {
    if (flag.isNullOrBlank()) return

    val (text, bgColor) = when (flag.uppercase()) {
        "CRITICAL" -> "CRIT" to FlagCritical
        "H", "HIGH" -> "H" to FlagHigh
        "L", "LOW" -> "L" to FlagHigh
        "PENDING", "P" -> "P" to FlagPending
        "ABNORMAL" -> "!" to FlagCritical
        else -> flag to Color.Gray
    }

    Box(
        modifier = modifier
            .background(
                color = bgColor.copy(alpha = 0.2f),
                shape = RoundedCornerShape(4.dp)
            )
            .padding(horizontal = 6.dp, vertical = 2.dp)
    ) {
        Text(
            text = text,
            color = bgColor,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            style = MaterialTheme.typography.labelLarge
        )
    }
}

fun flagValueColor(flag: String?): Color {
    if (flag.isNullOrBlank()) return Color.Unspecified
    return when (flag.uppercase()) {
        "CRITICAL", "ABNORMAL" -> FlagCritical
        "H", "HIGH", "L", "LOW" -> FlagHigh
        "PENDING", "P" -> FlagPending
        else -> Color.Unspecified
    }
}
