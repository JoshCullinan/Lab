package com.labtrack.viewer.domain.auth

/**
 * Port of with_auth_retry() from core/auth.py.
 * Executes a suspend block; on SessionExpiredError, re-authenticates and retries once.
 */
suspend fun <T> withAuthRetry(
    auth: AuthManager,
    maxRetries: Int = 1,
    block: suspend () -> T
): T {
    for (attempt in 0..maxRetries) {
        try {
            return block()
        } catch (e: SessionExpiredError) {
            if (attempt == maxRetries) throw e
            auth.ensureAuthenticated()
        }
    }
    // Unreachable but required by compiler
    throw SessionExpiredError("Max retries exceeded")
}
