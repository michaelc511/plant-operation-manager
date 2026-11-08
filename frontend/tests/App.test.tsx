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
    await screen.findByText("Ticket #1002");
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
    await screen.findByText("Ticket #1002");
    fireEvent.click(screen.getByRole("button", { name: /grease the conveyor bearings/ }));
    expect(await screen.findByRole("article", { name: "Answer" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /grease the conveyor bearings/ })).toBeNull();
  });

  it("shows the backend error when an answer fails", async () => {
    mockBackend({ "/api/ask": () => jsonResponse({ detail: "Chat request failed: timeout" }, 503) });
    render(<App />);
    await screen.findByText("Ticket #1002");
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
    await screen.findByText("Ticket #1002");
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
    expect(screen.getByText("Loading ticket…")).toBeTruthy();
  });

  it("restores the active session's conversation on load", async () => {
    const fetchMock = mockBackend({ "/api/sessions/active": () => jsonResponse(OLD_SESSION) });
    render(<App />);
    expect(await screen.findByText("What PPE for the solvent tank?")).toBeTruthy();
    const card = screen.getByRole("article", { name: "Answer" });
    expect(within(card).getByText(/respirator and nitrile gloves/)).toBeTruthy();
    expect(within(card).getByText("EHS-SOP-001 §5.3")).toBeTruthy();
    const body = JSON.parse(fetchMock.mock.calls.find(([u]) => u === "/api/sessions/active")![1]!.body as string);
    expect(body).toEqual({ customer_id: "1", create: false }); // load never creates a ticket
  });

  it("closes the ticket, leaves none open, and New ticket opens a blank one", async () => {
    const fetchMock = mockBackend({
      "/api/sessions/active": () => jsonResponse(OLD_SESSION),
      "/api/sessions/sess0000old0/close": () => jsonResponse({ ...OLD_SESSION, status: "closed", state: "closed" }),
      "/api/sessions/new": () => jsonResponse({ ...SESSION, session_id: "sess2222new0", ticket_no: 1003, created: true }),
    });
    render(<App />);
    await screen.findByText("What PPE for the solvent tank?");
    fireEvent.click(screen.getByRole("button", { name: "Close ticket" }));
    expect(await screen.findByText(/No open ticket/)).toBeTruthy();
    expect(screen.queryByText("What PPE for the solvent tank?")).toBeNull();
    expect(screen.queryByRole("button", { name: "Close ticket" })).toBeNull();
    expect(fetchMock.mock.calls.filter(([u]) => u === "/api/sessions/active")).toHaveLength(1); // no auto-create

    fireEvent.click(screen.getByRole("button", { name: "New ticket" }));
    expect(await screen.findByText("Ticket #1003")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Ask the plant documentation" })).toBeTruthy();
    const call = fetchMock.mock.calls.find(([u]) => u === "/api/sessions/new")!;
    expect(JSON.parse(call[1]!.body as string)).toEqual({ customer_id: "1" });
  });

  it("asking with no open ticket opens one from the answer", async () => {
    mockBackend({ "/api/sessions/active": () => jsonResponse(null) });
    render(<App />);
    await screen.findByText(/No open ticket/);
    fireEvent.click(screen.getByRole("button", { name: /grease the conveyor bearings/ }));
    expect(await screen.findByText("Ticket #1002")).toBeTruthy(); // ANSWER.ticket_no
    expect(screen.getByText("Open")).toBeTruthy();
  });

  it("shows the demo customer, the open ticket and no session ID", async () => {
    mockBackend();
    render(<App />);
    await screen.findByText("Ticket #1002");
    const card = screen.getByLabelText("Customer");
    expect(within(card).getByText("Carl Wayne")).toBeTruthy();
    expect(screen.getByText("Ticket #1002")).toBeTruthy();
    expect(screen.getByText("Open")).toBeTruthy();
    expect(screen.queryByText(/sess1111/)).toBeNull(); // no raw session ID on screen
    expect((screen.getByLabelText("Customer ID") as HTMLInputElement).value).toBe("1");
  });

  it("shows the customer ID read-only and always uses Carl's ID", async () => {
    const fetchMock = mockBackend({
      "/api/sessions/new": () => jsonResponse({ ...SESSION, session_id: "sess2222new0", ticket_no: 1003, created: true }),
    });
    render(<App />);
    await screen.findByText("Ticket #1002");
    const field = screen.getByLabelText("Customer ID") as HTMLInputElement;
    expect(field.readOnly).toBe(true);
    fireEvent.change(field, { target: { value: "42" } });
    fireEvent.click(screen.getByRole("button", { name: "New ticket" }));
    expect(await screen.findByText("Ticket #1003")).toBeTruthy();
    for (const [u, init] of fetchMock.mock.calls)
      if (String(u).startsWith("/api/sessions/")) expect(JSON.parse(init!.body as string).customer_id).toBe("1");
    expect(within(screen.getByLabelText("Customer")).getByText("Carl Wayne")).toBeTruthy();
  });

  it("lists the other tickets with their state on the History tab and reopens one", async () => {
    const fetchMock = mockBackend({
      "/api/sessions/sess0000old0/resume": () => jsonResponse({ ...OLD_SESSION, status: "active", state: "open" }),
    });
    render(<App />);
    await screen.findByText("Ticket #1002");
    fireEvent.click(screen.getByRole("tab", { name: "History" }));
    const list = within(await screen.findByRole("region", { name: /Ticket history/ }));
    expect(await list.findByText("#1001")).toBeTruthy();
    expect(list.getByText("On hold")).toBeTruthy();
    expect(list.queryByText("#1002")).toBeNull(); // the open ticket stays on the Ask tab
    fireEvent.click(list.getByRole("button", { name: "Reopen" }));

    expect(await screen.findByText("What PPE for the solvent tank?")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Ask" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("Ticket #1001")).toBeTruthy();
    const call = fetchMock.mock.calls.find(([u]) => u === "/api/sessions/sess0000old0/resume")!;
    expect(JSON.parse(call[1]!.body as string)).toEqual({ customer_id: "1" });
  });
});
