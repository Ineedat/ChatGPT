import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ReviewPanel } from "./ReviewPanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const run = {
  id: "run-1",
  project_id: "project-1",
  file_id: "file-1",
  display_name: "app.log",
  output_name: "clean-app.log",
  status: "pending_review",
  actor_username: "operator",
  parent_run_id: null,
  created_at: "2026-10-28T10:00:00+00:00",
  completed_at: "2026-10-28T10:01:00+00:00",
  input_bytes: 100,
  output_bytes: 80,
  lines_processed: 2,
  replacements: 1,
  validated: 1,
  residual_matches: 0,
  last_comment: "",
  exception_reason: ""
};

function stubReviewFetch() {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/reviews/runs?limit=100") return { ok: true, json: async () => [run] } as Response;
    if (url === "/api/reviews/queue") return { ok: true, json: async () => [run] } as Response;
    if (url === "/api/reviews/saved-searches") return { ok: true, json: async () => [] } as Response;
    if (url === "/api/reviews/audit?limit=50") return { ok: true, json: async () => [] } as Response;
    if (url.includes("/search?")) return { ok: true, json: async () => ({ query: "REDACTED", match_count: 1, truncated: false, results: [{ line_number: 2, snippet: "token=REDACTED" }] }) } as Response;
    if (url.endsWith("/approve")) return { ok: true, json: async () => ({ status: "approved" }) } as Response;
    return { ok: true, json: async () => ({}) } as Response;
  }));
}

describe("review workflow UI", () => {
  it("shows a pending run and searches the sanitized output", async () => {
    stubReviewFetch();
    render(<ReviewPanel roles={["reviewer"]} />);
    fireEvent.click(await screen.findByRole("button", { name: "Prüfen" }));
    fireEvent.change(screen.getByRole("textbox", { name: /Suchbegriff/ }), { target: { value: "REDACTED" } });
    fireEvent.click(screen.getByRole("button", { name: "Ausgabe durchsuchen" }));
    expect(await screen.findByText("token=REDACTED")).toBeInTheDocument();
    expect(screen.getByText("Zeile 2")).toBeInTheDocument();
  });


  it("supports regex searches and persists the selected search mode", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/reviews/runs?limit=100") return { ok: true, json: async () => [run] } as Response;
      if (url === "/api/reviews/queue") return { ok: true, json: async () => [run] } as Response;
      if ((url === "/api/reviews/saved-searches" && init?.method !== "POST") || url === "/api/reviews/audit?limit=50") return { ok: true, json: async () => [] } as Response;
      if (url.includes("/search?")) return { ok: true, json: async () => ({ query: "token\\s*=.*", match_type: "regex", match_count: 1, truncated: false, results: [{ line_number: 2, snippet: "token=REDACTED" }] }) } as Response;
      if (url === "/api/reviews/saved-searches" && init?.method === "POST") return { ok: true, json: async () => ({ id: "saved-1" }) } as Response;
      return { ok: true, json: async () => [] } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ReviewPanel roles={["reviewer"]} />);
    fireEvent.click(await screen.findByRole("button", { name: "Prüfen" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Suchart" }), { target: { value: "regex" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Suchbegriff" }), { target: { value: "token\\s*=.*" } });
    fireEvent.click(screen.getByRole("button", { name: "Ausgabe durchsuchen" }));
    expect(await screen.findByText("token=REDACTED")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reviews/runs/run-1/search?q=token%5Cs*%3D.*&match_type=regex",
      expect.anything()
    );
    fireEvent.change(screen.getByRole("textbox", { name: /Name für eigenes Suchmuster/ }), { target: { value: "Token regex" } });
    fireEvent.click(screen.getByRole("button", { name: "Suchmuster speichern" }));
    expect(fetchMock).toHaveBeenCalledWith("/api/reviews/saved-searches", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ name: "Token regex", query: "token\\s*=.*", match_type: "regex" })
    }));
  });

  it("submits an explicit approval decision", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/reviews/runs?limit=100") return { ok: true, json: async () => [run] } as Response;
      if (url === "/api/reviews/queue") return { ok: true, json: async () => [run] } as Response;
      if (url === "/api/reviews/saved-searches" || url === "/api/reviews/audit?limit=50") return { ok: true, json: async () => [] } as Response;
      if (url.endsWith("/approve")) return { ok: true, json: async () => ({ status: "approved" }) } as Response;
      return { ok: true, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ReviewPanel roles={["approver"]} />);
    fireEvent.click(await screen.findByRole("button", { name: "Prüfen" }));
    fireEvent.change(screen.getByRole("textbox", { name: /Kommentar/ }), { target: { value: "Stichprobe geprüft" } });
    fireEvent.click(screen.getByRole("button", { name: "Freigeben" }));
    expect(await screen.findByText(/Prüfentscheidung gespeichert: approved/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/reviews/runs/run-1/approve", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ comment: "Stichprobe geprüft", exception: false, exception_reason: "" })
    }));
  });

  it("does not show reviewer controls to an operator", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/reviews/runs?limit=100") return { ok: true, json: async () => [run] } as Response;
      return { ok: false, json: async () => ({ detail: "Forbidden" }) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ReviewPanel roles={["operator"]} />);
    expect(await screen.findByText(/Laufhistorie/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Warteschlange/ })).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith("/api/reviews/queue", expect.anything());
  });

  it("loads source profiles and reuses the selected profile for a returned run", async () => {
    const returnedRun = { ...run, status: "returned" };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/reviews/runs?limit=100") return { ok: true, json: async () => [returnedRun] } as Response;
      if (url === "/api/reviews/queue") return { ok: true, json: async () => [] } as Response;
      if (url === "/api/reviews/saved-searches" || url === "/api/reviews/audit?limit=50") return { ok: true, json: async () => [] } as Response;
      if (url === "/api/rules/config") return { ok: true, json: async () => ({ profiles: [{ id: "nginx", name: "Nginx" }] }) } as Response;
      if (url.endsWith("/sanitize-jobs") && init?.method === "POST") return { ok: true, json: async () => ({ id: "retry-job" }) } as Response;
      return { ok: true, json: async () => [returnedRun] } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ReviewPanel roles={["operator"]} />);
    fireEvent.click(await screen.findByRole("button", { name: "Details" }));
    const profileSelect = await screen.findByRole("combobox", { name: "Quellprofil für die Überarbeitung" });
    expect(await screen.findByRole("option", { name: "Nginx" })).toBeInTheDocument();
    fireEvent.change(profileSelect, { target: { value: "nginx" } });
    fireEvent.change(screen.getByRole("textbox", { name: /Neuer absoluter Ausgabepfad/ }), {
      target: { value: "/tmp/clean-app-reworked.log" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Erneut bereinigen" }));
    expect(await screen.findByText(/Überarbeitete Bereinigung wurde gestartet/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/files/file-1/sanitize-jobs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          output_path: "/tmp/clean-app-reworked.log",
          retry_of_run_id: "run-1",
          profile_id: "nginx"
        })
      })
    );
  });

  it("filters run history and navigates between a returned run and its rework", async () => {
    const child = { ...run, id: "run-2", display_name: "app-reworked.log", output_name: "clean-app-reworked.log", status: "returned", parent_run_id: "run-1" };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/reviews/runs?limit=100") return { ok: true, json: async () => [child, run] } as Response;
      if (url === "/api/reviews/queue") return { ok: true, json: async () => [run] } as Response;
      if (url === "/api/reviews/saved-searches" || url === "/api/reviews/audit?limit=50") return { ok: true, json: async () => [] } as Response;
      return { ok: true, json: async () => [] } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ReviewPanel roles={["operator"]} />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Details" }))[1]);
    expect(await screen.findByRole("button", { name: /app-reworked.log.*returned/ })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Suche in Läufen" }), { target: { value: "app-reworked" } });
    expect(screen.getByText("Laufhistorie (1 von 2)")).toBeInTheDocument();
    expect(screen.getByText("app-reworked.log")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "returned" } });
    expect(screen.getByText("Laufhistorie (1 von 2)")).toBeInTheDocument();
  });

});
