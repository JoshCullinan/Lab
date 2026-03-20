package com.labtrack.viewer.data.config

/**
 * All CSS selectors from core/config.py — verbatim copy.
 * Used by WebViewBridge to interact with TrakCare DOM.
 */
object Selectors {
    // ── Login Selectors ─────────────────────────────────────────────────────
    const val USERNAME = "#SSUser_Logon_0-item-USERNAME"
    const val PASSWORD = "#SSUser_Logon_0-item-PASSWORD"
    const val LOGIN_BUTTON = "#SSUser_Logon_0-button-Logon"
    const val LOGGED_IN_INDICATOR = "#tc_NavBar-misc-profileToggle"
    const val SESSION_EXPIRED = "#SSUser_Logon_0-form"

    // ── Patient Search Selectors (web.DEBDebtor.FindList) ───────────────────
    const val SEARCH_SPECIMEN = "#web_DEBDebtor_FindList_0-item-SpecimenParam"
    const val SEARCH_SURNAME = "#web_DEBDebtor_FindList_0-item-SurnameParam"
    const val SEARCH_NAME = "#web_DEBDebtor_FindList_0-item-GivenNameParam"
    const val SEARCH_MRN = "#web_DEBDebtor_FindList_0-item-MRNParam"
    const val SEARCH_EPISODE = "#web_DEBDebtor_FindList_0-item-EpisodeParam"
    const val SEARCH_HOSPITAL_MRN = "#web_DEBDebtor_FindList_0-item-HospitalMRN"
    const val SEARCH_BUTTON = "#web_DEBDebtor_FindList_0-button-Find"
    const val SEARCH_CLEAR = "#web_DEBDebtor_FindList_0-button-Clear"

    // Search results table (patient list)
    const val SEARCH_RESULTS_TABLE = "#tweb_DEBDebtor_FindList_0"
    const val SEARCH_NO_MATCHES = "#web_EPVisitNumber_List_Banner-misc-noMatches"
    const val SEARCH_RESULT_ROW = """tr[id^="web_DEBDebtor_FindList_0-row-"]"""
    const val MRN_LINK = "#web_DEBDebtor_FindList_0-row-0-item-MRN-link"
    const val EPISODES_DROPDOWN = "#web_DEBDebtor_FindList_0-row-0-item-Episodes"
    const val EPISODE_ROW = """tr[id^="web_EPVisitNumber_List_0_0-row-"]"""
    const val EPISODE_ACTION_BUTTON = "#web_EPVisitNumber_List_0_0-row-0-misc-actionButton"
    const val TEST_SET_LINK = """a[id^="VISTS_"]"""

    // ── Result Detail Selectors ─────────────────────────────────────────────
    const val BANNER_MRN = "#web_EPVisitNumber_List_Banner-row-0-item-MRNLink-link"
    const val BANNER_EPISODE = "#web_EPVisitNumber_List_Banner-row-0-item-Episode"
    const val BANNER_GIVEN_NAME = "#web_EPVisitNumber_List_Banner-row-0-item-GivenName"
    const val BANNER_SURNAME = "#web_EPVisitNumber_List_Banner-row-0-item-Surname"
    const val BANNER_DOB = "#web_EPVisitNumber_List_Banner-row-0-item-DOB"

    // Result metadata
    const val RESULT_STATUS = "#web_EPVisitTestSet_Result_0-item-VISTSStatusResult"
    const val RESULT_ORDERED_BY = "#web_EPVisitTestSet_Result_0-item-OrderedBy"
    const val RESULT_COLLECTION_DATE = "#web_EPVisitTestSet_Result_0-item-CollectionDate"
    const val RESULT_COLLECTION_TIME = "#web_EPVisitTestSet_Result_0-item-CollectionTime"
    const val RESULT_RESULT_DATE = "#web_EPVisitTestSet_Result_0-item-ResultDate"
    const val RESULT_RESULT_TIME = "#web_EPVisitTestSet_Result_0-item-ResultTime"

    // Results table
    const val RESULTS_TABLE = "#tweb_EPVisitTestSet_Result_0"
    const val RESULTS_FORM = "#web_EPVisitTestSet_Result_0-form"
    const val RESULT_ROW = """tr[id^="web_EPVisitTestSet_Result_0-row-"]"""

    // Dynamic selectors (require row index substitution)
    fun mrnLinkForRow(rowIndex: Int) =
        "#web_DEBDebtor_FindList_0-row-$rowIndex-item-MRN-link"

    fun episodesDropdownForRow(rowIndex: Int) =
        "#web_DEBDebtor_FindList_0-row-$rowIndex-item-Episodes"
}
