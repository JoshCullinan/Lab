package com.labtrack.viewer.data.models

data class EpisodeRow(
    val rowIndex: Int,
    val episodeNumber: String,
    val doctor: String,
    val collectionDatetime: String,
    val pdfSelector: String,
    val clickable: List<ClickableLink>,
    val pending: List<String>
)

data class ClickableLink(
    val id: String,
    val text: String
)
