package com.labtrack.viewer.domain.webview

import android.content.Context
import android.net.http.SslError
import android.webkit.CookieManager
import android.webkit.SslErrorHandler
import android.webkit.WebView
import android.webkit.WebViewClient
import com.labtrack.viewer.data.config.AppConfig
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import java.io.BufferedInputStream
import java.net.HttpURLConnection
import java.net.URL

/**
 * Suspend-function wrapper around Android WebView, replacing Playwright's async API.
 *
 * All WebView interactions run on Main thread via withContext(Dispatchers.Main).
 * JS results bridge back via CompletableDeferred through WebViewJsInterface.
 *
 * The WebView is lazily created on first use (must happen on the main thread).
 * Initialization is guarded by a Mutex to prevent double-creation.
 */
class WebViewBridge(private val context: Context) {

    private val jsInterface = WebViewJsInterface()
    private lateinit var webView: WebView
    private lateinit var popupHandler: PopupHandler

    @Volatile
    private var initialized = false
    private val initMutex = Mutex()

    private suspend fun ensureInitialized() {
        if (initialized) return
        initMutex.withLock {
            if (!initialized) {
                withContext(Dispatchers.Main) {
                    webView = WebViewFactory.create(context, jsInterface)
                    popupHandler = PopupHandler(webView)
                    webView.webChromeClient = popupHandler
                    initialized = true
                }
            }
        }
    }

    // ── Selector escaping ───────────────────────────────────────────────────

    /**
     * Escape a CSS selector for safe embedding in a JS string literal.
     * Prevents injection via selectors scraped from the DOM.
     */
    private fun escapeSelector(selector: String): String =
        selector.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "")
            .replace("\r", "")

    // ── Navigation ──────────────────────────────────────────────────────────

    suspend fun navigateTo(url: String, timeoutMs: Long = AppConfig.PAGE_TIMEOUT_MS) {
        ensureInitialized()
        val deferred = CompletableDeferred<Unit>()

        withContext(Dispatchers.Main) {
            webView.webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView, finishedUrl: String?) {
                    super.onPageFinished(view, finishedUrl)
                    deferred.complete(Unit)
                }

                override fun onReceivedError(
                    view: WebView,
                    errorCode: Int,
                    description: String?,
                    failingUrl: String?
                ) {
                    deferred.completeExceptionally(
                        RuntimeException("WebView error $errorCode: $description")
                    )
                }

                @android.annotation.SuppressLint("WebViewClientOnReceivedSslError")
                override fun onReceivedSslError(
                    view: WebView,
                    handler: SslErrorHandler,
                    error: SslError
                ) {
                    handler.cancel()
                    deferred.completeExceptionally(
                        RuntimeException("SSL error: ${error.primaryError}")
                    )
                }
            }
            webView.loadUrl(url)
        }

        try {
            withTimeout(timeoutMs) {
                deferred.await()
            }
        } catch (e: TimeoutCancellationException) {
            // For SPA hash navigation, onPageFinished may not fire.
            // Fall through — caller uses waitForSelector to confirm readiness.
        }
    }

    // ── Selector operations ─────────────────────────────────────────────────

    suspend fun waitForSelector(
        selector: String,
        timeoutMs: Long = AppConfig.PAGE_TIMEOUT_MS,
        visible: Boolean = false
    ): Boolean {
        ensureInitialized()
        val escaped = escapeSelector(selector)
        val (callId, deferred) = jsInterface.registerSelectorDeferred()

        val visibilityCheck = if (visible) {
            " && el.offsetParent !== null"
        } else ""

        val js = """
            (function() {
                var attempts = 0;
                var maxAttempts = ${timeoutMs / 100};
                var interval = setInterval(function() {
                    var el = document.querySelector('$escaped');
                    if (el$visibilityCheck) {
                        clearInterval(interval);
                        LabTrackBridge.onSelectorResult($callId, true);
                    } else if (++attempts >= maxAttempts) {
                        clearInterval(interval);
                        LabTrackBridge.onSelectorResult($callId, false);
                    }
                }, 100);
            })();
        """.trimIndent()

        withContext(Dispatchers.Main) {
            webView.evaluateJavascript(js, null)
        }

        return try {
            withTimeout(timeoutMs + 2000) {
                deferred.await()
            }
        } catch (e: TimeoutCancellationException) {
            jsInterface.cancelSelector(callId)
            false
        }
    }

    suspend fun queryExists(selector: String): Boolean {
        ensureInitialized()
        val escaped = escapeSelector(selector)
        val result = evaluateJs(
            "document.querySelector('$escaped') !== null"
        )
        return result == "true"
    }

    // ── Input operations ────────────────────────────────────────────────────

    suspend fun fillField(selector: String, value: String) {
        ensureInitialized()
        val escapedSel = escapeSelector(selector)
        val escapedVal = value.replace("\\", "\\\\").replace("'", "\\'")
        evaluateJs("""
            (function() {
                var el = document.querySelector('$escapedSel');
                if (el) {
                    el.value = '$escapedVal';
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
            })()
        """.trimIndent())
    }

    suspend fun clickElement(selector: String) {
        ensureInitialized()
        val escaped = escapeSelector(selector)
        evaluateJs("""
            (function() {
                var el = document.querySelector('$escaped');
                if (el) el.click();
            })()
        """.trimIndent())
    }

    // ── JavaScript evaluation ───────────────────────────────────────────────

    suspend fun evaluateJs(js: String): String {
        ensureInitialized()
        val deferred = CompletableDeferred<String>()

        withContext(Dispatchers.Main) {
            webView.evaluateJavascript(js) { result ->
                deferred.complete(result ?: "null")
            }
        }

        return try {
            withTimeout(AppConfig.PAGE_TIMEOUT_MS) {
                deferred.await()
            }
        } catch (e: TimeoutCancellationException) {
            "null"
        }
    }

    suspend fun evaluateJsJson(js: String): String {
        return evaluateJs("JSON.stringify($js)")
    }

    // ── URL & State ─────────────────────────────────────────────────────────

    suspend fun getCurrentUrl(): String {
        ensureInitialized()
        return withContext(Dispatchers.Main) {
            webView.url ?: ""
        }
    }

    // ── PDF download ────────────────────────────────────────────────────────

    suspend fun clickAndDownloadPdf(
        pdfLinkSelector: String,
        timeoutMs: Long = AppConfig.PDF_POPUP_TIMEOUT_MS
    ): ByteArray? {
        ensureInitialized()
        popupHandler.popupPdfUrl = null
        val deferred = CompletableDeferred<Unit>()
        popupHandler.pdfBytesDeferred = deferred

        clickElement(pdfLinkSelector)

        try {
            withTimeout(timeoutMs) {
                deferred.await()
            }
        } catch (e: TimeoutCancellationException) {
            return null
        }

        val pdfUrl = popupHandler.popupPdfUrl ?: return null
        return downloadWithCookies(pdfUrl)
    }

    private suspend fun downloadWithCookies(urlString: String): ByteArray? =
        withContext(Dispatchers.IO) {
            try {
                val url = URL(urlString)
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "GET"

                val cookies = CookieManager.getInstance().getCookie(urlString)
                if (!cookies.isNullOrBlank()) {
                    conn.setRequestProperty("Cookie", cookies)
                }
                conn.setRequestProperty("User-Agent", AppConfig.USER_AGENT)
                conn.connect()

                if (conn.responseCode == 200) {
                    val bytes = BufferedInputStream(conn.inputStream).use { it.readBytes() }
                    if (bytes.size >= 5 && String(bytes, 0, 5) == "%PDF-") {
                        bytes
                    } else null
                } else null
            } catch (e: Exception) {
                null
            }
        }

    // ── Utility ─────────────────────────────────────────────────────────────

    suspend fun delay(ms: Long) {
        kotlinx.coroutines.delay(ms)
    }

    suspend fun goBack() {
        ensureInitialized()
        withContext(Dispatchers.Main) {
            webView.goBack()
        }
        delay(500)
    }

    /**
     * Reset the WebView state — clears cache, history, and JS state.
     * Called on session clear to prevent data leakage between users.
     */
    suspend fun reset() {
        if (!initialized) return
        withContext(Dispatchers.Main) {
            webView.stopLoading()
            webView.clearHistory()
            webView.clearCache(true)
            webView.loadUrl("about:blank")
        }
    }

    fun destroy() {
        if (initialized) {
            webView.destroy()
        }
    }
}
