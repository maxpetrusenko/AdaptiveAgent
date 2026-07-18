import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmationDialog } from "@/components/operator/confirmation-dialog";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ConfirmationDialog server rendering", () => {
  it("does not read browser globals before the client mounts", () => {
    vi.stubGlobal("document", undefined);

    expect(() =>
      renderToString(
        <ConfirmationDialog
          open
          eyebrow="Destructive action"
          title="Cancel task"
          description="This cannot be resumed."
          identity="task-1"
          outcome="The run stops."
          confirmLabel="Confirm"
          onClose={() => undefined}
          onConfirm={() => undefined}
        />
      )
    ).not.toThrow();
  });
});
