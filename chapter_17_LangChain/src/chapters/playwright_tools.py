"""Playwright tools for a LangChain agent (verified against Playwright 1.62).

Design rules every tool here follows, because an LLM is the caller:

1. Return a string, never raise. An agent cannot catch an exception, but it can
   read "Error: no element matches #login" and try a different selector.
2. The docstring IS the tool description the model reads. Say when to use the
   tool, not just what it does.
3. Prefer role/label/text lookups over CSS. The agent guesses CSS badly; it is
   much better at "the button called Sign in".
"""

import json
import os
from functools import wraps

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from langchain.tools import tool

# Shared browser state across tools (module-level, like globals in TypeScript)
_playwright = None
_browser: Browser | None = None
_context: BrowserContext | None = None
_page: Page | None = None

# Diagnostics collected by listeners registered in launch_browser().
_console_errors: list[str] = []
_failed_requests: list[str] = []


def _brief(exc: BaseException) -> str:
    """Playwright errors are paragraphs. An agent only needs the first line."""
    return str(exc).strip().splitlines()[0]


def _record_console_message(message) -> None:
    """Keep console errors only - warnings and logs are noise for an agent."""
    if message.type == "error":
        _console_errors.append(message.text)


def _record_failed_request(request) -> None:
    _failed_requests.append(f"{request.method} {request.url} -> {request.failure or 'failed'}")


def _needs_page(fn):
    """Guard + error funnel, so 20 tools do not repeat the same 6 lines.

    Catching broad Exception is deliberate here: a tool that raises kills the
    agent run, while a tool that returns an error string lets the agent adapt.
    """
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        if _page is None:
            return "Error: Browser not launched. Call launch_browser first."
        try:
            return await fn(*args, **kwargs)
        except PlaywrightTimeoutError as exc:
            return f"Timeout: {_brief(exc)}"
        except Exception as exc:
            return f"Error: {_brief(exc)}"
    return wrapper


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------

@tool
async def launch_browser(headless: bool = False) -> str:
    """Launch a Chromium browser. Always call this first, before any other tool."""
    global _playwright, _browser, _context, _page
    if _browser:
        return "Browser is already open."
    _console_errors.clear()
    _failed_requests.clear()
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(headless=headless, slow_mo=700)
    _context = await _browser.new_context()
    _page = await _context.new_page()
    # 30s (the default) is a long time for an agent to sit blocked on a typo.
    _page.set_default_timeout(15_000)
    _page.on("console", _record_console_message)
    _page.on("requestfailed", _record_failed_request)
    return f"Browser launched successfully ({'headless' if headless else 'visible'} mode)."


@tool
async def close_browser() -> str:
    """Close the browser and free the session. Call this last."""
    global _playwright, _browser, _context, _page
    if not _browser:
        return "No browser is open."
    await _browser.close()
    await _playwright.stop()
    _playwright = _browser = _context = _page = None
    return "Browser closed successfully."


# --------------------------------------------------------------------------
# Seeing the page - call these before guessing a selector
# --------------------------------------------------------------------------

@tool
@_needs_page
async def snapshot_page(selector: str = "body") -> str:
    """Get the ARIA snapshot: every role, name and value on the page as a YAML tree.

    Call this FIRST whenever you do not already know what is on the page. It is
    the cheapest way to find out what you can click or type into, and the names
    it returns are exactly what click_by_role and type_by_label expect.
    """
    snap = await _page.locator(selector).aria_snapshot()
    return snap[:6000] or "Snapshot is empty."


@tool
@_needs_page
async def get_page_info() -> str:
    """Get the current URL and page title. Use it to confirm navigation worked."""
    return f"URL: {_page.url}\nTitle: {await _page.title()}"


# --------------------------------------------------------------------------
# Navigation
# --------------------------------------------------------------------------

@tool
@_needs_page
async def navigate_to(url: str) -> str:
    """Navigate to a full URL, for example https://example.com/login."""
    await _page.goto(url, wait_until="domcontentloaded")
    return f"Navigated to {url}"


@tool
@_needs_page
async def go_back() -> str:
    """Go back one entry in browser history."""
    await _page.go_back(wait_until="domcontentloaded")
    return f"Went back. Now at {_page.url}"


@tool
@_needs_page
async def reload_page() -> str:
    """Reload the current page. Useful after a change that needs a refresh."""
    await _page.reload(wait_until="domcontentloaded")
    return f"Reloaded {_page.url}"


@tool
@_needs_page
async def wait_for_element(selector: str, state: str = "visible", timeout_ms: int = 10000) -> str:
    """Wait until an element reaches a state: visible, hidden, attached or detached.

    Use this instead of retrying a failed click. Never sleep; Playwright already
    auto-waits, and this is the explicit version for slow, async pages.
    """
    await _page.locator(selector).wait_for(state=state, timeout=timeout_ms)
    return f"Element {selector} is now {state}."


# --------------------------------------------------------------------------
# Interacting - CSS selector versions
# --------------------------------------------------------------------------

@tool
@_needs_page
async def type_text(selector: str, text: str) -> str:
    """Type text into an input field found by CSS selector."""
    await _page.locator(selector).fill(text)
    return f'Typed "{text}" into {selector}'


@tool
@_needs_page
async def click_element(selector: str) -> str:
    """Click on an element found by CSS selector."""
    await _page.locator(selector).click()
    return f"Clicked on {selector}"


@tool
@_needs_page
async def hover_element(selector: str) -> str:
    """Hover over an element to reveal menus or tooltips that appear on hover."""
    await _page.locator(selector).hover()
    return f"Hovered over {selector}"


@tool
@_needs_page
async def press_key(key: str, selector: str = "") -> str:
    """Press a keyboard key such as Enter, Tab, Escape, ArrowDown or Control+A.

    Leave selector empty to send the key to the page, or pass one to focus an
    element first. Use this to submit a form that has no visible submit button.
    """
    if selector:
        await _page.locator(selector).press(key)
        return f"Pressed {key} on {selector}"
    await _page.keyboard.press(key)
    return f"Pressed {key}"


@tool
@_needs_page
async def select_dropdown_option(selector: str, value: str) -> str:
    """Choose an option in a native <select> dropdown, by visible label or value."""
    try:
        chosen = await _page.locator(selector).select_option(label=value)
    except Exception:
        chosen = await _page.locator(selector).select_option(value)
    return f"Selected {chosen} in {selector}"


@tool
@_needs_page
async def set_checkbox(selector: str, checked: bool = True) -> str:
    """Tick or untick a checkbox or radio button. Safe to call when already correct."""
    locator = _page.locator(selector)
    await (locator.check() if checked else locator.uncheck())
    return f"Set {selector} to checked={checked}"


@tool
@_needs_page
async def upload_file(selector: str, file_path: str) -> str:
    """Upload a local file to an <input type=file>.

    Works on hidden inputs, so do not try to click the file button first - an
    OS file dialog cannot be driven by the browser.
    """
    if not os.path.exists(file_path):
        return f"Error: no such file: {file_path}"
    await _page.locator(selector).set_input_files(file_path)
    return f"Uploaded {os.path.basename(file_path)} to {selector}"


@tool
@_needs_page
async def drag_and_drop(source_selector: str, target_selector: str) -> str:
    """Drag one element onto another, for kanban boards and sortable lists."""
    await _page.drag_and_drop(source_selector, target_selector)
    return f"Dragged {source_selector} onto {target_selector}"


@tool
@_needs_page
async def scroll_to_element(selector: str) -> str:
    """Scroll an element into view. Rarely needed - clicks auto-scroll already."""
    await _page.locator(selector).scroll_into_view_if_needed()
    return f"Scrolled {selector} into view"


# --------------------------------------------------------------------------
# Interacting - resilient locators (prefer these over CSS)
# --------------------------------------------------------------------------

@tool
@_needs_page
async def click_by_role(role: str, name: str) -> str:
    """Click an element by its ARIA role and visible name, e.g. role="button", name="Sign in".

    Prefer this over click_element: it survives CSS and markup changes, and the
    role/name pairs come straight out of snapshot_page.
    """
    await _page.get_by_role(role, name=name).first.click()
    return f'Clicked {role} named "{name}"'


@tool
@_needs_page
async def click_by_text(text: str) -> str:
    """Click the first element containing this visible text. Use for links and cards."""
    await _page.get_by_text(text).first.click()
    return f'Clicked element containing text "{text}"'


@tool
@_needs_page
async def type_by_label(label: str, text: str) -> str:
    """Type into the field with this form label or placeholder, e.g. label="Password".

    Prefer this over type_text - it is how a human finds the field, and it does
    not break when the CSS class changes.
    """
    field = _page.get_by_label(label)
    if await field.count() == 0:
        field = _page.get_by_placeholder(label)
    await field.first.fill(text)
    return f'Typed "{text}" into the field labelled "{label}"'


# --------------------------------------------------------------------------
# Reading and asserting - this is a QA agent, so let it verify
# --------------------------------------------------------------------------

@tool
@_needs_page
async def get_text(selector: str) -> str:
    """Extract the text content of an element found by CSS selector."""
    text = await _page.locator(selector).text_content()
    return (text or "No text found").strip()


@tool
@_needs_page
async def get_all_texts(selector: str) -> str:
    """Get the text of EVERY element matching the selector, as a numbered list.

    Use for tables, search results and list items, instead of calling get_text
    once per row.
    """
    texts = await _page.locator(selector).all_inner_texts()
    if not texts:
        return f"No elements match {selector}"
    return "\n".join(f"{i}. {t.strip()}" for i, t in enumerate(texts[:50], 1))


@tool
@_needs_page
async def get_attribute_value(selector: str, attribute: str) -> str:
    """Read one HTML attribute, such as href, value, class, disabled or aria-label."""
    value = await _page.locator(selector).first.get_attribute(attribute)
    return f"{attribute}={value!r}" if value is not None else f"{selector} has no {attribute}"


@tool
@_needs_page
async def count_elements(selector: str) -> str:
    """Count how many elements match a selector. Use to assert list lengths."""
    return f"{await _page.locator(selector).count()} element(s) match {selector}"


@tool
@_needs_page
async def assert_visible(selector: str, should_be_visible: bool = True) -> str:
    """Check whether an element is visible. Returns PASS or FAIL, never raises.

    This is the verification step of a test - call it after an action to decide
    whether the scenario actually passed.
    """
    actual = await _page.locator(selector).first.is_visible()
    ok = actual == should_be_visible
    return (f"{'PASS' if ok else 'FAIL'}: {selector} visible={actual}, "
            f"expected visible={should_be_visible}")


@tool
@_needs_page
async def assert_text_contains(selector: str, expected_text: str) -> str:
    """Check an element's text contains the expected substring. Returns PASS or FAIL."""
    actual = ((await _page.locator(selector).first.text_content()) or "").strip()
    ok = expected_text.lower() in actual.lower()
    return (f"{'PASS' if ok else 'FAIL'}: expected {expected_text!r} "
            f"{'found in' if ok else 'NOT found in'} {actual!r}")


# --------------------------------------------------------------------------
# Diagnostics - what a human tester checks that an agent usually forgets
# --------------------------------------------------------------------------

@tool
@_needs_page
async def get_console_errors() -> str:
    """List JavaScript console errors since the browser launched.

    A page can look perfect and still be broken. Check this before declaring a
    scenario passed.
    """
    if not _console_errors:
        return "No console errors."
    return f"{len(_console_errors)} console error(s):\n" + "\n".join(
        f"- {e}" for e in _console_errors[-20:])


@tool
@_needs_page
async def get_failed_requests() -> str:
    """List network requests that failed since launch - broken APIs, images, 4xx/5xx."""
    if not _failed_requests:
        return "No failed network requests."
    return f"{len(_failed_requests)} failed request(s):\n" + "\n".join(
        f"- {r}" for r in _failed_requests[-20:])


@tool
@_needs_page
async def take_screenshot(filename: str = "screenshot.png") -> str:
    """Take a full page screenshot and save it in the screenshots folder."""
    os.makedirs("screenshots", exist_ok=True)
    path = f"screenshots/{filename}"
    await _page.screenshot(path=path, full_page=True)
    return f"Screenshot saved as {path}"


# --------------------------------------------------------------------------
# Advanced - test conditions you cannot reach by clicking
# --------------------------------------------------------------------------

@tool
@_needs_page
async def set_viewport(width: int = 1280, height: int = 720) -> str:
    """Resize the viewport to test responsive layouts. Try 390x844 for mobile."""
    await _page.set_viewport_size({"width": width, "height": height})
    return f"Viewport set to {width}x{height}"


@tool
@_needs_page
async def mock_api_response(url_pattern: str, status: int = 500, body: str = "{}") -> str:
    """Force an API call to return a fake status and body, e.g. url_pattern="**/api/cart".

    This is how you test error states that you cannot trigger by clicking: a 500
    from the backend, an empty list, a timeout banner.
    """
    async def handler(route):
        await route.fulfill(status=status, content_type="application/json", body=body)
    await _page.route(url_pattern, handler)
    return f"Requests matching {url_pattern} will now return HTTP {status}"


@tool
@_needs_page
async def save_login_state(path: str = "auth_state.json") -> str:
    """Save cookies and localStorage to a file so a later run can skip logging in."""
    state = await _context.storage_state()
    with open(path, "w") as fh:
        json.dump(state, fh)
    return f"Saved {len(state.get('cookies', []))} cookie(s) to {path}"


# --------------------------------------------------------------------------
# Bundles - give an agent the smallest set that can do its job
# --------------------------------------------------------------------------

CORE_TOOLS = [
    launch_browser, close_browser, snapshot_page, get_page_info,
    navigate_to, click_by_role, click_by_text, type_by_label,
    click_element, type_text, get_text, take_screenshot,
]

INTERACTION_TOOLS = [
    hover_element, press_key, select_dropdown_option, set_checkbox,
    upload_file, drag_and_drop, scroll_to_element, wait_for_element,
    go_back, reload_page,
]

ASSERTION_TOOLS = [
    assert_visible, assert_text_contains, count_elements,
    get_all_texts, get_attribute_value,
]

DIAGNOSTIC_TOOLS = [get_console_errors, get_failed_requests]

ADVANCED_TOOLS = [set_viewport, mock_api_response, save_login_state]

PLAYWRIGHT_TOOLS = (
    CORE_TOOLS + INTERACTION_TOOLS + ASSERTION_TOOLS
    + DIAGNOSTIC_TOOLS + ADVANCED_TOOLS
)
