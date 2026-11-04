import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { RuleTestPanel } from "./RuleTestPanel";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const config = {
  schema_version: 1 as const, profiles: [],
  rules: [{
    id: "ip", name: "IP", category: "network", match_type: "plain" as const,
    pattern: "192.0.2.17", replacement: "[IP]", replacement_mode: "fixed" as const,
    mapping_prefix: null, case_sensitive: true, priority: 10, profile_id: null, enabled: true
  }]
};
const draft = { ...config.rules[0] };

describe("rule test preview", () => {
  it("submits the selected rule and displays the non-persistent preview", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((_input, init) => Promise.resolve({
      ok: true, json: async () => init?.method === "POST" ? ({
        mode: "single-rule", preview_text: "client=[IP]", changed: true, input_chars: 17, output_chars: 13,
        rule_results: [{ rule_id: "ip", name: "IP", priority: 10, enabled: true, match_count: 1,
          matches: [{ start: 7, end: 18, value: "192.0.2.17", replacement: "[IP]", chained_from: [] }],
          matches_truncated: false, chained_match_count: 0 }],
        overlaps: [], overlaps_truncated: false, conflicts: []
      }) : []
    } as Response)));
    render(<RuleTestPanel config={config} draft={draft} selectedId="ip" draftDirty={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Muster testen" }));
    expect(await screen.findByText("client=[IP]")).toBeInTheDocument();
    expect(screen.getByText("1 Treffer")).toBeInTheDocument();
  });

  it("includes a not-yet-saved draft when testing a single rule", async () => {
    const fetchMock = vi.fn().mockImplementation((_input, init) => Promise.resolve({ ok: true, json: async () => init?.method === "POST" ? ({
      mode: "single-rule", preview_text: "safe", changed: false, input_chars: 4, output_chars: 4,
      rule_results: [], overlaps: [], overlaps_truncated: false, conflicts: []
    }) : [] } as Response));
    vi.stubGlobal("fetch", fetchMock);
    const changedDraft = { ...draft, id: "", name: "Draft", pattern: "demo" };
    render(<RuleTestPanel config={config} draft={changedDraft} selectedId="" draftDirty />);
    fireEvent.click(screen.getByRole("button", { name: "Muster testen" }));
    await screen.findByText("Keine Änderung");
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    const body = JSON.parse(postCall?.[1].body as string);
    expect(body.rule_id).toBe("preview-draft");
    expect(body.config.rules.some((rule: { id: string }) => rule.id === "preview-draft")).toBe(true);
  });
});

  it("does not silently test the saved rule when the current draft is incomplete", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const invalidDraft = { ...draft, pattern: "" };
    render(<RuleTestPanel config={config} draft={invalidDraft} selectedId="ip" draftDirty />);
    fireEvent.click(screen.getByRole("button", { name: "Muster testen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Regelentwurf ist unvollständig");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });


it("loads a registered file into synchronized original and sanitized panes", async () => {
  const preview = {
    mode: "enabled-rules", preview_text: "client=[IP]\n", original_text: "client=192.0.2.17\n",
    changed: true, input_chars: 18, output_chars: 13, source_offset: 0, next_offset: 18,
    total_bytes: 18, has_previous: false, has_next: false, window_chars: 18,
    rule_results: [{ rule_id: "ip", name: "IP", priority: 10, enabled: true, match_count: 1,
      matches: [{ start: 7, end: 17, value: "192.0.2.17", replacement: "[IP]", chained_from: [] }],
      matches_truncated: false, chained_match_count: 0 }],
    overlaps: [], overlaps_truncated: false, conflicts: []
  };
  const fetchMock = vi.fn().mockImplementation((input, init) => {
    const url = String(input);
    const payload = url === "/api/projects" ? [{ id: "project-1", name: "Demo" }]
      : url.endsWith("/files") ? [{ id: "file-1", display_name: "application.log", size_bytes: 18, detected_format: "text" }]
      : preview;
    return Promise.resolve({ ok: true, json: async () => init?.method === "POST" ? preview : payload } as Response);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<RuleTestPanel config={config} draft={draft} selectedId="ip" draftDirty={false} />);
  await screen.findByRole("option", { name: /application.log/ });
  fireEvent.click(screen.getByRole("button", { name: "Anfang" }));
  expect(await screen.findByText("Original")).toBeInTheDocument();
  expect(screen.getByText("Bereinigte Vorschau")).toBeInTheDocument();
  expect(screen.getByText("192.0.2.17")).toHaveClass("rule-file-hit");
  expect(screen.getByText("[IP]")).toHaveClass("rule-file-replacement");
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/files/file-1/preview"))).toBe(true);
});
