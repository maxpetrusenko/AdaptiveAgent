import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

// Test that key components render without crashing
describe("Component rendering", () => {
  it("ChatInput renders", async () => {
    const { ChatInput } = await import("@/components/chat/chat-input");
    render(<ChatInput onSend={() => {}} />);
    expect(screen.getByPlaceholderText("Type a message...")).toBeDefined();
  });

  it("CaseList renders empty state", async () => {
    const { CaseList } = await import("@/components/cases/case-list");
    render(<CaseList cases={[]} />);
    expect(screen.getByText("No test cases yet.")).toBeDefined();
  });

  it("EvalRunList renders empty state", async () => {
    const { EvalRunList } = await import("@/components/evals/eval-run-list");
    render(<EvalRunList runs={[]} onSelect={() => {}} />);
    expect(screen.getByText(/No eval runs yet/)).toBeDefined();
  });

  it("EvalResultsTable renders empty state", async () => {
    const { EvalResultsTable } = await import("@/components/evals/eval-results-table");
    render(<EvalResultsTable results={[]} />);
    expect(screen.getByText("Select an eval run to see results.")).toBeDefined();
  });

  it("AdaptationList renders empty state", async () => {
    const { AdaptationList } = await import("@/components/adapt/adaptation-list");
    render(<AdaptationList runs={[]} onSelect={() => {}} />);
    expect(screen.getByText(/No adaptation runs yet/)).toBeDefined();
  });
});
