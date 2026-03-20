package com.labtrack.viewer.data.repository

import android.webkit.CookieManager
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class CookieRepositoryImpl @Inject constructor() : CookieRepository {

    override fun clearCookies() {
        CookieManager.getInstance().removeAllCookies(null)
        CookieManager.getInstance().flush()
    }

    override fun flushCookies() {
        CookieManager.getInstance().flush()
    }
}
