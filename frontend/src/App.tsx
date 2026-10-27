import { FormEvent, useCallback, useEffect, useState } from "react";
import { HelpTooltip } from "./components/HelpTooltip";
import { helpTopics } from "./help/content";

type Tab = "overview" | "help";
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
      {selectedProject && <section className="panel selected-project" aria-live="polite">
        <p className="eyebrow">GEÖFFNETES PROJEKT</p><h3>{selectedProject.name}</h3>
        <p>{selectedProject.description || "Keine Beschreibung hinterlegt."}</p>
        <p className="field-help">Status: Entwurf. Dateiimport und Verarbeitung sind noch nicht verfügbar.</p>
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
