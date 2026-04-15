import { test, expect } from "@playwright/test";

test.describe("Adaptation", () => {
  test("adapt page loads with Improve button", async ({ page }) => {
    await page.goto("/adapt");
    await expect(page.getByRole("heading", { name: "Adaptation", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Improve" })).toBeVisible();
  });

  test("shows empty state message", async ({ page }) => {
    await page.goto("/adapt");
    await expect(page.getByText(/No adaptation runs yet/)).toBeVisible();
    await expect(page.getByText("Select an adaptation run to see details.")).toBeVisible();
  });
});
