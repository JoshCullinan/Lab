package com.labtrack.viewer.data.config

/**
 * All regex patterns ported from core/results.py and core/barcode.py.
 */
object Patterns {
    // ── Specimen ID (barcode) ───────────────────────────────────────────────
    // Accept any alphanumeric string (with optional hyphen) of 6-20 chars that
    // contains at least one digit. TrakCare validates server-side.
    // Covers formats like: W25-123456, AKDM0811NOF, AKDM0811P, AB12345HOF, etc.
    val SPECIMEN_ID = Regex("[A-Za-z0-9][A-Za-z0-9-]{4,18}[A-Za-z0-9]")

    // ── PDF line parsing ────────────────────────────────────────────────────

    // Unit pattern: allows parentheses for units like Log(copies/mL), x10^9/L
    private const val UNIT_PAT = """[a-zA-Z\u00b5/%][/a-zA-Z\u00b5\u00b2%0-9.*^()]*"""

    // 4-field: Name Value Unit RefRange
    val PDF_LINE_RE = Regex(
        """^(?<name>.+?)\s+(?<value>[><]?\d[\d.]*\s*[HL]?)\s+(?<unit>$UNIT_PAT)\s+(?<range>\d[\d.]*\s*-\s*\d[\d.]*\s*)?$"""
    )

    // 4-field with single-sided ref range
    val PDF_LINE_RE_SINGLESIDED = Regex(
        """^(?<name>.+?)\s+(?<value>[><]?\d[\d.]*\s*[HL]?)\s+(?<unit>$UNIT_PAT)\s+(?<range>[<>]\d[\d.]*\s*)?$"""
    )

    // 2-field: Name Value (indices like "2+" or "Not detected")
    val PDF_LINE_RE2 = Regex(
        """^(?<name>.+?)\s+(?<value>Not detected|\d+[+])\s*$"""
    )

    // 3-field: Name Value Unit (no ref range)
    val PDF_LINE_RE3 = Regex(
        """^(?<name>.+?)\s+(?<value>[><]?\d[\d.]*\s*[HL]?)\s+(?<unit>$UNIT_PAT)\s*$"""
    )

    // 3-field with compound unit (e.g. "eGFR (MDRD) 51 mL/min/1.73 m²")
    val PDF_LINE_RE_COMPOUND = Regex(
        """^(?<name>.+?)\s+(?<value>[><]?\d[\d.]*\s*[HL]?)\s+(?<unit>mL/min/[\d.]+\s*\S*)\s*$"""
    )

    // 2-field: Name bare-numeric-value (no unit)
    val PDF_LINE_RE_BARE = Regex(
        """^(?<name>.+?)\s+(?<value>[><]?\d[\d.]+)\s*$"""
    )

    // ── Flag extraction ─────────────────────────────────────────────────────
    val FLAG_SUFFIX = Regex("""\s([HL])\s*$""")

    // ── Ref range parsing ───────────────────────────────────────────────────
    val REF_RANGE_DUAL = Regex("""^([\d.]+)\s*-\s*([\d.]+)\s*$""")
    val REF_RANGE_SINGLE = Regex("""^([<>])([\d.]+)\s*$""")
}
