/**
 * 5 real Playwright login tests against TTACart.
 *
 * Test 5 is the planted flaky one. Its flakiness is SIMULATED, not random:
 * with FLAKY_BUILD=2 it waits only 50ms for the product grid, which it never
 * makes. Simulated on purpose so the lesson is reproducible in a classroom.
 */
import { test, expect, type Page } from "@playwright/test";

const URL = "https://app.thetestingacademy.com/playwright/ttacart/";
const USER = "standard_user";
const PASSWORD = "tta_secret";
const FLAKY = process.env.FLAKY_BUILD === "2";

async function login(page: Page, user: string, password: string) {
  await page.goto(URL);
  await page.locator("#user-name").fill(user);
  await page.locator("#password").fill(password);
  await page.locator("#login-button").click();
}

test("valid_login", async ({ page }) => {
  await login(page, USER, PASSWORD);
  await expect(page).toHaveURL(/\/inventory/);
});

test("invalid_password", async ({ page }) => {
  await login(page, USER, "wrong_password");
  await expect(page.getByRole("alert")).toContainText("do not match");
});

test("empty_username", async ({ page }) => {
  // No app alert here: the field is `required`, so the browser blocks submit.
  await login(page, "", PASSWORD);
  await expect(page).toHaveURL(URL);
  const msg = await page.locator("#user-name").evaluate(
    (e: HTMLInputElement) => e.validationMessage);
  expect(msg).toBe("Please fill out this field.");
});

test("locked_out_user", async ({ page }) => {
  await login(page, "locked_out_user", PASSWORD);
  await expect(page.getByRole("alert")).toContainText("locked out");
});

test("products_load", async ({ page }) => {
  await login(page, USER, PASSWORD);
  await expect(page.locator("article")).toHaveCount(6, { timeout: FLAKY ? 50 : 10_000 });
});
