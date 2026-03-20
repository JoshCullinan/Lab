package com.labtrack.viewer.domain.auth

import com.labtrack.viewer.data.config.AppConfig
import com.labtrack.viewer.data.config.Selectors
import com.labtrack.viewer.data.repository.AuthRepository
import com.labtrack.viewer.data.repository.CookieRepository
import com.labtrack.viewer.domain.webview.WebViewBridge
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Port of core/auth.py — login, session validation, retry.
 * Uses WebViewBridge instead of Playwright page calls.
 */
@Singleton
class AuthManager @Inject constructor(
    private val authRepo: AuthRepository,
    private val cookieRepo: CookieRepository,
    private val bridge: WebViewBridge
) {

    // ── Session validity ────────────────────────────────────────────────────

    suspend fun isSessionValid(): Boolean {
        return try {
            bridge.navigateTo(
                AppConfig.BASE_URL,
                timeoutMs = AppConfig.PAGE_TIMEOUT_MS
            )

            val selectorBoth = "${Selectors.LOGGED_IN_INDICATOR}, ${Selectors.SESSION_EXPIRED}"
            bridge.waitForSelector(selectorBoth, timeoutMs = AppConfig.PAGE_TIMEOUT_MS)

            val url = bridge.getCurrentUrl()
            if (url.contains("SSUser.Logon")) {
                return false
            }

            bridge.queryExists(Selectors.LOGGED_IN_INDICATOR)
        } catch (e: Exception) {
            false
        }
    }

    // ── Login ───────────────────────────────────────────────────────────────

    suspend fun login(): Boolean {
        val username = authRepo.getUsername()
            ?: throw AuthenticationError("No username saved. Please enter your credentials.")
        val password = authRepo.getPassword()
            ?: throw AuthenticationError("No password saved. Please enter your credentials.")

        val loginUrl = AppConfig.BASE_URL + AppConfig.LOGIN_HASH
        bridge.navigateTo(loginUrl, timeoutMs = AppConfig.PAGE_TIMEOUT_MS)

        val formVisible = bridge.waitForSelector(
            Selectors.USERNAME,
            timeoutMs = AppConfig.PAGE_TIMEOUT_MS,
            visible = true
        )

        if (!formVisible) {
            val loggedIn = bridge.queryExists(Selectors.LOGGED_IN_INDICATOR)
            if (loggedIn) {
                cookieRepo.flushCookies()
                return true
            }
            throw AuthenticationError(
                "Login form did not appear — check selectors"
            )
        }

        bridge.fillField(Selectors.USERNAME, username)
        bridge.fillField(Selectors.PASSWORD, password)
        bridge.clickElement(Selectors.LOGIN_BUTTON)

        val success = bridge.waitForSelector(
            Selectors.LOGGED_IN_INDICATOR,
            timeoutMs = AppConfig.PAGE_TIMEOUT_MS
        )

        if (!success) {
            throw AuthenticationError(
                "Login failed — still on login page after submitting credentials. " +
                "Check that your username and password are correct."
            )
        }

        cookieRepo.flushCookies()
        return true
    }

    // ── High-level entry point ──────────────────────────────────────────────

    suspend fun ensureAuthenticated(): Boolean {
        if (isSessionValid()) return true
        cookieRepo.clearCookies()
        login()
        return true
    }

    // ── Session check (used by ResultsManager) ──────────────────────────────

    suspend fun checkForSessionExpiry() {
        val url = bridge.getCurrentUrl()
        if (url.contains("SSUser.Logon")) {
            throw SessionExpiredError("Session expired — redirected to login page")
        }
    }

    /**
     * Clear all session state: cookies, credentials, and WebView cache.
     * Prevents data leakage between different users on the same device.
     */
    suspend fun clearSession() {
        cookieRepo.clearCookies()
        authRepo.clearCredentials()
        bridge.reset()
    }
}
