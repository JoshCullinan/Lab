package com.labtrack.viewer.domain.webview

import android.webkit.JavascriptInterface
import kotlinx.coroutines.CompletableDeferred
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong

/**
 * JavaScript interface bridging JS callbacks → Kotlin CompletableDeferred.
 * Added to WebView via addJavascriptInterface(this, "LabTrackBridge").
 *
 * Uses a ConcurrentHashMap of callId → deferred to avoid the race condition
 * where a second waitForSelector call clobbers the first's deferred.
 */
class WebViewJsInterface {

    private val counter = AtomicLong(0)
    private val selectorDeferreds = ConcurrentHashMap<Long, CompletableDeferred<Boolean>>()

    /** Register a new selector poll and return its unique callId. */
    fun registerSelectorDeferred(): Pair<Long, CompletableDeferred<Boolean>> {
        val id = counter.incrementAndGet()
        val deferred = CompletableDeferred<Boolean>()
        selectorDeferreds[id] = deferred
        return id to deferred
    }

    @JavascriptInterface
    fun onSelectorResult(callId: Long, found: Boolean) {
        selectorDeferreds.remove(callId)?.complete(found)
    }

    /** Cancel and clean up a deferred that timed out on the Kotlin side. */
    fun cancelSelector(callId: Long) {
        selectorDeferreds.remove(callId)?.cancel()
    }
}
