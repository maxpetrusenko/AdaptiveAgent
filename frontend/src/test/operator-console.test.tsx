import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OperatorConsole } from "@/components/operator/operator-console";
import type {
  OperatorTask,
  PromotionCandidate,
} from "@/lib/operator-types";

const task: OperatorTask = {
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
          artifact_ref: "trace://pytest-49",
          digest: "sha256:49-green",
          source: "ci",
          verifier: "pytest",
          status: "verified",
          recorded_at: "2026-07-18T01:10:00Z",
        },
      ],
    },
    {
      id: "review-pending",
      description: "Independent review is anchored",
      evidence: [
        {
          summary: "Review mentioned without an anchor",
          artifact_ref: "javascript:alert('unsafe')",
          digest: null,
          source: "operator-note",
          verifier: "unassigned",
          status: "unverified",
          recorded_at: "2026-07-18T01:12:00Z",
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

const candidate: PromotionCandidate = {
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
    {
      kind: "tool_description",
      target: "calculator",
      summary: "Clarify exact arithmetic use",
    },
  ],
};

describe("OperatorConsole", () => {
  it("renders task plan state, budget pressure, timeline, and evidence", () => {
    render(
      <OperatorConsole
        tasks={[task]}
        candidates={[candidate]}
        onTaskAction={vi.fn()}
        onPromote={vi.fn()}
        onRollback={vi.fn()}
      />
    );

    expect(
      screen.getByRole("heading", { name: "Ship a verified adaptive runtime" })
    ).toBeInTheDocument();
    expect(screen.getByText("Plan v2")).toBeInTheDocument();
    expect(screen.getByText("1 / 3 stalls")).toBeInTheDocument();
    expect(screen.getByText("5 / 12 actions")).toBeInTheDocument();
    expect(screen.getByText("Verify protected evaluation")).toBeInTheDocument();
    expect(screen.getByText("49 backend tests passed")).toBeInTheDocument();
    expect(screen.getByText("Verified by pytest")).toBeInTheDocument();
    expect(screen.getByText("Submitted by unassigned")).toBeInTheDocument();
    expect(screen.getByText("Source: ci")).toBeInTheDocument();
    expect(screen.getByText("sha256:49-green")).toBeInTheDocument();
    expect(screen.getByText("Checkpoint #7")).toBeInTheDocument();
    expect(screen.getByText("Unverified")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Open proof: Review mentioned without an anchor" })
    ).not.toBeInTheDocument();
    expect(screen.getByText("javascript:alert('unsafe')")).toBeInTheDocument();
    expect(
      screen.getByRole("link", {
        name: "Open trace trace://pytest-49",
      })
    ).toHaveAttribute(
      "href",
      "trace://pytest-49"
    );
  });

  it("offers lifecycle controls appropriate to the selected task", () => {
    const onTaskAction = vi.fn();
    const { rerender } = render(
      <OperatorConsole
        tasks={[task]}
        candidates={[candidate]}
        onTaskAction={onTaskAction}
        onPromote={vi.fn()}
        onRollback={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Pause task" }));
    expect(onTaskAction).toHaveBeenCalledWith("task-1", "pause");

    rerender(
      <OperatorConsole
        tasks={[{ ...task, status: "paused" }]}
        candidates={[candidate]}
        onTaskAction={onTaskAction}
        onPromote={vi.fn()}
        onRollback={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Resume task" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Cancel task" })).toBeVisible();
  });

  it("shows replan-required state without offering an invalid resume", () => {
    render(
      <OperatorConsole
        tasks={[
          {
            ...task,
            status: "replan_required",
            replan_reason: "stall_threshold_reached",
          } as unknown as OperatorTask,
        ]}
        candidates={[candidate]}
        onTaskAction={vi.fn()}
        onPromote={vi.fn()}
        onRollback={vi.fn()}
      />
    );

    expect(screen.getByText("Replan required")).toBeVisible();
    expect(screen.getByText(/stall_threshold_reached/)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Resume task" })
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel task" })).toBeVisible();
  });

  it("confirms task cancellation and disables a pending duplicate action", () => {
    const onTaskAction = vi.fn();
    render(
      <OperatorConsole
        tasks={[task]}
        candidates={[candidate]}
        pendingActionIds={new Set(["task:task-1"])}
        onTaskAction={onTaskAction}
        onPromote={vi.fn()}
        onRollback={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: "Pause task" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel task" })).toBeDisabled();
  });

  it("traps dialog focus and restores background interactivity", () => {
    render(
      <OperatorConsole
        tasks={[task]}
        candidates={[{ ...candidate, status: "promoted" }]}
        onTaskAction={vi.fn()}
        onPromote={vi.fn()}
        onRollback={vi.fn()}
      />
    );

    const rollbackTrigger = screen.getByRole("button", {
      name: "Rollback candidate",
    });
    fireEvent.click(rollbackTrigger);
    const dialog = screen.getByRole("alertdialog");
    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Confirm rollback" });
    expect(document.body.firstElementChild).toHaveAttribute("inert");
    expect(cancel).toHaveFocus();

    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(cancel).toHaveFocus();

    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(document.body.firstElementChild).not.toHaveAttribute("inert");
    expect(rollbackTrigger).toHaveFocus();
  });

  it("labels HTTP evidence with its hostname", () => {
    const httpTask = {
      ...task,
      acceptance_criteria: [
        {
          ...task.acceptance_criteria[0],
          evidence: [
            {
              ...task.acceptance_criteria[0].evidence[0],
              artifact_ref: "https://ci.example.com/runs/49",
            },
          ],
        },
      ],
    };
    render(
      <OperatorConsole
        tasks={[httpTask]}
        candidates={[]}
        onTaskAction={vi.fn()}
        onPromote={vi.fn()}
        onRollback={vi.fn()}
      />
    );

    expect(
      screen.getByRole("link", { name: "Open proof from ci.example.com" })
    ).toHaveAttribute("href", "https://ci.example.com/runs/49");
  });

  it("confirms task cancellation when no lifecycle action is pending", () => {
    const onTaskAction = vi.fn();
    render(
      <OperatorConsole
        tasks={[task]}
        candidates={[candidate]}
        onTaskAction={onTaskAction}
        onPromote={vi.fn()}
        onRollback={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancel task" }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("Ship a verified adaptive runtime");
    expect(dialog).toHaveTextContent("cannot be resumed");
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm task cancellation" })
    );
    expect(onTaskAction).toHaveBeenCalledTimes(1);
    expect(onTaskAction).toHaveBeenCalledWith("task-1", "cancel");
  });

  it("requires the candidate hash before dangerous promotion", () => {
    const onPromote = vi.fn();
    render(
      <OperatorConsole
        tasks={[task]}
        candidates={[candidate]}
        onTaskAction={vi.fn()}
        onPromote={onPromote}
        onRollback={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Promote candidate" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "This changes the active agent"
    );
    const confirmButton = screen.getByRole("button", {
      name: "Confirm promotion",
    });
    expect(confirmButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Type candidate hash to confirm"), {
      target: { value: "cand-8f2a" },
    });
    expect(confirmButton).toBeEnabled();
    fireEvent.click(confirmButton);
    expect(onPromote).toHaveBeenCalledWith("cand-8f2a");
  });

  it("shows separated evaluation evidence and explicit rollback", () => {
    const onRollback = vi.fn();
    render(
      <OperatorConsole
        tasks={[task]}
        candidates={[{ ...candidate, status: "promoted" }]}
        onTaskAction={vi.fn()}
        onPromote={vi.fn()}
        onRollback={onRollback}
      />
    );

    expect(screen.getByText("Training")).toBeVisible();
    expect(screen.getByText("Validation")).toBeVisible();
    expect(screen.getByText("Protected")).toBeVisible();
    expect(screen.getByText("+11 pts")).toBeVisible();
    expect(screen.getByText("tool_description")).toBeVisible();
    expect(screen.getByText("calculator")).toBeVisible();
    expect(screen.getByText("Clarify exact arithmetic use")).toBeVisible();
    const rollbackTrigger = screen.getByRole("button", {
      name: "Rollback candidate",
    });
    fireEvent.click(rollbackTrigger);
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("cand-8f2a");
    expect(dialog).toHaveTextContent("restore parent parent-412f");
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(rollbackTrigger).toHaveFocus();

    fireEvent.click(rollbackTrigger);
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm rollback" })
    );
    expect(onRollback).toHaveBeenCalledWith("cand-8f2a");
  });

  it("renders regressions in red and never enables a rejected candidate", () => {
    render(
      <OperatorConsole
        tasks={[task]}
        candidates={[
          {
            ...candidate,
            decision: "reject",
            status: "rejected",
            results: {
              ...candidate.results,
              validation: { baseline: 0.8, candidate: 0.7 },
            },
          },
        ]}
        onTaskAction={vi.fn()}
        onPromote={vi.fn()}
        onRollback={vi.fn()}
      />
    );

    expect(screen.getByText("-10 pts")).toHaveClass("text-red-700");
    expect(screen.getByText("Promotion vetoed")).toBeVisible();
    expect(screen.getByRole("button", { name: "Promote candidate" })).toBeDisabled();
  });
});
