import { FormEvent, useCallback, useEffect, useState } from "react";
import { HelpTooltip } from "./components/HelpTooltip";
import { helpTopics } from "./help/content";

type Tab = "overview" | "help";
type ImportedFile = { id: string; project_id: string; display_name: string; size_bytes: number; modified_at: string; imported_at: string; state: string; format_hint?: string; detected_format?: string; format_override?: string | null };
type FolderImportResult = { registered_count: number; skipped_count: number; registered_files: ImportedFile[]; issues: { file_name: string; reason: string }[]; limit_reached: boolean };
type FormatValidationResult = { file_id: string; format: string; valid: boolean; bytes_checked: number; error?: string };
type Project = {
  id: string;
  name: string;
  description: string;
  status: "draft" | "active" | "archived";
  created_at: string;
  updated_at: string;
};

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [folderPath, setFolderPath] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [importedFiles, setImportedFiles] = useState<ImportedFile[]>([]);
  const [importing, setImporting] = useState(false);
  const [importMessage, setImportMessage] = useState("");
  const [importIssues, setImportIssues] = useState<FolderImportResult["issues"]>([]);
  const [validatingFiles, setValidatingFiles] = useState<string[]>([]);
  const [validationResults, setValidationResults] = useState<Record<string, FormatValidationResult>>({});

  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/projects");
      if (!response.ok) throw new Error("Projektliste konnte nicht geladen werden.");
      setProjects(await response.json() as Project[]);
      setError("");
    } catch {
      setError("Backend nicht erreichbar. Bitte FastAPI lokal auf 127.0.0.1:8000 starten.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadProjects(); }, [loadProjects]);

  const loadImportedFiles = useCallback(async (projectId: string) => {
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/files`);
      if (!response.ok) throw new Error("Dateiliste konnte nicht geladen werden.");
      setImportedFiles(await response.json() as ImportedFile[]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Dateiliste konnte nicht geladen werden.");
    }
  }, []);

  useEffect(() => {
    if (selectedProject) void loadImportedFiles(selectedProject.id);
    else setImportedFiles([]);
  }, [selectedProject, loadImportedFiles]);

  async function registerSingleFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject || !sourcePath.trim() || importing) return;
    setImporting(true);
    setError("");
    setImportMessage("");
    setImportIssues([]);
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(selectedProject.id)}/files`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: sourcePath })
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { detail?: string };
        throw new Error(body.detail || "Datei konnte nicht registriert werden.");
      }
      const file = await response.json() as ImportedFile;
      setImportedFiles(current => [...current.filter(item => item.id !== file.id), file]);
      setSourcePath("");
      setImportMessage("Datei registriert. Der Inhalt wurde nicht verarbeitet.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Datei konnte nicht registriert werden.");
    } finally {
      setImporting(false);
    }
  }

  async function registerFolder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject || !folderPath.trim() || importing) return;
    setImporting(true);
    setError("");
    setImportMessage("");
    setImportIssues([]);
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(selectedProject.id)}/files/import-folder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: folderPath, recursive })
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { detail?: string };
        throw new Error(body.detail || "Ordner konnte nicht importiert werden.");
      }
      const result = await response.json() as FolderImportResult;
      setImportedFiles(current => {
        const byId = new Map(current.map(file => [file.id, file]));
        result.registered_files.forEach(file => byId.set(file.id, file));
        return [...byId.values()];
      });
      setImportIssues(result.issues);
      setImportMessage(`Registriert: ${result.registered_count}; übersprungen: ${result.skipped_count}.${result.limit_reached ? " Das Dateilimit wurde erreicht." : ""} Es wurden keine Log-Inhalte gelesen.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Ordner konnte nicht importiert werden.");
    } finally {
      setImporting(false);
    }
  }

  async function detectFileFormat(file: ImportedFile) {
    if (!selectedProject) return;
    setError("");
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(selectedProject.id)}/files/${encodeURIComponent(file.id)}/detect-format`, { method: "POST" });
      const body = await response.json() as { detected_format?: string; format_override?: string | null; detail?: string };
      if (!response.ok) throw new Error(body.detail || "Format konnte nicht erkannt werden.");
      setImportedFiles(current => current.map(item => item.id === file.id ? { ...item, detected_format: body.detected_format, format_override: body.format_override ?? item.format_override } : item));
      setImportMessage(`Format-Erkennung für ${file.display_name}: ${body.detected_format}. Es wurden höchstens 64 KiB lokal untersucht und das Ergebnis lokal gespeichert.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Format konnte nicht erkannt werden.");
    }
  }
  async function validateFileFormat(file: ImportedFile) {
    if (!selectedProject || validatingFiles.includes(file.id)) return;
    setError("");
    setValidatingFiles(current => [...current, file.id]);
    setValidationResults(current => {
      const next = { ...current };
      delete next[file.id];
      return next;
    });
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(selectedProject.id)}/files/${encodeURIComponent(file.id)}/validate-format`, { method: "POST" });
      const body = await response.json() as FormatValidationResult & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Vollständige Formatvalidierung fehlgeschlagen.");
      setValidationResults(current => ({ ...current, [file.id]: body }));
      setImportMessage(`Formatvalidierung für ${file.display_name} abgeschlossen: ${body.valid ? "gültig" : "ungültig"} (${body.bytes_checked.toLocaleString("de-DE")} Byte geprüft).`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Vollständige Formatvalidierung fehlgeschlagen.");
    } finally {
      setValidatingFiles(current => current.filter(id => id !== file.id));
    }
  }

  async function setFileFormatOverride(file: ImportedFile, formatOverride: string) {
    if (!selectedProject) return;
    setError("");
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(selectedProject.id)}/files/${encodeURIComponent(file.id)}/format`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format_override: formatOverride || null })
      });
      const body = await response.json() as ImportedFile & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Format-Auswahl konnte nicht gespeichert werden.");
      setImportedFiles(current => current.map(item => item.id === file.id ? body : item));
      setImportMessage(formatOverride ? `Manuelles Format für ${file.display_name} gespeichert: ${formatOverride}.` : `Manuelle Format-Auswahl für ${file.display_name} entfernt.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Format-Auswahl konnte nicht gespeichert werden.");
    }
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectName.trim() || saving) return;
    setSaving(true);
    setError("");
    try {
      const response = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: projectName, description: projectDescription })
      });
      if (!response.ok) {
        if (response.status === 422) throw new Error("Bitte einen gültigen Projektnamen eingeben (1–80 Zeichen).");
        throw new Error("Projekt konnte nicht gespeichert werden.");
      }
      const project = await response.json() as Project;
      setProjects(current => [project, ...current.filter(item => item.id !== project.id)]);
      setSelectedProject(project);
      setProjectName("");
      setProjectDescription("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unbekannter Fehler beim Speichern.");
    } finally {
      setSaving(false);
    }
  }

  async function openProject(id: string) {
    setError("");
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(id)}`);
      if (!response.ok) throw new Error("Projekt konnte nicht geöffnet werden.");
      setSelectedProject(await response.json() as Project);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unbekannter Fehler beim Öffnen.");
    }
  }

  return <main className="app-shell">
    <header className="topbar">
      <div><p className="eyebrow">LOKAL · OFFLINE-FIRST</p><h1>LogSanitizer</h1></div>
      <nav aria-label="Hauptnavigation" className="nav-tabs">
        <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>Übersicht</button>
        <button className={tab === "help" ? "active" : ""} onClick={() => setTab("help")}>Hilfe</button>
      </nav>
    </header>
    {tab === "overview" ? <>
      <section className="hero">
        <span className="status-pill"><span className="status-dot" /> Entwicklungsgerüst</span>
        <h2>Logs sicher vorbereiten.</h2>
        <p>Die lokale Arbeitsumgebung für die regelbasierte Bereinigung von Anwendungslogs.</p>
        <div className="notice" role="status"><strong>Noch nicht für echte Logdaten freigegeben.</strong><span>Regel-Engine, Streaming-Verarbeitung, geschützte Zuordnungen und Freigabekontrollen sind noch nicht implementiert.</span></div>
      </section>
      <section className="panel">
        <div className="section-heading"><div><p className="eyebrow">ARBEITSBEREICH</p><h3>Projekt vorbereiten</h3></div>
          <HelpTooltip label="Projektname" help="Ein Projekt gruppiert Logdateien, Regeln und konsistente Platzhalterzuordnungen. Der Projektname und die optionale Beschreibung werden lokal in SQLite gespeichert. Noch werden keine Dateien importiert oder verarbeitet."><span className="help-label">Hilfe zum Projekt</span></HelpTooltip>
        </div>
        <form onSubmit={event => void createProject(event)}>
          <label htmlFor="project-name">Projektname</label>
          <input id="project-name" value={projectName} onChange={event => setProjectName(event.target.value)} placeholder="z. B. Testprojekt" maxLength={80} required />
          <label htmlFor="project-description">Beschreibung <span className="optional-label">(optional)</span></label>
          <input id="project-description" value={projectDescription} onChange={event => setProjectDescription(event.target.value)} placeholder="z. B. Analyse eines Anwendungsfehlers" maxLength={500} />
          <p className="field-help">Projekte werden lokal gespeichert. Das Anlegen startet keinen Import und keine Verarbeitung.</p>
          <button className="primary-button" type="submit" disabled={!projectName.trim() || saving}>{saving ? "Speichert …" : "Projekt anlegen"}</button>
        </form>
      </section>
      {error && <p className="error-message" role="alert">{error}</p>}
      <section className="projects-section">
        <div className="section-heading"><div><p className="eyebrow">LOKALE METADATEN</p><h3>Vorhandene Projekte</h3></div><button className="secondary-button" onClick={() => void loadProjects()} disabled={loading}>{loading ? "Lädt …" : "Aktualisieren"}</button></div>
        {loading ? <p className="muted-message">Projektliste wird geladen …</p> : projects.length === 0 ? <p className="muted-message">Noch keine Projekte vorhanden. Lege oben ein Projekt an.</p> : <div className="project-list">{projects.map(project => <article className={selectedProject?.id === project.id ? "project-card selected" : "project-card"} key={project.id}>
          <div><h4>{project.name}</h4><p>{project.description || "Keine Beschreibung"}</p><span className="project-meta">Erstellt: {new Date(project.created_at).toLocaleString("de-DE")} · Status: {project.status === "draft" ? "Entwurf" : project.status}</span></div>
          <button className="secondary-button" onClick={() => void openProject(project.id)}>Öffnen</button>
        </article>)}</div>}
      </section>
      {selectedProject && <section className="panel selected-project" aria-label="Geöffnetes Projekt" aria-live="polite">
        <p className="eyebrow">GEÖFFNETES PROJEKT</p><h3>{selectedProject.name}</h3>
        <p>{selectedProject.description || "Keine Beschreibung hinterlegt."}</p>
        <p className="field-help">Dateien werden nur registriert. Es findet noch keine Verarbeitung oder Bereinigung statt.</p>
        <div className="import-grid">
          <form onSubmit={event => void registerSingleFile(event)} aria-label="Einzeldatei registrieren">
            <h4>Einzelne Datei</h4>
            <label htmlFor="source-path">Absoluter Dateipfad</label>
            <input id="source-path" value={sourcePath} onChange={event => setSourcePath(event.target.value)} placeholder="z. B. /var/log/service.log" maxLength={4096} required />
            <p className="field-help">Der Pfad muss auf dem Rechner des lokalen FastAPI-Backends existieren. Quelldateien bleiben unverändert.</p>
            <button className="secondary-button" type="submit" disabled={!sourcePath.trim() || importing}>{importing ? "Registriert …" : "Datei registrieren"}</button>
          </form>
          <form onSubmit={event => void registerFolder(event)} aria-label="Ordner registrieren">
            <h4>Ordner importieren</h4>
            <label htmlFor="folder-path">Absoluter Ordnerpfad</label>
            <input id="folder-path" value={folderPath} onChange={event => setFolderPath(event.target.value)} placeholder="z. B. /var/log/my-service" maxLength={4096} required />
            <label className="checkbox-label" htmlFor="recursive"><input id="recursive" type="checkbox" checked={recursive} onChange={event => setRecursive(event.target.checked)} /> Unterordner einbeziehen</label>
            <p className="field-help">Bis zu 5.000 Dateikandidaten pro Aufruf. Doppelte Dateien und übersprungene Einträge werden angezeigt.</p>
            <button className="secondary-button" type="submit" disabled={!folderPath.trim() || importing}>{importing ? "Importiert …" : "Ordner registrieren"}</button>
          </form>
        </div>
        <p className="field-help">Hinweis: Dies ist eine Pfadeingabe, noch kein nativer Dateiauswahldialog. Ein Browser-Dateidialog kann dem lokalen Backend nicht sicher den lokalen Dateisystempfad übergeben.</p>
        {importMessage && <p className="success-message" role="status">{importMessage}</p>}
        {importIssues.length > 0 && <div className="import-issues" aria-label="Übersprungene Einträge"><h4>Übersprungene Einträge ({importIssues.length})</h4><ul>{importIssues.map((issue, index) => <li key={`${issue.file_name}-${index}`}><strong>{issue.file_name}</strong>: {issue.reason}</li>)}</ul></div>}
        <div className="section-heading file-list-heading"><h4>Registrierte Dateien ({importedFiles.length})</h4><button className="secondary-button" type="button" onClick={() => void loadImportedFiles(selectedProject.id)}>Liste aktualisieren</button></div>
        {importedFiles.length === 0 ? <p className="muted-message">Noch keine Dateien registriert.</p> : <ul className="registered-file-list">{importedFiles.map(file => <li key={file.id}><div><strong>{file.display_name}</strong><span>{file.state === "registered" ? "Registriert" : file.state}</span><span>Endungs-Hinweis: {({ json: "JSON", jsonl: "JSON Lines", text: "Text", xml: "XML", csv: "CSV", unknown: "unbekannt" } as Record<string, string>)[file.format_hint || "unknown"] || "unbekannt"}</span><span>Erkannt: {({ json: "JSON", jsonl: "JSON Lines", text: "Text", xml: "XML", csv: "CSV", unknown: "unbekannt" } as Record<string, string>)[file.detected_format || "unknown"] || "unbekannt"}</span><label>Format manuell festlegen <select aria-label={`Format für ${file.display_name}`} value={file.format_override || ""} onChange={event => void setFileFormatOverride(file, event.target.value)}><option value="">Automatisch (Erkennung verwenden)</option><option value="text">Text</option><option value="json">JSON</option><option value="jsonl">JSON Lines</option><option value="xml">XML</option><option value="csv">CSV</option><option value="unknown">Unbekannt</option></select></label><button className="secondary-button" type="button" onClick={() => void detectFileFormat(file)}>Format lokal prüfen</button><button className="secondary-button" type="button" onClick={() => void validateFileFormat(file)} disabled={validatingFiles.includes(file.id)}>{validatingFiles.includes(file.id) ? "Validiert …" : "Vollständig validieren"}</button>{validationResults[file.id] && <p className={validationResults[file.id].valid ? "success-message" : "error-message"} role="status">{validationResults[file.id].valid ? "Format gültig" : "Format ungültig"} · {validationResults[file.id].format} · {validationResults[file.id].bytes_checked.toLocaleString("de-DE")} Byte geprüft{validationResults[file.id].error ? ` · ${validationResults[file.id].error}` : ""}</p>}</div><span>{file.size_bytes.toLocaleString("de-DE")} Byte</span></li>)}</ul>}
      </section>}
      <section className="feature-grid" aria-label="Projektprinzipien">
        <article className="feature-card"><span className="feature-number">01</span><h3>Lokal bleiben</h3><p>Keine Cloud- oder externen API-Abhängigkeiten im vorgesehenen Betrieb.</p></article>
        <article className="feature-card"><span className="feature-number">02</span><h3>Originale schützen</h3><p>Quelldateien bleiben unverändert. Verarbeitung erfolgt in getrennten Arbeitsbereichen.</p></article>
        <article className="feature-card"><span className="feature-number">03</span><h3>Freigabe kontrollieren</h3><p>Unvollständige Läufe dürfen später nicht exportiert oder freigegeben werden.</p></article>
      </section>
    </> : <section className="help-page"><p className="eyebrow">OFFLINE-HANDBUCH</p><h2>Hilfe und Grundlagen</h2><p className="intro">Diese Hilfe ist lokal eingebunden. Die Themen werden während der Entwicklung erweitert.</p>
      <div className="help-list">{helpTopics.map(topic => <article className="help-topic" key={topic.id}><h3>{topic.title}</h3><p>{topic.summary}</p><ul>{topic.steps.map(step => <li key={step}>{step}</li>)}</ul></article>)}</div>
    </section>}
    <footer><span>LogSanitizer · 0.1.0-dev</span><span>Keine echten oder vertraulichen Logs in diesem Entwicklungsstand verarbeiten.</span></footer>
  </main>;
}
