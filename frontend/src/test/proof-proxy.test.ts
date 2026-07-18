import { describe, expect, it } from "vitest";

import {
  buildProofBackendUrl,
  proofProxyHeaders,
} from "@/lib/proof-proxy";
import { assertLocalProxyRequest } from "@/lib/local-proxy-policy";

describe("proof proxy boundary", () => {
  it("allows only the shipped knowledge and research proof routes", () => {
    expect(
      buildProofBackendUrl(
        "http://backend:8000",
        "POST",
        ["knowledge", "ingest"],
        ""
      )
    ).toBe("http://backend:8000/api/knowledge/ingest");
    expect(
      buildProofBackendUrl(
        "http://backend:8000/",
        "POST",
        ["research", "proof-tenant", "runs"],
        "?mode=live"
      )
    ).toBe(
      "http://backend:8000/api/research/proof-tenant/runs?mode=live"
    );
    expect(() =>
      buildProofBackendUrl("http://backend:8000", "POST", ["tasks"], "")
    ).toThrow(/not allowed/i);
    expect(() =>
      buildProofBackendUrl(
        "http://backend:8000",
        "POST",
        ["knowledge", "..", "tasks"],
        ""
      )
    ).toThrow(/invalid/i);
    expect(() =>
      buildProofBackendUrl(
        "http://backend:8000",
        "DELETE",
        ["knowledge", "ingest"],
        ""
      )
    ).toThrow(/not allowed/i);
  });

  it("fails closed unless local proof mode and a same-origin browser request are explicit", () => {
    const localRequest = {
      mode: "local",
      requestUrl: "http://localhost:3737/api/proof/knowledge/ingest",
      origin: "http://localhost:3737",
      fetchSite: "same-origin",
    };
    expect(() => assertLocalProxyRequest(localRequest)).not.toThrow();
    expect(() =>
      assertLocalProxyRequest({ ...localRequest, mode: undefined })
    ).toThrow(/disabled/i);
    expect(() =>
      assertLocalProxyRequest({
        ...localRequest,
        requestUrl: "https://agent.example.com/api/proof/knowledge/ingest",
        origin: "https://agent.example.com",
      })
    ).toThrow(/loopback/i);
    expect(() =>
      assertLocalProxyRequest({
        ...localRequest,
        origin: "https://attacker.example",
        fetchSite: "cross-site",
      })
    ).toThrow(/same-origin/i);
  });

  it("keeps the operator token in server-side forwarding headers", () => {
    const headers = proofProxyHeaders(
      new Headers({ "content-type": "application/json" }),
      "server-secret"
    );

    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("x-operator-token")).toBe("server-secret");
    expect(headers.get("cookie")).toBeNull();
  });
});
