package com.labtrack.viewer.domain.webview

import android.annotation.SuppressLint
import android.content.Context
import android.webkit.CookieManager
import android.webkit.WebSettings
import android.webkit.WebView
import com.labtrack.viewer.data.config.AppConfig

/**
 * Creates a hidden (offscreen) WebView configured for TrakCare automation.
 */
object WebViewFactory {

    @SuppressLint("SetJavaScriptEnabled")
    fun create(context: Context, jsInterface: WebViewJsInterface): WebView {
        val webView = WebView(context)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            userAgentString = AppConfig.USER_AGENT
            cacheMode = WebSettings.LOAD_DEFAULT
            setSupportMultipleWindows(true)
            javaScriptCanOpenWindowsAutomatically = true
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        }

        // Enable cookies
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
        }

        // Add JS interface
        webView.addJavascriptInterface(jsInterface, "LabTrackBridge")

        return webView
    }
}
