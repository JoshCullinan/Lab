package com.labtrack.viewer.data.models

data class EpisodeData(
    val patientName: String,
    val patientId: String,
    val episode: String,
    val dob: String,
    val doctor: String,
    val collectionDatetime: String,
    val clickable: List<ClickableLink>,
    val pending: List<String>,
    val rows: List<EpisodeRow>
)
