import { useCallback, useEffect, useState } from "react";

type ApprovedExport = {
  run_id: string;
  file_id: string;
  relative_path: string;
  output_bytes: number;
  completed_at: string | null;
  download_url: string;
};
type WritableFile = { write(data: Uint8Array): Promise<void>; close(): Promise<void>; abort?: () => Promise<void> };
type FileHandle = { createWritable(): Promise<WritableFile> };
type DirectoryHandle = {
  getDirectoryHandle(name: string, options?: { create?: boolean }): Promise<DirectoryHandle>;
  getFileHandle(name: string, options?: { create?: boolean }): Promise<FileHandle>;
};
type PickerWindow = Window & { showDirectoryPicker?: () => Promise<DirectoryHandle> };

async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const method = (init.method || "GET").toUpperCase();
  const csrf = document.cookie.split("; ").find(item => item.startsWith("logsanitizer_csrf="))?.split("=").slice(1).join("=");
  const headers = new Headers(init.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  return fetch(input, { ...init, headers, credentials: "same-origin" });
}

async function writeStreamToFolder(root: DirectoryHandle, relativePath: string, response: Response) {
  if (!response.ok || !response.body) throw new Error("Eine freigegebene Datei konnte nicht geladen werden.");
  const parts = relativePath.replaceAll("\\", "/").split("/");
  if (!parts.length || parts.some(part => !part || part === "." || part === ".." || part.includes(":"))) {
    throw new Error("Ein ungültiger relativer Dateipfad wurde vom Server geliefert.");
  }
  let directory = root;
  for (const part of parts.slice(0, -1)) directory = await directory.getDirectoryHandle(part, { create: true });
  const file = await directory.getFileHandle(parts[parts.length - 1], { create: true });
  const writable = await file.createWritable();
  const reader = response.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) await writable.write(value);
    }
    await writable.close();
  } catch (error) {
    await writable.abort?.();
    throw error;
  } finally {
    reader.releaseLock();
  }
}

export function ExportPanel({ projectId }: { projectId: string }) {
  const [files, setFiles] = useState<ApprovedExport[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const canPickFolder = typeof (window as PickerWindow).showDirectoryPicker === "function";

  const loadFiles = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch(`/api/reviews/projects/${encodeURIComponent(projectId)}/exports/approved`);
      const body = await response.json() as ApprovedExport[] & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Freigegebene Dateien konnten nicht geladen werden.");
      setFiles(body);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Freigegebene Dateien konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { void loadFiles(); }, [loadFiles]);

  async function exportToFolder() {
    const picker = (window as PickerWindow).showDirectoryPicker;
    if (!picker || exporting || files.length === 0) return;
    setExporting(true);
    setError("");
    setMessage("");
    try {
      const root = await picker.call(window);
      const audit = await apiFetch(`/api/reviews/projects/${encodeURIComponent(projectId)}/exports/audit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method: "folder", run_ids: files.map(file => file.run_id) })
      });
      const auditBody = await audit.json().catch(() => ({})) as { detail?: string };
      if (!audit.ok) throw new Error(auditBody.detail || "Export konnte nicht protokolliert werden.");
      let completed = 0;
      for (const file of files) {
        const response = await apiFetch(`/api/reviews/projects/${encodeURIComponent(projectId)}/exports/approved/${encodeURIComponent(file.run_id)}/content`);
        await writeStreamToFolder(root, file.relative_path, response);
        completed += 1;
        setMessage(`Export läuft: ${completed} von ${files.length} Dateien übertragen.`);
      }
      setMessage(`Export abgeschlossen: ${completed} freigegebene Dateien wurden im gewählten Ordner abgelegt. Die Originaldateien wurden nicht exportiert.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Ordnerexport fehlgeschlagen.");
    } finally {
      setExporting(false);
    }
  }

  return <section className="panel approved-export-panel" aria-label="Freigegebene Dateien exportieren">
    <div className="section-heading">
      <div><p className="eyebrow">NACH DER FREIGABE</p><h3>Freigegebene Dateien exportieren</h3></div>
      <button className="secondary-button" type="button" onClick={() => void loadFiles()} disabled={loading || exporting}>Aktualisieren</button>
    </div>
    <p className="field-help">Die Bereinigungsergebnisse verbleiben zunächst im internen Arbeitsbereich. Hier werden ausschließlich freigegebene und erfolgreich validierte Dateien angeboten.</p>
    {loading ? <p className="muted-message">Freigaben werden geladen …</p> : files.length === 0 ? <p className="muted-message">Noch keine exportierbaren Dateien freigegeben.</p> : <>
      <div className="approved-export-summary"><strong>{files.length} Dateien freigegeben</strong><span>{files.reduce((sum, file) => sum + file.output_bytes, 0).toLocaleString("de-DE")} Byte</span></div>
      <div className="approved-export-list">
        {files.map(file => <div className="approved-export-item" key={file.run_id}><span>{file.relative_path}</span><span>{file.output_bytes.toLocaleString("de-DE")} Byte</span></div>)}
      </div>
      <div className="rule-actions">
        {canPickFolder && <button className="primary-button" type="button" onClick={() => void exportToFolder()} disabled={exporting}>{exporting ? "Exportiert …" : "In Ordner auf diesem Gerät exportieren"}</button>}
        <a className="secondary-button" href={`/api/reviews/projects/${encodeURIComponent(projectId)}/exports/approved.zip`} download={`LogSanitizer-${projectId}-freigegeben.zip`} aria-disabled={exporting}>Als ZIP herunterladen</a>
      </div>
      {!canPickFolder && <p className="field-help">Der direkte Ordnerexport wird von diesem Browser nicht unterstützt. Verwende den ZIP-Download; er funktioniert auch im Netzwerkbetrieb.</p>}
    </>}
    {message && <p className="success-message" role="status">{message}</p>}
    {error && <p className="error-message" role="alert">{error}</p>}
  </section>;
}
