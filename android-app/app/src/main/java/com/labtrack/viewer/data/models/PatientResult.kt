package com.labtrack.viewer.data.models

data class PatientResult(
    val patientName: String,
    val patientId: String,
    val specimenId: String,
    val episode: String,
    val requestingDoctor: String,
    val dob: String,
    val status: String,
    val collectionDatetime: String,
    val resultDatetime: String,
    val tests: List<TestResult> = emptyList()
)
