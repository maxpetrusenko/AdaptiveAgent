import { expect, test } from "@playwright/test";

import { e2eBackendUrl } from "./database";

const task = {
  id: "task-1",
  goal: "Ship a verified adaptive runtime",
  constraints: ["Protected cases cannot regress"],
  acceptance_criteria: [
    {
      id: "tests-green",
      description: "All tests pass",
      evidence: [
        {
          summary: "49 backend tests passed",
          artifact_ref: "https://example.com/proof/49",
          digest: "sha256:49-green",
          source: "ci",
          verifier: "pytest",
          status: "verified",
          recorded_at: "2026-07-18T01:10:00Z",
        },
      ],
    },
  ],
  steps: [
    { id: "step-1", title: "Implement durable task ledger", status: "completed" },
    { id: "step-2", title: "Verify protected evaluation", status: "active" },
    { id: "step-3", title: "Promote candidate", status: "pending" },
  ],
  status: "active",
  plan_version: 2,
  current_step_index: 1,
  stall_count: 1,
  stall_threshold: 3,
  action_budget: 12,
  actions_used: 5,
  replan_reason: "stall_threshold_reached",
  escalation_reason: null,
  created_at: "2026-07-18T00:00:00Z",
  updated_at: "2026-07-18T01:10:00Z",
  completed_at: null,
  checkpoint: {
    sequence: 7,
    operation: "advance",
    idempotency_key: "advance-7",
    updated_at: "2026-07-18T01:10:00Z",
  },
};

const candidate = {
  id: "cand-8f2a",
  title: "Tool-routing prompt v3",
  status: "ready",
  parent_hash: "parent-412f",
  candidate_hash: "cand-8f2a",
  rationale:
    "Validated quality gain cleared uncertainty, protected, latency, and cost gates",
  decision: "promote",
  results: {
    training: { baseline: 0.62, candidate: 0.81 },
    validation: { baseline: 0.65, candidate: 0.76 },
    protected: { baseline: 1, candidate: 1 },
  },
  lower_confidence_bound: 0.07,
  latency_ratio: 1.08,
  cost_ratio: 1.04,
  mutations: [
    { kind: "prompt", target: "system", summary: "Require tool evidence" },
  ],
};

test.describe("mocked operator evidence", () => {
test.beforeEach(async ({ page }) => {
  await page.route("**/api/tasks", (route) =>
    route.fulfill({ json: [task] })
  );
  await page.route("**/api/operator/tasks/task-1/*", async (route) => {
    const action = route.request().url().split("/").at(-1);
    await route.fulfill({
      json: { ...task, status: action === "pause" ? "paused" : task.status },
    });
  });
  await page.route("**/api/adapt/candidates", (route) =>
    route.fulfill({ json: [candidate] })
  );
  await page.route("**/api/operator/adapt/candidates/cand-8f2a/promote", (route) =>
    route.fulfill({ json: { ...candidate, status: "promoted" } })
  );
});

test("operator pauses work and promotes only after explicit confirmation", async ({
  page,
}) => {
  await page.goto("/tasks");
  await expect(
    page.getByRole("heading", { name: "Mission ledger" })
  ).toBeVisible();
  await expect(page.getByText("Verify protected evaluation")).toBeVisible();
  await expect(page.getByText("49 backend tests passed")).toBeVisible();

  await page.getByRole("button", { name: "Pause task" }).click();
  await expect(page.getByRole("button", { name: "Resume task" })).toBeVisible();

  await page.getByRole("button", { name: "Promote candidate" }).click();
  const confirm = page.getByRole("button", { name: "Confirm promotion" });
  await expect(confirm).toBeDisabled();
  await page
    .getByLabel("Type candidate hash to confirm")
    .fill("cand-8f2a");
  await confirm.click();
  await expect(page.getByText("Active candidate")).toBeVisible();
});

test("operator console remains usable at a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tasks");

  await expect(
    page.getByRole("heading", { name: "Mission ledger" })
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause task" })).toBeVisible();
  await expect(page.getByText("Validation", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth
    )
  ).toBe(true);
});
});

test("real task API lifecycle persists across refreshes", async ({
  page,
  request,
}) => {
  const goal = `E2E durable task ${Date.now()}`;
  const created = await request.post(`${e2eBackendUrl}/api/tasks`, {
    headers: { "x-operator-token": "e2e-local-operator-token" },
    data: {
      goal,
      constraints: ["Do not skip proof"],
      acceptance_criteria: [
        { id: "e2e-proof", description: "Lifecycle is persisted" },
      ],
      steps: [{ title: "Exercise lifecycle" }],
      stall_threshold: 3,
      action_budget: 5,
    },
  });
  expect(created.status()).toBe(201);

  await page.goto("/tasks");
  await expect(page.getByRole("heading", { name: goal })).toBeVisible();
  await page.getByRole("button", { name: "Pause task" }).click();
  await expect(page.getByRole("button", { name: "Resume task" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Resume task" })).toBeVisible();
  await page.getByRole("button", { name: "Resume task" }).click();
  await expect(page.getByRole("button", { name: "Pause task" })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Cancel task" }).click();
  await expect(page.getByRole("alertdialog")).toContainText(goal);
  await page
    .getByRole("button", { name: "Confirm task cancellation" })
    .click();
  await page.reload();
  await expect(page.getByText("cancelled", { exact: true }).first()).toBeVisible();
});

test("real promotion governance persists activation and rollback", async ({
  page,
  request,
}) => {
  const response = await request.get(
    `${e2eBackendUrl}/api/adapt/candidates`
  );
  expect(response.ok()).toBe(true);
  const candidates = await response.json();
  const ready = candidates.find(
    (item: { id: string }) => item.id === "demo-promotion-ready"
  );
  const rejected = candidates.find(
    (item: { id: string }) => item.id === "demo-promotion-rejected"
  );
  expect(ready).toBeTruthy();
  expect(rejected).toBeTruthy();

  await page.goto("/tasks");
  await page
    .getByRole("button", { name: new RegExp(rejected.candidate_hash) })
    .click();
  await expect(
    page.getByRole("button", { name: "Promote candidate" })
  ).toBeDisabled();

  await page
    .getByRole("button", { name: new RegExp(ready.candidate_hash) })
    .click();
  await page.getByRole("button", { name: "Promote candidate" }).click();
  await page
    .getByLabel("Type candidate hash to confirm")
    .fill(ready.candidate_hash);
  await page.getByRole("button", { name: "Confirm promotion" }).click();
  await expect(page.getByText("Active candidate")).toBeVisible();

  await page.reload();
  await page
    .getByRole("button", { name: new RegExp(ready.candidate_hash) })
    .click();
  await expect(page.getByText("Active candidate")).toBeVisible();
  await page.getByRole("button", { name: "Rollback candidate" }).click();
  await expect(page.getByRole("alertdialog")).toContainText(
    `restore parent ${ready.parent_hash}`
  );
  await page.getByRole("button", { name: "Confirm rollback" }).click();
  await expect(page.getByText("Rolled back")).toBeVisible();

  await page.reload();
  await page
    .getByRole("button", { name: new RegExp(ready.candidate_hash) })
    .click();
  await expect(page.getByText("Rolled back")).toBeVisible();

  const promptsResponse = await request.get(
    `${e2eBackendUrl}/api/adapt/prompts`
  );
  expect(promptsResponse.ok()).toBe(true);
  const prompts = await promptsResponse.json();
  expect(
    prompts.find(
      (prompt: { id: string }) => prompt.id === "demo-prompt-parent-v1"
    ).is_active
  ).toBe(true);
  expect(
    prompts.find(
      (prompt: { id: string }) => prompt.id === "demo-prompt-candidate-ready"
    ).is_active
  ).toBe(false);
});
