# LabTrack Viewer — Project CLAUDE.md

## Project Overview
Open-source Python CLI tool to replace the paid NHLS TrakCare Lab Web View browser experience.

**Purpose:** The web app requires repeated manual logins and has no official API. This tool automates the browser via Playwright, avoiding repeated logins and eliminating the need for a paid subscription.

**Roadmap:** Python prototype → iOS (Swift) → Android (Kotlin). `core/` is pure business logic with no UI coupling so it ports cleanly.

---

## Tech Stack
- **Automation:** Playwright (async Chromium, headless by default)
- **CLI UI:** Rich (tables, panels, spinners, colorized output)
- **Barcode scanning:** OpenCV (`opencv-python`) + `pyzbar` (Code-128 / QR decoding)
- **PDF parsing:** `pdfplumber` (text extraction) + `pytesseract` + `fitz` (PyMuPDF) for OCR fallback
- **Async runtime:** Python `asyncio`

---

## File Structure
```
main.py                  # CLI entry point — argparse, mode dispatch, async orchestration
core/
  session_manager.py     # Playwright lifecycle, cookie persistence (data/cookies.json)
  auth.py                # Login flow, session validity check, retry helper
  results.py             # Core business logic — search, episode scraping, PDF parsing, DOM parsing
  barcode.py             # Webcam scanning, ID extraction (NHLS specimen ID pattern)
  config.py              # ALL CSS selectors (login, search, results — fully populated), URLs, timeouts
ui/
  display.py             # Rich console UI — patient header, results table, spinners, status messages
explore.py               # Selector discovery: headed browser, DOM dump to data/dump.txt
requirements.txt
userpsw.txt              # Credentials (line 1=username, line 2=password) — gitignored
data/
  cookies.json           # Persisted auth cookies — auto-created, gitignored
  dump.txt               # DOM dumps from explore.py
```

---

## Key Design Decisions

### `core/` is UI-agnostic
All `core/` modules have zero imports from `ui/`. Business logic (search, parsing, scraping) is pure and testable without a console. The JS in `_parse_results()` is intentionally portable to WKWebView/WebView for mobile ports.

### PDF parsing has two approaches
1. **Fast path:** `pdfplumber` text extraction — works for text-based TrakCare PDFs
2. **Fallback:** OCR via `pytesseract` + `fitz` (PyMuPDF) render at 2x scale — for scanned/image PDFs

Regex-based line parsers (`_PDF_LINE_RE`, `_PDF_LINE_RE2`, `_PDF_LINE_RE3`, etc.) handle the 4-field TrakCare layout: `Name Value Unit RefRange`.

### Cookie-based session persistence
Cookies saved to `data/cookies.json` on successful login. `SessionManager` loads them on launch. `AuthManager.is_session_valid()` navigates to the app and checks for the logged-in indicator to detect expiry. No username/password sent on every request.

### Worklist selectors fully configured
`core/config.py` has all selectors populated for: login form, patient search form, search results table, episode list, result detail page, and results table. `explore.py` is the tool to discover new/changed selectors.

---

## Usage

```bash
python main.py --scan                # Webcam barcode scan → search → display results
python main.py --specimen W25-123    # Direct specimen ID lookup
python main.py --recent              # Show most recent results (worklist)
python main.py --clear-session       # Delete saved cookies, force re-login
python main.py --headed              # Show browser window (debug / selector discovery)
python explore.py                    # Run selector discovery tool
```

---

## Dependencies

```
playwright
rich
opencv-python
pyzbar
pdfplumber
pytesseract       # OCR (optional — installed separately)
PyMuPDF (fitz)    # PDF render for OCR (optional)
```

> **Note:** `pytesseract` and `fitz` are optional — OCR is a fallback when text extraction fails. Install with: `pip install pytesseract PyMuPDF`

---

## Known Issues / Caveats

- `results.py` has a duplicate `_SECTION_HEADERS` frozenset definition and a duplicate `_parse_pdf_text` method (lines 265–369 vs 452–563). The second definition (lines 452–563) is the active one — the first is dead code.
- `_parse_pdf_ocr` renders at 2x scale but uses `pytesseract.image_to_string` directly rather than passing a PIL Image — may need adjustment depending on Tesseract version.
- `--recent` mode uses worklist selectors which depend on `SEL_EPISODES_DROPDOWN` / `SEL_EPISODE_ROW` being correct for the current TrakCare version.
- NHLS specimen ID pattern (`r"[A-Z]?\d{2}-?\d{5,10}"`) may need adjustment once real facility barcodes are examined.
