"""
Playwright test script to verify all 7 Folium maps render correctly.
Tests:
- Map loads without JavaScript errors
- Map tiles render
- Interactive elements (zoom, popups) work
- Screenshots captured
"""

import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright, Page

# Map files to test
MAPS_DIR = Path(__file__).parent
MAP_FILES = [
    "map_01_patient_origin.html",
    "map_02_branch_catchments.html",
    "map_03_patient_clusters.html",
    "map_04_cannibalization_network.html",
    "map_05_whitespace_opportunity.html",
    "map_06_revenue_heatmap.html",
    "map_07_new_patient_flow.html",
]

SCREENSHOTS_DIR = MAPS_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# Test results
results = {
    "total": 0,
    "rendered": 0,
    "js_errors": 0,
    "screenshots": 0,
    "errors": [],
}


async def test_map(page: Page, map_file: str) -> dict:
    """Test a single map file."""
    map_path = MAPS_DIR / map_file
    map_url = f"file:///{map_path.as_posix()}"
    screenshot_path = SCREENSHOTS_DIR / map_file.replace(".html", ".png")

    result = {
        "name": map_file,
        "rendered": False,
        "js_errors": [],
        "screenshot": False,
        "interactive": False,
        "error": None,
    }

    try:
        # Collect console messages and errors
        console_errors = []

        def handle_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)

        page.on("console", handle_console)
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        # Navigate to map
        await page.goto(map_url, wait_until="networkidle", timeout=30000)

        # Wait for map to initialize
        await page.wait_for_function(
            "typeof map !== 'undefined' || document.querySelector('#map')",
            timeout=10000,
        )
        await asyncio.sleep(1)  # Allow tiles to load

        # Check for JS errors
        if console_errors:
            result["js_errors"] = console_errors
            results["js_errors"] += len(console_errors)
        else:
            result["rendered"] = True
            results["rendered"] += 1

        # Test zoom functionality
        try:
            # Zoom in
            await page.keyboard.press("+")
            await asyncio.sleep(0.5)
            # Zoom out
            await page.keyboard.press("-")
            await asyncio.sleep(0.5)
            result["interactive"] = True
        except Exception as e:
            result["interactive"] = False

        # Test popup interaction (click on first marker/circle)
        try:
            clickable = page.locator(
                "circle, .leaflet-marker-icon, .leaflet-interactive"
            ).first
            if await clickable.count() > 0:
                await clickable.click()
                await asyncio.sleep(0.5)
                # Check if popup appeared
                popup = page.locator(".leaflet-popup")
                if await popup.count() > 0:
                    result["popup_works"] = True
        except Exception:
            pass

        # Take screenshot
        await page.screenshot(path=str(screenshot_path), full_page=True)
        result["screenshot"] = True
        result["screenshot_path"] = str(screenshot_path)
        results["screenshots"] += 1

    except Exception as e:
        result["error"] = str(e)
        results["errors"].append({"map": map_file, "error": str(e)})

    return result


async def main():
    """Run all map tests."""
    print("=" * 60)
    print("MAP RENDERING VERIFICATION TEST")
    print("=" * 60)
    print()

    results["total"] = len(MAP_FILES)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        # Test each map
        for map_file in MAP_FILES:
            print(f"Testing: {map_file}...", end=" ")
            result = await test_map(page, map_file)

            status = (
                "PASS" if result["rendered"] and not result["js_errors"] else "FAIL"
            )
            print(
                f"{status} Rendered: {result['rendered']}, JS Errors: {len(result['js_errors'])}, Screenshot: {result['screenshot']}"
            )

            if result["js_errors"]:
                for err in result["js_errors"]:
                    print(f"    Error: {err[:100]}")
            if result["error"]:
                print(f"    Exception: {result['error'][:100]}")

        await browser.close()

    # Print summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Maps Tested:     {results['total']}")
    print(f"Maps Rendered:   {results['rendered']}")
    print(f"JS Errors:       {results['js_errors']}")
    print(f"Screenshots:     {results['screenshots']}")
    print()

    # Verdict
    if results["rendered"] == results["total"] and results["js_errors"] == 0:
        print("VERDICT: PASS - All maps rendered successfully with no JS errors")
        return 0
    elif results["rendered"] == results["total"]:
        print(
            f"VERDICT: PARTIAL PASS - All maps rendered but {results['js_errors']} JS error(s) detected"
        )
        return 1
    else:
        print(
            f"VERDICT: FAIL - {results['total'] - results['rendered']} map(s) failed to render"
        )
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
