import { FormEvent, useCallback, useEffect, useState } from "react";

type ReviewRun = {
  id: string;
  project_id: string;
  file_id: string;
  display_name: string;
  output_name: string;
  status: string;
  actor_username: string;
  parent_run_id: string | null;
  created_at: string;
  completed_at: string | null;
  input_bytes: number;
  output_bytes: number;
  lines_processed: number;
  replacements: number;
  validated: number | boolean;
  residual_matches: number;
  last_comment: string;
  exception_reason: string;
};
type SavedSearch = { id: string; name: string; query: string; created_at: string };
type SearchResult = { line_number: number; snippet: string };
type AuditEvent = {
  id: number;
  run_id: string;
  actor_username: string;
  action: string;
  comment: string;
  exception_reason: string;
  created_at: string;
};

async function reviewFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const method = (init.method || "GET").toUpperCase();
  const csrf = document.cookie.split("; ").find(item => item.startsWith("logsanitizer_csrf="))?.split("=").slice(1).join("=");
  const headers = new Headers(init.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  return fetch(input, { ...init, headers, credentials: "same-origin" });
}

export function ReviewPanel({ roles }: { roles: string[] }) {
  const canReview = roles.some(role => ["admin", "reviewer", "approver"].includes(role));
  const [queue, setQueue] = useState<ReviewRun[]>([]);
  const [history, setHistory] = useState<ReviewRun[]>([]);
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [savedSearchId, setSavedSearchId] = useState("");
  const [matches, setMatches] = useState<SearchResult[]>([]);
  const [matchCount, setMatchCount] = useState(0);
  const [searchTruncated, setSearchTruncated] = useState(false);
  const [searchName, setSearchName] = useState("");
  const [comment, setComment] = useState("");
  const [exception, setException] = useState(false);
  const [exceptionReason, setExceptionReason] = useState("");
  const [retryOutput, setRetryOutput] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      const historyResponse = await reviewFetch("/api/reviews/runs?limit=100");
      if (!historyResponse.ok) throw new Error("Laufhistorie konnte nicht geladen werden.");
      setHistory(await historyResponse.json() as ReviewRun[]);
      if (canReview) {
        const [queueResponse, searchesResponse, auditResponse] = await Promise.all([
          reviewFetch("/api/reviews/queue"),
          reviewFetch("/api/reviews/saved-searches"),
          reviewFetch("/api/reviews/audit?limit=50")
        ]);
        if (!queueResponse.ok || !searchesResponse.ok || !auditResponse.ok) {
          throw new Error("Prüferdaten konnten nicht vollständig geladen werden.");
        }
        setQueue(await queueResponse.json() as ReviewRun[]);
        setSavedSearches(await searchesResponse.json() as SavedSearch[]);
        setAudit(await auditResponse.json() as AuditEvent[]);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Prüfdaten konnten nicht geladen werden.");
    }
  }, [canReview]);

  useEffect(() => { void refresh(); }, [refresh]);

  const selectedRun = [...queue, ...history].find(run => run.id === selectedId);

  async function searchOutput(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedRun || !canReview || busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const params = new URLSearchParams();
      if (savedSearchId) params.set("saved_search_id", savedSearchId);
      else params.set("q", query);
      const response = await reviewFetch(
        `/api/reviews/runs/${encodeURIComponent(selectedRun.id)}/search?${params.toString()}`
      );
      const body = await response.json() as { detail?: string; results?: SearchResult[]; match_count?: number; truncated?: boolean; query?: string };
      if (!response.ok) throw new Error(body.detail || "Suche fehlgeschlagen.");
      setMatches(body.results || []);
      setMatchCount(body.match_count || 0);
      setSearchTruncated(Boolean(body.truncated));
      setMessage(`Suche nach „${body.query}“: ${body.match_count} Treffer angezeigt.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Suche fehlgeschlagen.");
      setMatches([]);
      setMatchCount(0);
    } finally {
      setBusy(false);
    }
  }

  async function saveSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!searchName.trim() || !query.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await reviewFetch("/api/reviews/saved-searches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: searchName, query })
      });
      const body = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Suchmuster konnte nicht gespeichert werden.");
      setSearchName("");
      setSavedSearchId("");
      setMessage("Eigenes Suchmuster wurde gespeichert.");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Suchmuster konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteSearch(id: string) {
    setError("");
    try {
      const response = await reviewFetch(`/api/reviews/saved-searches/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Suchmuster konnte nicht gelöscht werden.");
      if (savedSearchId === id) setSavedSearchId("");
      await refresh();
      setMessage("Eigenes Suchmuster wurde gelöscht.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Suchmuster konnte nicht gelöscht werden.");
    }
  }

  async function decide(action: "approve" | "return" | "stop") {
    if (!selectedRun || busy) return;
    if (exception && (!exceptionReason.trim() || action !== "approve")) {
      setError("Eine begründete Ausnahme ist nur bei einer Freigabe möglich.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await reviewFetch(
        `/api/reviews/runs/${encodeURIComponent(selectedRun.id)}/${action}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ comment, exception: action === "approve" && exception, exception_reason: action === "approve" && exception ? exceptionReason : "" })
        }
      );
      const body = await response.json() as { detail?: string; status?: string };
      if (!response.ok) throw new Error(body.detail || "Entscheidung konnte nicht gespeichert werden.");
      setMessage(`Prüfentscheidung gespeichert: ${body.status}.`);
      setComment("");
      setException(false);
      setExceptionReason("");
      setMatches([]);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Entscheidung konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  async function addComment() {
    if (!selectedRun || !comment.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await reviewFetch(
        `/api/reviews/runs/${encodeURIComponent(selectedRun.id)}/comments`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ comment }) }
      );
      const body = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Kommentar konnte nicht gespeichert werden.");
      setMessage("Kommentar wurde im Audit-Protokoll gespeichert.");
      setComment("");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Kommentar konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  async function startRework(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedRun || selectedRun.status !== "returned" || !retryOutput.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await reviewFetch(
        `/api/projects/${encodeURIComponent(selectedRun.project_id)}/files/${encodeURIComponent(selectedRun.file_id)}/sanitize-jobs`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ output_path: retryOutput, retry_of_run_id: selectedRun.id })
        }
      );
      const body = await response.json() as { detail?: string; id?: string };
      if (!response.ok) throw new Error(body.detail || "Überarbeitete Bereinigung konnte nicht gestartet werden.");
      setRetryOutput("");
      setMessage("Überarbeitete Bereinigung wurde gestartet. Nach erfolgreicher Pflichtvalidierung wird sie erneut zur Prüfung vorgelegt.");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Überarbeitung konnte nicht gestartet werden.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="review-page" aria-label="Prüfung und Laufhistorie">
    <div className="review-heading">
      <div><p className="eyebrow">NACHVOLLZIEHBAR · LOKAL</p><h2>Prüfung &amp; Verlauf</h2></div>
      <button className="secondary-button" type="button" onClick={() => void refresh()} disabled={busy}>Aktualisieren</button>
    </div>
    <p className="review-intro">Nur erfolgreich validierte Bereinigungen können in die Prüfer-Warteschlange gelangen. Die Suche durchsucht ausschließlich die bereinigte Ausgabe, niemals die Originaldatei.</p>
    {error && <p className="error-message" role="alert">{error}</p>}
    {message && <p className="success-message" role="status">{message}</p>}
    {canReview && <section className="review-section" aria-label="Prüfer-Warteschlange">
      <div className="section-heading"><h3>Warteschlange ({queue.length})</h3><span className="field-help">Bewusste Freigabe erforderlich</span></div>
      {queue.length === 0 ? <p className="muted-message">Keine ausstehenden Prüfungen.</p> : <ul className="review-run-list">{queue.map(run =>
        <li key={run.id} className={selectedId === run.id ? "selected" : ""}>
          <div><strong>{run.display_name}</strong><span>Ausgabe: {run.output_name}</span><span>Erstellt: {new Date(run.created_at).toLocaleString("de-DE")}</span><span>{run.replacements} Ersetzungen · {run.lines_processed.toLocaleString("de-DE")} Zeilen</span></div>
          <button className="secondary-button" type="button" onClick={() => { setSelectedId(run.id); setMatches([]); setQuery(""); setSavedSearchId(""); setMessage(""); }}>Prüfen</button>
        </li>)}</ul>}
    </section>}
    {canReview && selectedRun?.status === "pending_review" && <section className="review-section" aria-label="Ausgabe prüfen">
      <h3>Stichprobensuche: {selectedRun.display_name}</h3>
      <form className="review-search-form" onSubmit={event => void searchOutput(event)}>
        <label>Suchbegriff (wörtlich, ohne Regex)
          <input value={query} maxLength={200} onChange={event => { setQuery(event.target.value); setSavedSearchId(""); }} placeholder="z. B. REDACTED oder ein erwarteter Platzhalter" />
        </label>
        <label>Eigenes gespeichertes Suchmuster
          <select value={savedSearchId} onChange={event => { setSavedSearchId(event.target.value); const saved = savedSearches.find(item => item.id === event.target.value); if (saved) setQuery(saved.query); }}>
            <option value="">Ad-hoc-Suche verwenden</option>
            {savedSearches.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <button className="secondary-button" type="submit" disabled={busy || (!query.trim() && !savedSearchId)}>Ausgabe durchsuchen</button>
      </form>
      {matches.length > 0 && <div className="review-results" aria-label="Suchtreffer">
        <p>{matchCount} Treffer angezeigt (maximal 20). {searchTruncated ? "Weitere Treffer können vorhanden sein." : ""}</p>
        <ol>{matches.map(match => <li key={match.line_number}><span>Zeile {match.line_number}</span><code>{match.snippet}</code></li>)}</ol>
      </div>}
      {matchCount === 0 && message.startsWith("Suche nach") && <p className="muted-message">Keine Treffer für diese Suche.</p>}
      <form className="review-save-search" onSubmit={event => void saveSearch(event)}>
        <label>Name für eigenes Suchmuster<input value={searchName} maxLength={80} onChange={event => setSearchName(event.target.value)} placeholder="z. B. Prüfmuster für Tokens" /></label>
        <button className="secondary-button" type="submit" disabled={busy || !searchName.trim() || !query.trim()}>Suchmuster speichern</button>
      </form>
      {savedSearches.length > 0 && <div className="saved-search-list"><strong>Eigene Suchmuster</strong><ul>{savedSearches.map(item => <li key={item.id}><span>{item.name}: {item.query}</span><button type="button" className="text-button" onClick={() => void deleteSearch(item.id)}>Löschen</button></li>)}</ul></div>}
      <label className="review-comment-label">Kommentar (optional für Entscheidung)
        <textarea value={comment} maxLength={1000} onChange={event => setComment(event.target.value)} rows={3} placeholder="Prüfhinweise, Rückgabegrund oder Freigabekommentar" />
      </label>
      <button className="secondary-button" type="button" disabled={busy || !comment.trim()} onClick={() => void addComment()}>Kommentar protokollieren</button>
      <label className="review-exception-toggle"><input type="checkbox" checked={exception} onChange={event => setException(event.target.checked)} /> Begründete Ausnahme freigeben</label>
      {exception && <label className="review-comment-label">Ausnahmebegründung (Pflichtfeld)<textarea value={exceptionReason} maxLength={1000} onChange={event => setExceptionReason(event.target.value)} rows={3} required placeholder="Warum ist diese dokumentierte Ausnahme vertretbar?" /></label>}
      <div className="review-actions">
        <button className="primary-button" type="button" disabled={busy || (exception && !exceptionReason.trim())} onClick={() => void decide("approve")}>Freigeben</button>
        <button className="secondary-button" type="button" disabled={busy} onClick={() => void decide("return")}>Zur Überarbeitung zurückgeben</button>
        <button className="secondary-button" type="button" disabled={busy} onClick={() => void decide("stop")}>Vorgang stoppen</button>
      </div>
    </section>}
    {selectedRun && <section className="review-section" aria-label="Laufdetails">
      <h3>Ausgewählter Lauf</h3>
      <dl className="review-details">
        <div><dt>Status</dt><dd>{selectedRun.status}</dd></div>
        <div><dt>Quelle</dt><dd>{selectedRun.display_name}</dd></div>
        <div><dt>Bereinigte Ausgabe</dt><dd>{selectedRun.output_name}</dd></div>
        <div><dt>Validierung</dt><dd>{selectedRun.validated ? "Bestanden" : "Nicht bestanden"} · Resttreffer: {selectedRun.residual_matches}</dd></div>
        <div><dt>Ersetzungen</dt><dd>{selectedRun.replacements}</dd></div>
        {selectedRun.last_comment && <div><dt>Letzter Kommentar</dt><dd>{selectedRun.last_comment}</dd></div>}
        {selectedRun.exception_reason && <div><dt>Ausnahmebegründung</dt><dd>{selectedRun.exception_reason}</dd></div>}
        {selectedRun.parent_run_id && <div><dt>Überarbeitet aus</dt><dd>{selectedRun.parent_run_id}</dd></div>}
      </dl>
      {selectedRun.status === "returned" && roles.some(role => ["admin", "operator"].includes(role)) && <form className="review-rework-form" onSubmit={event => void startRework(event)}>
        <h4>Überarbeitung starten</h4>
        <label>Neuer absoluter Ausgabepfad<input value={retryOutput} maxLength={4096} onChange={event => setRetryOutput(event.target.value)} required placeholder="Neuer Pfad; vorhandene Dateien werden nicht überschrieben" /></label>
        <button className="secondary-button" type="submit" disabled={busy || !retryOutput.trim()}>Erneut bereinigen</button>
      </form>}
    </section>}
    <section className="review-section" aria-label="Laufhistorie">
      <h3>Laufhistorie ({history.length})</h3>
      {history.length === 0 ? <p className="muted-message">Noch keine Bereinigungsläufe gespeichert.</p> : <ul className="review-run-list">{history.map(run =>
        <li key={run.id} className={selectedId === run.id ? "selected" : ""}>
          <div><strong>{run.display_name}</strong><span>{run.output_name} · {run.status}</span><span>{new Date(run.created_at).toLocaleString("de-DE")}</span>{run.last_comment && <span>Kommentar: {run.last_comment}</span>}</div>
          <button className="secondary-button" type="button" onClick={() => { setSelectedId(run.id); setMatches([]); setMessage(""); }}>Details</button>
        </li>)}</ul>}
    </section>
    {canReview && <section className="review-section" aria-label="Audit-Protokoll">
      <h3>Audit-Protokoll (letzte {audit.length} Ereignisse)</h3>
      {audit.length === 0 ? <p className="muted-message">Noch keine Audit-Ereignisse.</p> : <ul className="audit-list">{audit.map(event =>
        <li key={event.id}><div><strong>{event.action}</strong><span>{event.actor_username} · Lauf {event.run_id}</span><span>{new Date(event.created_at).toLocaleString("de-DE")}</span>{event.comment && <p>{event.comment}</p>}{event.exception_reason && <p>Ausnahme: {event.exception_reason}</p>}</div></li>)}</ul>}
    </section>}
  </section>;
}
