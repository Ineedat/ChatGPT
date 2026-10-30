import { useState } from "react";

type Rule = {
  id: string; name: string; category: string; match_type: "plain" | "regex";
  pattern: string; replacement: string; replacement_mode: "fixed" | "indexed";
  mapping_prefix?: string | null; case_sensitive: boolean; priority: number;
  profile_id?: string | null; enabled: boolean;
};
type Profile = { id: string; name: string; source_hint?: string | null };
type Config = { schema_version: 1; profiles: Profile[]; rules: Rule[] };
type Match = { start: number; end: number; value: string; replacement: string; chained_from: string[] };
type Preview = {
  mode: string; preview_text: string; changed: boolean; input_chars: number; output_chars: number;
  rule_results: { rule_id: string; name: string; priority: number; enabled: boolean; match_count: number;
    matches: Match[]; matches_truncated: boolean; chained_match_count: number }[];
  overlaps: { first_rule_id: string; second_rule_id: string; start: number; end: number; example: string }[];
  overlaps_truncated: boolean;
  conflicts: { rule_id: string; conflicts_with: string; reason: string }[];
};
type Props = { config: Config; draft: Rule; selectedId: string; draftDirty: boolean };

async function requestPreview(payload: object) {
  const csrf = document.cookie.split("; ").find(item => item.startsWith("logsanitizer_csrf="))?.split("=").slice(1).join("=");
  const headers = new Headers({ "Content-Type": "application/json" });
  if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  return fetch("/api/rules/preview", { method: "POST", headers, credentials: "same-origin", body: JSON.stringify(payload) });
}

export function RuleTestPanel({ config, draft, selectedId, draftDirty }: Props) {
  const [sample, setSample] = useState("client=192.0.2.17 user=alice@example.test token=demo-token");
  const [profileId, setProfileId] = useState("");
  const [mode, setMode] = useState<"single" | "all">("single");
  const [result, setResult] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);

  async function runPreview() {
    setRunning(true); setError(""); setResult(null);
    if (draftDirty && (!draft.name.trim() || !draft.pattern.trim() || !draft.replacement.trim())) {
      setError("Der aktuelle Regelentwurf ist unvollständig. Ergänze Name, Suchmuster und Ersetzung vor dem Test.");
      setRunning(false);
      return;
    }
    const previewConfig = { ...config, rules: [...config.rules] };
    let testRuleId: string | null = null;
    if (draftDirty && draft.name.trim() && draft.pattern.trim() && draft.replacement.trim()) {
      const draftId = selectedId || "preview-draft";
      const draftRule = { ...draft, id: draftId, profile_id: draft.profile_id || null,
        mapping_prefix: draft.replacement_mode === "indexed" ? (draft.mapping_prefix || "VALUE") : null };
      const existing = previewConfig.rules.findIndex(rule => rule.id === draftId);
      if (existing >= 0) previewConfig.rules[existing] = draftRule;
      else previewConfig.rules.push(draftRule);
      if (mode === "single") testRuleId = draftId;
    } else if (mode === "single") {
      testRuleId = selectedId || null;
    }
    if (mode === "single" && !testRuleId) {
      setError("Bitte zuerst eine Regel auswählen oder einen vollständigen Regelentwurf eingeben.");
      setRunning(false);
      return;
    }
    try {
      const response = await requestPreview({ config: previewConfig, sample_text: sample, profile_id: profileId || null, rule_id: mode === "single" ? testRuleId : null });
      const body = await response.json() as Preview & { detail?: string | { msg?: string }[] };
      if (!response.ok) {
        const detail = typeof body.detail === "string" ? body.detail : Array.isArray(body.detail) ? body.detail.map(item => item.msg).join("; ") : "Die Vorschau konnte nicht erstellt werden.";
        throw new Error(detail);
      }
      setResult(body);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Die Vorschau konnte nicht erstellt werden.");
    } finally { setRunning(false); }
  }

  return <section className="rule-test-workspace">
    <div className="rule-test-input">
      <div className="rules-list-heading"><h3>Regeltest und Bereinigungsvorschau</h3><span className="field-help">Nur Beispieldaten · keine Dateiänderung</span></div>
      <p className="muted-message">Teste eine einzelne Regel – auch wenn sie noch deaktiviert ist – oder simuliere alle aktiven Regeln in Prioritätsreihenfolge. Die Vorschau schreibt keine Projekt-Mappings.</p>
      <label>Testmodus<select value={mode} onChange={event => setMode(event.target.value as "single" | "all")}><option value="single">Ausgewählte Regel</option><option value="all">Alle aktiven Regeln</option></select></label>
      <label>Quellprofil<select value={profileId} onChange={event => setProfileId(event.target.value)}><option value="">Kein Profil / nur globale Regeln</option>{config.profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</select></label>
      <label>Beispieltext<textarea value={sample} onChange={event => setSample(event.target.value)} maxLength={65536} rows={7} spellCheck={false} /></label>
      <div className="rule-test-footer"><span className="field-help">{sample.length.toLocaleString()} / 65.536 Zeichen</span><button className="secondary-button" type="button" onClick={() => void runPreview()} disabled={running || !sample.trim()}>{running ? "Teste …" : "Muster testen"}</button></div>
      {error && <p className="error-message" role="alert">{error}</p>}
    </div>
    {result && <div className="rule-test-results" aria-live="polite">
      <div className="rules-list-heading"><h3>Ergebnis</h3><span className={result.changed ? "rule-test-status changed" : "rule-test-status"}>{result.changed ? "Ersetzungen gefunden" : "Keine Änderung"}</span></div>
      <div className="rule-test-output"><label>Bereinigte Vorschau</label><pre>{result.preview_text}</pre></div>
      <p className="field-help">{result.input_chars.toLocaleString()} Zeichen vorher · {result.output_chars.toLocaleString()} Zeichen nachher</p>
      {result.rule_results.length === 0 && <p className="muted-message">Für diese Auswahl sind keine aktiven Regeln vorhanden.</p>}
      {result.rule_results.map(item => <article className="rule-test-rule" key={item.rule_id}>
        <div><strong>{item.name}</strong><small>{item.rule_id} · Priorität {item.priority} · {item.enabled ? "aktiv" : "Einzeltest einer deaktivierten Regel"}</small></div>
        <span>{item.match_count} Treffer</span>
        {item.matches.length > 0 && <ul>{item.matches.map((match, index) => <li key={index}><code>{match.value}</code> → <code>{match.replacement}</code>{match.chained_from.length > 0 && <small> Folgetreffer nach {match.chained_from.join(", ")}</small>}</li>)}</ul>}
        {item.matches_truncated && <small>Anzeige auf {100} Treffer begrenzt.</small>}
        {item.chained_match_count > 0 && <small className="rule-test-warning">Achtung: {item.chained_match_count} Treffer reagieren auf zuvor erzeugte Ersetzungen.</small>}
      </article>)}
      {result.conflicts.length > 0 && <div className="rules-conflicts"><strong>Konfigurationskonflikte</strong><ul>{result.conflicts.map(item => <li key={item.rule_id}>{item.rule_id} ↔ {item.conflicts_with}: {item.reason}</li>)}</ul></div>}
      {result.overlaps.length > 0 && <div className="rules-conflicts"><strong>Überlappende Treffer im ursprünglichen Beispiel</strong><ul>{result.overlaps.map((item, index) => <li key={index}>{item.first_rule_id} ↔ {item.second_rule_id}: „{item.example}“</li>)}</ul></div>}
      {result.overlaps_truncated && <p className="field-help">Weitere Überlappungen wurden nicht angezeigt.</p>}
    </div>}
  </section>;
}
