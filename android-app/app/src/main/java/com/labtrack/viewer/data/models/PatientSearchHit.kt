package com.labtrack.viewer.data.models

data class PatientSearchHit(
    val rowIndex: Int,
    val mrn: String,
    val surname: String,
    val givenName: String,
    val dob: String,
    val episode: String
)
