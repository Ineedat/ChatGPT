"""Launch LogSanitizer with the bind address selected by deployment configuration."""
import uvicorn

from logsanitizer.deployment import load_settings


def main() -> None:
    settings = load_settings()
    server = settings["server"]
    options = {}
    if settings["profile"] == "network":
        options = {
            "ssl_certfile": server["tls_certfile"],
            "ssl_keyfile": server["tls_keyfile"],
        }
    uvicorn.run(
        "logsanitizer.main:app",
        host=server["bind_host"],
        port=server["port"],
        reload=False,
        **options,
    )


if __name__ == "__main__":
    main()
