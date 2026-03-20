import io
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

import pdfplumber
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from core import config
from core.auth import AuthManager, SessionExpiredError
from core.session_manager import SessionManager


def _dbg(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    test_name: str
    value: str
    unit: str
    reference_range: str
    flag: Optional[str]          # "H", "L", "CRITICAL", "PENDING", or None
    collection_datetime: str


@dataclass
class PatientResult:
    patient_name: str
    patient_id: str
    specimen_id: str
    episode: str
    requesting_doctor: str
    dob: str
    status: str
    collection_datetime: str
    result_datetime: str
    tests: list[TestResult] = field(default_factory=list)


@dataclass
class EpisodeRow:
    row_index: int
    episode_number: str
    doctor: str
    collection_datetime: str
    pdf_selector: str           # "#web_EPVisitNumber_List_1-row-N-item-DocRptPDF-link"
    clickable: list[dict]       # [{id, text}] — VISTS_ links scoped to this row
    pending: list[str]


@dataclass
class PatientSearchHit:
    row_index: int
    mrn: str
    surname: str
    given_name: str
    dob: str
    episode: str


# ── Manager ───────────────────────────────────────────────────────────────────

class ResultsManager:
    def __init__(self, session: SessionManager, auth: AuthManager):
        self._session = session
        self._auth = auth

    # ── Public API ────────────────────────────────────────────────────────────

    async def search_by_specimen(self, specimen_id: str) -> Optional[PatientResult]:
        """Search for a patient result by specimen ID."""
        await self._auth.ensure_authenticated()
        page = await self._session.get_page()

        await self._navigate_to_search(page)
        await self._submit_search(page, specimen_id)

        try:
            await page.wait_for_selector(
                config.SEL_MRN_LINK, state="visible", timeout=config.PAGE_TIMEOUT_MS,
            )
        except PlaywrightTimeout:
            self._check_for_session_expiry(page)
            no_matches = await page.query_selector(config.SEL_SEARCH_NO_MATCHES)
            if no_matches and await no_matches.is_visible():
                return None
            return None

        mrn_link = await page.query_selector(config.SEL_MRN_LINK)
        if not mrn_link:
            return None
        await mrn_link.click()

        return await self._process_patient_page(page, specimen_id)

    async def search_by_episode(self, episode_id: str) -> Optional[PatientResult]:
        """Search for a patient result by episode number."""
        await self._auth.ensure_authenticated()
        page = await self._session.get_page()

        await self._navigate_to_search(page)
        await page.click(config.SEL_SEARCH_CLEAR)
        await page.wait_for_timeout(500)
        await page.fill(config.SEL_SEARCH_EPISODE, episode_id)
        await page.click(config.SEL_SEARCH_BUTTON)

        # TrakCare may show a patient list or navigate directly to the episode
        try:
            await page.wait_for_selector(
                config.SEL_MRN_LINK, state="visible", timeout=config.PAGE_TIMEOUT_MS,
            )
            mrn_link = await page.query_selector(config.SEL_MRN_LINK)
            if mrn_link:
                await mrn_link.click()
        except PlaywrightTimeout:
            # May have navigated directly to episode list — check for banner
            try:
                await page.wait_for_selector(
                    config.SEL_BANNER_SURNAME, timeout=5000,
                )
            except PlaywrightTimeout:
                self._check_for_session_expiry(page)
                return None

        return await self._process_patient_page(page, episode_id)

    async def search_by_hospital_mrn(self, hospital_mrn: str) -> Optional[PatientResult]:
        """Search for a patient result by hospital MRN."""
        await self._auth.ensure_authenticated()
        page = await self._session.get_page()

        await self._navigate_to_search(page)
        await page.click(config.SEL_SEARCH_CLEAR)
        await page.wait_for_timeout(500)
        await page.fill(config.SEL_SEARCH_HOSPITAL_MRN, hospital_mrn)
        await page.click(config.SEL_SEARCH_BUTTON)

        try:
            await page.wait_for_selector(
                config.SEL_MRN_LINK, state="visible", timeout=config.PAGE_TIMEOUT_MS,
            )
        except PlaywrightTimeout:
            self._check_for_session_expiry(page)
            return None

        mrn_link = await page.query_selector(config.SEL_MRN_LINK)
        if not mrn_link:
            return None
        await mrn_link.click()

        return await self._process_patient_page(page, hospital_mrn)

    async def search_patients_by_hospital_mrn(self, hospital_mrn: str) -> list[dict]:
        """Search by hospital MRN → return patient list for selection.

        Returns list of patient hit dicts (like search_by_name).
        """
        await self._auth.ensure_authenticated()
        page = await self._session.get_page()

        await self._navigate_to_search(page)
        await page.click(config.SEL_SEARCH_CLEAR)
        await page.wait_for_timeout(500)
        await page.fill(config.SEL_SEARCH_HOSPITAL_MRN, hospital_mrn)
        await page.click(config.SEL_SEARCH_BUTTON)

        # Wait for first patient row MRN link to appear
        try:
            await page.wait_for_selector(
                config.SEL_MRN_LINK, state="visible", timeout=config.PAGE_TIMEOUT_MS,
            )
        except PlaywrightTimeout:
            self._check_for_session_expiry(page)
            return []

        return await page.evaluate('''
            () => {
                const rows = document.querySelectorAll('tr[id^="web_DEBDebtor_FindList_0-row-"]');
                return Array.from(rows).map((row, i) => {
                    function cellText(suffix) {
                        const el = row.querySelector('[id$="' + suffix + '"]');
                        return el ? el.innerText.trim() : '';
                    }
                    return {
                        row_index: i,
                        mrn: cellText('-item-MRN-link') || cellText('-item-MRN'),
                        surname: cellText('-item-Surname'),
                        given_name: cellText('-item-GivenName'),
                        dob: cellText('-item-DOB'),
                        episode: cellText('-item-Episode'),
                    };
                });
            }
        ''')

    async def list_episodes_for_patient(self, patient_row_index: int) -> Optional[dict]:
        """Click a patient row from search results, wait for episode list, return scraped data."""
        page = await self._session.get_page()
        mrn_selector = f'#web_DEBDebtor_FindList_0-row-{patient_row_index}-item-MRN-link'

        mrn_link = await page.query_selector(mrn_selector)
        if not mrn_link:
            return None
        await mrn_link.click()

        try:
            await page.wait_for_selector(
                config.SEL_BANNER_SURNAME, timeout=config.PAGE_TIMEOUT_MS,
            )
        except PlaywrightTimeout:
            self._check_for_session_expiry(page)
            return None

        return await self._scrape_episode_list(page)

    async def load_episode_results(self, row_index: int, episode_data: dict) -> Optional[PatientResult]:
        """Given a scraped episode list and a selected row index, load that episode's results.

        Directly clicks the PDF link for the target row on the current page (which
        opens a popup), keeping us on the episode list so subsequent calls work.
        Never navigates away — safe to call repeatedly for multiple rows.
        """
        rows = episode_data.get("rows", [])
        target = None
        for r in rows:
            if r["row_index"] == row_index:
                target = r
                break
        if not target:
            return None

        episode_num = target.get("episode_number", "")
        page = await self._session.get_page()

        # Small settle delay between PDF fetches
        await page.wait_for_timeout(500)

        pdf_link = await page.query_selector(target["pdf_selector"])
        if not pdf_link:
            return None

        pdf_bytes = await self._fetch_pdf_bytes(page, pdf_link)
        if not pdf_bytes:
            return None

        tests = self._parse_pdf(pdf_bytes, target["collection_datetime"])
        if not tests:
            return None

        return PatientResult(
            patient_name=episode_data["patient_name"],
            patient_id=episode_data["patient_id"],
            specimen_id=episode_num or f"row-{row_index}",
            episode=episode_num,
            requesting_doctor=target.get("doctor", ""),
            dob=episode_data["dob"],
            status="", collection_datetime=target["collection_datetime"],
            result_datetime="", tests=tests,
        )

    async def search_by_name(self, surname: str, given_name: str = "") -> list[dict]:
        """Search by surname (and optional given name). Returns list of patient hit dicts."""
        await self._auth.ensure_authenticated()
        page = await self._session.get_page()

        await self._navigate_to_search(page)
        await page.click(config.SEL_SEARCH_CLEAR)
        await page.wait_for_timeout(500)
        await page.fill(config.SEL_SEARCH_SURNAME, surname)
        if given_name:
            await page.fill(config.SEL_SEARCH_NAME, given_name)
        await page.click(config.SEL_SEARCH_BUTTON)

        try:
            await page.wait_for_selector(
                config.SEL_SEARCH_RESULTS_TABLE, timeout=config.PAGE_TIMEOUT_MS,
            )
        except PlaywrightTimeout:
            self._check_for_session_expiry(page)
            return []

        hits = await page.evaluate('''
            () => {
                const rows = document.querySelectorAll('tr[id^="web_DEBDebtor_FindList_0-row-"]');
                return Array.from(rows).map((row, i) => {
                    function cellText(suffix) {
                        const el = row.querySelector('[id$="' + suffix + '"]');
                        return el ? el.innerText.trim() : '';
                    }
                    return {
                        row_index: i,
                        mrn: cellText('-item-MRN-link') || cellText('-item-MRN'),
                        surname: cellText('-item-Surname'),
                        given_name: cellText('-item-GivenName'),
                        dob: cellText('-item-DOB'),
                        episode: cellText('-item-Episode'),
                    };
                });
            }
        ''')
        return hits

    async def open_patient_by_hit(self, hit: dict, search_term: str) -> Optional[PatientResult]:
        """Click a specific patient row from search results and load their data."""
        page = await self._session.get_page()
        row_index = hit["row_index"]
        mrn_selector = f'#web_DEBDebtor_FindList_0-row-{row_index}-item-MRN-link'

        mrn_link = await page.query_selector(mrn_selector)
        if not mrn_link:
            return None
        await mrn_link.click()

        return await self._process_patient_page(page, search_term)

    # ── Shared patient page processor ─────────────────────────────────────────

    async def _process_patient_page(self, page: Page, search_id: str) -> Optional[PatientResult]:
        """Wait for episode list banner, scrape all episodes, fetch all PDFs, fall back to DOM."""
        try:
            await page.wait_for_selector(
                config.SEL_BANNER_SURNAME, timeout=config.PAGE_TIMEOUT_MS,
            )
        except PlaywrightTimeout:
            self._check_for_session_expiry(page)
            return None

        episode_data = await self._scrape_episode_list(page)

        result = await self._try_pdf_approach_all_rows(page, search_id, episode_data)
        if result:
            return result

        return await self._click_test_sets(page, search_id, episode_data)

    # ── Episode list scraping ────────────────────────────────────────────────

    async def _scrape_episode_list(self, page: Page) -> dict:
        """Scrape all episode rows for patient info and test set status."""
        return await page.evaluate(r'''
            () => {
                function text(id) {
                    const el = document.getElementById(id);
                    return el ? el.innerText.trim() : '';
                }

                const surname   = text('web_EPVisitNumber_List_Banner-row-0-item-Surname');
                const givenName = text('web_EPVisitNumber_List_Banner-row-0-item-GivenName');
                const mrn       = text('web_EPVisitNumber_List_Banner-row-0-item-MRNLink-link');
                const episode   = text('web_EPVisitNumber_List_Banner-row-0-item-Episode');
                const dob       = text('web_EPVisitNumber_List_Banner-row-0-item-DOB');

                // Global VISTS_ links — flat list for backward-compat fallback
                const allVistsLinks = Array.from(document.querySelectorAll('a[id^="VISTS_"]'))
                    .map(a => ({id: a.id, text: a.innerText.trim()}));
                const clickableNames = new Set(allVistsLinks.map(l => l.text));

                // Per-row iteration over all episode rows
                const episodeTrs = document.querySelectorAll('tr[id^="web_EPVisitNumber_List_1-row-"]');
                const rows = Array.from(episodeTrs).map((tr, i) => {
                    const rowId = tr.id;
                    const idMatch = rowId.match(/-row-(\d+)$/);
                    const rowIndex = idMatch ? parseInt(idMatch[1]) : i;

                    const doctor         = text(rowId + '-item-Doctor');
                    const collectionDate = text(rowId + '-item-CollectionDate');
                    const collectionTime = text(rowId + '-item-CollectionTime');
                    const episodeNum     = text(rowId + '-item-Episode') || '';
                    const pdfSelector    = '#' + rowId + '-item-DocRptPDF-link';

                    // VISTS_ links scoped to this row
                    const rowVistsLinks = Array.from(tr.querySelectorAll('a[id^="VISTS_"]'))
                        .map(a => ({id: a.id, text: a.innerText.trim()}));

                    return {
                        row_index: rowIndex,
                        episode_number: episodeNum,
                        doctor: doctor,
                        collection_datetime: collectionDate + ' ' + collectionTime,
                        pdf_selector: pdfSelector,
                        clickable: rowVistsLinks,
                        pending: [],
                    };
                });

                // Global pending tests: text nodes in TSList cell that aren't links
                const tsListLabel = document.querySelector('[id$="-item-TSList-label"]');
                let pending = [];
                if (tsListLabel) {
                    const container = tsListLabel.closest('td') || tsListLabel.parentElement;
                    if (container) {
                        const walker = document.createTreeWalker(
                            container, NodeFilter.SHOW_TEXT, null, false
                        );
                        let node;
                        while (node = walker.nextNode()) {
                            const t = node.textContent.trim();
                            if (t && t.length <= 10 && t !== 'Test Set List' && !clickableNames.has(t)) {
                                pending.push(t);
                            }
                        }
                    }
                }

                // Backward-compat flat fields (use first row values)
                const firstRow = rows[0] || {};

                return {
                    patient_name: surname + ', ' + givenName,
                    patient_id: mrn,
                    episode: episode,
                    dob: dob,
                    doctor: firstRow.doctor || '',
                    collection_datetime: firstRow.collection_datetime || '',
                    clickable: allVistsLinks,
                    pending: pending,
                    rows: rows,
                };
            }
        ''')

    # ── PDF helpers ──────────────────────────────────────────────────────────

    async def _fetch_pdf_bytes(self, page: Page, pdf_link) -> Optional[bytes]:
        """Open the PDF popup, download the bytes, close the popup."""
        try:
            async with page.context.expect_page(timeout=20000) as new_page_info:
                await pdf_link.click()

            new_page = await new_page_info.value
            # networkidle required — PDF frame URL is empty until JS loads it
            await new_page.wait_for_load_state("networkidle", timeout=30000)

            pdf_bytes = None
            for frame in new_page.frames:
                url = frame.url
                # Skip non-http frames (empty, about:blank, chrome-extension:)
                if not url or not url.startswith('http') or url == new_page.url:
                    continue
                try:
                    response = await new_page.context.request.get(url)
                    body = await response.body()
                    if body[:5] == b'%PDF-':
                        pdf_bytes = body
                        break
                except Exception:
                    pass

            await new_page.close()
            return pdf_bytes

        except Exception as e:
            _dbg(f"DEBUG: _fetch_pdf_bytes error: {e}")
            return None

    async def _try_pdf_approach_all_rows(
        self, page: Page, search_id: str, scrape_data: dict
    ) -> Optional[PatientResult]:
        """Try to download and parse the PDF for every episode row, aggregate all tests."""
        rows = scrape_data.get("rows", [])
        if not rows:
            return None

        all_tests: list[TestResult] = []

        for row in rows:
            pdf_link = await page.query_selector(row["pdf_selector"])
            if not pdf_link:
                continue

            pdf_bytes = await self._fetch_pdf_bytes(page, pdf_link)
            if not pdf_bytes:
                continue

            row_tests = self._parse_pdf(pdf_bytes, row["collection_datetime"])
            all_tests.extend(row_tests)

        if not all_tests:
            return None

        # Append global pending tests
        for name in scrape_data.get("pending", []):
            all_tests.append(TestResult(
                test_name=name, value="Pending", unit="", reference_range="",
                flag="PENDING", collection_datetime="",
            ))

        first_row = rows[0]
        return PatientResult(
            patient_name=scrape_data["patient_name"],
            patient_id=scrape_data["patient_id"],
            specimen_id=search_id,
            episode=scrape_data.get("episode", ""),
            requesting_doctor=first_row.get("doctor", ""),
            dob=scrape_data["dob"],
            status="",
            collection_datetime=first_row.get("collection_datetime", ""),
            result_datetime="",
            tests=all_tests,
        )

    def _parse_pdf(self, pdf_bytes: bytes, collection_dt: str) -> list[TestResult]:
        """Parse a TrakCare lab result PDF. Returns [] on failure."""
        tests: list[TestResult] = []

        # Fast path: pdfplumber text extraction — concatenate ALL pages
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                all_text = []
                for pg in pdf.pages:
                    text = pg.extract_text() or ""
                    if text.strip():
                        all_text.append(text)
                if all_text:
                    tests = self._parse_pdf_text("\n".join(all_text), collection_dt)
        except Exception as e:
            _dbg(f"DEBUG: pdfplumber text extraction error: {e}")

        # Fallback: OCR for scanned/image-based PDFs
        if not tests:
            tests = self._parse_pdf_ocr(pdf_bytes, collection_dt)

        return tests

    # ── PDF text parser ──────────────────────────────────────────────────────

    # Unit pattern: allows parentheses for units like Log(copies/mL), x10^9/L
    _UNIT_PAT = r'[a-zA-Z\xb5/%][/a-zA-Z\xb5\xb2%0-9.*^()]*'

    # 4-field: Name Value Unit RefRange  (ref range is "x - y")
    _PDF_LINE_RE = re.compile(
        r'^(?P<name>.+?)\s+(?P<value>[><]?\d+[\d.]*\s*[HL]?)\s+(?P<unit>' + _UNIT_PAT + r')\s+(?P<range>\d+[\d.]*\s*-\s*\d+[\d.]*\s*)?$'
    )
    # 4-field with single-sided ref range: Name Value Unit <x or >x
    _PDF_LINE_RE_SINGLESIDED = re.compile(
        r'^(?P<name>.+?)\s+(?P<value>[><]?\d+[\d.]*\s*[HL]?)\s+(?P<unit>' + _UNIT_PAT + r')\s+(?P<range>[<>]\d+[\d.]*\s*)?$'
    )
    # 2-field: Name Value (indices like "2+" or "Not detected")
    _PDF_LINE_RE2 = re.compile(
        r'^(?P<name>.+?)\s+(?P<value>Not detected|\d+[+])\s*$'
    )
    # 3-field: Name Value Unit (no ref range — lipid fractions, TSH, B12, etc.)
    _PDF_LINE_RE3 = re.compile(
        r'^(?P<name>.+?)\s+(?P<value>[><]?\d+[\d.]*\s*[HL]?)\s+(?P<unit>' + _UNIT_PAT + r')\s*$'
    )
    # 3-field with compound unit containing a space (e.g. "eGFR (MDRD) 51 mL/min/1.73 m²")
    _PDF_LINE_RE_COMPOUND = re.compile(
        r'^(?P<name>.+?)\s+(?P<value>[><]?\d+[\d.]*\s*[HL]?)\s+(?P<unit>mL/min/[\d.]+\s*\S*)\s*$'
    )
    # 2-field: Name bare-numeric-value (no unit, e.g. "Fluid pH 8.00")
    _PDF_LINE_RE_BARE = re.compile(
        r'^(?P<name>.+?)\s+(?P<value>[><]?\d+[\d.]+)\s*$'
    )

    # ── Section header sets ──────────────────────────────────────────────────

    _SECTION_HEADERS = frozenset([
        # Chemistry
        'blood chemistry', 'liver function tests', 'lipids', 'inflammatory markers',
        'haematinics', 'thyroid function tests', 'indices', 'indices in serum',
        'creatinine and estimated gfr',
        # Fluid chemistry
        'fluid chemistry',
        # Haematology / immunology
        'cdarv', 'full blood count',
        # Virology
        'hiv molecular investigations', 'hiv viral load',
    ])

    # Micro/culture sections — captured as free-text blocks
    _MICRO_SECTION_HEADERS = frozenset([
        'gram stain', 'bacterial culture', 'tb-naat',
    ])

    _ADVISORY_HEADERS = frozenset([
        'cardiovascular risk', 'disclaimer',
        'evaluation of effusion results',
        'cd4 arv comment', 'comment',
        'lower respiratory tract infection',
        'systemic bacterial infection',
        'systemic bacterial infection / sepsis',
    ])

    @staticmethod
    def _is_section_header(line: str, section_headers: frozenset) -> bool:
        # Strip trailing :<tag> (e.g. "Blood chemistry:<Continued>") and colons
        cleaned = re.sub(r':<.*?>$', '', line).strip().rstrip(':')
        # Also handle "TB-NAAT: GeneXpert MTB/Rif Ultra" — take text before first colon
        if ':' in cleaned:
            prefix = cleaned.split(':')[0].strip()
            if prefix.lower() in section_headers:
                return True
        return cleaned.lower() in section_headers

    @staticmethod
    def _is_advisory_header(line: str, advisory_headers: frozenset) -> bool:
        stripped = line.strip().rstrip(':')
        if stripped.lower() in advisory_headers:
            return True
        # All-caps text-only lines with 2+ words (department headers like CHEMICAL PATHOLOGY)
        if (line == line.upper() and len(line.split()) >= 2
                and line[0].isalpha() and not any(c.isdigit() for c in line)):
            return True
        return False

    @staticmethod
    def _extract_flag(value_str: str) -> tuple[Optional[str], str]:
        m = re.search(r'\s([HL])\s*$', value_str)
        if m:
            return m.group(1), value_str[:m.start()].rstrip()
        return None, value_str

    @staticmethod
    def _preprocess_pdf_text(text: str) -> str:
        """Fix superscript artifacts from pdfplumber extraction."""
        # Fix superscript 9 in units like "x 10 /L" → "x10^9/L"
        # pdfplumber extracts the superscript 9 as a standalone line
        text = re.sub(r' x 10 /L', ' x10^9/L', text)
        # Fix superscript 2 in "mL/min/1.73 m" → "mL/min/1.73m²"
        text = re.sub(r'mL/min/([\d.]+)\s+m\b', r'mL/min/\1m²', text)
        return text

    def _parse_pdf_text(self, text: str, collection_dt: str) -> list[TestResult]:
        """Parse pdfplumber-extracted text — section-based state machine."""
        text = self._preprocess_pdf_text(text)

        tests: list[TestResult] = []
        in_results_section = False
        in_micro_section = False
        micro_lines: list[str] = []
        micro_name = ""

        def _flush_micro():
            nonlocal micro_lines, micro_name, in_micro_section
            if micro_lines:
                tests.append(TestResult(
                    test_name=micro_name,
                    value="\n".join(micro_lines),
                    unit="", reference_range="", flag=None,
                    collection_datetime=collection_dt,
                ))
            micro_lines = []
            micro_name = ""
            in_micro_section = False

        for raw in text.split('\n'):
            line = raw.strip()
            if not line:
                continue

            if self._is_skip_line(line):
                continue

            # ── Section transitions ──

            if self._is_section_header(line, self._SECTION_HEADERS):
                _flush_micro()
                in_results_section = True
                continue

            if self._is_section_header(line, self._MICRO_SECTION_HEADERS):
                _flush_micro()
                in_micro_section = True
                # Use the header text (before colon) as the section name
                micro_name = re.sub(r':<.*?>$', '', line).strip().rstrip(':')
                if ':' in micro_name:
                    # "TB-NAAT: GeneXpert MTB/Rif Ultra" → keep full text
                    pass
                in_results_section = False
                continue

            if self._is_advisory_header(line, self._ADVISORY_HEADERS):
                _flush_micro()
                in_results_section = False
                continue

            # ── Micro section: accumulate free text ──

            if in_micro_section:
                micro_lines.append(line)
                continue

            if not in_results_section:
                continue

            # ── Standard result line matching ──

            # 4-field: Name Value Unit RefRange
            m = self._PDF_LINE_RE.match(line)
            if m:
                flag, value_str = self._extract_flag(m.group('value').strip())
                tests.append(TestResult(
                    test_name=m.group('name').strip(),
                    value=value_str,
                    unit=m.group('unit').strip(),
                    reference_range=(m.group('range') or '').strip(),
                    flag=flag,
                    collection_datetime=collection_dt,
                ))
                continue

            # 4-field single-sided ref range
            m_ss = self._PDF_LINE_RE_SINGLESIDED.match(line)
            if m_ss:
                flag, value_str = self._extract_flag(m_ss.group('value').strip())
                tests.append(TestResult(
                    test_name=m_ss.group('name').strip(),
                    value=value_str,
                    unit=m_ss.group('unit').strip(),
                    reference_range=(m_ss.group('range') or '').strip(),
                    flag=flag,
                    collection_datetime=collection_dt,
                ))
                continue

            # 2-field: Name + "Not detected" or "2+"
            m2 = self._PDF_LINE_RE2.match(line)
            if m2:
                tests.append(TestResult(
                    test_name=m2.group('name').strip(),
                    value=m2.group('value').strip(),
                    unit='', reference_range='', flag=None,
                    collection_datetime=collection_dt,
                ))
                continue

            # 3-field: Name Value Unit
            m3 = self._PDF_LINE_RE3.match(line)
            if m3:
                name = m3.group('name').strip()
                if not re.search(r'\d\s-\s*$', name):
                    flag, value_str = self._extract_flag(m3.group('value').strip())
                    tests.append(TestResult(
                        test_name=name,
                        value=value_str,
                        unit=m3.group('unit').strip(),
                        reference_range='', flag=flag,
                        collection_datetime=collection_dt,
                    ))
                continue

            # Compound unit (eGFR)
            mc = self._PDF_LINE_RE_COMPOUND.match(line)
            if mc:
                flag, value_str = self._extract_flag(mc.group('value').strip())
                tests.append(TestResult(
                    test_name=mc.group('name').strip(),
                    value=value_str,
                    unit=mc.group('unit').strip(),
                    reference_range='', flag=flag,
                    collection_datetime=collection_dt,
                ))
                continue

            # Bare numeric: Name Value (no unit, e.g. "Fluid pH 8.00")
            mb = self._PDF_LINE_RE_BARE.match(line)
            if mb:
                tests.append(TestResult(
                    test_name=mb.group('name').strip(),
                    value=mb.group('value').strip(),
                    unit='', reference_range='', flag=None,
                    collection_datetime=collection_dt,
                ))
                continue

        # Flush any trailing micro section
        _flush_micro()

        return tests

    def _is_skip_line(self, raw: str) -> bool:
        """Return True for page banners, headers, footer, and non-result lines."""
        upper = raw.upper()

        # Page banners (first page and continuation pages)
        if 'LAB NUMBER:' in upper:
            return True
        if 'PRACTICE NUMBER' in upper:
            return True
        if 'PATIENT:' in upper and 'REPORT TO:' in upper:
            return True
        if 'BHEKI MLANGENI' in upper or 'ZOLA JABULANI' in upper:
            return True
        if re.match(r'pg\s+\d+\s+of\s+\d+', raw, re.IGNORECASE):
            return True
        if re.match(r'LH\s+\w+', raw):
            return True
        # Continuation page location lines: "Hospital, Ward, Hospital Number XXXXX"
        if 'HOSPITAL NUMBER' in upper and ',' in raw:
            return True
        if 'PRINTED:' in upper or 'COLLECTED:' in upper or 'RECEIVED:' in upper:
            return True
        if '1ST PRINT:' in upper or 'REPRINT:' in upper:
            return True

        # Footer
        if 'AUTHORIZED BY:' in upper or 'AUTHORISED BY:' in upper or '-- END OF LABORATORY REPORT --' in upper:
            return True

        # Non-result metadata lines
        if re.match(r'\d{2}/\d{2}/\d{2}\s+\(\d+y\)\s+Sex\s+[MF]', raw):
            return True
        if re.match(r'Sample Ref:', raw) or re.match(r'Hospital Number:', raw):
            return True
        if re.match(r'\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}', raw):
            return True
        if re.match(r'\d{4}\s*$', raw):
            return True
        if re.match(r'^[MF]\s+\d+y\)', raw):
            return True
        # "@" referral lines (e.g. "@ Test referred to another NHLS laboratory")
        if raw.startswith('@') or raw.startswith('@ '):
            return True
        # "Specimen received:" / "Tests requested:" lines
        if re.match(r'(Specimen received|Tests requested):', raw):
            return True
        # "Patient Location:" lines
        if raw.startswith('Patient Location:'):
            return True
        # "FOR ENQUIRIES" boilerplate
        if 'FOR ENQUIRIES' in upper:
            return True

        # Lipid target table rows
        if re.match(r'<\d+(\.\d+)?\s*mmol/L\s*$', raw):
            return True
        if re.match(r'(Low Risk|Moderate Risk|High Risk|Very High Risk)', raw, re.IGNORECASE):
            return True
        if re.match(r'(TC target|LDLC target|non-HDLC target|Risk Category)', raw, re.IGNORECASE):
            return True
        if re.match(r'(Fasting triglycerides|When TG|While higher|Additionally)', raw):
            return True

        # Reference/citation lines
        if re.match(r'(https?://|References:)', raw):
            return True
        if re.match(r'[A-Z][a-z]+ [A-Z]+,?\s+et al\.', raw):
            return True
        # Journal citations (e.g. "Clin Chim Acta", "Eur Heart J")
        if re.search(r'Clin Chim|Eur Heart|S Afr Med|doi\.org', raw):
            return True
        # Commentary boilerplate that matches bare-numeric pattern
        if raw.startswith('Based on the sample') or raw.startswith('The result should'):
            return True
        if 'effusions' in raw.lower() and 'Acta' in raw:
            return True

        # Purely numeric standalone lines (page numbers, superscript digits)
        if re.match(r'^\d[\d\s.-]*$', raw):
            return True

        return False

    def _parse_pdf_ocr(self, pdf_bytes: bytes, collection_dt: str) -> list[TestResult]:
        """Render PDF pages to images and run Tesseract OCR."""
        try:
            import pytesseract
            import fitz  # PyMuPDF
        except ImportError as e:
            _dbg(f"DEBUG: Missing dependency for OCR: {e}")
            return []

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            _dbg(f"DEBUG: Failed to open PDF with PyMuPDF: {e}")
            return []

        all_text = []
        for page_num, page in enumerate(doc):
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            try:
                text = pytesseract.image_to_string(img_bytes)
                all_text.append(text)
            except Exception as e:
                _dbg(f"DEBUG: OCR failed on page {page_num + 1}: {e}")

        doc.close()

        if not all_text:
            return []

        return self._parse_pdf_text("\n".join(all_text), collection_dt)

    # ── Click through test sets ──────────────────────────────────────────────

    async def _click_test_sets(self, page: Page, specimen_id: str, episode_data: dict) -> Optional[PatientResult]:
        """Click each test set link and aggregate all results."""
        clickable = episode_data.get("clickable", [])
        if not clickable:
            pending = episode_data.get("pending", [])
            if not pending:
                return None
            return PatientResult(
                patient_name=episode_data["patient_name"],
                patient_id=episode_data["patient_id"],
                specimen_id=specimen_id,
                episode=episode_data["episode"],
                requesting_doctor=episode_data.get("doctor", ""),
                dob=episode_data["dob"],
                status="",
                collection_datetime=episode_data.get("collection_datetime", ""),
                result_datetime="",
                tests=[
                    TestResult(test_name=n, value="Pending", unit="", reference_range="",
                               flag="PENDING", collection_datetime="")
                    for n in pending
                ],
            )

        first_link = await page.query_selector(f'#{clickable[0]["id"]}')
        if not first_link:
            return None
        await first_link.click()

        try:
            await page.wait_for_selector(config.SEL_RESULTS_TABLE, timeout=config.PAGE_TIMEOUT_MS)
        except PlaywrightTimeout:
            self._check_for_session_expiry(page)
            return None

        result = await self._parse_result_detail(page, specimen_id)
        if not result:
            return None

        for ts in clickable[1:]:
            await page.go_back(wait_until="domcontentloaded")
            try:
                await page.wait_for_selector(f'#{ts["id"]}', state="visible", timeout=10000)
            except PlaywrightTimeout:
                continue
            ts_link = await page.query_selector(f'#{ts["id"]}')
            if not ts_link:
                continue
            await ts_link.click()
            try:
                await page.wait_for_selector(config.SEL_RESULTS_TABLE, timeout=10000)
            except PlaywrightTimeout:
                continue
            extra = await self._parse_test_rows(page)
            result.tests.extend(extra)

        for name in episode_data.get("pending", []):
            result.tests.append(TestResult(
                test_name=name, value="Pending", unit="", reference_range="",
                flag="PENDING", collection_datetime="",
            ))

        return result

    # ── Navigation helpers ────────────────────────────────────────────────────

    async def _navigate_to_search(self, page: Page) -> None:
        """Navigate to the Patient Find search page."""
        search_url = config.BASE_URL + config.SEARCH_HASH
        await page.goto(search_url, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
        self._check_for_session_expiry(page)
        await page.wait_for_selector(config.SEL_SEARCH_SPECIMEN, timeout=config.PAGE_TIMEOUT_MS)

    async def _submit_search(self, page: Page, specimen_id: str) -> None:
        """Clear the form, fill specimen ID, and click Search."""
        await page.click(config.SEL_SEARCH_CLEAR)
        await page.wait_for_timeout(500)
        await page.fill(config.SEL_SEARCH_SPECIMEN, specimen_id)
        await page.click(config.SEL_SEARCH_BUTTON)

    # ── Result detail parsing ─────────────────────────────────────────────────

    _JS_PARSE_DETAIL = """
    () => {
        function text(id) {
            const el = document.getElementById(id);
            return el ? el.innerText.trim() : '';
        }

        return {
            patient_name: text('web_EPVisitNumber_List_Banner-row-0-item-Surname')
                + ', ' + text('web_EPVisitNumber_List_Banner-row-0-item-GivenName'),
            patient_id: text('web_EPVisitNumber_List_Banner-row-0-item-MRNLink-link'),
            episode: text('web_EPVisitNumber_List_Banner-row-0-item-Episode'),
            dob: text('web_EPVisitNumber_List_Banner-row-0-item-DOB'),
            requesting_doctor: text('web_EPVisitTestSet_Result_0-item-OrderedBy'),
            status: text('web_EPVisitTestSet_Result_0-item-VISTSStatusResult'),
            collection_datetime: text('web_EPVisitTestSet_Result_0-item-CollectionDate')
                + ' ' + text('web_EPVisitTestSet_Result_0-item-CollectionTime'),
            result_datetime: text('web_EPVisitTestSet_Result_0-item-ResultDate')
                + ' ' + text('web_EPVisitTestSet_Result_0-item-ResultTime'),
        };
    }
    """

    _JS_PARSE_ROWS = """
    () => {
        function text(id) {
            const el = document.getElementById(id);
            return el ? el.innerText.trim() : '';
        }

        const collectionDate = text('web_EPVisitTestSet_Result_0-item-CollectionDate');
        const collectionTime = text('web_EPVisitTestSet_Result_0-item-CollectionTime');

        const rows = document.querySelectorAll('tr[id^="web_EPVisitTestSet_Result_0-row-"]');
        const tests = [];
        rows.forEach(row => {
            const rowId = row.id;
            const testName = text(rowId + '-item-TestItem');
            const value    = text(rowId + '-item-Value');

            let flag = null;
            const statusEl = document.getElementById(rowId + '-item-Value-status');
            if (statusEl) {
                const statusText = statusEl.innerText.trim();
                if (statusText) flag = statusText;
            }
            if (!flag) {
                const valueEl = document.getElementById(rowId + '-item-Value');
                if (valueEl) {
                    const color = window.getComputedStyle(valueEl).color;
                    if (color === 'rgb(255, 0, 0)' || color === 'rgb(204, 0, 0)') {
                        flag = 'ABNORMAL';
                    }
                }
            }

            const cells = row.querySelectorAll('td');
            let unit = '';
            let refRange = '';
            if (cells.length > 2) unit = cells[2] ? cells[2].innerText.trim() : '';
            if (cells.length > 3) refRange = cells[3] ? cells[3].innerText.trim() : '';

            if (testName) {
                tests.push({
                    test_name: testName,
                    value: value,
                    unit: unit,
                    reference_range: refRange,
                    flag: flag,
                    collection_datetime: collectionDate + ' ' + collectionTime,
                });
            }
        });
        return tests;
    }
    """

    async def _parse_result_detail(self, page: Page, specimen_id: str) -> Optional[PatientResult]:
        """Parse patient info and test rows from the result detail page."""
        data = await page.evaluate(self._JS_PARSE_DETAIL)
        if not data or not data.get("patient_name", "").replace(", ", ""):
            return None

        tests = await self._parse_test_rows(page)

        return PatientResult(
            patient_name=data["patient_name"],
            patient_id=data["patient_id"],
            specimen_id=specimen_id,
            episode=data["episode"],
            requesting_doctor=data["requesting_doctor"],
            dob=data["dob"],
            status=data["status"],
            collection_datetime=data["collection_datetime"],
            result_datetime=data["result_datetime"],
            tests=tests,
        )

    async def _parse_test_rows(self, page: Page) -> list[TestResult]:
        """Parse just the test result rows from the current page."""
        raw = await page.evaluate(self._JS_PARSE_ROWS)
        results = []
        for t in raw:
            if "comment" in t["test_name"].lower():
                continue
            flag = t["flag"] if t["flag"] else self._infer_flag(t["value"], t["reference_range"])
            results.append(TestResult(
                test_name=t["test_name"],
                value=t["value"],
                unit=t["unit"],
                reference_range=t["reference_range"],
                flag=flag,
                collection_datetime=t["collection_datetime"],
            ))
        return results

    @staticmethod
    def _infer_flag(value: str, ref_range: str) -> Optional[str]:
        """Derive H/L flag by comparing numeric value against reference range."""
        if not ref_range:
            return None
        try:
            v = float(re.sub(r'[^\d.]', '', value))
        except (ValueError, TypeError):
            return None
        m = re.match(r'^([\d.]+)\s*-\s*([\d.]+)\s*$', ref_range.strip())
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if v < lo:
                return 'L'
            if v > hi:
                return 'H'
            return None
        m_ss = re.match(r'^([<>])([\d.]+)\s*$', ref_range.strip())
        if m_ss:
            op, bound = m_ss.group(1), float(m_ss.group(2))
            if op == '<' and v >= bound:
                return 'H'
            if op == '>' and v <= bound:
                return 'L'
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _check_for_session_expiry(self, page: Page) -> None:
        if "SSUser.Logon" in page.url:
            raise SessionExpiredError("Session expired — redirected to login page")
