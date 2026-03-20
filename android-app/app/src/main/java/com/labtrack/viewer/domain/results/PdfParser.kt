package com.labtrack.viewer.domain.results

import android.content.Context
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.labtrack.viewer.data.config.Patterns
import com.labtrack.viewer.data.models.TestResult
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.text.PDFTextStripper
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import java.io.ByteArrayInputStream
import java.io.File

/**
 * Port of PDF parsing from core/results.py.
 * Fast path: PDFBox-Android text extraction (replaces pdfplumber).
 * Fallback: Android PdfRenderer + ML Kit OCR (replaces pytesseract + fitz).
 */
class PdfParser(private val context: Context) {

    // ── Section header sets (verbatim from Python) ──────────────────────────

    private val sectionHeaders = setOf(
        "blood chemistry", "liver function tests", "lipids", "inflammatory markers",
        "haematinics", "thyroid function tests", "indices", "indices in serum",
        "creatinine and estimated gfr",
        "fluid chemistry",
        "cdarv", "full blood count",
        "hiv molecular investigations", "hiv viral load"
    )

    private val microSectionHeaders = setOf(
        "gram stain", "bacterial culture", "tb-naat"
    )

    private val advisoryHeaders = setOf(
        "cardiovascular risk", "disclaimer",
        "evaluation of effusion results",
        "cd4 arv comment", "comment",
        "lower respiratory tract infection",
        "systemic bacterial infection",
        "systemic bacterial infection / sepsis"
    )

    // ── Public API ──────────────────────────────────────────────────────────

    suspend fun parsePdf(pdfBytes: ByteArray, collectionDt: String): List<TestResult> {
        var tests = parsePdfText(pdfBytes, collectionDt)
        if (tests.isEmpty()) {
            tests = parsePdfOcr(pdfBytes, collectionDt)
        }
        return tests
    }

    // ── Fast path: PDFBox text extraction ───────────────────────────────────

    private suspend fun parsePdfText(
        pdfBytes: ByteArray,
        collectionDt: String
    ): List<TestResult> = withContext(Dispatchers.IO) {
        try {
            val doc = PDDocument.load(ByteArrayInputStream(pdfBytes))
            val stripper = PDFTextStripper()
            val text = stripper.getText(doc)
            doc.close()
            if (text.isBlank()) return@withContext emptyList()
            parseTextContent(text, collectionDt)
        } catch (e: Exception) {
            emptyList()
        }
    }

    // ── Fallback: PdfRenderer + ML Kit OCR ──────────────────────────────────

    private suspend fun parsePdfOcr(
        pdfBytes: ByteArray,
        collectionDt: String
    ): List<TestResult> = withContext(Dispatchers.IO) {
        val tempFile = File(context.cacheDir, "temp_ocr_${System.nanoTime()}.pdf")
        try {
            tempFile.writeBytes(pdfBytes)

            val fd = ParcelFileDescriptor.open(tempFile, ParcelFileDescriptor.MODE_READ_ONLY)
            val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
            val allText = StringBuilder()

            try {
                val renderer = PdfRenderer(fd)
                try {
                    for (i in 0 until renderer.pageCount) {
                        val page = renderer.openPage(i)
                        // Render at 2x scale (matching Python fitz.Matrix(2.0, 2.0))
                        val bitmap = Bitmap.createBitmap(
                            page.width * 2, page.height * 2, Bitmap.Config.ARGB_8888
                        )
                        page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                        page.close()

                        val inputImage = InputImage.fromBitmap(bitmap, 0)
                        val result = recognizer.process(inputImage).await()
                        allText.append(result.text).append("\n")
                        bitmap.recycle()
                    }
                } finally {
                    renderer.close()
                }
            } finally {
                fd.close()
            }

            if (allText.isBlank()) return@withContext emptyList()
            parseTextContent(allText.toString(), collectionDt)
        } catch (e: Exception) {
            emptyList()
        } finally {
            tempFile.delete()
        }
    }

    // ── Text parsing state machine (verbatim port from Python) ──────────────

    private fun preprocessText(text: String): String {
        var result = text
        // Fix superscript 9 in units like "x 10 /L" → "x10^9/L"
        result = result.replace(Regex(" x 10 /L"), " x10^9/L")
        // Fix superscript 2 in "mL/min/1.73 m" → "mL/min/1.73m²"
        result = result.replace(Regex("mL/min/([\\d.]+)\\s+m\\b"), "mL/min/$1m²")
        return result
    }

    fun parseTextContent(rawText: String, collectionDt: String): List<TestResult> {
        val text = preprocessText(rawText)
        val tests = mutableListOf<TestResult>()
        var inResultsSection = false
        var inMicroSection = false
        val microLines = mutableListOf<String>()
        var microName = ""

        fun flushMicro() {
            if (microLines.isNotEmpty()) {
                tests.add(
                    TestResult(
                        testName = microName,
                        value = microLines.joinToString("\n"),
                        unit = "", referenceRange = "", flag = null,
                        collectionDatetime = collectionDt
                    )
                )
            }
            microLines.clear()
            microName = ""
            inMicroSection = false
        }

        for (raw in text.split('\n')) {
            val line = raw.trim()
            if (line.isEmpty()) continue
            if (isSkipLine(line)) continue

            // ── Section transitions ──
            if (isSectionHeader(line, sectionHeaders)) {
                flushMicro()
                inResultsSection = true
                continue
            }
            if (isSectionHeader(line, microSectionHeaders)) {
                flushMicro()
                inMicroSection = true
                microName = line.replace(Regex(":<.*?>$"), "").trim().trimEnd(':')
                inResultsSection = false
                continue
            }
            if (isAdvisoryHeader(line)) {
                flushMicro()
                inResultsSection = false
                continue
            }

            // ── Micro section: accumulate free text ──
            if (inMicroSection) {
                microLines.add(line)
                continue
            }
            if (!inResultsSection) continue

            // ── Standard result line matching ──
            if (tryMatch4Field(line, collectionDt, tests)) continue
            if (tryMatch4FieldSingleSided(line, collectionDt, tests)) continue
            if (tryMatch2Field(line, collectionDt, tests)) continue
            if (tryMatch3Field(line, collectionDt, tests)) continue
            if (tryMatchCompound(line, collectionDt, tests)) continue
            tryMatchBare(line, collectionDt, tests)
        }

        flushMicro()
        return tests
    }

    // ── Line matchers ───────────────────────────────────────────────────────

    private fun tryMatch4Field(line: String, collectionDt: String, tests: MutableList<TestResult>): Boolean {
        val m = Patterns.PDF_LINE_RE.find(line) ?: return false
        val (flag, value) = extractFlag(m.groups["value"]!!.value.trim())
        tests.add(TestResult(
            testName = m.groups["name"]!!.value.trim(),
            value = value,
            unit = m.groups["unit"]!!.value.trim(),
            referenceRange = (m.groups["range"]?.value ?: "").trim(),
            flag = flag,
            collectionDatetime = collectionDt
        ))
        return true
    }

    private fun tryMatch4FieldSingleSided(line: String, collectionDt: String, tests: MutableList<TestResult>): Boolean {
        val m = Patterns.PDF_LINE_RE_SINGLESIDED.find(line) ?: return false
        val (flag, value) = extractFlag(m.groups["value"]!!.value.trim())
        tests.add(TestResult(
            testName = m.groups["name"]!!.value.trim(),
            value = value,
            unit = m.groups["unit"]!!.value.trim(),
            referenceRange = (m.groups["range"]?.value ?: "").trim(),
            flag = flag,
            collectionDatetime = collectionDt
        ))
        return true
    }

    private fun tryMatch2Field(line: String, collectionDt: String, tests: MutableList<TestResult>): Boolean {
        val m = Patterns.PDF_LINE_RE2.find(line) ?: return false
        tests.add(TestResult(
            testName = m.groups["name"]!!.value.trim(),
            value = m.groups["value"]!!.value.trim(),
            unit = "", referenceRange = "", flag = null,
            collectionDatetime = collectionDt
        ))
        return true
    }

    private fun tryMatch3Field(line: String, collectionDt: String, tests: MutableList<TestResult>): Boolean {
        val m = Patterns.PDF_LINE_RE3.find(line) ?: return false
        val name = m.groups["name"]!!.value.trim()
        if (Regex("\\d\\s-\\s*$").containsMatchIn(name)) return true // skip partial range lines
        val (flag, value) = extractFlag(m.groups["value"]!!.value.trim())
        tests.add(TestResult(
            testName = name,
            value = value,
            unit = m.groups["unit"]!!.value.trim(),
            referenceRange = "", flag = flag,
            collectionDatetime = collectionDt
        ))
        return true
    }

    private fun tryMatchCompound(line: String, collectionDt: String, tests: MutableList<TestResult>): Boolean {
        val m = Patterns.PDF_LINE_RE_COMPOUND.find(line) ?: return false
        val (flag, value) = extractFlag(m.groups["value"]!!.value.trim())
        tests.add(TestResult(
            testName = m.groups["name"]!!.value.trim(),
            value = value,
            unit = m.groups["unit"]!!.value.trim(),
            referenceRange = "", flag = flag,
            collectionDatetime = collectionDt
        ))
        return true
    }

    private fun tryMatchBare(line: String, collectionDt: String, tests: MutableList<TestResult>): Boolean {
        val m = Patterns.PDF_LINE_RE_BARE.find(line) ?: return false
        tests.add(TestResult(
            testName = m.groups["name"]!!.value.trim(),
            value = m.groups["value"]!!.value.trim(),
            unit = "", referenceRange = "", flag = null,
            collectionDatetime = collectionDt
        ))
        return true
    }

    // ── Helpers ─────────────────────────────────────────────────────────────

    private fun extractFlag(valueStr: String): Pair<String?, String> {
        val m = Patterns.FLAG_SUFFIX.find(valueStr)
        return if (m != null) {
            Pair(m.groupValues[1], valueStr.substring(0, m.range.first).trimEnd())
        } else {
            Pair(null, valueStr)
        }
    }

    private fun isSectionHeader(line: String, headers: Set<String>): Boolean {
        val cleaned = line.replace(Regex(":<.*?>$"), "").trim().trimEnd(':')
        if (':' in cleaned) {
            val prefix = cleaned.split(':')[0].trim()
            if (prefix.lowercase() in headers) return true
        }
        return cleaned.lowercase() in headers
    }

    private fun isAdvisoryHeader(line: String): Boolean {
        val stripped = line.trim().trimEnd(':')
        if (stripped.lowercase() in advisoryHeaders) return true
        // All-caps text-only lines with 2+ words
        if (line == line.uppercase() && line.split("\\s+".toRegex()).size >= 2
            && line[0].isLetter() && line.none { it.isDigit() }
        ) return true
        return false
    }

    private fun isSkipLine(raw: String): Boolean {
        val upper = raw.uppercase()

        if ("LAB NUMBER:" in upper) return true
        if ("PRACTICE NUMBER" in upper) return true
        if ("PATIENT:" in upper && "REPORT TO:" in upper) return true
        if ("BHEKI MLANGENI" in upper || "ZOLA JABULANI" in upper) return true
        if (Regex("^pg\\s+\\d+\\s+of\\s+\\d+", RegexOption.IGNORE_CASE).containsMatchIn(raw)) return true
        if (Regex("^LH\\s+\\w+").containsMatchIn(raw)) return true
        if ("HOSPITAL NUMBER" in upper && ',' in raw) return true
        if ("PRINTED:" in upper || "COLLECTED:" in upper || "RECEIVED:" in upper) return true
        if ("1ST PRINT:" in upper || "REPRINT:" in upper) return true

        if ("AUTHORIZED BY:" in upper || "AUTHORISED BY:" in upper || "-- END OF LABORATORY REPORT --" in upper) return true

        if (Regex("^\\d{2}/\\d{2}/\\d{2}\\s+\\(\\d+y\\)\\s+Sex\\s+[MF]").containsMatchIn(raw)) return true
        if (raw.startsWith("Sample Ref:") || raw.startsWith("Hospital Number:")) return true
        if (Regex("^\\d{1,2}/\\d{1,2}/\\d{4}\\s+\\d{1,2}:\\d{2}").containsMatchIn(raw)) return true
        if (Regex("^\\d{4}\\s*$").containsMatchIn(raw)) return true
        if (Regex("^[MF]\\s+\\d+y\\)").containsMatchIn(raw)) return true
        if (raw.startsWith('@') || raw.startsWith("@ ")) return true
        if (Regex("^(Specimen received|Tests requested):").containsMatchIn(raw)) return true
        if (raw.startsWith("Patient Location:")) return true
        if ("FOR ENQUIRIES" in upper) return true

        if (Regex("^<\\d+(\\.\\d+)?\\s*mmol/L\\s*$").containsMatchIn(raw)) return true
        if (Regex("^(Low Risk|Moderate Risk|High Risk|Very High Risk)", RegexOption.IGNORE_CASE).containsMatchIn(raw)) return true
        if (Regex("^(TC target|LDLC target|non-HDLC target|Risk Category)", RegexOption.IGNORE_CASE).containsMatchIn(raw)) return true
        if (Regex("^(Fasting triglycerides|When TG|While higher|Additionally)").containsMatchIn(raw)) return true

        if (Regex("^(https?://|References:)").containsMatchIn(raw)) return true
        if (Regex("^[A-Z][a-z]+ [A-Z]+,?\\s+et al\\.").containsMatchIn(raw)) return true
        if (Regex("Clin Chim|Eur Heart|S Afr Med|doi\\.org").containsMatchIn(raw)) return true
        if (raw.startsWith("Based on the sample") || raw.startsWith("The result should")) return true
        if ("effusions" in raw.lowercase() && "Acta" in raw) return true

        if (Regex("^\\d[\\d\\s.-]*$").containsMatchIn(raw)) return true

        return false
    }

    companion object {
        /** Derive H/L flag by comparing numeric value against reference range. */
        fun inferFlag(value: String, refRange: String): String? {
            if (refRange.isBlank()) return null
            val v = Regex("[^\\d.]").replace(value, "").toDoubleOrNull() ?: return null

            val dualMatch = Patterns.REF_RANGE_DUAL.find(refRange.trim())
            if (dualMatch != null) {
                val lo = dualMatch.groupValues[1].toDouble()
                val hi = dualMatch.groupValues[2].toDouble()
                return when {
                    v < lo -> "L"
                    v > hi -> "H"
                    else -> null
                }
            }

            val singleMatch = Patterns.REF_RANGE_SINGLE.find(refRange.trim())
            if (singleMatch != null) {
                val op = singleMatch.groupValues[1]
                val bound = singleMatch.groupValues[2].toDouble()
                return when {
                    op == "<" && v >= bound -> "H"
                    op == ">" && v <= bound -> "L"
                    else -> null
                }
            }

            return null
        }
    }
}
