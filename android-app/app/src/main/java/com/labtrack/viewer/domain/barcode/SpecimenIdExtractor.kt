package com.labtrack.viewer.domain.barcode

import com.labtrack.viewer.data.config.Patterns

/**
 * Port of BarcodeScanner._extract_specimen_id() from core/barcode.py.
 * Validates and cleans a raw barcode string into an NHLS specimen ID.
 */
object SpecimenIdExtractor {

    fun extract(rawBarcode: String): String? {
        val raw = rawBarcode.trim()
        if (raw.length < 6 || raw.length > 20) return null

        // Must be alphanumeric (with optional hyphens) and contain at least one digit
        val match = Patterns.SPECIMEN_ID.find(raw) ?: return null
        val value = match.value
        if (value.none { it.isDigit() }) return null

        return value.uppercase()
    }
}
