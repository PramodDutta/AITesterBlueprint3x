"""5 real Playwright login tests against TTACart.

Test 5 is the planted flaky one. Its flakiness is SIMULATED, not random: with
FLAKY_BUILD=2 it waits only 50ms for the product grid, which it never makes.
Simulated on purpose, so the lesson is reproducible in a classroom; a genuinely
random test would make the demo a coin toss.
"""
import os
import re

from playwright.sync_api import Page, expect

URL = "https://app.thetestingacademy.com/playwright/ttacart/"
USER, PASSWORD = "standard_user", "tta_secret"
FLAKY = os.getenv("FLAKY_BUILD") == "2"


def login(page: Page, user: str, password: str) -> None:
    page.goto(URL)
    page.locator("#user-name").fill(user)
    page.locator("#password").fill(password)
    page.locator("#login-button").click()


def test_valid_login(page: Page) -> None:
    login(page, USER, PASSWORD)
    expect(page).to_have_url(re.compile(r"/inventory"))


def test_invalid_password(page: Page) -> None:
    login(page, USER, "wrong_password")
    expect(page.get_by_role("alert")).to_contain_text("do not match")


def test_empty_username(page: Page) -> None:
    """No app alert here: the field is `required`, so the browser blocks submit."""
    login(page, "", PASSWORD)
    expect(page).to_have_url(URL)                       # never navigated
    assert page.locator("#user-name").evaluate(
        "e => e.validationMessage") == "Please fill out this field."


def test_locked_out_user(page: Page) -> None:
    login(page, "locked_out_user", PASSWORD)
    expect(page.get_by_role("alert")).to_contain_text("locked out")


def test_products_load(page: Page) -> None:
    """The planted flaky test: a timeout too tight to meet in build 2."""
    login(page, USER, PASSWORD)
    expect(page.locator("article")).to_have_count(6, timeout=50 if FLAKY else 10_000)
