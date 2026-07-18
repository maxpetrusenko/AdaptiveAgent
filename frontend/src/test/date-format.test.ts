import { describe, expect, it } from "vitest";

import { formatDate, formatDateTime } from "@/lib/date-format";

describe("stable date formatting", () => {
  it("uses an explicit locale and UTC timezone", () => {
    expect(formatDate("2026-07-18T12:34:56Z")).toBe("Jul 18, 2026");
    expect(formatDateTime("2026-07-18T12:34:56Z")).toBe(
      "Jul 18, 2026, 12:34 PM UTC"
    );
  });
});
