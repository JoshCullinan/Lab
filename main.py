"""
LabTrack Viewer — CLI entry point

Usage examples:
    python main.py --scan                # Webcam barcode scan → search → display results
    python main.py --specimen W25-123    # Direct specimen ID lookup
    python main.py --episode LH00899939  # Look up by episode number
    python main.py --name "SMITH"        # Search by surname (pick from list)
    python main.py --name "SMITH JOHN"   # Search by surname + given name
    python main.py --hospital-mrn 12345  # Look up by hospital MRN
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
    mode.add_argument("--episode", metavar="ID", help="Look up by episode number")
    mode.add_argument("--name", metavar="NAME", help="Search by name: \"SMITH\" or \"SMITH JOHN\"")
    mode.add_argument("--hospital-mrn", metavar="MRN", help="Look up by hospital MRN (first result)")
    mode.add_argument("--folder", metavar="NUMBER", help="Hospital folder number — list episodes, pick one")
    mode.add_argument("--recent", action="store_true", help="Show most recent results")
    mode.add_argument("--clear-session", action="store_true", help="Delete saved cookies and exit")

    parser.add_argument("--headed", action="store_true", help="Show browser window (debug mode)")
    parser.add_argument("--camera", type=int, default=0, metavar="INDEX", help="Webcam index (default 0)")
    parser.add_argument("--limit", type=int, default=10, metavar="N", help="Max recent results to show (default 10)")
    return parser


def _parse_name_arg(name_arg: str) -> tuple[str, str]:
    """Parse a name argument into (surname, given_name).

    "SMITH"      → ("SMITH", "")
    "SMITH JOHN" → ("SMITH", "JOHN")
    """
    parts = name_arg.strip().split(None, 1)
    surname = parts[0] if parts else ""
    given_name = parts[1] if len(parts) > 1 else ""
    return surname, given_name


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


async def run_episode_mode(args, session: SessionManager, auth: AuthManager, display: ResultsDisplay) -> None:
    episode_id = args.episode.strip()
    rm = ResultsManager(session, auth)
    display.show_info(f"Searching for episode: {episode_id}")

    with display.show_spinner("Loading results…"):
        result = await with_auth_retry(
            rm.search_by_episode(episode_id), auth
        )

    if result is None:
        display.show_error(f"No results found for episode: {episode_id}")
        return

    display.show_patient_header(result)
    display.show_results_table(result)


async def run_name_mode(args, session: SessionManager, auth: AuthManager, display: ResultsDisplay) -> None:
    surname, given_name = _parse_name_arg(args.name)
    rm = ResultsManager(session, auth)

    label = surname + (f" {given_name}" if given_name else "")
    display.show_info(f"Searching for name: {label}")

    with display.show_spinner("Searching…"):
        hits = await with_auth_retry(
            rm.search_by_name(surname, given_name), auth
        )

    if not hits:
        display.show_error(f"No patients found matching: {label}")
        return

    display.show_patient_list(hits)

    # Prompt user to pick a patient
    while True:
        try:
            choice = input(f"\nSelect patient (1-{len(hits)}), or 'q' to quit: ").strip()
        except (EOFError, KeyboardInterrupt):
            display.show_info("\nCancelled.")
            return

        if choice.lower() == 'q':
            return

        if not choice.isdigit() or not (1 <= int(choice) <= len(hits)):
            display.show_error(f"Enter a number between 1 and {len(hits)}")
            continue

        break

    selected = hits[int(choice) - 1]
    display.show_info(f"Loading results for {selected.get('surname', '')}, {selected.get('given_name', '')}…")

    with display.show_spinner("Loading results…"):
        result = await with_auth_retry(
            rm.open_patient_by_hit(selected, label), auth
        )

    if result is None:
        display.show_error("No results found for selected patient.")
        return

    display.show_patient_header(result)
    display.show_results_table(result)


async def run_hospital_mrn_mode(args, session: SessionManager, auth: AuthManager, display: ResultsDisplay) -> None:
    hospital_mrn = args.hospital_mrn.strip()
    rm = ResultsManager(session, auth)
    display.show_info(f"Searching for hospital MRN: {hospital_mrn}")

    with display.show_spinner("Loading results…"):
        result = await with_auth_retry(
            rm.search_by_hospital_mrn(hospital_mrn), auth
        )

    if result is None:
        display.show_error(f"No results found for hospital MRN: {hospital_mrn}")
        return

    display.show_patient_header(result)
    display.show_results_table(result)


async def run_folder_mode(args, session: SessionManager, auth: AuthManager, display: ResultsDisplay) -> None:
    folder_num = args.folder.strip()
    rm = ResultsManager(session, auth)
    display.show_info(f"Searching for hospital folder: {folder_num}")

    # Step 1: Search and get patient list
    with display.show_spinner("Searching…"):
        patients = await with_auth_retry(
            rm.search_patients_by_hospital_mrn(folder_num), auth
        )

    if not patients:
        display.show_error(f"No patient found for hospital folder: {folder_num}")
        return

    # Step 2: If multiple patients, let user pick
    patient_idx = 0
    if len(patients) > 1:
        display.show_patient_list(patients)
        while True:
            try:
                choice = input(f"\nSelect patient (1-{len(patients)}), or 'q' to quit: ").strip()
            except (EOFError, KeyboardInterrupt):
                display.show_info("\nCancelled.")
                return
            if choice.lower() == 'q':
                return
            if not choice.isdigit() or not (1 <= int(choice) <= len(patients)):
                display.show_error(f"Enter a number between 1 and {len(patients)}")
                continue
            patient_idx = int(choice) - 1
            break

    selected_patient = patients[patient_idx]
    display.show_info(
        f"Loading episodes for {selected_patient.get('surname', '')}, "
        f"{selected_patient.get('given_name', '')} ({selected_patient.get('mrn', '')})…"
    )

    # Step 3: Click into patient, get episode list
    with display.show_spinner("Loading episodes…"):
        episode_data = await rm.list_episodes_for_patient(selected_patient["row_index"])

    if not episode_data:
        display.show_error("Failed to load episode list.")
        return

    rows = episode_data.get("rows", [])
    if not rows:
        display.show_error("No episodes found for this patient.")
        return

    display.show_episode_list(episode_data)

    # Step 4: Let user pick an episode (or 'a' for all)
    while True:
        try:
            prompt = f"\nSelect episode (1-{len(rows)}), 'a' for all, or 'q' to quit: "
            choice = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            display.show_info("\nCancelled.")
            return

        if choice.lower() == 'q':
            return

        if choice.lower() == 'a':
            for i, row in enumerate(rows):
                ep_num = row.get("episode_number", "")
                display.show_info(f"\nLoading episode {i+1}/{len(rows)}: {ep_num}…")
                with display.show_spinner("Loading…"):
                    result = await with_auth_retry(
                        rm.load_episode_results(row["row_index"], episode_data), auth
                    )
                if result:
                    display.show_patient_header(result)
                    display.show_results_table(result)
                    display.show_info("-" * 60)
                else:
                    display.show_error(f"No results for episode {ep_num}")
            return

        if not choice.isdigit() or not (1 <= int(choice) <= len(rows)):
            display.show_error(f"Enter a number between 1 and {len(rows)}")
            continue

        break

    selected_row = rows[int(choice) - 1]
    ep_num = selected_row.get("episode_number", "")
    display.show_info(f"Loading episode: {ep_num}…")

    with display.show_spinner("Loading results…"):
        result = await with_auth_retry(
            rm.load_episode_results(selected_row["row_index"], episode_data), auth
        )

    if result is None:
        display.show_error(f"No results found for episode: {ep_num}")
        return

    display.show_patient_header(result)
    display.show_results_table(result)


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
        display.show_info("-" * 60)


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
            elif args.episode:
                await run_episode_mode(args, session, auth, display)
            elif args.name:
                await run_name_mode(args, session, auth, display)
            elif args.hospital_mrn:
                await run_hospital_mrn_mode(args, session, auth, display)
            elif args.folder:
                await run_folder_mode(args, session, auth, display)
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
