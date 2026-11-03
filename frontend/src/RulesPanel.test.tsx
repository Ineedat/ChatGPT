import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RulesPanel } from "./RulesPanel";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

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

  it("validates an imported JSON file before staging it and exports the active draft", async () => {
    const config = { schema_version: 1, profiles: [], rules: [] };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => config } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ valid: true, conflicts: [] }) } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const NativeURL = globalThis.URL;
    const createUrl = vi.fn(() => "blob:rules-export");
    const revokeUrl = vi.fn();
    class MockURL extends NativeURL {}
    Object.assign(MockURL, { createObjectURL: createUrl, revokeObjectURL: revokeUrl });
    vi.stubGlobal("URL", MockURL);
    render(<RulesPanel />);
    await screen.findByRole("button", { name: "JSON importieren" });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(fileInput).toBeTruthy();
    const file = new File(["{}"], "rules.json", { type: "application/json" });
    Object.defineProperty(file, "text", { value: async () => JSON.stringify(config) });
    fireEvent.change(fileInput, { target: { files: [file] } });
    expect(await screen.findByText(/Importvorschau: rules.json/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/rules/config/validate", expect.objectContaining({ method: "POST" }));
    expect(screen.getByRole("button", { name: "In Entwurf übernehmen" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "In Entwurf übernehmen" }));
    expect(await screen.findByText(/Import übernommen und als ungespeicherter Entwurf/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "JSON exportieren" }));
    expect(createUrl).toHaveBeenCalledTimes(1);
    expect(revokeUrl).toHaveBeenCalledWith("blob:rules-export");
  });

  it("adds a categorized library template as a disabled editable rule", async () => {
    const library = {
      categories: [{ name: "IP-Adresse", description: "IPv4 und IPv6", template_count: 1 }],
      templates: [{
        id: "ipv4-addresses", name: "IPv4-Adressen", category: "IP-Adresse",
        description: "Erkennt IPv4-Adressen.", pattern: String.raw`(?<![\\w.])(?:25[0-5]\\.){3}25[0-5](?![\\w.])`,
        mapping_prefix: "IP", priority: 100, example_before: "client=192.0.2.17",
        example_after: "client=[IP_1]", notes: "Synthetisches Beispiel.",
        match_type: "regex", replacement: "", replacement_mode: "indexed",
        case_sensitive: false, enabled: false, profile_id: null
      }]
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ schema_version: 1, profiles: [], rules: [] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => library } as Response);
    vi.stubGlobal("fetch", fetchMock);
    render(<RulesPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Vorlagenbibliothek" }));
    expect(await screen.findByText("IPv4-Adressen")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Vorlage übernehmen" }));
    expect(await screen.findByLabelText("Regelname")).toHaveValue("IPv4-Adressen");
    expect(screen.getByLabelText("Regel aktiviert")).not.toBeChecked();
    expect(screen.getByLabelText("Platzhalter-Präfix")).toHaveValue("IP");
    expect(screen.getByRole("button", { name: "Konfiguration speichern" })).toBeEnabled();
  });

  it("discards an uncommitted rule draft before allowing source-profile creation", async () => {
    let saved = { ...initialConfig, profiles: [] as { id: string; name: string; source_hint: string | null }[] };
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/rules/config" && init?.method !== "PUT") return { ok: true, json: async () => saved } as Response;
      if (url === "/api/rules/config/validate") return { ok: true, json: async () => ({ valid: true, conflicts: [] }) } as Response;
      if (url === "/api/rules/config" && init?.method === "PUT") {
        saved = JSON.parse(String(init.body));
        return { ok: true, json: async () => saved } as Response;
      }
      return { ok: true, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<RulesPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Neue Regel" }));
    fireEvent.change(screen.getByLabelText("Regelname"), { target: { value: "Noch nicht übernommene Regel" } });
    fireEvent.click(screen.getByRole("button", { name: /Quellprofile/ }));
    expect(confirm).toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Profilname"), { target: { value: "Webserver" } });
    fireEvent.click(screen.getByRole("button", { name: "Profil speichern" }));
    expect(await screen.findByText(/Quellprofil „Webserver“ wurde gespeichert/)).toBeInTheDocument();
    expect(saved.profiles).toHaveLength(1);
    expect(saved.profiles[0].name).toBe("Webserver");
    expect(saved.rules).toHaveLength(1);
    expect(saved.rules[0].id).toBe("ipv4");
    expect(fetchMock).toHaveBeenCalledWith("/api/rules/config", expect.objectContaining({ method: "PUT" }));
  });

});

  it("creates and edits source profiles with immediate persistence", async () => {
    let saved = { ...initialConfig, profiles: [] as { id: string; name: string; source_hint: string | null }[] };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/rules/config" && init?.method !== "PUT") return { ok: true, json: async () => saved } as Response;
      if (url === "/api/rules/config/validate") return { ok: true, json: async () => ({ valid: true, conflicts: [] }) } as Response;
      if (url === "/api/rules/config" && init?.method === "PUT") {
        saved = JSON.parse(String(init.body));
        return { ok: true, json: async () => saved } as Response;
      }
      return { ok: true, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<RulesPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /Quellprofile/ }));
    fireEvent.change(screen.getByLabelText("Profilname"), { target: { value: "Apache" } });
    fireEvent.change(screen.getByLabelText("Quellhinweis (optional)"), { target: { value: "httpd" } });
    fireEvent.click(screen.getByRole("button", { name: "Profil speichern" }));
    expect(await screen.findByText(/Quellprofil „Apache“ wurde gespeichert/)).toBeInTheDocument();
    expect(saved.profiles).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    fireEvent.change(screen.getByLabelText("Profilname"), { target: { value: "Apache Webserver" } });
    fireEvent.click(screen.getByRole("button", { name: "Profil speichern" }));
    expect(await screen.findByText(/Quellprofil „Apache Webserver“ wurde gespeichert/)).toBeInTheDocument();
    expect(saved.profiles[0].name).toBe("Apache Webserver");
    fireEvent.click(screen.getByRole("button", { name: "Löschen" }));
    expect(await screen.findByText("Quellprofil wurde gelöscht.")).toBeInTheDocument();
    expect(saved.profiles).toHaveLength(0);
    expect(confirm).toHaveBeenCalledWith("Quellprofil „Apache Webserver“ wirklich löschen?");
  });


it("prevents deleting a source profile that is still referenced by a rule", async () => {
  const saved = {
    ...initialConfig,
    rules: initialConfig.rules.map(rule => ({ ...rule, profile_id: "nginx" }))
  };
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/rules/config" && init?.method !== "PUT") return { ok: true, json: async () => saved } as Response;
    if (url === "/api/rules/config/validate") return { ok: true, json: async () => ({ valid: true, conflicts: [] }) } as Response;
    return { ok: true, json: async () => saved } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<RulesPanel />);
  fireEvent.click(await screen.findByRole("button", { name: /Quellprofile/ }));
  fireEvent.click(screen.getByRole("button", { name: "Löschen" }));
  expect(await screen.findByText(/Das Profil wird noch von Regeln verwendet/)).toBeInTheDocument();
  expect(confirm).not.toHaveBeenCalled();
  expect(fetchMock).not.toHaveBeenCalledWith("/api/rules/config", expect.objectContaining({ method: "PUT" }));
  expect(saved.profiles).toHaveLength(1);
});
