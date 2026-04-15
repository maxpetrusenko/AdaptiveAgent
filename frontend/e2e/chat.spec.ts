import { test, expect } from "@playwright/test";

test.describe("Chat", () => {
  test("chat page has session sidebar and input", async ({ page }) => {
    await page.goto("/chat");
    await expect(page.getByText("Sessions", { exact: true })).toBeVisible();
    await expect(page.getByPlaceholder("Type a message...")).toBeVisible();
  });

  test("can create a new session via + button", async ({ page }) => {
    await page.goto("/chat");
    // Click the + button to create a session
    await page.locator("button").filter({ has: page.locator("svg") }).first().click();
    // Wait for a session to appear in the list
    await page.waitForTimeout(1000);
    // The session list should now have at least one entry
    const sessionButtons = page.locator("button").filter({ hasText: /New Chat|Chat/ });
    await expect(sessionButtons.first()).toBeVisible({ timeout: 5000 });
  });

  test("sending a message shows user bubble", async ({ page }) => {
    await page.goto("/chat");
    const input = page.getByPlaceholder("Type a message...");
    await input.fill("Hello from e2e test");
    await input.press("Enter");

    // User message should appear
    await expect(page.getByText("Hello from e2e test")).toBeVisible({ timeout: 5000 });
  });
});
