import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../src/api/client";
import { ANSWER, jsonResponse } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("posts the question to /api/ask", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(ANSWER));
    vi.stubGlobal("fetch", fetchMock);
    const res = await api.ask("How often?");
    expect(res.query_id).toBe(7);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/ask");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ question: "How often?" });
  });

  it("surfaces the backend's detail message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "OPENAI_API_KEY is not set." }, 503)));
    await expect(api.ask("hello there")).rejects.toMatchObject({ status: 503, message: "OPENAI_API_KEY is not set." });
  });

  it("joins validation errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: [{ msg: "too short" }] }, 422)));
    await expect(api.ask("x")).rejects.toThrow("too short");
  });

  it("gives a friendly message when the server can't be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await api.health().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.message).toMatch(/Can't reach the server/);
  });

  it("sends feedback for a query", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    await api.feedback(7, false);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/queries/7/feedback");
    expect(JSON.parse(init.body)).toEqual({ helpful: false, note: null });
  });
});
