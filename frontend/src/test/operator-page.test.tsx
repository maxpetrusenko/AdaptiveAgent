import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TasksPage from "@/app/tasks/page";
import { operatorApi } from "@/lib/operator-api";

vi.mock("@/lib/operator-api", () => ({
  operatorApi: {
    listTasks: vi.fn(),
    listCandidates: vi.fn(),
    transitionTask: vi.fn(),
    promoteCandidate: vi.fn(),
    rollbackCandidate: vi.fn(),
  },
}));

const api = vi.mocked(operatorApi);

const task = {
  id: "task-page",
  goal: "Persist operator state",
  constraints: [],
  acceptance_criteria: [
    { id: "proof", description: "Proof exists", evidence: [] },
  ],
  steps: [{ id: "step", title: "Verify state", status: "active" as const }],
  status: "active" as const,
  plan_version: 1,
  current_step_index: 0,
  stall_count: 0,
  stall_threshold: 3,
  action_budget: 5,
  actions_used: 0,
  replan_reason: null,
  escalation_reason: null,
  created_at: "2026-07-18T00:00:00Z",
  updated_at: "2026-07-18T00:00:00Z",
  completed_at: null,
  checkpoint: {
    sequence: 1,
    operation: "create",
    idempotency_key: null,
    updated_at: "2026-07-18T00:00:00Z",
  },
};

const candidate = {
  id: "candidate-page",
  title: "Persisted candidate",
  status: "promoted" as const,
  parent_hash: "parent-page",
  candidate_hash: "candidate-page",
  rationale: "Passed gates",
  decision: "promote" as const,
  results: {
    training: { baseline: 0.5, candidate: 0.7 },
    validation: { baseline: 0.5, candidate: 0.7 },
    protected: { baseline: 1, candidate: 1 },
  },
  lower_confidence_bound: 0.1,
  latency_ratio: 1,
  cost_ratio: 1,
  mutations: [{ kind: "prompt", target: "system", summary: "Add evidence" }],
};

describe("TasksPage persistence", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listTasks.mockResolvedValue([task]);
    api.listCandidates.mockResolvedValue([candidate]);
  });

  it("persists the rollback response in the visible authority state", async () => {
    api.rollbackCandidate.mockResolvedValue({
      ...candidate,
      status: "rolled_back",
    });
    render(<TasksPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Rollback candidate" })
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm rollback" })
    );

    expect(await screen.findByText("Rolled back")).toBeVisible();
    expect(api.rollbackCandidate).toHaveBeenCalledWith("candidate-page");
  });

  it("keeps the prior candidate on error and retries both evidence feeds", async () => {
    api.rollbackCandidate.mockRejectedValue(new Error("offline"));
    render(<TasksPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Rollback candidate" })
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm rollback" })
    );

    expect(
      await screen.findByText(
        "Rollback failed. Check the active candidate before retrying."
      )
    ).toBeVisible();
    expect(screen.getByText("Active candidate")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => {
      expect(api.listTasks).toHaveBeenCalledTimes(2);
      expect(api.listCandidates).toHaveBeenCalledTimes(2);
    });
  });

  it("locks every lifecycle control while one task mutation is pending", async () => {
    let resolveTransition: ((value: typeof task) => void) | undefined;
    api.transitionTask.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveTransition = resolve;
        })
    );
    render(<TasksPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Pause task" })
    );
    expect(screen.getByRole("button", { name: "Pause task" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel task" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel task" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(api.transitionTask).toHaveBeenCalledTimes(1);

    resolveTransition?.({ ...task, status: "paused" });
  });

  it.each([401, 403])(
    "explains operator-session requirements after a %s mutation response",
    async (status) => {
      api.transitionTask.mockRejectedValue(
        Object.assign(new Error("unauthorized"), { status })
      );
      render(<TasksPage />);

      fireEvent.click(
        await screen.findByRole("button", { name: "Pause task" })
      );

      expect(
        await screen.findByText(/Operator session required/)
      ).toBeVisible();
      expect(
        screen.getByText(/never expose OPERATOR_API_TOKEN through NEXT_PUBLIC/i)
      ).toBeVisible();
    }
  );
});
