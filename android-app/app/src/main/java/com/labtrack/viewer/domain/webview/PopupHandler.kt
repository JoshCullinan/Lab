package com.labtrack.viewer.domain.webview

import android.annotation.SuppressLint
import android.net.http.SslError
import android.os.Message
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import kotlinx.coroutines.CompletableDeferred

/**
 * Handles popup windows from the main WebView (used for PDF downloads).
 * TrakCare opens PDF reports in new windows — we intercept and extract the PDF URL.
 */
class PopupHandler(
    private val parentWebView: WebView
) : WebChromeClient() {

    @Volatile
    var pdfBytesDeferred: CompletableDeferred<Unit>? = null

    @Volatile
    var popupPdfUrl: String? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreateWindow(
        view: WebView,
        isDialog: Boolean,
        isUserGesture: Boolean,
        resultMsg: Message
    ): Boolean {
        val popupWebView = WebView(view.context)
        popupWebView.settings.javaScriptEnabled = true
        popupWebView.settings.domStorageEnabled = true

        popupWebView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest
            ): Boolean = false

            override fun onPageFinished(view: WebView, url: String?) {
                super.onPageFinished(view, url)
                // After the popup page loads, extract PDF URL from iframe
                view.evaluateJavascript("""
                    (function() {
                        var frames = document.querySelectorAll('iframe, embed, object');
                        for (var i = 0; i < frames.length; i++) {
                            var src = frames[i].src || frames[i].data || '';
                            if (src && src.startsWith('http')) {
                                return src;
                            }
                        }
                        return window.location.href;
                    })()
                """.trimIndent()) { result ->
                    val pdfUrl = result?.trim('"') ?: ""
                    if (pdfUrl.isNotBlank() && pdfUrl.startsWith("http")) {
                        popupPdfUrl = pdfUrl
                    }
                    // Destroy popup after extraction, then signal completion
                    view.destroy()
                    pdfBytesDeferred?.complete(Unit)
                }
            }

            @SuppressLint("WebViewClientOnReceivedSslError")
            override fun onReceivedSslError(
                view: WebView,
                handler: SslErrorHandler,
                error: SslError
            ) {
                handler.cancel()
            }
        }

        val transport = resultMsg.obj as? WebView.WebViewTransport
        transport?.webView = popupWebView
        resultMsg.sendToTarget()
        return true
    }
}
