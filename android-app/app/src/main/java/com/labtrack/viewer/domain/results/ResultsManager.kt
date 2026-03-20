package com.labtrack.viewer.domain.results

import com.labtrack.viewer.data.config.AppConfig
import com.labtrack.viewer.data.config.Selectors
import com.labtrack.viewer.data.models.ClickableLink
import com.labtrack.viewer.data.models.EpisodeData
import com.labtrack.viewer.data.models.EpisodeRow
import com.labtrack.viewer.data.models.PatientResult
import com.labtrack.viewer.data.models.PatientSearchHit
import com.labtrack.viewer.data.models.TestResult
import com.labtrack.viewer.domain.auth.AuthManager
import com.labtrack.viewer.domain.auth.SessionExpiredError
import com.labtrack.viewer.domain.webview.WebViewBridge
import org.json.JSONArray
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Port of core/results.py ResultsManager.
 * All search methods, episode scraping, PDF parsing, DOM parsing.
 */
@Singleton
class ResultsManager @Inject constructor(
    private val auth: AuthManager,
    private val pdfParser: PdfParser,
    private val bridge: WebViewBridge
) {

    // ── Public API ──────────────────────────────────────────────────────────

    suspend fun searchBySpecimen(specimenId: String): PatientResult? {
        auth.ensureAuthenticated()
        val b = bridge

        navigateToSearch(b)
        submitSearch(b, specimenId)

        val found = b.waitForSelector(
            Selectors.MRN_LINK,
            timeoutMs = AppConfig.PAGE_TIMEOUT_MS,
            visible = true
        )
        if (!found) {
            auth.checkForSessionExpiry()
            return null
        }

        b.clickElement(Selectors.MRN_LINK)
        return processPatientPage(b, specimenId)
    }

    suspend fun searchByEpisode(episodeId: String): PatientResult? {
        auth.ensureAuthenticated()
        val b = bridge

        navigateToSearch(b)
        b.clickElement(Selectors.SEARCH_CLEAR)
        b.delay(500)
        b.fillField(Selectors.SEARCH_EPISODE, episodeId)
        b.clickElement(Selectors.SEARCH_BUTTON)

        val found = b.waitForSelector(
            Selectors.MRN_LINK,
            timeoutMs = AppConfig.PAGE_TIMEOUT_MS,
            visible = true
        )
        if (found) {
            b.clickElement(Selectors.MRN_LINK)
        } else {
            // May have navigated directly to episode
            val hasBanner = b.waitForSelector(Selectors.BANNER_SURNAME, timeoutMs = 5000)
            if (!hasBanner) {
                auth.checkForSessionExpiry()
                return null
            }
        }

        return processPatientPage(b, episodeId)
    }

    suspend fun searchByHospitalMrn(hospitalMrn: String): PatientResult? {
        auth.ensureAuthenticated()
        val b = bridge

        navigateToSearch(b)
        b.clickElement(Selectors.SEARCH_CLEAR)
        b.delay(500)
        b.fillField(Selectors.SEARCH_HOSPITAL_MRN, hospitalMrn)
        b.clickElement(Selectors.SEARCH_BUTTON)

        val found = b.waitForSelector(
            Selectors.MRN_LINK,
            timeoutMs = AppConfig.PAGE_TIMEOUT_MS,
            visible = true
        )
        if (!found) {
            auth.checkForSessionExpiry()
            return null
        }

        b.clickElement(Selectors.MRN_LINK)
        return processPatientPage(b, hospitalMrn)
    }

    suspend fun searchPatientsByHospitalMrn(hospitalMrn: String): List<PatientSearchHit> {
        auth.ensureAuthenticated()
        val b = bridge

        navigateToSearch(b)
        b.clickElement(Selectors.SEARCH_CLEAR)
        b.delay(500)
        b.fillField(Selectors.SEARCH_HOSPITAL_MRN, hospitalMrn)
        b.clickElement(Selectors.SEARCH_BUTTON)

        val found = b.waitForSelector(
            Selectors.MRN_LINK,
            timeoutMs = AppConfig.PAGE_TIMEOUT_MS,
            visible = true
        )
        if (!found) {
            auth.checkForSessionExpiry()
            return emptyList()
        }

        return parseSearchResults(b)
    }

    suspend fun searchByName(surname: String, givenName: String = ""): List<PatientSearchHit> {
        auth.ensureAuthenticated()
        val b = bridge

        navigateToSearch(b)
        b.clickElement(Selectors.SEARCH_CLEAR)
        b.delay(500)
        b.fillField(Selectors.SEARCH_SURNAME, surname)
        if (givenName.isNotBlank()) {
            b.fillField(Selectors.SEARCH_NAME, givenName)
        }
        b.clickElement(Selectors.SEARCH_BUTTON)

        val found = b.waitForSelector(
            Selectors.SEARCH_RESULTS_TABLE,
            timeoutMs = AppConfig.PAGE_TIMEOUT_MS
        )
        if (!found) {
            auth.checkForSessionExpiry()
            return emptyList()
        }

        return parseSearchResults(b)
    }

    suspend fun openPatientByHit(hit: PatientSearchHit, searchTerm: String): PatientResult? {
        auth.ensureAuthenticated()
        val b = bridge
        val mrnSelector = Selectors.mrnLinkForRow(hit.rowIndex)

        val exists = b.queryExists(mrnSelector)
        if (!exists) return null
        b.clickElement(mrnSelector)

        return processPatientPage(b, searchTerm)
    }

    suspend fun listEpisodesForPatient(patientRowIndex: Int): EpisodeData? {
        val b = bridge
        val mrnSelector = Selectors.mrnLinkForRow(patientRowIndex)

        val exists = b.queryExists(mrnSelector)
        if (!exists) return null
        b.clickElement(mrnSelector)

        val hasBanner = b.waitForSelector(
            Selectors.BANNER_SURNAME,
            timeoutMs = AppConfig.PAGE_TIMEOUT_MS
        )
        if (!hasBanner) {
            auth.checkForSessionExpiry()
            return null
        }

        return scrapeEpisodeList(b)
    }

    suspend fun loadEpisodeResults(rowIndex: Int, episodeData: EpisodeData): PatientResult? {
        auth.ensureAuthenticated()
        val target = episodeData.rows.find { it.rowIndex == rowIndex } ?: return null
        val b = bridge

        b.delay(500)

        val pdfBytes = b.clickAndDownloadPdf(target.pdfSelector)
        if (pdfBytes == null || pdfBytes.isEmpty()) return null

        val tests = pdfParser.parsePdf(pdfBytes, target.collectionDatetime)
        if (tests.isEmpty()) return null

        return PatientResult(
            patientName = episodeData.patientName,
            patientId = episodeData.patientId,
            specimenId = target.episodeNumber.ifBlank { "row-$rowIndex" },
            episode = target.episodeNumber,
            requestingDoctor = target.doctor,
            dob = episodeData.dob,
            status = "",
            collectionDatetime = target.collectionDatetime,
            resultDatetime = "",
            tests = tests
        )
    }

    // ── Shared patient page processor ───────────────────────────────────────

    private suspend fun processPatientPage(b: WebViewBridge, searchId: String): PatientResult? {
        val hasBanner = b.waitForSelector(
            Selectors.BANNER_SURNAME,
            timeoutMs = AppConfig.PAGE_TIMEOUT_MS
        )
        if (!hasBanner) {
            auth.checkForSessionExpiry()
            return null
        }

        val episodeData = scrapeEpisodeList(b)

        // Try PDF approach for all rows
        val pdfResult = tryPdfApproachAllRows(b, searchId, episodeData)
        if (pdfResult != null) return pdfResult

        // Fall back to clicking test set links
        return clickTestSets(b, searchId, episodeData)
    }

    // ── Episode list scraping ───────────────────────────────────────────────

    private suspend fun scrapeEpisodeList(b: WebViewBridge): EpisodeData {
        val jsonStr = b.evaluateJsJson(JsSnippets.SCRAPE_EPISODE_LIST)
        val cleaned = cleanJsonString(jsonStr)
        val json = try {
            JSONObject(cleaned)
        } catch (e: org.json.JSONException) {
            throw RuntimeException("Failed to parse episode list JSON: ${e.message}")
        }

        val clickableArray = json.optJSONArray("clickable") ?: JSONArray()
        val pendingArray = json.optJSONArray("pending") ?: JSONArray()
        val rowsArray = json.optJSONArray("rows") ?: JSONArray()

        val globalClickable = parseClickableLinks(clickableArray)
        val globalPending = parseStringArray(pendingArray)

        val rows = mutableListOf<EpisodeRow>()
        for (i in 0 until rowsArray.length()) {
            val rowJson = rowsArray.getJSONObject(i)
            rows.add(EpisodeRow(
                rowIndex = rowJson.optInt("row_index", i),
                episodeNumber = rowJson.optString("episode_number", ""),
                doctor = rowJson.optString("doctor", ""),
                collectionDatetime = rowJson.optString("collection_datetime", ""),
                pdfSelector = rowJson.optString("pdf_selector", ""),
                clickable = parseClickableLinks(rowJson.optJSONArray("clickable") ?: JSONArray()),
                pending = parseStringArray(rowJson.optJSONArray("pending") ?: JSONArray())
            ))
        }

        return EpisodeData(
            patientName = json.optString("patient_name", ""),
            patientId = json.optString("patient_id", ""),
            episode = json.optString("episode", ""),
            dob = json.optString("dob", ""),
            doctor = json.optString("doctor", ""),
            collectionDatetime = json.optString("collection_datetime", ""),
            clickable = globalClickable,
            pending = globalPending,
            rows = rows
        )
    }

    // ── PDF approach ────────────────────────────────────────────────────────

    private suspend fun tryPdfApproachAllRows(
        b: WebViewBridge,
        searchId: String,
        episodeData: EpisodeData
    ): PatientResult? {
        if (episodeData.rows.isEmpty()) return null

        val allTests = mutableListOf<TestResult>()

        for (row in episodeData.rows) {
            val exists = b.queryExists(row.pdfSelector)
            if (!exists) continue

            val pdfBytes = b.clickAndDownloadPdf(row.pdfSelector)
            if (pdfBytes == null || pdfBytes.isEmpty()) continue

            allTests.addAll(pdfParser.parsePdf(pdfBytes, row.collectionDatetime))
        }

        if (allTests.isEmpty()) return null

        // Append global pending tests
        for (name in episodeData.pending) {
            allTests.add(TestResult(
                testName = name, value = "Pending", unit = "", referenceRange = "",
                flag = "PENDING", collectionDatetime = ""
            ))
        }

        val firstRow = episodeData.rows.first()
        return PatientResult(
            patientName = episodeData.patientName,
            patientId = episodeData.patientId,
            specimenId = searchId,
            episode = episodeData.episode,
            requestingDoctor = firstRow.doctor,
            dob = episodeData.dob,
            status = "",
            collectionDatetime = firstRow.collectionDatetime,
            resultDatetime = "",
            tests = allTests
        )
    }

    // ── Click through test sets ─────────────────────────────────────────────

    private suspend fun clickTestSets(
        b: WebViewBridge,
        specimenId: String,
        episodeData: EpisodeData
    ): PatientResult? {
        val clickable = episodeData.clickable
        if (clickable.isEmpty()) {
            if (episodeData.pending.isEmpty()) return null
            return PatientResult(
                patientName = episodeData.patientName,
                patientId = episodeData.patientId,
                specimenId = specimenId,
                episode = episodeData.episode,
                requestingDoctor = episodeData.doctor,
                dob = episodeData.dob,
                status = "",
                collectionDatetime = episodeData.collectionDatetime,
                resultDatetime = "",
                tests = episodeData.pending.map { name ->
                    TestResult(
                        testName = name, value = "Pending", unit = "", referenceRange = "",
                        flag = "PENDING", collectionDatetime = ""
                    )
                }
            )
        }

        // Click first test set link
        val firstSelector = "#${clickable.first().id}"
        val exists = b.queryExists(firstSelector)
        if (!exists) return null
        b.clickElement(firstSelector)

        val hasTable = b.waitForSelector(
            Selectors.RESULTS_TABLE,
            timeoutMs = AppConfig.PAGE_TIMEOUT_MS
        )
        if (!hasTable) {
            auth.checkForSessionExpiry()
            return null
        }

        val result = parseResultDetail(b, specimenId) ?: return null

        // Click remaining test set links and accumulate extra tests
        val extraTests = mutableListOf<TestResult>()
        for (ts in clickable.drop(1)) {
            b.goBack()
            val tsSelector = "#${ts.id}"
            val tsVisible = b.waitForSelector(tsSelector, timeoutMs = 10000, visible = true)
            if (!tsVisible) continue
            b.clickElement(tsSelector)
            val table = b.waitForSelector(Selectors.RESULTS_TABLE, timeoutMs = 10000)
            if (!table) continue
            extraTests.addAll(parseTestRows(b))
        }

        // Append pending tests
        val finalTests = (result.tests + extraTests).toMutableList()
        for (name in episodeData.pending) {
            finalTests.add(TestResult(
                testName = name, value = "Pending", unit = "", referenceRange = "",
                flag = "PENDING", collectionDatetime = ""
            ))
        }

        return result.copy(tests = finalTests)
    }

    // ── Result detail parsing ───────────────────────────────────────────────

    private suspend fun parseResultDetail(b: WebViewBridge, specimenId: String): PatientResult? {
        val jsonStr = b.evaluateJsJson(JsSnippets.PARSE_DETAIL)
        val cleaned = cleanJsonString(jsonStr)
        val data = JSONObject(cleaned)

        val patientName = data.optString("patient_name", "")
        if (patientName.replace(", ", "").isBlank()) return null

        val tests = parseTestRows(b)

        return PatientResult(
            patientName = patientName,
            patientId = data.optString("patient_id", ""),
            specimenId = specimenId,
            episode = data.optString("episode", ""),
            requestingDoctor = data.optString("requesting_doctor", ""),
            dob = data.optString("dob", ""),
            status = data.optString("status", ""),
            collectionDatetime = data.optString("collection_datetime", ""),
            resultDatetime = data.optString("result_datetime", ""),
            tests = tests
        )
    }

    private suspend fun parseTestRows(b: WebViewBridge): List<TestResult> {
        val jsonStr = b.evaluateJsJson(JsSnippets.PARSE_ROWS)
        val cleaned = cleanJsonString(jsonStr)
        val arr = JSONArray(cleaned)

        val results = mutableListOf<TestResult>()
        for (i in 0 until arr.length()) {
            val t = arr.getJSONObject(i)
            val testName = t.optString("test_name", "")
            if ("comment" in testName.lowercase()) continue

            val rawFlag = t.optString("flag", "")
            val value = t.optString("value", "")
            val refRange = t.optString("reference_range", "")
            val flag = rawFlag.ifBlank { null } ?: PdfParser.inferFlag(value, refRange)

            results.add(TestResult(
                testName = testName,
                value = value,
                unit = t.optString("unit", ""),
                referenceRange = refRange,
                flag = flag,
                collectionDatetime = t.optString("collection_datetime", "")
            ))
        }
        return results
    }

    private suspend fun parseSearchResults(b: WebViewBridge): List<PatientSearchHit> {
        val jsonStr = b.evaluateJsJson(JsSnippets.PARSE_SEARCH_RESULTS)
        val cleaned = cleanJsonString(jsonStr)
        val arr = JSONArray(cleaned)

        val hits = mutableListOf<PatientSearchHit>()
        for (i in 0 until arr.length()) {
            val h = arr.getJSONObject(i)
            hits.add(PatientSearchHit(
                rowIndex = h.optInt("row_index", i),
                mrn = h.optString("mrn", ""),
                surname = h.optString("surname", ""),
                givenName = h.optString("given_name", ""),
                dob = h.optString("dob", ""),
                episode = h.optString("episode", "")
            ))
        }
        return hits
    }

    // ── Navigation helpers ──────────────────────────────────────────────────

    private suspend fun navigateToSearch(b: WebViewBridge) {
        val searchUrl = AppConfig.BASE_URL + AppConfig.SEARCH_HASH
        b.navigateTo(searchUrl, timeoutMs = AppConfig.PAGE_TIMEOUT_MS)
        auth.checkForSessionExpiry()
        b.waitForSelector(Selectors.SEARCH_SPECIMEN, timeoutMs = AppConfig.PAGE_TIMEOUT_MS)
    }

    private suspend fun submitSearch(b: WebViewBridge, specimenId: String) {
        b.clickElement(Selectors.SEARCH_CLEAR)
        b.delay(500)
        b.fillField(Selectors.SEARCH_SPECIMEN, specimenId)
        b.clickElement(Selectors.SEARCH_BUTTON)
    }

    // ── JSON helpers ────────────────────────────────────────────────────────

    private fun cleanJsonString(raw: String): String {
        // evaluateJavascript wraps result in quotes and escapes it
        var s = raw.trim()
        if (s.startsWith("\"") && s.endsWith("\"")) {
            s = s.substring(1, s.length - 1)
            // Order matters: unescape backslashes first to avoid corrupting other sequences
            s = s.replace("\\\\", "\\")
                .replace("\\\"", "\"")
                .replace("\\/", "/")
                .replace("\\n", "\n")
                .replace("\\t", "\t")
        }
        return s
    }

    private fun parseClickableLinks(arr: JSONArray): List<ClickableLink> {
        val links = mutableListOf<ClickableLink>()
        for (i in 0 until arr.length()) {
            val obj = arr.getJSONObject(i)
            links.add(ClickableLink(
                id = obj.optString("id", ""),
                text = obj.optString("text", "")
            ))
        }
        return links
    }

    private fun parseStringArray(arr: JSONArray): List<String> {
        val list = mutableListOf<String>()
        for (i in 0 until arr.length()) {
            list.add(arr.getString(i))
        }
        return list
    }
}
