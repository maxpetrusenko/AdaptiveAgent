import { test, expect } from "@playwright/test";

test.describe("Evaluations", () => {
  test("evals page loads with Run Eval button", async ({ page }) => {
    await page.goto("/evals");
    await expect(page.getByRole("heading", { name: "Evaluations" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Run Eval" })).toBeVisible();
    await expect(page.getByText("Pass Rate Over Time")).toBeVisible();
  });

  test("shows empty state when no runs exist", async ({ page }) => {
    await page.goto("/evals");
    await expect(page.getByText(/No eval runs yet/)).toBeVisible();
  });
});
