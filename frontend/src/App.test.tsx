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
