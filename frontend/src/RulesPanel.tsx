import { useEffect, useState } from "react";
import { RuleLibraryPanel } from "./RuleLibraryPanel";
import { RuleTestPanel } from "./RuleTestPanel";

type RuleProfile = { id: string; name: string; source_hint?: string | null };
type SanitizationRule = {
  id: string; name: string; category: string; match_type: "plain" | "regex";
  pattern: string; replacement: string; replacement_mode: "fixed" | "indexed";
  mapping_prefix?: string | null; case_sensitive: boolean; priority: number;
  profile_id?: string | null; enabled: boolean;
};
type RuleConfig = { schema_version: 1; profiles: RuleProfile[]; rules: SanitizationRule[] };
type Conflict = { rule_id: string; conflicts_with: string; reason: string };
type RuleTemplate = { id: string; name: string; category: string; pattern: string; mapping_prefix: string; priority: number; match_type: "regex"; replacement_mode: "indexed"; replacement: string; case_sensitive: boolean; enabled: boolean; profile_id: null };
const emptyRule = (): SanitizationRule => ({
  id: "", name: "", category: "IP-Adresse", match_type: "regex", pattern: "",
  replacement: "[IP]", replacement_mode: "fixed", mapping_prefix: "IP",
  case_sensitive: false, priority: 100, profile_id: null, enabled: true
});
const categories = ["IP-Adresse", "Hostname / Domain", "Benutzername", "E-Mail-Adresse", "Personenbezogene Daten", "Passwort / Token / API-Key", "Dateipfad", "Systemname / Infrastruktur", "Sonstiges"];

async function request(path: string, init?: RequestInit) {
  const csrf = document.cookie.split("; ").find(item => item.startsWith("logsanitizer_csrf="))?.split("=").slice(1).join("=");
  const headers = new Headers(init?.headers);
  if (init?.method && !["GET", "HEAD"].includes(init.method.toUpperCase()) && csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  return fetch(path, { ...init, headers, credentials: "same-origin" });
}
function makeId(name: string, existing: string[]) {
  const base = name.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48) || "regel";
  let candidate = base, index = 2;
  while (existing.includes(candidate)) candidate = `${base}-${index++}`;
  return candidate;
}

export function RulesPanel() {
  const [config, setConfig] = useState<RuleConfig>({ schema_version: 1, profiles: [], rules: [] });
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState<SanitizationRule>(emptyRule());
  const [profileDraft, setProfileDraft] = useState<RuleProfile>({ id: "", name: "", source_hint: "" });
  const [section, setSection] = useState<"rules" | "profiles" | "library" | "test">("rules");
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [draftDirty, setDraftDirty] = useState(false);

  useEffect(() => {
    void request("/api/rules/config").then(async response => {
      if (!response.ok) throw new Error("Regelkonfiguration konnte nicht geladen werden.");
      const data = await response.json() as RuleConfig;
      setConfig(data);
      if (data.rules[0]) { setSelectedId(data.rules[0].id); setDraft(data.rules[0]); }
    }).catch(cause => { setLoadFailed(true); setError(cause instanceof Error ? cause.message : "Ladefehler."); })
      .finally(() => setLoading(false));
  }, []);

  function confirmDiscardDraft() { return !draftDirty || window.confirm("Nicht übernommene Regeländerungen verwerfen?"); }
  function selectRule(rule: SanitizationRule) { if (!confirmDiscardDraft()) return; setSelectedId(rule.id); setDraft({ ...rule }); setDraftDirty(false); setMessage(""); }
  function updateDraft<K extends keyof SanitizationRule>(key: K, value: SanitizationRule[K]) {
    setDraft(current => ({ ...current, [key]: value })); setDraftDirty(true); setMessage(""); setError("");
  }
  function newRule() { if (!confirmDiscardDraft()) return; setSelectedId(""); setDraft(emptyRule()); setDraftDirty(false); setMessage(""); }
  function saveDraft() {
    if (!draft.name.trim() || !draft.pattern.trim() || !draft.replacement.trim()) { setError("Name, Suchmuster und Ersetzung sind Pflichtfelder."); return; }
    const id = selectedId || makeId(draft.name, config.rules.map(rule => rule.id));
    const next = { ...draft, id, profile_id: draft.profile_id || null, mapping_prefix: draft.replacement_mode === "indexed" ? (draft.mapping_prefix || "VALUE") : null };
    setConfig(current => ({ ...current, rules: selectedId ? current.rules.map(rule => rule.id === selectedId ? next : rule) : [...current.rules, next] }));
    setSelectedId(id); setDraft(next); setDraftDirty(false); setDirty(true); setMessage("Änderung vorgemerkt. Mit „Konfiguration speichern“ dauerhaft übernehmen.");
  }
  function duplicateRule(rule: SanitizationRule) {
    if (!confirmDiscardDraft()) return;
    const copy = { ...rule, id: makeId(rule.id + "-kopie", config.rules.map(item => item.id)), name: rule.name + " (Kopie)" };
    setConfig(current => ({ ...current, rules: [...current.rules, copy] }));
    setSelectedId(copy.id); setDraft(copy); setDraftDirty(false); setDirty(true);
  }
  function deleteRule(rule: SanitizationRule) {
    if (!confirmDiscardDraft() || !window.confirm(`Regel „${rule.name}“ wirklich löschen?`)) return;
    setConfig(current => ({ ...current, rules: current.rules.filter(item => item.id !== rule.id) }));
    if (selectedId === rule.id) { setSelectedId(""); setDraft(emptyRule()); setDraftDirty(false); }
    setDirty(true);
  }
  async function persist() {
    setSaving(true); setError(""); setMessage(""); setConflicts([]);
    try {
      const validation = await request("/api/rules/config/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config) });
      const checked = await validation.json() as { valid?: boolean; conflicts?: Conflict[]; detail?: unknown };
      if (!validation.ok) throw new Error(typeof checked.detail === "string" ? checked.detail : "Regelkonfiguration ist ungültig.");
      if (!checked.valid) { setConflicts(checked.conflicts || []); throw new Error("Regelkonflikte müssen vor dem Speichern behoben werden."); }
      const response = await request("/api/rules/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config) });
      const body = await response.json() as RuleConfig & { detail?: unknown };
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Speichern fehlgeschlagen.");
      setConfig(body); setDirty(false); setMessage("Regelkonfiguration wurde lokal gespeichert.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Speichern fehlgeschlagen."); }
    finally { setSaving(false); }
  }
  function addTemplate(template: RuleTemplate) {
    if (!confirmDiscardDraft()) return;
    const id = makeId(template.id, config.rules.map(rule => rule.id));
    const next: SanitizationRule = {
      id, name: template.name, category: template.category, match_type: template.match_type,
      pattern: template.pattern, replacement: `[${template.mapping_prefix}_1]`,
      replacement_mode: template.replacement_mode, mapping_prefix: template.mapping_prefix,
      case_sensitive: template.case_sensitive, priority: template.priority, profile_id: null,
      enabled: false
    };
    setConfig(current => ({ ...current, rules: [...current.rules, next] }));
    setSelectedId(id); setDraft(next); setDraftDirty(false); setDirty(true); setSection("rules");
    setMessage("Vorlage übernommen und zunächst deaktiviert. Prüfe das Muster und aktiviere die Regel erst nach einem erfolgreichen Test.");
    setError("");
  }

  function addProfile() {
    if (!profileDraft.name.trim()) { setError("Bitte einen Profilnamen eingeben."); return; }
    const id = profileDraft.id || makeId(profileDraft.name, config.profiles.map(profile => profile.id));
    const next = { ...profileDraft, id, source_hint: profileDraft.source_hint?.trim() || null };
    setConfig(current => ({ ...current, profiles: current.profiles.some(profile => profile.id === id) ? current.profiles.map(profile => profile.id === id ? next : profile) : [...current.profiles, next] }));
    setProfileDraft({ id: "", name: "", source_hint: "" }); setDirty(true); setMessage("Quellprofil vorgemerkt. Änderungen anschließend speichern.");
  }
  function removeProfile(id: string) {
    if (config.rules.some(rule => rule.profile_id === id)) { setError("Das Profil wird noch von Regeln verwendet. Weise diese Regeln zuerst einem anderen Profil zu."); return; }
    setConfig(current => ({ ...current, profiles: current.profiles.filter(profile => profile.id !== id) }));
    setDirty(true);
  }

  if (loading) return <section className="rules-page"><p role="status">Regelkonfiguration wird geladen …</p></section>;
  if (loadFailed) return <section className="rules-page"><h2>Bereinigungsregeln</h2><p className="error-message" role="alert">{error || "Regelkonfiguration konnte nicht geladen werden."} Die bestehende Konfiguration bleibt unverändert; Speichern ist deaktiviert.</p></section>;
  return <section className="rules-page">
    <div className="rules-heading"><div><p className="eyebrow">REGELVERWALTUNG</p><h2>Bereinigungsregeln</h2><p>Globale Regeln und Regeln für bestimmte Quellprofile. Änderungen werden erst nach dem Speichern aktiv.</p></div><button className="primary-button" type="button" onClick={() => void persist()} disabled={!dirty || draftDirty || saving}>{saving ? "Prüft und speichert …" : "Konfiguration speichern"}</button></div>
    <nav className="rules-tabs" aria-label="Regelverwaltung"><button className={section === "rules" ? "active" : ""} onClick={() => { if (confirmDiscardDraft()) setSection("rules"); }}>Regeln ({config.rules.length})</button><button className={section === "library" ? "active" : ""} onClick={() => { if (confirmDiscardDraft()) setSection("library"); }}>Vorlagenbibliothek</button><button className={section === "profiles" ? "active" : ""} onClick={() => { if (confirmDiscardDraft()) setSection("profiles"); }}>Quellprofile ({config.profiles.length})</button><button className={section === "test" ? "active" : ""} onClick={() => setSection("test")}>Regeltest & Vorschau</button></nav>
    {error && <p className="error-message" role="alert">{error}</p>}
    {message && <p className="success-message" role="status">{message}</p>}
    {conflicts.length > 0 && <div className="rules-conflicts" role="alert"><strong>Konflikte gefunden</strong><ul>{conflicts.map(item => <li key={item.rule_id}>{item.rule_id} ↔ {item.conflicts_with}: {item.reason}</li>)}</ul></div>}
    {section === "rules" ? <div className="rules-workspace">
      <aside className="rules-list-panel"><div className="rules-list-heading"><h3>Regelliste</h3><button className="secondary-button" onClick={newRule}>Neue Regel</button></div>
        <div className="rules-list">{config.rules.map(rule => <button key={rule.id} className={selectedId === rule.id ? "rule-list-item selected" : "rule-list-item"} onClick={() => selectRule(rule)}><span className={rule.enabled ? "rule-state enabled" : "rule-state"} /> <span><strong>{rule.name}</strong><small>{rule.category} · Priorität {rule.priority}{rule.profile_id ? " · Quellprofil" : " · Global"}</small></span></button>)}</div>
        {config.rules.length === 0 && <p className="muted-message">Noch keine Regeln angelegt.</p>}
      </aside>
      <div className="rule-editor-panel"><div className="rules-list-heading"><h3>{selectedId ? "Regel bearbeiten" : "Neue Regel"}</h3>{selectedId && <div className="rule-actions"><button className="text-button" onClick={() => { const rule = config.rules.find(item => item.id === selectedId); if (rule) duplicateRule(rule); }}>Kopieren</button><button className="text-button danger-text" onClick={() => { const rule = config.rules.find(item => item.id === selectedId); if (rule) deleteRule(rule); }}>Löschen</button></div>}</div>
        <div className="rule-form-grid">
          <label>Regelname<input value={draft.name} maxLength={120} onChange={event => updateDraft("name", event.target.value)} placeholder="z. B. IPv4-Adressen" /></label>
          <label>Kategorie<select value={draft.category} onChange={event => updateDraft("category", event.target.value)}>{categories.map(item => <option key={item}>{item}</option>)}</select></label>
          <label>Suchart<select value={draft.match_type} onChange={event => updateDraft("match_type", event.target.value as "plain" | "regex")}><option value="regex">Regulärer Ausdruck</option><option value="plain">Wörtlicher Text</option></select></label>
          <label>Suchmuster<input value={draft.pattern} maxLength={2000} onChange={event => updateDraft("pattern", event.target.value)} placeholder={draft.match_type === "regex" ? String.raw`\b(?:\d{1,3}\.){3}\d{1,3}\b` : "Exakter Text"} /></label>
          <label>Ersetzungsart<select value={draft.replacement_mode} onChange={event => updateDraft("replacement_mode", event.target.value as "fixed" | "indexed")}><option value="fixed">Fester Wert</option><option value="indexed">Indexierter Platzhalter</option></select></label>
          <label>Ersetzung<input value={draft.replacement} maxLength={200} onChange={event => updateDraft("replacement", event.target.value)} placeholder="[IP]" /></label>
          {draft.replacement_mode === "indexed" && <label>Platzhalter-Präfix<input value={draft.mapping_prefix || ""} maxLength={32} onChange={event => updateDraft("mapping_prefix", event.target.value)} placeholder="IP" /></label>}
          <label>Priorität<input type="number" min={1} max={10000} value={draft.priority} onChange={event => updateDraft("priority", Number(event.target.value))} /></label>
          <label>Geltungsbereich<select value={draft.profile_id || ""} onChange={event => updateDraft("profile_id", event.target.value || null)}><option value="">Global (alle Quellen)</option>{config.profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</select></label>
          <label className="rule-check"><input type="checkbox" checked={draft.case_sensitive} onChange={event => updateDraft("case_sensitive", event.target.checked)} /> Groß-/Kleinschreibung beachten</label>
          <label className="rule-check"><input type="checkbox" checked={draft.enabled} onChange={event => updateDraft("enabled", event.target.checked)} /> Regel aktiviert</label>
        </div>
        <div className="rule-editor-footer"><span className="field-help">ID: {selectedId || "wird beim Übernehmen automatisch erzeugt"}</span><button className="secondary-button" onClick={saveDraft}>Regel übernehmen</button></div>
      </div>
    </div> : section === "profiles" ? <div className="profile-workspace">
      <div className="profile-form"><h3>{profileDraft.id ? "Quellprofil bearbeiten" : "Quellprofil anlegen"}</h3><label>Profilname<input value={profileDraft.name} onChange={event => setProfileDraft(current => ({ ...current, name: event.target.value }))} placeholder="z. B. Webserver" maxLength={100} /></label><label>Quellhinweis (optional)<input value={profileDraft.source_hint || ""} onChange={event => setProfileDraft(current => ({ ...current, source_hint: event.target.value }))} placeholder="z. B. nginx" maxLength={200} /></label><div className="rule-actions"><button className="secondary-button" onClick={addProfile}>Profil übernehmen</button>{profileDraft.id && <button className="text-button" onClick={() => setProfileDraft({ id: "", name: "", source_hint: "" })}>Abbrechen</button>}</div></div>
      <div className="profile-list"><h3>Vorhandene Quellprofile</h3>{config.profiles.map(profile => <div className="profile-item" key={profile.id}><div><strong>{profile.name}</strong><small>{profile.source_hint || "Kein Quellhinweis"} · ID: {profile.id}</small></div><div className="rule-actions"><button className="text-button" onClick={() => { setProfileDraft({ ...profile, source_hint: profile.source_hint || "" }); setError(""); }}>Bearbeiten</button><button className="text-button danger-text" onClick={() => removeProfile(profile.id)}>Löschen</button></div></div>)}{config.profiles.length === 0 && <p className="muted-message">Noch keine Quellprofile angelegt.</p>}</div>
    </div> : section === "library" ? <RuleLibraryPanel onAddTemplate={addTemplate} /> : <RuleTestPanel config={config} draft={draft} selectedId={selectedId} draftDirty={draftDirty} />}
  </section>;
}
