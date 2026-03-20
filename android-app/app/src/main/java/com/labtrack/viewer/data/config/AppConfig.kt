package com.labtrack.viewer.data.config

object AppConfig {
    const val BASE_URL = "https://trakcarelabwebview.nhls.ac.za/trakcarelab/csp/system.Home.cls"
    const val LOGIN_HASH = "#/Component/SSUser.Logon"
    const val SEARCH_HASH = "#/Component/web.DEBDebtor.FindList"
    const val PAGE_TIMEOUT_MS = 30_000L
    const val PDF_POPUP_TIMEOUT_MS = 20_000L

    const val USER_AGENT =
        "Mozilla/5.0 (Linux; Android 14; Pixel 6) " +
        "AppleWebKit/537.36 (KHTML, like Gecko) " +
        "Chrome/124.0.0.0 Mobile Safari/537.36"
}
