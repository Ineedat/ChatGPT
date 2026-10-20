import { useState } from "react";
import { HelpTooltip } from "./components/HelpTooltip";
import { helpTopics } from "./help/content";

type Tab = "overview" | "help";

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [projectName, setProjectName] = useState("");

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
          <HelpTooltip label="Projektname" help="Ein Projekt gruppiert Logdateien, Regeln und konsistente Platzhalterzuordnungen. In diesem Entwicklungsstand wird noch kein Projekt dauerhaft gespeichert."><span className="help-label">Hilfe zum Projektname</span></HelpTooltip>
        </div>
        <label htmlFor="project-name">Projektname</label>
        <input id="project-name" value={projectName} onChange={event => setProjectName(event.target.value)} placeholder="z. B. Testprojekt" maxLength={80} />
        <p className="field-help">Dies ist derzeit nur ein UI-Prototyp; Eingaben werden nicht gespeichert.</p>
        <button className="primary-button" disabled={!projectName.trim()} onClick={() => window.alert("Projektverwaltung ist für einen späteren Meilenstein vorgesehen.")}>Projekt vorbereiten</button>
      </section>
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
