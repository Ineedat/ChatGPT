import { useEffect, useRef, useState } from "react";

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
type Project = { id: string; name: string };
type SourceFile = { id: string; display_name: string; size_bytes: number; detected_format?: string; format_override?: string | null };
type FilePreview = Preview & {
  original_text: string; source_offset: number; next_offset: number; total_bytes: number;
  has_previous: boolean; has_next: boolean; window_chars: number;
};
type Props = { config: Config; draft: Rule; selectedId: string; draftDirty: boolean };

async function apiRequest(url: string, payload?: object) {
  const csrf = document.cookie.split("; ").find(item => item.startsWith("logsanitizer_csrf="))?.split("=").slice(1).join("=");
  const headers = new Headers();
  if (payload) headers.set("Content-Type", "application/json");
  if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  return fetch(url, { method: payload ? "POST" : "GET", headers, credentials: "same-origin",
    ...(payload ? { body: JSON.stringify(payload) } : {}) });
}
function highlight(text: string, terms: string[], className: string) {
  const unique = [...new Set(terms.filter(Boolean))].sort((a, b) => b.length - a.length);
  if (!unique.length) return text;
  const escaped = unique.map(term => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp("(" + escaped.join("|") + ")", "g");
  return text.split(pattern).map((part, index) =>
    unique.includes(part) ? <mark className={className} key={index}>{part}</mark> : part
  );
}

export function RuleTestPanel({ config, draft, selectedId, draftDirty }: Props) {
  const [sample, setSample] = useState("client=192.0.2.17 user=alice@example.test token=demo-token");
  const [profileId, setProfileId] = useState("");
  const [mode, setMode] = useState<"single" | "all">("single");
  const [result, setResult] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [files, setFiles] = useState<SourceFile[]>([]);
  const [fileId, setFileId] = useState("");
  const [filePreview, setFilePreview] = useState<FilePreview | null>(null);
  const [fileError, setFileError] = useState("");
  const [fileLoading, setFileLoading] = useState(false);
  const originalPane = useRef<HTMLDivElement>(null);
  const cleanedPane = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    void apiRequest("/api/projects").then(async response => {
      if (!response.ok) throw new Error("Projektliste konnte nicht geladen werden.");
      const items = await response.json() as Project[];
      if (active) { setProjects(items); if (items.length) setProjectId(items[0].id); }
    }).catch(() => { if (active) setFileError("Projektliste ist nicht verfügbar."); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!projectId) { setFiles([]); setFileId(""); return; }
    let active = true;
    void apiRequest(`/api/projects/${encodeURIComponent(projectId)}/files`).then(async response => {
      if (!response.ok) throw new Error("Dateiliste konnte nicht geladen werden.");
      const items = await response.json() as SourceFile[];
      if (active) {
        setFiles(items);
        setFileId(items[0]?.id ?? "");
        setFilePreview(null);
      }
    }).catch(() => { if (active) setFileError("Dateiliste konnte nicht geladen werden."); });
    return () => { active = false; };
  }, [projectId]);

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
    } else if (mode === "single") testRuleId = selectedId || null;
    if (mode === "single" && !testRuleId) {
      setError("Bitte zuerst eine Regel auswählen oder einen vollständigen Regelentwurf eingeben.");
      setRunning(false);
      return;
    }
    try {
      const response = await apiRequest("/api/rules/preview", {
        config: previewConfig, sample_text: sample, profile_id: profileId || null,
        rule_id: mode === "single" ? testRuleId : null
      });
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

  async function loadFileWindow(options: { byteOffset?: number; fromEnd?: boolean } = {}) {
    if (!projectId || !fileId) { setFileError("Bitte ein Projekt und eine registrierte Datei auswählen."); return; }
    setFileLoading(true); setFileError("");
    const previewConfig = { ...config, rules: [...config.rules] };
    let testRuleId: string | null = null;
    if (draftDirty) {
      if (!draft.name.trim() || !draft.pattern.trim() || !draft.replacement.trim()) {
        setFileError("Der aktuelle Regelentwurf ist unvollständig."); setFileLoading(false); return;
      }
      const draftId = selectedId || "preview-draft";
      const draftRule = { ...draft, id: draftId, profile_id: draft.profile_id || null,
        mapping_prefix: draft.replacement_mode === "indexed" ? (draft.mapping_prefix || "VALUE") : null };
      const existing = previewConfig.rules.findIndex(rule => rule.id === draftId);
      if (existing >= 0) previewConfig.rules[existing] = draftRule;
      else previewConfig.rules.push(draftRule);
      if (mode === "single") testRuleId = draftId;
    } else if (mode === "single") testRuleId = selectedId || null;
    if (mode === "single" && !testRuleId) {
      setFileError("Bitte zuerst eine Regel auswählen."); setFileLoading(false); return;
    }
    try {
      const response = await apiRequest(`/api/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(fileId)}/preview`, {
        config: previewConfig, byte_offset: options.byteOffset ?? 0, from_end: options.fromEnd ?? false,
        profile_id: profileId || null, rule_id: mode === "single" ? testRuleId : null
      });
      const body = await response.json() as FilePreview & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Dateifenster konnte nicht geladen werden.");
      setFilePreview(body);
      setResult(null);
    } catch (cause) {
      setFileError(cause instanceof Error ? cause.message : "Dateifenster konnte nicht geladen werden.");
    } finally { setFileLoading(false); }
  }

  function syncScroll(source: "original" | "cleaned") {
    const from = source === "original" ? originalPane.current : cleanedPane.current;
    const to = source === "original" ? cleanedPane.current : originalPane.current;
    if (from && to && Math.abs(to.scrollTop - from.scrollTop) > 1) to.scrollTop = from.scrollTop;
  }

  const originalTerms = filePreview?.rule_results.flatMap(rule => rule.matches.map(match => match.value)) ?? [];
  const replacementTerms = filePreview?.rule_results.flatMap(rule => rule.matches.map(match => match.replacement)) ?? [];

  return <section className="rule-test-workspace">
    <div className="rule-test-input">
      <div className="rules-list-heading"><h3>Regeltest und Bereinigungsvorschau</h3><span className="field-help">Keine Originaldatei wird verändert</span></div>
      <p className="muted-message">Teste eine einzelne Regel – auch wenn sie noch deaktiviert ist – oder simuliere alle aktiven Regeln in Prioritätsreihenfolge. Die Vorschau schreibt keine Projekt-Mappings.</p>
      <label>Testmodus<select value={mode} onChange={event => setMode(event.target.value as "single" | "all")}><option value="single">Ausgewählte Regel</option><option value="all">Alle aktiven Regeln</option></select></label>
      <label>Quellprofil<select value={profileId} onChange={event => setProfileId(event.target.value)}><option value="">Kein Profil / nur globale Regeln</option>{config.profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</select></label>
      <label>Beispieltext<textarea value={sample} onChange={event => setSample(event.target.value)} maxLength={65536} rows={7} spellCheck={false} /></label>
      <div className="rule-test-footer"><span className="field-help">{sample.length.toLocaleString()} / 65.536 Zeichen</span><button className="secondary-button" type="button" onClick={() => void runPreview()} disabled={running || !sample.trim()}>{running ? "Teste …" : "Muster testen"}</button></div>
      {error && <p className="error-message" role="alert">{error}</p>}
    </div>
    <div className="rule-test-results" aria-live="polite">
      <div className="rules-list-heading"><h3>Dateivorschau</h3><span className="field-help">Max. 65.536 Zeichen je Fenster</span></div>
      <div className="rule-file-preview">
        <div className="rule-file-toolbar">
          <label>Projekt<select value={projectId} onChange={event => setProjectId(event.target.value)}><option value="">Projekt wählen</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
          <label>Quelldatei<select value={fileId} onChange={event => { setFileId(event.target.value); setFilePreview(null); }}><option value="">Datei wählen</option>{files.map(file => <option key={file.id} value={file.id}>{file.display_name} · {(file.format_override || file.detected_format || "unbekannt").toUpperCase()}</option>)}</select></label>
          <button className="secondary-button" type="button" onClick={() => void loadFileWindow({ byteOffset: 0 })} disabled={fileLoading || !fileId}>Anfang</button>
          <button className="secondary-button" type="button" onClick={() => void loadFileWindow({ fromEnd: true })} disabled={fileLoading || !fileId}>Ende</button>
          <button className="secondary-button" type="button" onClick={() => void loadFileWindow({ byteOffset: filePreview?.next_offset ?? 0 })} disabled={fileLoading || !filePreview?.has_next}>Weiter</button>
          <button className="secondary-button" type="button" onClick={() => void loadFileWindow({ byteOffset: Math.max(0, (filePreview?.source_offset ?? 0) - 262144) })} disabled={fileLoading || !filePreview?.has_previous}>Zurück</button>
          <button className="secondary-button" type="button" onClick={() => void loadFileWindow({ byteOffset: 0 })} disabled={fileLoading || !fileId}>Neu laden</button>
        </div>
        {fileError && <p className="error-message" role="alert">{fileError}</p>}
        {fileLoading && <p role="status">Dateifenster wird geladen …</p>}
        {filePreview && <>
          <p className="rule-file-meta">Bytes {filePreview.source_offset.toLocaleString()}–{filePreview.next_offset.toLocaleString()} von {filePreview.total_bytes.toLocaleString()} · {filePreview.window_chars.toLocaleString()} Zeichen · {filePreview.rule_results.reduce((sum, item) => sum + item.match_count, 0).toLocaleString()} Treffer in diesem Fenster</p>
          <div className="rule-file-panes">
            <section className="rule-file-pane"><h4>Original</h4><div className="rule-file-scroll" ref={originalPane} onScroll={() => syncScroll("original")}><pre>{highlight(filePreview.original_text, originalTerms, "rule-file-hit")}</pre></div></section>
            <section className="rule-file-pane"><h4>Bereinigte Vorschau</h4><div className="rule-file-scroll" ref={cleanedPane} onScroll={() => syncScroll("cleaned")}><pre>{highlight(filePreview.preview_text, replacementTerms, "rule-file-replacement")}</pre></div></section>
          </div>
        </>}
      </div>
      {result && <span className={result.changed ? "rule-test-status changed" : "rule-test-status"}>{result.changed ? "Ersetzungen gefunden" : "Keine Änderung"}</span>}
      {result && <div className="rule-test-output"><label>Bereinigte Beispielvorschau</label><pre>{result.preview_text}</pre></div>}
      {result && <p className="field-help">{result.input_chars.toLocaleString()} Zeichen vorher · {result.output_chars.toLocaleString()} Zeichen nachher</p>}
      {result?.rule_results.map(item => <article className="rule-test-rule" key={item.rule_id}><div><strong>{item.name}</strong><small>{item.rule_id} · Priorität {item.priority}</small></div><span>{item.match_count} Treffer</span>{item.matches.length > 0 && <ul>{item.matches.map((match, index) => <li key={index}><code>{match.value}</code> → <code>{match.replacement}</code></li>)}</ul>}</article>)}
    </div>
  </section>;
}
