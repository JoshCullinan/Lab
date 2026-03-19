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


# ── Manager ───────────────────────────────────────────────────────────────────

class ResultsManager:
    def __init__(self, session: SessionManager, auth: AuthManager):
        self._session = session
        self._auth = auth

    # ── Public API ────────────────────────────────────────────────────────────

    async def search_by_specimen(self, specimen_id: str) -> Optional[PatientResult]:
        """
        Search for a patient result by specimen ID.
        Flow: search → click MRN → episode list → click each test set → aggregate.
        """
        await self._auth.ensure_authenticated()
        page = await self._session.get_page()

        # Step 1: Navigate to search page and submit search
        await self._navigate_to_search(page)
        await self._submit_search(page, specimen_id)

        # Step 2: Wait for MRN link to appear (search results loaded)
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

        # Step 3: Click the MRN link to open the episode list
        mrn_link = await page.query_selector(config.SEL_MRN_LINK)
        if not mrn_link:
            return None
        await mrn_link.click()

        # Step 4: Wait for the episode list page to load
        try:
            await page.wait_for_selector(
                config.SEL_BANNER_SURNAME, timeout=config.PAGE_TIMEOUT_MS,
            )
        except PlaywrightTimeout:
            self._check_for_session_expiry(page)
            return None

        # Step 5: Gather episode page data (patient info, test set names, pending status)
        episode_data = await self._scrape_episode_list(page)

        # Step 6: Try PDF approach (fast — one download gets all results)
        result = await self._try_pdf_approach(page, specimen_id, episode_data)
        if result:
            return result

        # Step 7: Fall back to clicking each test set link
        return await self._click_test_sets(page, specimen_id, episode_data)

    # ── Episode list scraping ────────────────────────────────────────────────

    async def _scrape_episode_list(self, page: Page) -> dict:
        """Scrape the episode list page for patient info and test set status."""
        return await page.evaluate('''
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

                const doctor         = text('web_EPVisitNumber_List_1-row-0-item-Doctor');
                const collectionDate = text('web_EPVisitNumber_List_1-row-0-item-CollectionDate');
                const collectionTime = text('web_EPVisitNumber_List_1-row-0-item-CollectionTime');

                // Clickable test set links
                const vistsLinks = Array.from(document.querySelectorAll('a[id^="VISTS_"]'))
                    .map(a => ({id: a.id, text: a.innerText.trim()}));
                const clickableNames = new Set(vistsLinks.map(l => l.text));

                // Find pending tests: text nodes in the TSList cell that aren't links
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

                return {
                    patient_name: surname + ', ' + givenName,
                    patient_id: mrn,
                    episode: episode,
                    dob: dob,
                    doctor: doctor,
                    collection_datetime: collectionDate + ' ' + collectionTime,
                    clickable: vistsLinks,
                    pending: pending,
                };
            }
        ''')

    # ── PDF approach ─────────────────────────────────────────────────────────

    async def _try_pdf_approach(self, page: Page, specimen_id: str, episode_data: dict) -> Optional[PatientResult]:
        """Download and parse the PDF report from the episode list page."""
        try:
            pdf_link = await page.query_selector(
                '#web_EPVisitNumber_List_1-row-0-item-DocRptPDF-link'
            )
            if not pdf_link:
                return None

            async with page.context.expect_page(timeout=15000) as new_page_info:
                await pdf_link.click()

            new_page = await new_page_info.value
            await new_page.wait_for_load_state("domcontentloaded", timeout=30000)

            # The PDF is in an iframe/frame inside the wrapper page
            pdf_bytes = None
            for frame in new_page.frames:
                if frame.url != new_page.url:
                    try:
                        response = await new_page.context.request.get(frame.url)
                        body = await response.body()
                        if body[:5] == b'%PDF-':
                            pdf_bytes = body
                            break
                    except Exception:
                        pass

            await new_page.close()

            if not pdf_bytes:
                return None

            return self._parse_pdf(pdf_bytes, specimen_id, episode_data)

        except Exception as e:
            _dbg(f"DEBUG: PDF approach error: {e}")
            return None

    def _parse_pdf(self, pdf_bytes: bytes, specimen_id: str, episode_data: dict) -> Optional[PatientResult]:
        """Parse a TrakCare lab result PDF using text extraction or OCR."""
        tests = []
        collection_dt = episode_data.get("collection_datetime", "")

        # ── Step 1: Try text extraction first (fast path for text-based PDFs) ──
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for pg in pdf.pages:
                    text = pg.extract_text() or ""
                    if text.strip():
                        tests = self._parse_pdf_text(text, collection_dt)
                        if tests:
                            break
        except Exception as e:
            _dbg(f"DEBUG: pdfplumber text extraction error: {e}")

        # ── Step 2: Fall back to OCR for scanned/image-based PDFs ──
        if not tests:
            tests = self._parse_pdf_ocr(pdf_bytes, collection_dt)

        if not tests:
            return None

        # Add pending tests
        for name in episode_data.get("pending", []):
            tests.append(TestResult(
                test_name=name, value="Pending", unit="", reference_range="",
                flag="PENDING", collection_datetime="",
            ))

        return PatientResult(
            patient_name=episode_data["patient_name"],
            patient_id=episode_data["patient_id"],
            specimen_id=specimen_id,
            episode=episode_data["episode"],
            requesting_doctor=episode_data.get("doctor", ""),
            dob=episode_data["dob"],
            status="",
            collection_datetime=collection_dt,
            result_datetime="",
            tests=tests,
        )

    # ── PDF text parser ──────────────────────────────────────────────────────
    # TrakCare PDFs (via pdfplumber) lay out each result on a single line:
    #   Name  Value  Unit  RefRange
    # e.g. "Sodium 136 mmol/L 136 - 145"
    # e.g. "Bicarbonate 16 L mmol/L 23 - 29"   (flag embedded in value)
    # e.g. "Haemoglobin index 2+"              (no unit or range — index)
    # e.g. "Lipaemia index Not detected"       (no unit or range)
    # e.g. "Vitamin B12 >1476 pmol/L"          (no ref range — only upper limit known)
    # e.g. "Total cholesterol 1.34 mmol/L"     (no ref range — lipid fraction)

    # Unit charset: ASCII letters + µ (U+00B5) + common symbols
    _UNIT_FIRST = r'[a-zA-Z\xb5/%]'
    _UNIT_REST  = r'[/a-zA-Z\xb5\xb2%0-9.*^]'

    # 4-field: Name Value Unit RefRange  (ref range is "x - y")
    _PDF_LINE_RE = re.compile(
        r'^(?P<name>.+?)\s+(?P<value>[><]?\d+[\d.]*\s*[HL]?)\s+(?P<unit>[a-zA-Z\xb5/%]+[/a-zA-Z\xb5\xb2%0-9.*^]*)\s+(?P<range>\d+[\d.]*\s*-\s*\d+[\d.]*\s*)?$'
    )
    # 4-field with single-sided ref range: Name Value Unit <x or >x
    _PDF_LINE_RE_SINGLESIDED = re.compile(
        r'^(?P<name>.+?)\s+(?P<value>[><]?\d+[\d.]*\s*[HL]?)\s+(?P<unit>[a-zA-Z\xb5/%]+[/a-zA-Z\xb5\xb2%0-9.*^]*)\s+(?P<range>[<>]\d+[\d.]*\s*)?$'
    )
    # 2-field: Name Value (indices like "2+" or "Not detected")
    _PDF_LINE_RE2 = re.compile(
        r'^(?P<name>.+?)\s+(?P<value>Not detected|\d+[+])\s*$'
    )
    # 3-field: Name Value Unit (no ref range — lipid fractions, TSH, B12, etc.)
    _PDF_LINE_RE3 = re.compile(
        r'^(?P<name>.+?)\s+(?P<value>[><]?\d+[\d.]*\s*[HL]?)\s+(?P<unit>[a-zA-Z\xb5/%]+[/a-zA-Z\xb5\xb2%0-9.*^]*)\s*$'
    )
    # 3-field with compound unit containing a space (e.g. "eGFR (MDRD) 51 mL/min/1.73 m²")
    _PDF_LINE_RE_COMPOUND = re.compile(
        r'^(?P<name>.+?)\s+(?P<value>[><]?\d+[\d.]*\s*[HL]?)\s+(?P<unit>mL/min/[\d.]+\s*\S*)\s*$'
    )

    _SECTION_HEADERS = frozenset([
        'blood chemistry', 'liver function tests', 'lipids', 'inflammatory markers',
        'haematinics', 'thyroid function tests', 'indices', 'indices in serum',
        'creatinine and estimated gfr',
    ])

    # All-caps headers that introduce advisory/commentary blocks (not results)
    _ADVISORY_HEADERS = frozenset([
        'cardiovascular risk',
        'disclaimer',
    ])

    @staticmethod
    def _is_section_header(line: str, section_headers: frozenset) -> bool:
        """Check if line is a results section header (with optional <Continued> tag)."""
        cleaned = re.sub(r':<.*?>$', '', line).strip().rstrip(':')
        return cleaned.lower() in section_headers

    @staticmethod
    def _is_advisory_header(line: str, advisory_headers: frozenset) -> bool:
        """Check if line starts a non-results advisory/commentary block."""
        upper = line.upper().strip(':').strip()
        if upper.lower() in advisory_headers:
            return True
        # All-caps text-only lines with 2+ words are advisory (no digits — avoids matching
        # result lines like "ALT 476 H U/L 7 - 35" which are also trivially all-uppercase)
        if (line == line.upper() and len(line.split()) >= 2
                and line[0].isalpha() and not any(c.isdigit() for c in line)):
            return True
        return False

    @staticmethod
    def _extract_flag(value_str: str) -> tuple[Optional[str], str]:
        """Extract trailing H/L flag from a value string. Returns (flag, cleaned_value)."""
        m = re.search(r'\s([HL])\s*$', value_str)
        if m:
            return m.group(1), value_str[:m.start()].rstrip()
        return None, value_str

    def _parse_pdf_text(self, text: str, collection_dt: str) -> list[TestResult]:
        """Parse pdfplumber-extracted text — single-line format.

        Uses section-based state tracking: only parses result lines when
        inside a recognised results section (e.g. 'Blood chemistry:'),
        and stops parsing when advisory/commentary blocks are detected
        (e.g. 'CARDIOVASCULAR RISK').
        """
        tests = []
        in_results_section = False
        for raw in text.split('\n'):
            line = raw.strip()
            if not line:
                continue

            if self._is_skip_line(line):
                continue

            # ── Section transitions ──
            if self._is_section_header(line, self._SECTION_HEADERS):
                in_results_section = True
                continue

            if self._is_advisory_header(line, self._ADVISORY_HEADERS):
                in_results_section = False
                continue

            if not in_results_section:
                continue

            # Try 4-field pattern: Name Value Unit RefRange (double-sided like "136 - 145")
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

            # Try 4-field with single-sided ref range: Value Unit <x or >x
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

            # Try 2-field pattern: Name Value (indices like "2+" or "Not detected")
            m2 = self._PDF_LINE_RE2.match(line)
            if m2:
                tests.append(TestResult(
                    test_name=m2.group('name').strip(),
                    value=m2.group('value').strip(),
                    unit='',
                    reference_range='',
                    flag=None,
                    collection_datetime=collection_dt,
                ))
                continue

            # Try 3-field pattern: Name Value Unit (no ref range — lipid fractions, TSH, B12, etc.)
            m3 = self._PDF_LINE_RE3.match(line)
            if m3:
                name = m3.group('name').strip()
                # Skip lines where the name looks like a range fragment
                # (e.g. "HDL Cholesterol 1.0 -" — pdfplumber split a favourable-value note)
                if not re.search(r'\d\s-\s*$', name):
                    flag, value_str = self._extract_flag(m3.group('value').strip())
                    tests.append(TestResult(
                        test_name=name,
                        value=value_str,
                        unit=m3.group('unit').strip(),
                        reference_range='',
                        flag=flag,
                        collection_datetime=collection_dt,
                    ))
                continue

            # Try compound-unit 3-field: Name Value two-token-unit (e.g. "eGFR (MDRD) 51 mL/min/1.73 m²")
            mc = self._PDF_LINE_RE_COMPOUND.match(line)
            if mc:
                flag, value_str = self._extract_flag(mc.group('value').strip())
                tests.append(TestResult(
                    test_name=mc.group('name').strip(),
                    value=value_str,
                    unit=mc.group('unit').strip(),
                    reference_range='',
                    flag=flag,
                    collection_datetime=collection_dt,
                ))
                continue

            # Unrecognised line inside section — skip it; advisory headers already
            # handle section exits via _is_advisory_header above.

        return tests

    def _is_skip_line(self, raw: str) -> bool:
        """Return True for page banners, headers, footer, and non-result lines."""
        upper = raw.upper()

        # Page banners
        if 'PRACTICE NUMBER' in upper or 'LAB NUMBER:' in upper or 'COLLECTED:' in upper:
            if 'REPORT TO:' in upper or 'PATIENT:' in upper:
                return True
        if 'BHEKI MLANGENI LABORATORY' in upper:
            return True
        if re.match(r'pg\s+\d+\s+of\s+\d+', raw, re.IGNORECASE):
            return True
        if re.match(r'LH\s+\w+', raw):
            return True

        # Footer
        if 'AUTHORIZED BY:' in upper or 'AUTHORISED BY:' in upper or '-- END OF LABORATORY REPORT --' in upper:
            return True

        # Non-result inlined lines
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

        # Lipid target table rows
        if re.match(r'<\d+(\.\d+)?\s*mmol/L\s*$', raw):
            return True
        if re.match(r'(Low Risk|Moderate Risk|High Risk|Very High Risk)', raw, re.IGNORECASE):
            return True
        if re.match(r'(TC target|LDLC target|non-HDLC target|Risk Category)', raw, re.IGNORECASE):
            return True

        # Purely numeric standalone lines (page numbers, isolated ranges)
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
            # No clickable tests — return patient info with only pending
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

        # Click first link to get patient info + first batch of results
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

        # Click remaining links: back → wait for link → click → parse
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

        # Append pending tests at the end
        for name in episode_data.get("pending", []):
            result.tests.append(TestResult(
                test_name=name, value="Pending", unit="", reference_range="",
                flag="PENDING", collection_datetime="",
            ))

        return result

    # ── Navigation helpers ────────────────────────────────────────────────────

    async def _navigate_to_search(self, page: Page) -> None:
        """Navigate to the Patient Find search page."""
        if config.SEARCH_HASH in page.url:
            return
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

            // Flag detection
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
            # Skip commentary rows (e.g. "Creatinine plus auto comment")
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
        # Double-sided range: "x - y"
        m = re.match(r'^([\d.]+)\s*-\s*([\d.]+)\s*$', ref_range.strip())
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if v < lo:
                return 'L'
            if v > hi:
                return 'H'
            return None
        # Single-sided range: "<x" or ">x"
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
