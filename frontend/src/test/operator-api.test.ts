import { afterEach, describe, expect, it, vi } from "vitest";

import { operatorApi } from "@/lib/operator-api";

describe("operator API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads tasks and promotion candidates from their governed endpoints", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify([{ id: "task-1" }]), { status: 200 })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([{ id: "candidate-1" }]), { status: 200 })
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(operatorApi.listTasks()).resolves.toEqual([{ id: "task-1" }]);
    await expect(operatorApi.listCandidates()).resolves.toEqual([
      { id: "candidate-1" },
    ]);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/tasks"
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/adapt/candidates"
    );
  });

  it("sends lifecycle and promotion commands without implicit mutation", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ status: "ok" }), { status: 200 })
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await operatorApi.transitionTask("task-1", "pause");
    await operatorApi.promoteCandidate("candidate-1");
    await operatorApi.rollbackCandidate("candidate-1");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/tasks/task-1/pause",
      expect.objectContaining({ method: "POST" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/adapt/candidates/candidate-1/promote",
      expect.objectContaining({ method: "POST" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/api/adapt/candidates/candidate-1/rollback",
      expect.objectContaining({ method: "POST" })
    );
  });
});
