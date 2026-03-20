package com.labtrack.viewer.data.repository

/**
 * Manages WebView cookie persistence.
 * Android's CookieManager handles most of this automatically,
 * but we expose an explicit clear for session reset.
 */
interface CookieRepository {
    fun clearCookies()
    fun flushCookies()
}
