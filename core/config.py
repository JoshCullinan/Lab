from pathlib import Path

# ── URLs ──────────────────────────────────────────────────────────────────────
BASE_URL = "https://trakcarelabwebview.nhls.ac.za/trakcarelab/csp/system.Home.cls"
LOGIN_HASH = "#/Component/SSUser.Logon"
SEARCH_HASH = "#/Component/web.DEBDebtor.FindList"

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
COOKIES_PATH = _ROOT / "data" / "cookies.json"
CREDENTIALS_PATH = _ROOT / "userpsw.txt"

# ── Browser ───────────────────────────────────────────────────────────────────
BROWSER_HEADLESS = True
PAGE_TIMEOUT_MS = 30_000

# ── Login Selectors ──────────────────────────────────────────────────────────
SEL_USERNAME = "#SSUser_Logon_0-item-USERNAME"
SEL_PASSWORD = "#SSUser_Logon_0-item-PASSWORD"
SEL_LOGIN_BUTTON = "#SSUser_Logon_0-button-Logon"

# Post-login: the profile toggle shows the logged-in user's name
SEL_LOGGED_IN_INDICATOR = "#tc_NavBar-misc-profileToggle"

# The login form — present when session is expired / not authenticated
SEL_SESSION_EXPIRED = "#SSUser_Logon_0-form"

# ── Patient Search Selectors (web.DEBDebtor.FindList) ────────────────────────
SEL_SEARCH_SPECIMEN = "#web_DEBDebtor_FindList_0-item-SpecimenParam"
SEL_SEARCH_SURNAME = "#web_DEBDebtor_FindList_0-item-SurnameParam"
SEL_SEARCH_NAME = "#web_DEBDebtor_FindList_0-item-GivenNameParam"
SEL_SEARCH_MRN = "#web_DEBDebtor_FindList_0-item-MRNParam"
SEL_SEARCH_EPISODE = "#web_DEBDebtor_FindList_0-item-EpisodeParam"
SEL_SEARCH_HOSPITAL_MRN = "#web_DEBDebtor_FindList_0-item-HospitalMRN"
SEL_SEARCH_BUTTON = "#web_DEBDebtor_FindList_0-button-Find"
SEL_SEARCH_CLEAR = "#web_DEBDebtor_FindList_0-button-Clear"

# Search results table (patient list)
SEL_SEARCH_RESULTS_TABLE = "#tweb_DEBDebtor_FindList_0"
SEL_SEARCH_NO_MATCHES = "#web_EPVisitNumber_List_Banner-misc-noMatches"
# Patient rows: tr[id^="web_DEBDebtor_FindList_0-row-"]
SEL_SEARCH_RESULT_ROW = 'tr[id^="web_DEBDebtor_FindList_0-row-"]'
# MRN link on the first patient row — click to open results directly
SEL_MRN_LINK = '#web_DEBDebtor_FindList_0-row-0-item-MRN-link'
# Episodes dropdown icon on the patient row — click to expand episode details + test set links
SEL_EPISODES_DROPDOWN = "#web_DEBDebtor_FindList_0-row-0-item-Episodes"
# Episode rows within expanded patient: tr[id^="web_EPVisitNumber_List_0_0-row-"]
SEL_EPISODE_ROW = 'tr[id^="web_EPVisitNumber_List_0_0-row-"]'
# Episode row "• • •" action button
SEL_EPISODE_ACTION_BUTTON = '#web_EPVisitNumber_List_0_0-row-0-misc-actionButton'
# Test set links (e.g. "CRT", "NA", "K") — appear after expanding episodes
SEL_TEST_SET_LINK = 'a[id^="VISTS_"]'

# ── Result Detail Selectors (web.EPVisitTestSet.Result) ──────────────────────

# Patient banner (top bar on results page)
SEL_BANNER_MRN = "#web_EPVisitNumber_List_Banner-row-0-item-MRNLink-link"
SEL_BANNER_EPISODE = "#web_EPVisitNumber_List_Banner-row-0-item-Episode"
SEL_BANNER_GIVEN_NAME = "#web_EPVisitNumber_List_Banner-row-0-item-GivenName"
SEL_BANNER_SURNAME = "#web_EPVisitNumber_List_Banner-row-0-item-Surname"
SEL_BANNER_DOB = "#web_EPVisitNumber_List_Banner-row-0-item-DOB"

# Result metadata
SEL_RESULT_STATUS = "#web_EPVisitTestSet_Result_0-item-VISTSStatusResult"
SEL_RESULT_ORDERED_BY = "#web_EPVisitTestSet_Result_0-item-OrderedBy"
SEL_RESULT_COLLECTION_DATE = "#web_EPVisitTestSet_Result_0-item-CollectionDate"
SEL_RESULT_COLLECTION_TIME = "#web_EPVisitTestSet_Result_0-item-CollectionTime"
SEL_RESULT_RESULT_DATE = "#web_EPVisitTestSet_Result_0-item-ResultDate"
SEL_RESULT_RESULT_TIME = "#web_EPVisitTestSet_Result_0-item-ResultTime"
SEL_RESULT_COMMENTS = "#web_EPVisitTestSet_Result_0-item-Comments"
SEL_RESULT_REPORTABLE_REASON = "#web_EPVisitTestSet_Result_0-item-ReportableReason"

# Results table
SEL_RESULTS_TABLE = "#tweb_EPVisitTestSet_Result_0"
SEL_RESULTS_FORM = "#web_EPVisitTestSet_Result_0-form"
# Test result rows: tr[id^="web_EPVisitTestSet_Result_0-row-"]
SEL_RESULT_ROW = 'tr[id^="web_EPVisitTestSet_Result_0-row-"]'
# Within each row, cells follow the pattern:
#   [id$="-item-TestItem"]   → test name (e.g. "Thyroxine (free T4)")
#   [id$="-item-Value"]      → value (e.g. "10.8")
#   [id$="-item-Value-status"] → flag/status indicator
#   Units column (by position)
#   Reference Range column (by position — "PreferenceRange" in TrakCare)
