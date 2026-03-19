"""
LabTrack Viewer — CLI entry point

Usage examples:
    python main.py --scan                # Webcam barcode scan → search → display results
    python main.py --specimen W25-123    # Direct specimen ID lookup
    python main.py --recent              # Show most recent results
    python main.py --clear-session       # Delete saved cookies, force re-login
    python main.py --headed              # Show browser window (debug / selector discovery)
"""

import argparse
import asyncio
import sys

from core import config
from core.auth import AuthManager, AuthenticationError, with_auth_retry
from core.barcode import BarcodeScanner
from core.results import ResultsManager, SessionExpiredError
from core.session_manager import SessionManager
from ui.display import ResultsDisplay


# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="labtrack",
        description="LabTrack Viewer — open-source NHLS TrakCare Lab client",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--scan", action="store_true", help="Scan a barcode via webcam")
    mode.add_argument("--specimen", metavar="ID", help="Look up a specimen ID directly")
    mode.add_argument("--recent", action="store_true", help="Show most recent results")
    mode.add_argument("--clear-session", action="store_true", help="Delete saved cookies and exit")

    parser.add_argument("--headed", action="store_true", help="Show browser window (debug mode)")
    parser.add_argument("--camera", type=int, default=0, metavar="INDEX", help="Webcam index (default 0)")
    parser.add_argument("--limit", type=int, default=10, metavar="N", help="Max recent results to show (default 10)")
    return parser


async def _lookup_specimen(
    specimen_id: str,
    session: SessionManager,
    auth: AuthManager,
    display: ResultsDisplay,
) -> None:
    rm = ResultsManager(session, auth)
    display.show_info(f"Searching for specimen: {specimen_id}")

    with display.show_spinner("Loading results…"):
        result = await with_auth_retry(
            rm.search_by_specimen(specimen_id), auth
        )

    if result is None:
        display.show_error(f"No results found for specimen ID: {specimen_id}")
        return

    display.show_patient_header(result)
    display.show_results_table(result)


# ── Mode handlers ─────────────────────────────────────────────────────────────

async def run_scan_mode(args, session: SessionManager, auth: AuthManager, display: ResultsDisplay) -> None:
    display.show_scanning_status("Hold the barcode up to the camera. Press Q to cancel.")
    specimen_id = BarcodeScanner.scan_from_webcam(
        camera_index=args.camera,
        timeout_seconds=30,
    )
    if not specimen_id:
        display.show_error("No barcode detected within 30 seconds.")
        return

    display.show_success(f"Barcode detected: {specimen_id}")
    await _lookup_specimen(specimen_id, session, auth, display)


async def run_specimen_mode(args, session: SessionManager, auth: AuthManager, display: ResultsDisplay) -> None:
    await _lookup_specimen(args.specimen.strip(), session, auth, display)


async def run_recent_mode(args, session: SessionManager, auth: AuthManager, display: ResultsDisplay) -> None:
    rm = ResultsManager(session, auth)
    display.show_info("Fetching recent results…")

    with display.show_spinner("Loading…"):
        results = await with_auth_retry(
            rm.get_recent_results(limit=args.limit), auth
        )

    if not results:
        display.show_info("No recent results found (or worklist selectors not yet configured).")
        return

    for result in results:
        display.show_patient_header(result)
        display.show_results_table(result)
        display.show_info("─" * 60)


async def run_clear_session(session: SessionManager, display: ResultsDisplay) -> None:
    await session.clear_cookies()
    display.show_success("Session cleared. You will be asked to log in on the next run.")


# ── Main ──────────────────────────────────────────────────────────────────────

async def dispatch(args) -> None:
    display = ResultsDisplay()

    # --clear-session does not need the browser
    if args.clear_session:
        async with SessionManager(headless=True) as session:
            await run_clear_session(session, display)
        return

    # Override headless setting if --headed flag given
    if args.headed:
        config.BROWSER_HEADLESS = False

    async with SessionManager(headless=config.BROWSER_HEADLESS) as session:
        auth = AuthManager(session)

        try:
            if args.scan:
                await run_scan_mode(args, session, auth, display)
            elif args.specimen:
                await run_specimen_mode(args, session, auth, display)
            elif args.recent:
                await run_recent_mode(args, session, auth, display)
        except AuthenticationError as e:
            display.show_error(str(e))
            sys.exit(1)
        except SessionExpiredError as e:
            display.show_error(f"Session expired and could not be renewed: {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            display.show_info("\nCancelled.")


def main() -> None:
    parser = _make_parser()
    args = parser.parse_args()
    asyncio.run(dispatch(args))


if __name__ == "__main__":
    main()
