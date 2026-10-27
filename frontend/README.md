# Frontend

Requires Node.js 20 or later.

```bash
npm install
npm run dev
```

Vite binds to loopback (`127.0.0.1`) by default and proxies `/api` to the local FastAPI service at `127.0.0.1:8000`.

Build and test:

```bash
npm test
npm run build
```

The current UI can create/open projects and register a single file or folder by entering an absolute path. Registration stores metadata only: it does not read log contents or sanitize them. Folder import reports skipped entries and supports recursive traversal. A native operating-system file chooser is not implemented yet; a browser file chooser does not provide the backend with a trustworthy local filesystem path. Do not use this development scaffold with sensitive logs.


## Dateiformat-Hinweise

Die Dateiliste zeigt einen vorläufigen Format-Hinweis aus der Dateiendung. Unterstützt
werden die Hinweise JSON, JSON Lines, Text, XML und CSV; nicht zugeordnete Endungen
werden als „unbekannt“ angezeigt. Dieser Hinweis prüft den Dateiinhalt ausdrücklich
nicht und ist keine Freigabe zur Verarbeitung. Eine echte Formaterkennung mit
manueller Auswahl und Validierung folgt später.
