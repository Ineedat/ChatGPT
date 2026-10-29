"""Launch LogSanitizer with the bind address selected by deployment configuration."""
import uvicorn

from logsanitizer.deployment import server_bind


def main() -> None:
    host, port = server_bind()
    uvicorn.run("logsanitizer.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
