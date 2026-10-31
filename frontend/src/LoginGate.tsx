import { FormEvent, useState } from "react";

type AuthUser = { id: number; username: string; roles: string[] };

export function LoginGate({ onLogin }: { onLogin: (user: AuthUser) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const response = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }), credentials: "same-origin" });
      if (!response.ok) throw new Error("Anmeldung fehlgeschlagen. Bitte Zugangsdaten prüfen.");
      const session = await fetch("/api/auth/me", { credentials: "same-origin" });
      if (!session.ok) throw new Error("Sitzung konnte nicht geöffnet werden.");
      onLogin(await session.json() as AuthUser); setPassword("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Anmeldung fehlgeschlagen."); }
    finally { setBusy(false); }
  }
  return <main className="app-shell login-shell"><section className="login-card" aria-labelledby="login-title">
    <p className="eyebrow">LOKALER ZUGANG</p><h1 id="login-title">LogSanitizer</h1>
    <p>Melde dich mit einem lokal eingerichteten Benutzerkonto an.</p>
    <form onSubmit={submit}><label>Benutzername<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required /></label>
      <label>Passwort<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
      {error && <p role="alert" className="error-message">{error}</p>}<button type="submit" disabled={busy}>{busy ? "Anmeldung …" : "Anmelden"}</button>
    </form><p className="muted">Erster Administrator: <code>python -m logsanitizer.auth_cli</code> im Backend-Verzeichnis ausführen.</p>
  </section></main>;
}