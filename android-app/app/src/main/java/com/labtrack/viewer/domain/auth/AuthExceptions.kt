package com.labtrack.viewer.domain.auth

class AuthenticationError(message: String) : Exception(message)
class SessionExpiredError(message: String) : Exception(message)
