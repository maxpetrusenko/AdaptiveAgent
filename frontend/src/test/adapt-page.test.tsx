import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdaptPage from "@/app/adapt/page";

describe("AdaptPage governance copy", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      })
    );
  });

  it("describes evaluation without claiming automatic activation", () => {
    render(<AdaptPage />);

    expect(
      screen.getByRole("button", { name: "Evaluate candidate" })
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Review candidates in Tasks" })
    ).toHaveAttribute("href", "/tasks");
    expect(screen.getByText(/never activates automatically/i)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Improve" })
    ).not.toBeInTheDocument();
  });
});
