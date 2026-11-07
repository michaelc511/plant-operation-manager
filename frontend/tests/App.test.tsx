import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { AnswerText } from "../src/components/AnswerText";
import { ANSWER, HEALTH, OLD_SESSION, RECORD, SESSION, SUMMARIES, jsonResponse } from "./fixtures";

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

function mockBackend(overrides: Record<string, Handler> = {}) {
  const routes: Record<string, Handler> = {
    "/api/health": () => jsonResponse(HEALTH),
    "/api/ask": () => jsonResponse(ANSWER),
    "/api/queries?limit=30": () => jsonResponse([RECORD]),
    "/api/queries/7/feedback": () => jsonResponse({ ...RECORD, helpful: true }),
    "/api/sessions/active": () => jsonResponse(SESSION),
    "/api/sessions?customer_id=1&limit=20": () => jsonResponse(SUMMARIES),
    ...overrides,
  };
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const handler = routes[url];
    if (!handler) throw new Error(`unexpected fetch ${url}`);
    return handler(url, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// In-memory localStorage (this test environment doesn't provide one).
let store: Record<string, string> = {};
beforeEach(() => {
  store = {};
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => void (store[k] = v),
    removeItem: (k: string) => void delete store[k],
    clear: () => void (store = {}),
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AnswerText", () => {
  it("turns [n] markers into source links and drops out-of-range ones", () => {
    render(<AnswerText text="A [1]. B [2]. C [9]." citeIdPrefix="q1-cite" citationCount={2} />);
    const links = screen.getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["#q1-cite-1", "#q1-cite-2"]);
    expect(screen.queryByText("9")).toBeNull();
  });
});

describe("App", () => {
  it("shows sample questions and a connected status", async () => {
    mockBackend();
    render(<App />);
    expect(screen.getByRole("button", { name: /grease the conveyor bearings/ })).toBeTruthy();
    await waitFor(() => expect(screen.getByRole("img", { name: "Connected" })).toBeTruthy());
  });

  it("asks a typed question and renders the answer, sources and flags", async () => {
    const fetchMock = mockBackend();
    render(<App />);
    await screen.findByText("sess1111");
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "  How often do we grease CV-3?  " } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    const card = await screen.findByRole("article", { name: "Answer" });
    const askCall = fetchMock.mock.calls.find(([u]) => u === "/api/ask")!;
    expect(JSON.parse(askCall[1]!.body as string)).toEqual({
      question: "How often do we grease CV-3?",
      session_id: "sess1111aaaa",
      customer_id: "1",
    });

    expect(within(card).getByText("Answered")).toBeTruthy();
    expect(within(card).getByText("Maintenance")).toBeTruthy();
    expect(within(card).getByText("Safety")).toBeTruthy();
    const sources = within(card).getByRole("region", { name: "Sources" });
    expect(within(sources).getByText("MM-100 §4.1")).toBeTruthy();
    expect(within(sources).getByText(/pp\. 3-4/)).toBeTruthy();
    expect(within(card).getByRole("region", { name: "Check before acting" })).toBeTruthy();
  });

  it("asks a sample question when tapped", async () => {
    mockBackend();
    render(<App />);
    await screen.findByText("sess1111");
    fireEvent.click(screen.getByRole("button", { name: /grease the conveyor bearings/ }));
    expect(await screen.findByRole("article", { name: "Answer" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /grease the conveyor bearings/ })).toBeNull();
  });

  it("shows the backend error when an answer fails", async () => {
    mockBackend({ "/api/ask": () => jsonResponse({ detail: "Chat request failed: timeout" }, 503) });
    render(<App />);
    await screen.findByText("sess1111");
    fireEvent.click(screen.getByRole("button", { name: /grease the conveyor bearings/ }));
    expect((await screen.findByText(/Chat request failed: timeout/)).textContent).toBeTruthy();
  });

  it("warns when the server can't be reached", async () => {
    mockBackend({ "/api/health": () => Promise.reject(new TypeError("Failed to fetch")) });
    render(<App />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/Can't reach the server/);
  });

  it("sends feedback", async () => {
    const fetchMock = mockBackend();
    render(<App />);
    await screen.findByText("sess1111");
    fireEvent.click(screen.getByRole("button", { name: /grease the conveyor bearings/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Helpful" }));
    await screen.findByText("Thanks for the feedback");
    expect(fetchMock.mock.calls.some(([u]) => u === "/api/queries/7/feedback")).toBe(true);
  });

  it("lists past questions on the History tab and expands one", async () => {
    mockBackend();
    render(<App />);
    fireEvent.click(screen.getByRole("tab", { name: "History" }));
    const row = await screen.findByRole("button", { name: /grease the conveyor bearings/ });
    fireEvent.click(row);
    expect(await screen.findByRole("article", { name: "Answer" })).toBeTruthy();
  });

  it("holds questions until the session has loaded", () => {
    mockBackend({ "/api/sessions/active": () => new Promise(() => {}) });
    render(<App />);
    expect(screen.getByRole("button", { name: /grease the conveyor bearings/ }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Loading session…")).toBeTruthy();
  });

  it("restores the active session's conversation on load", async () => {
    const fetchMock = mockBackend({ "/api/sessions/active": () => jsonResponse(OLD_SESSION) });
    render(<App />);
    expect(await screen.findByText("What PPE for the solvent tank?")).toBeTruthy();
    const card = screen.getByRole("article", { name: "Answer" });
    expect(within(card).getByText(/respirator and nitrile gloves/)).toBeTruthy();
    expect(within(card).getByText("EHS-SOP-001 §5.3")).toBeTruthy();
    const body = JSON.parse(fetchMock.mock.calls.find(([u]) => u === "/api/sessions/active")![1]!.body as string);
    expect(body).toEqual({ customer_id: "1" });
  });

  it("ends the session and starts a blank one", async () => {
    let active = OLD_SESSION;
    const fetchMock = mockBackend({
      "/api/sessions/active": () => jsonResponse(active),
      "/api/sessions/sess0000old0/close": () => {
        active = { ...SESSION, session_id: "sess2222new0", created: true };
        return jsonResponse({ ...OLD_SESSION, status: "closed" });
      },
    });
    render(<App />);
    await screen.findByText("What PPE for the solvent tank?");
    fireEvent.click(screen.getByRole("button", { name: "End session" }));
    expect(await screen.findByText("sess2222")).toBeTruthy();
    expect(screen.queryByText("What PPE for the solvent tank?")).toBeNull();
    expect(screen.getByRole("heading", { name: "Ask the plant documentation" })).toBeTruthy();
    expect(fetchMock.mock.calls.some(([u]) => u === "/api/sessions/sess0000old0/close")).toBe(true);
  });

  it("switches customer and remembers the ID", async () => {
    const fetchMock = mockBackend();
    render(<App />);
    await screen.findByText("sess1111");
    const field = screen.getByLabelText("Customer ID");
    fireEvent.change(field, { target: { value: "42" } });
    fireEvent.blur(field);
    await waitFor(() => {
      const calls = fetchMock.mock.calls.filter(([u]) => u === "/api/sessions/active");
      expect(JSON.parse(calls[calls.length - 1][1]!.body as string)).toEqual({ customer_id: "42" });
    });
    expect(localStorage.getItem("pom.customerId")).toBe("42");
  });

  it("rejects a customer ID that looks like an email", async () => {
    const fetchMock = mockBackend();
    render(<App />);
    await screen.findByText("sess1111");
    const field = screen.getByLabelText("Customer ID");
    fireEvent.change(field, { target: { value: "bob@plant.com" } });
    fireEvent.blur(field);
    expect(screen.getByText(/no names or emails/)).toBeTruthy();
    expect(fetchMock.mock.calls.filter(([u]) => u === "/api/sessions/active")).toHaveLength(1);
  });

  it("lists sessions on the History tab and resumes an earlier one", async () => {
    const fetchMock = mockBackend({ "/api/sessions/sess0000old0/resume": () => jsonResponse(OLD_SESSION) });
    render(<App />);
    await screen.findByText("sess1111");
    fireEvent.click(screen.getByRole("tab", { name: "History" }));
    expect(await screen.findByText("Current")).toBeTruthy();
    expect(screen.getByText("Ended")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Resume" }));

    expect(await screen.findByText("What PPE for the solvent tank?")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Ask" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("sess0000")).toBeTruthy();
    const call = fetchMock.mock.calls.find(([u]) => u === "/api/sessions/sess0000old0/resume")!;
    expect(JSON.parse(call[1]!.body as string)).toEqual({ customer_id: "1" });
  });
});
