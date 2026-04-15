import { test, expect } from "@playwright/test";

test.describe("Test Cases", () => {
  test("displays seed cases on load", async ({ page }) => {
    await page.goto("/cases");
    // At least 10 seed cases should exist (may be 11 if create test ran first)
    await expect(page.getByText(/\(1[01] total\)/)).toBeVisible();
    await expect(page.getByText("Simple greeting")).toBeVisible();
    await expect(page.getByText("Math calculation")).toBeVisible();
  });

  test("Add Test Case button opens form", async ({ page }) => {
    await page.goto("/cases");
    await page.getByRole("button", { name: "Add Test Case" }).click();
    await expect(page.getByText("New Test Case")).toBeVisible();
    await expect(page.getByPlaceholder("Case name")).toBeVisible();
  });

  test("can create a new test case", async ({ page }) => {
    await page.goto("/cases");
    await page.getByRole("button", { name: "Add Test Case" }).click();

    await page.getByPlaceholder("Case name").fill("E2E Test Case");
    await page.getByPlaceholder("Input (what to send to the agent)").fill("What is 2+2?");
    await page.getByPlaceholder("Expected output (what the agent should respond)").fill("4");
    await page.getByPlaceholder("Tags (comma-separated)").fill("math,e2e");

    await page.getByRole("button", { name: "Create" }).click();

    // Wait for the form to close and case to appear
    // After creating, total should increase (may vary due to parallel tests)
    await expect(page.getByText(/\(1[12] total\)/)).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("E2E Test Case")).toBeVisible();
  });
});
