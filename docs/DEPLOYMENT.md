# Deployment and portable operation

LogSanitizer uses one JSON configuration file for deployment-specific settings. The template is config/deployment.example.json. The portable bundle includes a safe standalone config/deployment.json. Edit that file or set LOGSANITIZER_CONFIG to a protected external file. Relative data and certificate paths are resolved from the JSON file's directory.

## Standalone laptop (offline)

1. Set profile to standalone, server.bind_host to 127.0.0.1, and auth.provider to local.
2. Keep SMTP disabled. This profile rejects non-loopback binding and removes SMTP configuration from the process environment.
3. Choose data_dir:
   - ./data keeps SQLite databases, mapping database, and its separate key file in a writable directory beside the config.
   - Empty uses the platform user's LogSanitizer data directory.
4. Start LogSanitizer.exe on Windows or ./LogSanitizer on Linux. The bundled UI is served locally; open http://127.0.0.1:8000.
5. Create the first local administrator using the Python CLI before creating a bundle for end users, or provide a supported first-run setup workflow in a future release.

Standalone is intended for disconnected laptop use. No LDAP module is required at runtime for this profile, and SMTP is disabled.

## Network / Darksite profile

1. Set profile to network, choose the explicit interface address in server.bind_host, and set auth.provider to ldap.
2. Configure server.tls_certfile and server.tls_keyfile with an HTTPS certificate and private key. The portable launcher serves HTTPS directly in network mode. Keep the private key readable only by the service account.
3. Configure LDAP host/port, bind_dn, user_search_base, user_filter, username/group attributes, and explicit role_groups mapping. LDAPS or StartTLS is mandatory; certificate chain and hostname validation are enabled. Use ca_certs_file only for a private CA that is not in the system trust store.
4. Provide the LDAP service account password as LOGSANITIZER_LDAP_BIND_PASSWORD through the service manager or protected environment configuration. It must not be stored in JSON.
5. Optionally enable SMTP and set host, port, transport (starttls or ssl), sender, reviewer recipients, and operator recipients in JSON. If SMTP authentication is required, provide LOGSANITIZER_SMTP_USERNAME and LOGSANITIZER_SMTP_PASSWORD as environment secrets.
6. Install the optional LDAP dependency in source deployments with python -m pip install -e ".[ldap]". The portable build includes LDAP support.
7. Restrict the application port to intended Darksite clients using host firewall rules. Do not expose it to untrusted networks.

Network mode refuses to start when the bind address, LDAP setup, TLS files, role mapping, or LDAP service secret is missing. LDAP failures do not fall back to local-password authentication. User roles are synchronized from configured direct group membership on successful login; nested group expansion is not currently implemented.

## Backup, data and recovery

The configured data directory contains multiple SQLite metadata stores and mappings.key. Back up the database files and key as a coordinated set, with the key protected separately from ordinary backups. A backup that includes both the mapping database and key allows recovery of original values. Never place secrets in the deployment JSON or ship real LDAP/TLS private keys in the application bundle.

## Build notes

The repository's PyInstaller specification builds a one-folder bundle and includes the React frontend, configuration template, and offline documentation. Build separately on Windows and Linux; these are platform-specific outputs. The CI smoke test launches the standalone bundle and checks its local health endpoint. This build check does not replace a live LDAP/AD + SMTP integration test or a production security review.
