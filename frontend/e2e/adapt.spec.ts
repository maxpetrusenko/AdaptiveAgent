import { test, expect } from "@playwright/test";

test.describe("Adaptation", () => {
  test("adapt page exposes governed candidate evaluation", async ({ page }) => {
    await page.goto("/adapt");
    await expect(page.getByRole("heading", { name: "Adaptation", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Evaluate candidate" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Review candidates in Tasks" })).toHaveAttribute("href", "/tasks");
  });

  test("shows deterministic governed evaluation history", async ({ page }) => {
    await page.goto("/adapt");
    await expect(page.getByText("Rejected", { exact: true })).toHaveCount(2);
    await expect(page.getByText("Select an adaptation run to see details.")).toBeVisible();
  });
});
