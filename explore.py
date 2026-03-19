"""
Selector Discovery Tool
=======================
Run this script to auto-discover DOM selectors on the TrakCare login page.

    python explore.py

It will:
  1. Open a headed Chromium browser and navigate to the login page
  2. Wait for the SPA to render
  3. Automatically dump ALL element IDs, input fields, buttons, and links to data/dump.txt
  4. After you log in manually, press Enter in the terminal to re-dump the page
  5. Press Ctrl+C to exit

Each dump appends to data/dump.txt. Copy the selectors into core/config.py.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright
from core import config


DUMP_FILE = Path(__file__).parent / "data" / "dump.txt"

DUMP_JS = """
() => {
    const results = { inputs: [], buttons: [], elementsWithId: [], links: [], selects: [] };

    // All elements with an ID
    document.querySelectorAll('[id]').forEach(el => {
        results.elementsWithId.push({
            tag: el.tagName.toLowerCase(),
            id: el.id,
            type: el.type || '',
            name: el.name || '',
            className: el.className || '',
            text: (el.innerText || '').substring(0, 80).trim(),
            visible: el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0,
        });
    });

    // All input/textarea elements (even those without IDs)
    document.querySelectorAll('input, textarea').forEach(el => {
        results.inputs.push({
            tag: el.tagName.toLowerCase(),
            id: el.id || '(none)',
            type: el.type || 'text',
            name: el.name || '(none)',
            placeholder: el.placeholder || '',
            className: el.className || '',
            visible: el.offsetParent !== null,
        });
    });

    // All buttons and clickable elements
    document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"], a.btn').forEach(el => {
        results.buttons.push({
            tag: el.tagName.toLowerCase(),
            id: el.id || '(none)',
            type: el.type || '',
            text: (el.innerText || el.value || '').substring(0, 80).trim(),
            className: el.className || '',
            visible: el.offsetParent !== null,
        });
    });

    // All select elements
    document.querySelectorAll('select').forEach(el => {
        results.selects.push({
            id: el.id || '(none)',
            name: el.name || '(none)',
            className: el.className || '',
            options: Array.from(el.options).map(o => o.text).slice(0, 10),
        });
    });

    return results;
}
"""


def format_dump(data, label=""):
    """Format the DOM dump as a string."""
    lines = []

    if label:
        lines.append(f"\n{'='*60}")
        lines.append(f"  {label}")
        lines.append(f"  Dumped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"{'='*60}")

    lines.append(f"\n--- INPUTS ({len(data['inputs'])}) ---")
    for item in data["inputs"]:
        vis = "VISIBLE" if item["visible"] else "hidden"
        lines.append(f"  [{vis}] <{item['tag']}> id=\"{item['id']}\" type=\"{item['type']}\" "
                      f"name=\"{item['name']}\" placeholder=\"{item['placeholder']}\"")

    lines.append(f"\n--- BUTTONS ({len(data['buttons'])}) ---")
    for item in data["buttons"]:
        vis = "VISIBLE" if item["visible"] else "hidden"
        lines.append(f"  [{vis}] <{item['tag']}> id=\"{item['id']}\" text=\"{item['text']}\"")

    lines.append(f"\n--- ELEMENTS WITH IDs ({len(data['elementsWithId'])}) ---")
    for item in data["elementsWithId"]:
        vis = "VISIBLE" if item["visible"] else "hidden"
        text_preview = f" text=\"{item['text']}\"" if item["text"] else ""
        lines.append(f"  [{vis}] <{item['tag']}> id=\"{item['id']}\"{text_preview}")

    if data["selects"]:
        lines.append(f"\n--- SELECTS ({len(data['selects'])}) ---")
        for item in data["selects"]:
            lines.append(f"  id=\"{item['id']}\" name=\"{item['name']}\" options={item['options']}")

    lines.append("")
    return "\n".join(lines)


def write_dump(text):
    """Append dump text to the dump file."""
    DUMP_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DUMP_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")


async def main():
    # Clear previous dump file
    if DUMP_FILE.exists():
        DUMP_FILE.unlink()

    print("=" * 60)
    print("  LabTrack Selector Discovery")
    print(f"  Output: {DUMP_FILE}")
    print("=" * 60)
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        context = await browser.new_context(
            no_viewport=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        print(f"Navigating to: {config.BASE_URL + config.LOGIN_HASH}")
        await page.goto(config.BASE_URL + config.LOGIN_HASH)

        print("Waiting for page to render...")
        await page.wait_for_timeout(5000)

        # Auto-dump login page
        data = await page.evaluate(DUMP_JS)
        text = format_dump(data, label="LOGIN PAGE — Pre-Authentication")
        write_dump(text)
        print(f"  Dumped login page ({len(data['elementsWithId'])} elements) -> {DUMP_FILE}")

        print()
        print("-" * 60)
        print("The browser is still open. You can:")
        print("  1. Log in manually in the browser window")
        print("  2. Navigate to the patient search / results pages")
        print("  3. Come back here and press ENTER to dump the current page")
        print("  4. Press Ctrl+C to exit")
        print()
        print(f"All dumps are saved to: {DUMP_FILE}")
        print("-" * 60)

        dump_count = 1
        try:
            while True:
                await asyncio.to_thread(input, "\nPress ENTER to dump current page (or Ctrl+C to quit)... ")
                dump_count += 1
                url = page.url
                data = await page.evaluate(DUMP_JS)
                text = format_dump(data, label=f"DUMP #{dump_count} — {url}")
                write_dump(text)
                print(f"  Dumped page ({len(data['elementsWithId'])} elements) -> {DUMP_FILE}")
        except (KeyboardInterrupt, EOFError):
            pass

        await browser.close()

    print(f"\nDone. All dumps saved to: {DUMP_FILE}")
    print("Copy the selectors you need into core/config.py.")


if __name__ == "__main__":
    asyncio.run(main())
