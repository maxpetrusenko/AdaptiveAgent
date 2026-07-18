import { afterEach, describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { POST as proxyOperatorPost } from "@/app/api/operator/[...path]/route";
import { buildOperatorBackendUrl } from "@/lib/operator-proxy";

describe("operator proxy boundary", () => {
  afterEach(() => {
    delete process.env.OPERATOR_PROXY_MODE;
  });

  it.each([
    [["tasks", "task-1", "pause"], "POST"],
    [["tasks", "task-1", "resume"], "POST"],
    [["tasks", "task-1", "cancel"], "POST"],
    [["adapt", "candidates", "candidate-1", "promote"], "POST"],
    [["adapt", "candidates", "candidate-1", "rollback"], "POST"],
    [["adapt", "improve"], "POST"],
    [["cases"], "POST"],
    [["cases", "case-1"], "DELETE"],
    [["evals", "run"], "POST"],
  ])("allows the governed %j %s mutation", (path, method) => {
    expect(
      buildOperatorBackendUrl("http://backend:8000", method, path, "")
    ).toBe(`http://backend:8000/api/${path.join("/")}`);
  });

  it.each([
    [["tasks"], "DELETE"],
    [["tasks", "task-1", "advance"], "POST"],
    [["adapt", "prompts"], "POST"],
    [["cases", "case-1"], "POST"],
    [["chat", "sessions"], "POST"],
  ])("rejects the ungoverned %j %s mutation", (path, method) => {
    expect(() =>
      buildOperatorBackendUrl("http://backend:8000", method, path, "")
    ).toThrow(/not allowed/i);
  });

  it("denies an anonymous production-origin mutation before backend fetch", async () => {
    process.env.OPERATOR_PROXY_MODE = "local";
    const request = new NextRequest(
      "https://agent.example.com/api/operator/evals/run",
      {
        method: "POST",
        headers: {
          origin: "https://agent.example.com",
          "sec-fetch-site": "same-origin",
        },
      }
    );

    const response = await proxyOperatorPost(request, {
      params: Promise.resolve({ path: ["evals", "run"] }),
    });

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual({
      detail: "Operator proxy unavailable",
    });
  });
});
