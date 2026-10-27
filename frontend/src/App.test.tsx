import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import App from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("LogSanitizer app shell", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => []
    }));
  });

  it("shows the development-only warning", async () => {
    render(<App />);
    expect(screen.getByText(/Noch nicht für echte Logdaten freigegeben/i)).toBeInTheDocument();
    await screen.findByText(/Noch keine Projekte vorhanden/);
  });

  it("offers local help topics", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Hilfe" }));
    expect(await screen.findByRole("heading", { name: "Hilfe und Grundlagen" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Erste Schritte" })).toBeInTheDocument();
  });

  it("creates a project and displays the persisted response", async () => {
    const project = {
      id: "project-1",
      name: "Testprojekt",
      description: "Testbeschreibung",
      status: "draft",
      created_at: "2026-10-27T10:00:00+00:00",
      updated_at: "2026-10-27T10:00:00+00:00"
    };
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [] } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => project } as Response);

    render(<App />);
    fireEvent.change(screen.getByRole("textbox", { name: "Projektname" }), { target: { value: "Testprojekt" } });
    fireEvent.change(screen.getByRole("textbox", { name: /Beschreibung/ }), { target: { value: "Testbeschreibung" } });
    fireEvent.click(screen.getByRole("button", { name: "Projekt anlegen" }));

    const openedProject = await screen.findByRole("region", { name: "Geöffnetes Projekt" });
    expect(within(openedProject).getByRole("heading", { name: "Testprojekt" })).toBeInTheDocument();
    expect(within(openedProject).getByText("Testbeschreibung")).toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/projects", expect.objectContaining({ method: "POST" })));
  });
});


describe("project file registration UI", () => {
  const project = {
    id: "project-logs",
    name: "Logprojekt",
    description: "",
    status: "draft",
    created_at: "2026-10-27T10:00:00+00:00",
    updated_at: "2026-10-27T10:00:00+00:00"
  };

  it("registers a single absolute path and displays returned metadata", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [project] } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => project } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => [] } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        id: "file-1", project_id: project.id, display_name: "service.log", size_bytes: 120,
        modified_at: "2026-10-27T10:00:00+00:00", imported_at: "2026-10-27T10:00:00+00:00", state: "registered"
      }) } as Response);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Öffnen" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "Absoluter Dateipfad" }), { target: { value: "/var/log/service.log" } });
    fireEvent.click(screen.getByRole("button", { name: "Datei registrieren" }));

    expect(await screen.findByText("Datei registriert. Der Inhalt wurde nicht verarbeitet.")).toBeInTheDocument();
    expect(await screen.findByText("service.log")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(`/api/projects/${project.id}/files`, expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ path: "/var/log/service.log" })
    }));
  });

  it("shows skipped folder-import entries without processing log contents", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [project] } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => project } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => [] } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        registered_count: 1,
        skipped_count: 1,
        registered_files: [{
          id: "file-2", project_id: project.id, display_name: "app.log", size_bytes: 64,
          modified_at: "2026-10-27T10:00:00+00:00", imported_at: "2026-10-27T10:00:00+00:00", state: "registered"
        }],
        issues: [{ file_name: "old.log", reason: "Bereits in diesem Projekt registriert." }],
        limit_reached: false
      }) } as Response);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Öffnen" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "Absoluter Ordnerpfad" }), { target: { value: "/var/log/my-service" } });
    fireEvent.click(screen.getByRole("button", { name: "Ordner registrieren" }));

    expect(await screen.findByText(/Registriert: 1; übersprungen: 1/)).toBeInTheDocument();
    expect(await screen.findByText(/old.log/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(`/api/projects/${project.id}/files/import-folder`, expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ path: "/var/log/my-service", recursive: true })
    }));
  });
});
