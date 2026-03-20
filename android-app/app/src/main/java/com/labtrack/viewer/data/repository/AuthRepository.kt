package com.labtrack.viewer.data.repository

/**
 * Stores and retrieves user credentials using EncryptedSharedPreferences.
 */
interface AuthRepository {
    fun getUsername(): String?
    fun getPassword(): String?
    fun saveCredentials(username: String, password: String)
    fun clearCredentials()
    fun hasCredentials(): Boolean
}
