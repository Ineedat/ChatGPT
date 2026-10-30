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
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, json: async () => ({
        mode: "single-rule", preview_text: "client=[IP]", changed: true, input_chars: 17, output_chars: 13,
        rule_results: [{ rule_id: "ip", name: "IP", priority: 10, enabled: true, match_count: 1,
          matches: [{ start: 7, end: 18, value: "192.0.2.17", replacement: "[IP]", chained_from: [] }],
          matches_truncated: false, chained_match_count: 0 }],
        overlaps: [], overlaps_truncated: false
      })
    } as Response));
    render(<RuleTestPanel config={config} draft={draft} selectedId="ip" draftDirty={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Muster testen" }));
    expect(await screen.findByText("client=[IP]")).toBeInTheDocument();
    expect(screen.getByText("1 Treffer")).toBeInTheDocument();
  });

  it("includes a not-yet-saved draft when testing a single rule", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      mode: "single-rule", preview_text: "safe", changed: false, input_chars: 4, output_chars: 4,
      rule_results: [], overlaps: [], overlaps_truncated: false
    }) } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const changedDraft = { ...draft, id: "", name: "Draft", pattern: "demo" };
    render(<RuleTestPanel config={config} draft={changedDraft} selectedId="" draftDirty />);
    fireEvent.click(screen.getByRole("button", { name: "Muster testen" }));
    await screen.findByText("Keine Änderung");
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.rule_id).toBe("preview-draft");
    expect(body.config.rules.some((rule: { id: string }) => rule.id === "preview-draft")).toBe(true);
  });
});
