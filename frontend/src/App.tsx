import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { helpTopics } from "./help/content";
import { LoginGate } from "./LoginGate";
import { ReviewPanel } from "./ReviewPanel";
import { RulesPanel } from "./RulesPanel";
import { UserManagementPanel } from "./UserManagementPanel";

async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const method = (init.method || "GET").toUpperCase();
  const csrf = document.cookie.split("; ").find(item => item.startsWith("logsanitizer_csrf="))?.split("=").slice(1).join("=");
  const headers = new Headers(init.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  return fetch(input, { ...init, headers, credentials: "same-origin" });
}

type Tab = "overview" | "project" | "rules" | "review" | "users" | "help";
type ImportedFile = { id: string; project_id: string; display_name: string; relative_path?: string; size_bytes: number; modified_at: string; imported_at: string; state: string; format_hint?: string; detected_format?: string; format_override?: string | null };
type RuleProfile = { id: string; name: string; source_hint?: string | null };
type ImportMode = "file" | "folder";
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024 * 1024;
type FolderImportResult = { registered_count: number; skipped_count: number; registered_files: ImportedFile[]; issues: { file_name: string; reason: string }[]; limit_reached: boolean };
type FormatValidationResult = { file_id: string; format: string; valid: boolean; bytes_checked: number; error?: string };
type SanitizationJob = {
  id: string;
  status: "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
  phase: string;
  processed_bytes: number;
  total_bytes: number;
  lines_processed: number;
  error?: string;
  result?: { output_name: string; output_bytes: number; replacements: number; validated: boolean };
};
type Project = {
  id: string;
  name: string;
  description: string;
  status: "draft" | "active" | "archived";
  created_at: string;
  updated_at: string;
  output_directory: string;
};

function AppInner({ onLogout, user }: { onLogout: () => void; user: AuthUser }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [showProjectDialog, setShowProjectDialog] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [projectOutputDirectory, setProjectOutputDirectory] = useState("");
  const [savingOutputDirectory, setSavingOutputDirectory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [selectedUploadFiles, setSelectedUploadFiles] = useState<File[]>([]);
  const [importMode, setImportMode] = useState<ImportMode>("file");
  const [recursive, setRecursive] = useState(true);
  const [importedFiles, setImportedFiles] = useState<ImportedFile[]>([]);
  const [importing, setImporting] = useState(false);
  const [importMessage, setImportMessage] = useState("");
  useEffect(() => {
    const showHelp = (event: KeyboardEvent) => {
      if (event.key === "F1") {
        event.preventDefault();
        setTab("help");
      }
    };
    window.addEventListener("keydown", showHelp);
    return () => window.removeEventListener("keydown", showHelp);
  }, []);

  const [importIssues, setImportIssues] = useState<FolderImportResult["issues"]>([]);
  const [validatingFiles, setValidatingFiles] = useState<string[]>([]);
  const [validationResults, setValidationResults] = useState<Record<string, FormatValidationResult>>({});
  const [sanitizationJobs, setSanitizationJobs] = useState<Record<string, SanitizationJob>>({});
  const [sourceProfiles, setSourceProfiles] = useState<RuleProfile[]>([]);
  const [profilesLoaded, setProfilesLoaded] = useState(false);
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [profileSelections, setProfileSelections] = useState<Record<string, string>>({});
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [bulkFormatOverride, setBulkFormatOverride] = useState("");
  const [bulkProfileId, setBulkProfileId] = useState("");
  const [applyingBulkSettings, setApplyingBulkSettings] = useState(false);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchProgress, setBatchProgress] = useState<{ current: number; total: number; fileId: string; fileName: string } | null>(null);
  const batchStopRequestedRef = useRef(false);
  const batchJobIdRef = useRef<string | null>(null);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiFetch("/api/projects");
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
      const response = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}/files`);
      if (!response.ok) throw new Error("Dateiliste konnte nicht geladen werden.");
      setImportedFiles(await response.json() as ImportedFile[]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Dateiliste konnte nicht geladen werden.");
    }
  }, []);

  useEffect(() => {
    setProjectOutputDirectory(selectedProject?.output_directory || "");
  }, [selectedProject]);

  useEffect(() => {
    if (selectedProject) void loadImportedFiles(selectedProject.id);
    else setImportedFiles([]);
  }, [selectedProject?.id, loadImportedFiles]);

  async function registerSources(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const path = sourcePath.trim();
    if (!selectedProject || importing || (!selectedUploadFiles.length && !path)) return;

    if (selectedUploadFiles.length) {
      setImporting(true);
      setError("");
      setImportMessage("");
      setImportIssues([]);
      try {
        const formData = new FormData();
        selectedUploadFiles.forEach(file => formData.append("files", file, file.name));
        formData.append("relative_paths", JSON.stringify(selectedUploadFiles.map(file => file.webkitRelativePath || file.name)));
        const response = await apiFetch(`/api/projects/${encodeURIComponent(selectedProject.id)}/files/upload`, { method: "POST", body: formData });
        const body = await response.json() as FolderImportResult & { detail?: string };
        if (!response.ok) throw new Error(body.detail || "Dateien konnten nicht übernommen werden.");
        setImportedFiles(current => {
          const byId = new Map(current.map(file => [file.id, file]));
          body.registered_files.forEach(file => byId.set(file.id, file));
          return [...byId.values()];
        });
        setImportIssues(body.issues);
        const bytes = selectedUploadFiles.reduce((sum, file) => sum + file.size, 0);
        setImportMessage(`Übernommen: ${body.registered_count}; übersprungen: ${body.skipped_count}; ausgewählt: ${selectedUploadFiles.length} Dateien (${bytes.toLocaleString("de-DE")} Byte).${body.limit_reached ? " Das Limit von 5.000 Dateien wurde erreicht." : ""} Quelldateien bleiben unverändert.`);
        setSelectedUploadFiles([]);
        setSourcePath("");
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Dateien konnten nicht übernommen werden.");
      } finally {
        setImporting(false);
      }
      return;
    }
    if (!path) return;

    const isFolder = importMode === "folder";
    const endpoint = isFolder
      ? `/api/projects/${encodeURIComponent(selectedProject.id)}/files/import-folder`
      : `/api/projects/${encodeURIComponent(selectedProject.id)}/files`;

    setImporting(true);
    setError("");
    setImportMessage("");
    setImportIssues([]);
    try {
      const response = await apiFetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(isFolder ? { path, recursive } : { path })
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { detail?: string };
        throw new Error(body.detail || (isFolder ? "Ordner konnte nicht importiert werden." : "Datei konnte nicht registriert werden."));
      }

      if (isFolder) {
        const result = await response.json() as FolderImportResult;
        setImportedFiles(current => {
          const byId = new Map(current.map(file => [file.id, file]));
          result.registered_files.forEach(file => byId.set(file.id, file));
          return [...byId.values()];
        });
        setImportIssues(result.issues);
        setImportMessage(`Registriert: ${result.registered_count}; übersprungen: ${result.skipped_count}.${result.limit_reached ? " Das Dateilimit wurde erreicht." : ""} Es wurden keine Log-Inhalte gelesen.`);
      } else {
        const file = await response.json() as ImportedFile;
        setImportedFiles(current => [...current.filter(item => item.id !== file.id), file]);
        setImportMessage("Datei registriert. Der Inhalt wurde nicht verarbeitet.");
      }
      setSourcePath("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Dateien konnten nicht registriert werden.");
    } finally {
      setImporting(false);
    }
  }

  async function detectFileFormat(file: ImportedFile) {
    if (!selectedProject) return;
    setError("");
    try {
      const response = await apiFetch(`/api/projects/${encodeURIComponent(selectedProject.id)}/files/${encodeURIComponent(file.id)}/detect-format`, { method: "POST" });
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
      const response = await apiFetch(`/api/projects/${encodeURIComponent(selectedProject.id)}/files/${encodeURIComponent(file.id)}/validate-format`, { method: "POST" });
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

  async function loadSourceProfiles() {
    if (profilesLoaded || loadingProfiles) return;
    setLoadingProfiles(true);
    try {
      const response = await apiFetch("/api/rules/config");
      if (!response.ok) throw new Error("Quellprofile konnten nicht geladen werden.");
      const body = await response.json() as { profiles?: RuleProfile[] };
      setSourceProfiles(body.profiles || []);
      setProfilesLoaded(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Quellprofile konnten nicht geladen werden.");
    } finally {
      setLoadingProfiles(false);
    }
  }

  async function startSanitization(file: ImportedFile, waitForCompletion = false): Promise<SanitizationJob | null> {
    if (!selectedProject || !projectOutputDirectory.trim() || projectOutputDirectory.trim() !== (selectedProject?.output_directory || "") || sanitizationJobs[file.id] && ["queued", "running", "cancelling"].includes(sanitizationJobs[file.id].status)) return null;
    const separator = projectOutputDirectory.includes("\\") ? "\\" : "/";
    const relativePath = (file.relative_path || file.display_name).replace(/[\\/]+/g, separator);
    const outputPath = projectOutputDirectory.replace(/[\\/]+$/, "") + separator + relativePath;
    setError("");
    try {
      const response = await apiFetch(`/api/projects/${encodeURIComponent(selectedProject.id)}/files/${encodeURIComponent(file.id)}/sanitize-jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output_path: outputPath, profile_id: profileSelections[file.id] || null })
      });
      const body = await response.json() as { id?: string; detail?: string };
      if (!response.ok || !body.id) throw new Error(body.detail || "Bereinigung konnte nicht gestartet werden.");
      setSanitizationJobs(current => ({ ...current, [file.id]: { id: body.id!, status: "queued", phase: "queued", processed_bytes: 0, total_bytes: file.size_bytes, lines_processed: 0 } }));
      if (waitForCompletion) {
        batchJobIdRef.current = body.id;
        try { return await pollSanitizationJob(file, body.id); }
        finally { batchJobIdRef.current = null; }
      }
      void pollSanitizationJob(file, body.id);
      return { id: body.id, status: "queued", phase: "queued", processed_bytes: 0, total_bytes: file.size_bytes, lines_processed: 0 };
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Bereinigung konnte nicht gestartet werden.");
      return null;
    }
  }

  async function pollSanitizationJob(file: ImportedFile, jobId: string): Promise<SanitizationJob | null> {
    if (!selectedProject) return null;
    try {
      const url = `/api/projects/${encodeURIComponent(selectedProject.id)}/files/${encodeURIComponent(file.id)}/sanitize-jobs/${encodeURIComponent(jobId)}`;
      const response = await apiFetch(url);
      const body = await response.json() as SanitizationJob & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Fortschritt konnte nicht gelesen werden.");
      setSanitizationJobs(current => ({ ...current, [file.id]: body }));
      if (["queued", "running", "cancelling"].includes(body.status)) {
        await new Promise(resolve => window.setTimeout(resolve, 500));
        return await pollSanitizationJob(file, jobId);
      }
      if (body.status === "completed") {
        setImportMessage(`Bereinigung für ${file.display_name} abgeschlossen und validiert: ${body.result?.output_bytes.toLocaleString("de-DE")} Byte Ausgabe, ${body.result?.replacements} Ersetzungen.`);
      } else if (body.status === "cancelled") {
        setImportMessage(`Bereinigung für ${file.display_name} abgebrochen. Temporäre Ausgabe wurde verworfen.`);
      } else if (body.error) {
        setError(body.error);
      }
      return body;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Fortschritt konnte nicht gelesen werden.");
      return null;
    }
  }

  async function startBatchSanitization() {
    if (!selectedProject || batchRunning) return;
    const batchFiles = importedFiles.filter(file => selectedFileIds.includes(file.id));
    if (!batchFiles.length) return;
    const invalidFile = batchFiles.find(file =>
      !projectOutputDirectory.trim() ||
      !["text", "jsonl", "json"].includes(file.format_override || file.detected_format || "") ||
      Boolean(sanitizationJobs[file.id] && ["queued", "running", "cancelling"].includes(sanitizationJobs[file.id].status))
    );
    if (invalidFile) {
      setError(`Bitte prüfe Format, gespeicherten Ausgabeordner und Laufstatus für „${invalidFile.display_name}“.`);
      return;
    }
    const normalizedPaths = batchFiles.map(file => (file.relative_path || file.display_name).replaceAll("\\", "/").toLocaleLowerCase("en-US"));
    if (new Set(normalizedPaths).size !== normalizedPaths.length) {
      setError("Mehrere Dateien besitzen denselben relativen Pfad und würden sich im Ausgabeordner überschreiben.");
      return;
    }

    setError("");
    setBatchRunning(true);
    batchStopRequestedRef.current = false;
    let completed = 0;
    let failed = 0;
    let cancelled = 0;
    try {
      for (let index = 0; index < batchFiles.length; index += 1) {
        if (batchStopRequestedRef.current) break;
        const file = batchFiles[index];
        setBatchProgress({ current: index + 1, total: batchFiles.length, fileId: file.id, fileName: file.display_name });
        const result = await startSanitization(file, true);
        if (result?.status === "completed") completed += 1;
        else if (result?.status === "cancelled") {
          cancelled += 1;
          batchStopRequestedRef.current = true;
        } else failed += 1;
      }
      const notStarted = batchFiles.length - completed - failed - cancelled;
      setImportMessage(`Mehrdatei-Lauf beendet: ${completed} erfolgreich validiert, ${failed} fehlgeschlagen, ${cancelled} abgebrochen, ${notStarted} nicht gestartet. Jede erfolgreiche Datei ist einzeln in Prüfung & Verlauf verfügbar.`);
      setSelectedFileIds([]);
    } finally {
      batchJobIdRef.current = null;
      setBatchRunning(false);
      setBatchProgress(null);
    }
  }

  function stopBatchSanitization() {
    batchStopRequestedRef.current = true;
    const currentFile = batchProgress && importedFiles.find(file => file.id === batchProgress.fileId);
    if (currentFile && batchJobIdRef.current) void cancelSanitization(currentFile, batchJobIdRef.current);
  }

  async function cancelSanitization(file: ImportedFile, jobIdOverride?: string) {
    if (!selectedProject) return;
    if (batchRunning) batchStopRequestedRef.current = true;
    const job = sanitizationJobs[file.id];
    const jobId = jobIdOverride || job?.id;
    if (!jobId || job && !["queued", "running"].includes(job.status)) return;
    try {
      const response = await apiFetch(`/api/projects/${encodeURIComponent(selectedProject.id)}/files/${encodeURIComponent(file.id)}/sanitize-jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
      const body = await response.json() as { status?: string; detail?: string };
      if (!response.ok) throw new Error(body.detail || "Abbruch konnte nicht angefordert werden.");
      if (job) setSanitizationJobs(current => ({ ...current, [file.id]: { ...job, status: "cancelling" } }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Abbruch konnte nicht angefordert werden.");
    }
  }

  async function setFileFormatOverride(file: ImportedFile, formatOverride: string): Promise<boolean> {
    if (!selectedProject) return false;
    setError("");
    try {
      const response = await apiFetch(`/api/projects/${encodeURIComponent(selectedProject.id)}/files/${encodeURIComponent(file.id)}/format`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format_override: formatOverride || null })
      });
      const body = await response.json() as ImportedFile & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Format-Auswahl konnte nicht gespeichert werden.");
      setImportedFiles(current => current.map(item => item.id === file.id ? body : item));
      setImportMessage(formatOverride ? `Manuelles Format für ${file.display_name} gespeichert: ${formatOverride}.` : `Manuelle Format-Auswahl für ${file.display_name} entfernt.`);
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Format-Auswahl konnte nicht gespeichert werden.");
      return false;
    }
  }

  async function applySettingsToAllFiles() {
    if (applyingBulkSettings || batchRunning || importedFiles.length === 0) return;
    setApplyingBulkSettings(true);
    setError("");
    try {
      let successful = 0;
      for (const file of importedFiles) {
        if (await setFileFormatOverride(file, bulkFormatOverride)) successful += 1;
        else break;
      }
      if (successful !== importedFiles.length) return;
      setProfileSelections(current => {
        const next = { ...current };
        importedFiles.forEach(file => { next[file.id] = bulkProfileId; });
        return next;
      });
      setImportMessage(`Format und Quellprofil wurden auf alle ${importedFiles.length} Dateien angewendet.`);
    } finally {
      setApplyingBulkSettings(false);
    }
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectName.trim() || saving) return;
    setSaving(true);
    setError("");
    try {
      const response = await apiFetch("/api/projects", {
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
      setShowProjectDialog(false);
      setTab("project");
      setProjectName("");
      setProjectDescription("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unbekannter Fehler beim Speichern.");
    } finally {
      setSaving(false);
    }
  }

  async function saveProjectOutputDirectory() {
    if (!selectedProject || savingOutputDirectory) return;
    setSavingOutputDirectory(true);
    setError("");
    try {
      const response = await apiFetch("/api/projects/" + encodeURIComponent(selectedProject.id) + "/output-directory", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output_directory: projectOutputDirectory })
      });
      const body = await response.json() as Project & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Ausgabeordner konnte nicht gespeichert werden.");
      setSelectedProject(body);
      setProjects(current => current.map(project => project.id === body.id ? body : project));
      setProjectOutputDirectory(body.output_directory);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Ausgabeordner konnte nicht gespeichert werden.");
    } finally { setSavingOutputDirectory(false); }
  }

  async function openProject(id: string) {
    setError("");
    try {
      const response = await apiFetch(`/api/projects/${encodeURIComponent(id)}`);
      if (!response.ok) throw new Error("Projekt konnte nicht geöffnet werden.");
      setSelectedProject(await response.json() as Project);
      setTab("project");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unbekannter Fehler beim Öffnen.");
    }
  }

  const selectableFiles = importedFiles.filter(file =>
    ["text", "jsonl", "json"].includes(file.format_override || file.detected_format || "") &&
    !(sanitizationJobs[file.id] && ["queued", "running", "cancelling"].includes(sanitizationJobs[file.id].status))
  );
  const selectedBatchFiles = importedFiles.filter(file => selectedFileIds.includes(file.id));
  const batchHasDuplicateOutputs = new Set(selectedBatchFiles.map(file =>
    (file.relative_path || file.display_name).replaceAll("\\", "/").toLocaleLowerCase("en-US")
  )).size !== selectedBatchFiles.length;
  const batchReady = selectedBatchFiles.length > 0 && selectedBatchFiles.every(file =>
    Boolean(projectOutputDirectory.trim()) && projectOutputDirectory.trim() === (selectedProject?.output_directory || "") && ["text", "jsonl", "json"].includes(file.format_override || file.detected_format || "") &&
    !(sanitizationJobs[file.id] && ["queued", "running", "cancelling"].includes(sanitizationJobs[file.id].status))
  );

  const projectWorkspace = selectedProject ? <section className="panel selected-project" aria-label="Geöffnetes Projekt" aria-live="polite">
        <div className="section-heading"><div><p className="eyebrow">GEÖFFNETES PROJEKT</p><h3>{selectedProject.name}</h3></div><button className="secondary-button" type="button" onClick={() => setTab("rules")}>Regeln &amp; Quellprofile bearbeiten</button></div>
        <p>{selectedProject.description || "Keine Beschreibung hinterlegt."}</p>
        {error && <p className="error-message" role="alert">{error}</p>}
        <div className="project-output-setting"><label htmlFor="project-output-directory">Ausgabeordner<input id="project-output-directory" value={projectOutputDirectory} onChange={event => setProjectOutputDirectory(event.target.value)} placeholder="Absoluter Ordnerpfad" maxLength={4096} /></label><button className="secondary-button" type="button" disabled={savingOutputDirectory || projectOutputDirectory.trim() === (selectedProject.output_directory || "")} onClick={() => void saveProjectOutputDirectory()}>{savingOutputDirectory ? "Speichert …" : "Ausgabeordner speichern"}</button><p className="field-help">Alle Ergebnisse werden hier unter ihrem Originaldateinamen abgelegt. Der Ordner muss bereits existieren.</p></div>
        <p className="field-help">Dateien werden zunächst registriert. Die Bereinigung startest du anschließend ausdrücklich pro Datei; die Quelldateien bleiben unverändert.</p>
        <form className="import-source-form" onSubmit={event => void registerSources(event)} aria-label="Dateien hinzufügen">
          <div className="import-source-fields">
            <label htmlFor="import-mode">Quelle
              <select id="import-mode" value={importMode} onChange={event => { setImportMode(event.target.value as ImportMode); setSelectedUploadFiles([]); }}>
                <option value="file">Dateien auswählen</option>
                <option value="folder">Ordner auswählen</option>
              </select>
            </label>
            <label htmlFor="source-files">{importMode === "folder" ? "Lokaler Ordner" : "Lokale Dateien"}
              <input
                id="source-files"
                type="file"
                multiple
                onChange={event => { const files = Array.from(event.target.files || []); setSelectedUploadFiles(files); setError(files.some(file => file.size > MAX_UPLOAD_BYTES) ? "Mindestens eine Datei überschreitet das Limit von 5 GiB." : ""); }}
                ref={element => { if (element && importMode === "folder") element.setAttribute("webkitdirectory", ""); else element?.removeAttribute("webkitdirectory"); }}
              />
            </label>
            <span className="field-help">{selectedUploadFiles.length ? `${selectedUploadFiles.length} Dateien · ${selectedUploadFiles.reduce((sum, file) => sum + file.size, 0).toLocaleString("de-DE")} Byte` : "Mehrfachauswahl möglich"}</span>
          </div>
          {selectedUploadFiles.length > 0 && <p className="selected-upload-list" aria-live="polite">{selectedUploadFiles.slice(0, 5).map(file => file.webkitRelativePath || file.name).join(" · ")}{selectedUploadFiles.length > 5 ? ` · +${selectedUploadFiles.length - 5} weitere` : ""}</p>}
          <div className="import-source-footer">
            <p className="field-help">Dateien werden in den Projektarbeitsbereich kopiert, blockweise übertragen und dort verarbeitet. Maximal 5 GiB je Datei und 5.000 Dateien je Auswahl. Originaldateien bleiben unverändert.</p>
            <button className="primary-button" type="submit" disabled={(!selectedUploadFiles.length && !sourcePath.trim()) || selectedUploadFiles.some(file => file.size > MAX_UPLOAD_BYTES) || importing}>{importing ? "Übernimmt …" : "Auswahl übernehmen"}</button>
          </div>
          <details className="path-import-fallback">
            <summary>Alternativ: Backend-Pfad manuell registrieren</summary>
            <div className="import-source-fields">
              <label htmlFor="source-path">{importMode === "folder" ? "Absoluter Ordnerpfad" : "Absoluter Dateipfad"}
                <input id="source-path" value={sourcePath} onChange={event => setSourcePath(event.target.value)} placeholder={importMode === "folder" ? "z. B. /var/log/my-service" : "z. B. /var/log/service.log"} maxLength={4096} />
              </label>
              {importMode === "folder" && <label className="import-recursive-option" htmlFor="recursive"><input id="recursive" type="checkbox" checked={recursive} onChange={event => setRecursive(event.target.checked)} /> Unterordner einbeziehen</label>}
            </div>
            <p className="field-help">Dieser Fallback bezieht sich auf das Dateisystem des Backend-Rechners. Die Registrierung liest keine Log-Inhalte.</p>
          </details>
        </form>
        {importMessage && <p className="success-message" role="status">{importMessage}</p>}
        {importIssues.length > 0 && <div className="import-issues" aria-label="Übersprungene Einträge"><h4>Übersprungene Einträge ({importIssues.length})</h4><ul>{importIssues.map((issue, index) => <li key={`${issue.file_name}-${index}`}><strong>{issue.file_name}</strong>: {issue.reason}</li>)}</ul></div>}
        <div className="section-heading file-list-heading"><h4>Registrierte Dateien ({importedFiles.length})</h4><button className="secondary-button" type="button" onClick={() => void loadImportedFiles(selectedProject.id)}>Liste aktualisieren</button></div>
        <div className="bulk-file-settings" aria-label="Einstellungen für alle Dateien">
          <strong>Gemeinsame Einstellungen</strong>
          <label>Format für alle Dateien
            <select aria-label="Format für alle Dateien" value={bulkFormatOverride} onChange={event => setBulkFormatOverride(event.target.value)} disabled={batchRunning || applyingBulkSettings}>
              <option value="">Automatische Erkennung verwenden</option><option value="text">Text</option><option value="json">JSON</option><option value="jsonl">JSON Lines</option><option value="xml">XML</option><option value="csv">CSV</option><option value="unknown">Unbekannt</option>
            </select>
          </label>
          <label>Quellprofil für alle Dateien
            <select aria-label="Quellprofil für alle Dateien" value={bulkProfileId} onFocus={() => void loadSourceProfiles()} onChange={event => setBulkProfileId(event.target.value)} disabled={batchRunning || applyingBulkSettings}>
              <option value="">Globale Regeln (kein Quellprofil)</option>{sourceProfiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
            </select>
          </label>
          <button className="secondary-button" type="button" onClick={() => void applySettingsToAllFiles()} disabled={batchRunning || applyingBulkSettings || importedFiles.length === 0}>{applyingBulkSettings ? "Wird angewendet …" : "Auf alle Dateien anwenden"}</button>
        </div>
        {importedFiles.length > 0 && <div className="batch-toolbar" aria-label="Mehrdatei-Bereinigung">
          <div className="batch-selection-actions">
            <button className="secondary-button" type="button" onClick={() => setSelectedFileIds(selectableFiles.map(file => file.id))} disabled={batchRunning || selectableFiles.length === 0}>Geeignete auswählen ({selectableFiles.length})</button>
            <button className="secondary-button" type="button" onClick={() => setSelectedFileIds([])} disabled={batchRunning || selectedFileIds.length === 0}>Auswahl aufheben</button>
            <span>{selectedFileIds.length} ausgewählt</span>
          </div>
          <button className="primary-button" type="button" onClick={() => void startBatchSanitization()} disabled={batchRunning || !batchReady}>Ausgewählte Dateien nacheinander bereinigen</button>
          <p className="field-help">Alle bereinigten Dateien werden im Ausgabeordner dieses Projekts unter ihrem Originalnamen gespeichert. Die Verarbeitung läuft nacheinander; Projekt-Mappings bleiben dateiübergreifend identisch.</p>
          {batchHasDuplicateOutputs && selectedBatchFiles.length > 1 && <p className="error-message" role="alert">Mehrere Quelldateien haben denselben Namen und würden sich im Ausgabeordner überschreiben.</p>}
        </div>}
        {batchRunning && batchProgress && <div className="batch-progress" role="status">
          <strong>Mehrdatei-Lauf · Datei {batchProgress.current} von {batchProgress.total}</strong>
          <span>Aktuell: {batchProgress.fileName}</span>
          <button className="secondary-button" type="button" onClick={stopBatchSanitization}>Stapel abbrechen</button>
        </div>}
        {importedFiles.length === 0 ? <p className="muted-message">Noch keine Dateien registriert.</p> : <div className="registered-files-table-wrap">
          <table className="registered-files-table">
            <thead><tr><th scope="col">Datei</th><th scope="col">Größe</th><th scope="col">Format</th><th scope="col">Quellprofil</th><th scope="col">Status</th><th scope="col">Aktionen</th></tr></thead>
            <tbody>{importedFiles.map(file => {
              const relativePath = file.relative_path || file.display_name;
              const validation = validationResults[file.id];
              const job = sanitizationJobs[file.id];
              const effectiveFormat = file.format_override || file.detected_format || "unknown";
              const activeJob = Boolean(job && ["queued", "running", "cancelling"].includes(job.status));
              return <tr key={file.id}>
                <td className="registered-file-name">
                  <label className="batch-file-select"><input type="checkbox" aria-label={`Für Stapel auswählen: ${relativePath}`} checked={selectedFileIds.includes(file.id)} disabled={batchRunning || activeJob || !selectableFiles.some(item => item.id === file.id)} onChange={event => setSelectedFileIds(current => event.target.checked ? [...current, file.id] : current.filter(id => id !== file.id))} /><span title={relativePath}>{relativePath}</span></label>
                  <span className="table-file-state">{file.state === "registered" ? "Registriert" : file.state}</span>
                </td>
                <td className="file-size">{file.size_bytes.toLocaleString("de-DE")} Byte</td>
                <td>
                  <select aria-label={`Format für ${relativePath}`} value={file.format_override || ""} onChange={event => void setFileFormatOverride(file, event.target.value)} disabled={batchRunning || activeJob || applyingBulkSettings}>
                    <option value="">Automatisch ({effectiveFormat.toUpperCase()})</option><option value="text">Text</option><option value="json">JSON</option><option value="jsonl">JSON Lines</option><option value="xml">XML</option><option value="csv">CSV</option><option value="unknown">Unbekannt</option>
                  </select>
                  <span className="table-subtext">Erkannt: {(file.detected_format || "noch nicht geprüft").toUpperCase()} · Endung: {(file.format_hint || "unbekannt").toUpperCase()}</span>
                </td>
                <td>
                  <select aria-label={`Quellprofil für ${relativePath}`} value={profileSelections[file.id] || ""} onFocus={() => void loadSourceProfiles()} onChange={event => setProfileSelections(current => ({ ...current, [file.id]: event.target.value }))} disabled={batchRunning || activeJob}>
                    <option value="">Globale Regeln</option>{sourceProfiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
                  </select>
                </td>
                <td className="file-status-cell">
                  <span className={validation ? (validation.valid ? "file-state file-state-ready" : "file-state file-state-error") : "file-state"}>{validation ? (validation.valid ? "Validiert" : "Ungültig") : "Nicht validiert"}</span>
                  {validation && <span className="table-subtext">{validation.format} · {validation.bytes_checked.toLocaleString("de-DE")} Byte{validation.error ? ` · ${validation.error}` : ""}</span>}
                  {job && <span className={`file-state job-state-${job.status}`}>{({ queued: "Wartet", running: "Läuft", cancelling: "Abbruch angefordert", completed: "Abgeschlossen", failed: "Fehlgeschlagen", cancelled: "Abgebrochen", interrupted: "Unterbrochen" } as Record<string, string>)[job.status]}</span>}
                  {job && ["queued", "running"].includes(job.status) && <span className="table-subtext">{job.processed_bytes.toLocaleString("de-DE")} / {job.total_bytes.toLocaleString("de-DE")} Byte</span>}
                </td>
                <td className="file-row-actions">
                  <button className="secondary-button" type="button" onClick={() => void detectFileFormat(file)} disabled={batchRunning || activeJob}>Erkennen</button>
                  <button className="secondary-button" type="button" onClick={() => void validateFileFormat(file)} disabled={batchRunning || activeJob || validatingFiles.includes(file.id)}>{validatingFiles.includes(file.id) ? "Prüft …" : "Validieren"}</button>
                  {job && ["queued", "running"].includes(job.status) ? <button className="secondary-button" type="button" onClick={() => void cancelSanitization(file)}>Abbrechen</button> : job?.status === "completed" ? <button className="secondary-button" type="button" onClick={() => setTab("review")}>Prüfen</button> : <button className="primary-button" type="button" onClick={() => void startSanitization(file)} disabled={batchRunning || !projectOutputDirectory.trim() || !["text", "jsonl", "json"].includes(effectiveFormat) || activeJob}>Bereinigen</button>}
                </td>
              </tr>;
            })}</tbody>
          </table>
        </div>
      </section> : <p className="muted-message">Bitte zuerst ein Projekt auf der Startseite öffnen.</p>;

  return <main className="app-shell">
    <header className="topbar">
      <div><p className="eyebrow">LOKAL · OFFLINE-FIRST</p><h1>LogSanitizer</h1></div>
      <nav aria-label="Hauptnavigation" className="nav-tabs">
        <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>Startseite</button>
        {selectedProject && <button className={tab === "project" ? "active" : ""} onClick={() => setTab("project")}>Projekt</button>}
        {user.roles.some(role => ["admin", "rule_owner"].includes(role)) && <button className={tab === "rules" ? "active" : ""} onClick={() => setTab("rules")}>Regeln</button>}
        {user.roles.includes("admin") && <button className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>Benutzer</button>}
        <button className={tab === "review" ? "active" : ""} onClick={() => setTab("review")}>Prüfung &amp; Verlauf</button>
        <button className={tab === "help" ? "active" : ""} onClick={() => setTab("help")}>Hilfe</button>
      </nav>
      <button type="button" onClick={async () => { await apiFetch("/api/auth/logout", { method: "POST" }); onLogout(); }}>Abmelden</button>
    </header>
    {tab === "overview" ? <>
      <section className="hero">
        <span className="status-pill"><span className="status-dot" /> Lokaler Arbeitsbereich</span>
        <h2>Projekte verwalten.</h2>
        <p>Wähle ein bestehendes Projekt oder lege ein neues an.</p>
      </section>
      {error && <p className="error-message" role="alert">{error}</p>}
      <section className="projects-section home-projects">
        <div className="section-heading"><div><p className="eyebrow">ARBEITSBEREICH</p><h3>Projekte</h3></div><div className="rule-actions"><button className="secondary-button" type="button" onClick={() => void loadProjects()} disabled={loading}>{loading ? "Lädt …" : "Aktualisieren"}</button><button className="primary-button" type="button" onClick={() => setShowProjectDialog(true)}>Neues Projekt</button></div></div>
        {loading ? <p className="muted-message">Projektliste wird geladen …</p> : projects.length === 0 ? <p className="muted-message">Noch keine Projekte vorhanden. Über „Neues Projekt“ kannst du ein Projekt anlegen.</p> : <div className="project-list">{projects.map(project => <article className="project-card" key={project.id}>
          <div><h4>{project.name}</h4><p>{project.description || "Keine Beschreibung"}</p><span className="project-meta">Erstellt: {new Date(project.created_at).toLocaleString("de-DE")} · Status: {project.status === "draft" ? "Entwurf" : project.status}</span></div><button className="secondary-button" onClick={() => void openProject(project.id)}>Öffnen</button>
        </article>)}</div>}
      </section>
    </> : tab === "project" ? projectWorkspace : tab === "rules" ? <RulesPanel onBackToProject={() => setTab(selectedProject ? "project" : "overview")} /> : tab === "review" ? <ReviewPanel roles={user.roles} onBackToProject={() => setTab(selectedProject ? "project" : "overview")} /> : tab === "users" ? <UserManagementPanel currentUser={user} /> : <section className="help-page"><p className="eyebrow">OFFLINE-HANDBUCH</p><h2>Hilfe und Grundlagen</h2><p className="intro">Diese Hilfe ist vollständig lokal eingebunden. Drücke jederzeit F1, um sie zu öffnen. Die Hinweise funktionieren ohne Internetverbindung.</p>
      <div className="help-list">{helpTopics.map(topic => <article className="help-topic" key={topic.id}><h3>{topic.title}</h3><p>{topic.summary}</p><ul>{topic.steps.map(step => <li key={step}>{step}</li>)}</ul></article>)}</div>
    </section>}
    {showProjectDialog && <div className="modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setShowProjectDialog(false); }}>
      <section className="project-dialog" role="dialog" aria-modal="true" aria-labelledby="project-dialog-title">
        <div className="section-heading"><div><p className="eyebrow">PROJEKT ANLEGEN</p><h3 id="project-dialog-title">Neues Projekt</h3></div><button className="secondary-button" type="button" onClick={() => setShowProjectDialog(false)}>Schließen</button></div>
        <form onSubmit={event => void createProject(event)}>
          {error && <p className="error-message" role="alert">{error}</p>}
          <label htmlFor="project-name">Projektname</label>
          <input id="project-name" value={projectName} onChange={event => setProjectName(event.target.value)} placeholder="z. B. Analyse Anwendungsfehler" maxLength={80} required autoFocus />
          <label htmlFor="project-description">Beschreibung <span className="optional-label">(optional)</span></label>
          <input id="project-description" value={projectDescription} onChange={event => setProjectDescription(event.target.value)} placeholder="Kurze Beschreibung" maxLength={500} />
          <p className="field-help">Das Projekt wird lokal angelegt. Anschließend wechselst du direkt in den Projektbereich.</p>
          <div className="rule-actions"><button className="secondary-button" type="button" onClick={() => setShowProjectDialog(false)}>Abbrechen</button><button className="primary-button" type="submit" disabled={!projectName.trim() || saving}>{saving ? "Speichert …" : "Projekt erstellen"}</button></div>
        </form>
      </section>
    </div>}
    <footer><span>LogSanitizer · 0.1.0-dev</span><span>Keine echten oder vertraulichen Logs in diesem Entwicklungsstand verarbeiten.</span></footer>
  </main>;
}

type AuthUser = { id: number; username: string; roles: string[] };
export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    if (import.meta.env.MODE === "test") {
      setUser({ id: 1, username: "test-user", roles: ["admin", "operator", "reviewer", "approver"] });
      setChecking(false);
      return;
    }
    void fetch("/api/auth/me", { credentials: "same-origin" }).then(async response => {
      if (response.ok) setUser(await response.json() as AuthUser);
    }).catch(() => undefined).finally(() => setChecking(false));
  }, []);
  if (checking) return <main className="app-shell"><p role="status">Anmeldestatus wird geprüft …</p></main>;
  if (!user) return <LoginGate onLogin={setUser} />;
  return <AppInner onLogout={() => setUser(null)} user={user} />;
}