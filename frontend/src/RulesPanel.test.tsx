import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RulesPanel } from "./RulesPanel";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const initialConfig = {
  schema_version: 1 as const,
  profiles: [{ id: "nginx", name: "Nginx", source_hint: "nginx" }],
  rules: [{
    id: "ipv4", name: "IPv4-Adressen", category: "IP-Adresse", match_type: "regex" as const,
    pattern: String.raw`\b(?:\d{1,3}\.){3}\d{1,3}\b`, replacement: "[IP_1]",
    replacement_mode: "indexed" as const, mapping_prefix: "IP", case_sensitive: false,
    priority: 10, profile_id: null, enabled: true
  }]
};

describe("rule editor", () => {
  it("loads rules and exposes profile scope as a selection", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => initialConfig } as Response));
    render(<RulesPanel />);
    expect(await screen.findByText("IPv4-Adressen")).toBeInTheDocument();
    expect(screen.getByLabelText("Geltungsbereich")).toHaveValue("");
    expect(screen.getByRole("option", { name: "Nginx" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Konfiguration speichern" })).toBeDisabled();
  });

  it("creates a rule, validates conflicts and persists the complete configuration", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ schema_version: 1, profiles: [], rules: [] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ valid: true, conflicts: [] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ schema_version: 1, profiles: [], rules: [{
        id: "mail-adresse", name: "Mail-Adresse", category: "E-Mail-Adresse", match_type: "plain",
        pattern: "alice@example.test", replacement: "[EMAIL]", replacement_mode: "fixed",
        mapping_prefix: null, case_sensitive: false, priority: 100, profile_id: null, enabled: true
      }] }) } as Response);
    vi.stubGlobal("fetch", fetchMock);
    render(<RulesPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Neue Regel" }));
    fireEvent.change(screen.getByLabelText("Regelname"), { target: { value: "Mail-Adresse" } });
    fireEvent.change(screen.getByLabelText("Kategorie"), { target: { value: "E-Mail-Adresse" } });
    fireEvent.change(screen.getByLabelText("Suchart"), { target: { value: "plain" } });
    fireEvent.change(screen.getByLabelText("Suchmuster"), { target: { value: "alice@example.test" } });
    fireEvent.change(screen.getByLabelText("Ersetzung"), { target: { value: "[EMAIL]" } });
    fireEvent.click(screen.getByRole("button", { name: "Regel übernehmen" }));
    fireEvent.click(screen.getByRole("button", { name: "Konfiguration speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/rules/config/validate", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/rules/config", expect.objectContaining({ method: "PUT" }));
    expect(await screen.findByText("Regelkonfiguration wurde lokal gespeichert.")).toBeInTheDocument();
  });
});
