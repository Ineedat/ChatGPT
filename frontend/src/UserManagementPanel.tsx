import { FormEvent, useCallback, useEffect, useState } from "react";

type ManagedUser = {
  id: number;
  username: string;
  enabled: boolean;
  created_at: number;
  external: boolean;
  roles: string[];
};

type AuthUser = { id: number; username: string; roles: string[] };

const ROLE_OPTIONS = [
  { id: "admin", label: "Administrator" },
  { id: "operator", label: "Bearbeiter" },
  { id: "rule_owner", label: "Regelverantwortlicher" },
  { id: "reviewer", label: "Prüfer" },
  { id: "approver", label: "Freigeber" },
];

async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const method = (init.method || "GET").toUpperCase();
  const csrf = document.cookie.split("; ").find(item => item.startsWith("logsanitizer_csrf="))?.split("=").slice(1).join("=");
  const headers = new Headers(init.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrf) {
    headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  return fetch(input, { ...init, headers, credentials: "same-origin" });
}

export function UserManagementPanel({ currentUser }: { currentUser: AuthUser }) {
  const [view, setView] = useState<"list" | "create">("list");
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [roleDrafts, setRoleDrafts] = useState<Record<number, string[]>>({});
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [newRoles, setNewRoles] = useState<string[]>(["operator"]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch("/api/auth/users");
      const body = await response.json() as ManagedUser[] | { detail?: string };
      if (!response.ok || !Array.isArray(body)) {
        throw new Error(!Array.isArray(body) ? body.detail || "Benutzer konnten nicht geladen werden." : "Benutzer konnten nicht geladen werden.");
      }
      setUsers(body);
      setRoleDrafts(Object.fromEntries(body.map(user => [user.id, user.roles])));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Benutzer konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadUsers(); }, [loadUsers]);

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!username.trim() || password.length < 12 || newRoles.length === 0 || saving) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch("/api/auth/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password, roles: newRoles }),
      });
      const body = await response.json() as ManagedUser & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Benutzer konnte nicht angelegt werden.");
      setUsername("");
      setPassword("");
      setNewRoles(["operator"]);
      setMessage(`Benutzer „${body.username}“ wurde angelegt.`);
      setView("list");
      await loadUsers();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Benutzer konnte nicht angelegt werden.");
    } finally {
      setSaving(false);
    }
  }

  async function saveRoles(user: ManagedUser) {
    const roles = roleDrafts[user.id] || [];
    if (!roles.length) {
      setError("Jedem Benutzer muss mindestens eine Rolle zugewiesen sein.");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`/api/auth/users/${user.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ roles }),
      });
      const body = await response.json() as ManagedUser & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Rollen konnten nicht gespeichert werden.");
      setMessage(`Rollen für „${user.username}“ wurden gespeichert.`);
      await loadUsers();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Rollen konnten nicht gespeichert werden.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleEnabled(user: ManagedUser) {
    const action = user.enabled ? "deaktivieren" : "aktivieren";
    if (!window.confirm(`Benutzer „${user.username}“ wirklich ${action}?`)) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`/api/auth/users/${user.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !user.enabled }),
      });
      const body = await response.json() as ManagedUser & { detail?: string };
      if (!response.ok) throw new Error(body.detail || `Benutzer konnte nicht ${action} werden.`);
      setMessage(`Benutzer „${user.username}“ wurde ${user.enabled ? "deaktiviert" : "aktiviert"}.`);
      await loadUsers();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `Benutzer konnte nicht ${action} werden.`);
    } finally {
      setSaving(false);
    }
  }

  async function deleteUser(user: ManagedUser) {
    if (!window.confirm(`Benutzer „${user.username}“ endgültig löschen? Dieser Vorgang kann nicht rückgängig gemacht werden.`)) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(`/api/auth/users/${user.id}`, { method: "DELETE" });
      const body = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Benutzer konnte nicht gelöscht werden.");
      setMessage(`Benutzer „${user.username}“ wurde gelöscht.`);
      await loadUsers();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Benutzer konnte nicht gelöscht werden.");
    } finally {
      setSaving(false);
    }
  }

  const toggleRole = (id: number, role: string, checked: boolean) => {
    setRoleDrafts(current => {
      const roles = current[id] || [];
      return { ...current, [id]: checked ? [...roles, role] : roles.filter(item => item !== role) };
    });
  };

  return <section className="user-admin-page">
    <div className="section-heading">
      <div><p className="eyebrow">ADMINISTRATION</p><h2>Benutzerverwaltung</h2></div>
      <div className="user-admin-actions">{view === "list" ? <><button className="secondary-button" type="button" onClick={() => void loadUsers()} disabled={loading || saving}>Aktualisieren</button><button className="primary-button" type="button" onClick={() => { setError(""); setMessage(""); setView("create"); }}>Neuen Benutzer anlegen</button></> : <button className="secondary-button" type="button" onClick={() => { setView("list"); setError(""); }}>Zur Benutzerliste</button>}</div>
    </div>
    <p className="field-help">Lokale Benutzerkonten und ihre Rollen verwalten. Deaktivierte Konten können sich nicht anmelden; bestehende Sitzungen werden beendet.</p>
    {error && <p className="error-message" role="alert">{error}</p>}
    {message && <p className="success-message" role="status">{message}</p>}

    {view === "create" && <section className="panel user-create-panel" aria-label="Neuen Benutzer anlegen">
      <h3>Neuen Benutzer anlegen</h3>
      <form onSubmit={event => void createUser(event)}>
        <div className="user-create-fields">
          <label>Benutzername<input value={username} onChange={event => setUsername(event.target.value)} maxLength={80} autoComplete="off" required /></label>
          <label>Initiales Passwort<input type="password" value={password} onChange={event => setPassword(event.target.value)} minLength={12} maxLength={1024} autoComplete="new-password" required /></label>
        </div>
        <p className="field-help">Mindestens 12 Zeichen. Das Passwort wird nur bei der Anlage übermittelt und nicht erneut angezeigt.</p>
        <fieldset className="role-fieldset"><legend>Rollen</legend><div className="role-options">{ROLE_OPTIONS.map(role => <label key={role.id}><input type="checkbox" checked={newRoles.includes(role.id)} onChange={event => setNewRoles(current => event.target.checked ? [...current, role.id] : current.filter(item => item !== role.id))} />{role.label}</label>)}</div></fieldset>
        <div className="user-actions"><button className="secondary-button" type="button" onClick={() => setView("list")}>Abbrechen</button><button className="primary-button" type="submit" disabled={saving || !username.trim() || password.length < 12 || newRoles.length === 0}>{saving ? "Speichert …" : "Benutzer anlegen"}</button></div>
      </form>
    </section>}
    {view === "list" && <section className="user-list-section">
      <div className="section-heading"><h3>Vorhandene Benutzer ({users.length})</h3></div>
      {loading ? <p className="muted-message">Benutzerliste wird geladen …</p> : users.length === 0 ? <p className="muted-message">Keine Benutzer vorhanden.</p> : <div className="user-list">
        {users.map(user => {
          const roles = roleDrafts[user.id] || [];
          const changed = roles.length !== user.roles.length || roles.some(role => !user.roles.includes(role));
          const isSelf = user.id === currentUser.id;
          return <article className="user-card" key={user.id}>
            <div className="user-card-heading">
              <div><strong>{user.username}</strong><span className={user.enabled ? "user-status enabled" : "user-status disabled"}>{user.enabled ? "Aktiv" : "Deaktiviert"}</span>{isSelf && <span className="user-self-label">Dein Konto</span>}</div>
              <span className="user-kind">{user.external ? "LDAP-Konto" : "Lokales Konto"}</span>
            </div>
            <fieldset className="role-fieldset">
              <legend>Zugewiesene Rollen</legend>
              <div className="role-options">
                {ROLE_OPTIONS.map(role => <label key={role.id}>
                  <input type="checkbox" checked={roles.includes(role.id)} disabled={saving || (isSelf && role.id === "admin")} onChange={event => toggleRole(user.id, role.id, event.target.checked)} />
                  {role.label}
                </label>)}
              </div>
            </fieldset>
            <div className="user-actions">
              <button className="secondary-button" type="button" onClick={() => void saveRoles(user)} disabled={saving || !changed || roles.length === 0}>Rollen speichern</button>
              <button className="secondary-button" type="button" onClick={() => void toggleEnabled(user)} disabled={saving || isSelf}>{user.enabled ? "Deaktivieren" : "Aktivieren"}</button>
              <button className="danger-button" type="button" onClick={() => void deleteUser(user)} disabled={saving || isSelf || user.external} title={user.external ? "LDAP-Konten werden durch den Verzeichnisdienst verwaltet; bei Bedarf deaktivieren." : undefined}>Löschen</button>
            </div>
          </article>;
        })}
      </div>}
    </section>}
    {view === "list" && <p className="field-help">Schutzregeln: Das eigene Konto kann nicht deaktiviert oder gelöscht werden. Der letzte aktive Administrator kann weder seine Administratorrolle verlieren noch deaktiviert oder gelöscht werden. LDAP-Konten werden bei erfolgreicher LDAP-Anmeldung synchronisiert.</p>}
  </section>;
}
