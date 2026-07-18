import { expect, test } from "@playwright/test";

test("real Rust proof survives a controlled crash and resumes exactly once", async ({
  page,
}) => {
  await page.goto("/proof");

  await expect(
    page.getByRole("heading", { name: /Crash the worker/i })
  ).toBeVisible();
  await expect(page.getByText("No active evidence index")).toBeVisible();

  await page.getByRole("button", { name: "Ingest 3 sources" }).click();
  await expect(page.getByText("Native index ready")).toBeVisible();
  await expect(page.getByText("3 chunks active")).toBeVisible();

  await page
    .getByRole("button", { name: "Start deterministic run" })
    .click();
  await expect(page.getByText("Controlled crash sealed")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Resume from checkpoint" })
  ).toBeEnabled();

  await page.getByRole("button", { name: "Resume from checkpoint" }).click();
  await expect(page.getByText("Exactly-once effect reused")).toBeVisible();
  await expect(page.getByText("Fixture verifier passed")).toBeVisible();
  await expect(
    page.getByText(/separate native retrieval inspection/i)
  ).toBeVisible();
  await expect(page.getByText("Citations you can audit")).toBeVisible();
  await expect(page.getByText(/Tantivy BM25/i).first()).toBeVisible();
  await expect(page.getByText(/^attempt 1$/i)).toHaveCount(4);
});

test("proof remains usable without horizontal overflow on mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/proof");

  await expect(
    page.getByRole("heading", { name: /Crash the worker/i })
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Ingest 3 sources" })).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth
    )
  ).toBe(true);
});
