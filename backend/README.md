# Backend

From this directory:

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn logsanitizer.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: http://127.0.0.1:8000/api/health. API docs: http://127.0.0.1:8000/api/docs.

Run tests with `pytest`. This scaffold is not approved for real/sensitive logs and must not be exposed to a network.