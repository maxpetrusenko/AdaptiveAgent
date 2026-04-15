import { test, expect } from "@playwright/test";

test.describe("Navigation", () => {
  test("dashboard loads with metric cards", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByText("Pass Rate", { exact: true })).toBeVisible();
    await expect(page.getByText("Hallucination Rate")).toBeVisible();
    await expect(page.getByText("Avg Cost")).toBeVisible();
    await expect(page.getByText("Eval Cases")).toBeVisible();
  });

  test("sidebar links navigate to correct pages", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("link", { name: "Chat" }).click();
    await expect(page.getByText("Start a new conversation")).toBeVisible();

    await page.getByRole("link", { name: "Evals" }).click();
    await expect(page.getByRole("heading", { name: "Evaluations" })).toBeVisible();

    await page.getByRole("link", { name: "Cases" }).click();
    await expect(page.getByRole("heading", { name: "Test Cases" })).toBeVisible();

    await page.getByRole("link", { name: "Adapt" }).click();
    await expect(page.getByRole("heading", { name: "Adaptation", exact: true })).toBeVisible();
  });
});
