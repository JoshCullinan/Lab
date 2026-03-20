package com.labtrack.viewer.data.models

data class TestResult(
    val testName: String,
    val value: String,
    val unit: String,
    val referenceRange: String,
    val flag: String?,          // "H", "L", "CRITICAL", "PENDING", or null
    val collectionDatetime: String
)
