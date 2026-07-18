import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdaptPage from "@/app/adapt/page";
import EvalsPage from "@/app/evals/page";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("long-running page polling", () => {
  it.each([
    [AdaptPage, "Evaluate candidate", "/api/operator/adapt/improve"],
    [EvalsPage, "Run Eval", "/api/operator/evals/run"],
  ])("clears its interval when %s unmounts", async (Page, button, startPath) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith(startPath)) {
          return new Response(JSON.stringify({ id: "run-1" }), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      })
    );
    const timer = 7331 as unknown as ReturnType<typeof setInterval>;
    const interval = vi
      .spyOn(globalThis, "setInterval")
      .mockImplementation(() => timer);
    const clear = vi.spyOn(globalThis, "clearInterval");
    const view = render(<Page />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: button }));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(interval).toHaveBeenCalledOnce();
    clear.mockClear();
    view.unmount();

    expect(clear).toHaveBeenCalledWith(timer);
  });
});
