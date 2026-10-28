"""Create the first local administrator interactively; never expose bootstrap over HTTP."""
from getpass import getpass
from logsanitizer.auth import create_user, initialize_auth_database

def main() -> None:
    initialize_auth_database()
    username = input("Administrator username: ").strip()
    password = getpass("Password (minimum 12 characters): ")
    confirmation = getpass("Repeat password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    try:
        user_id = create_user(username, password, ["admin", "operator", "reviewer", "approver"])
    except Exception as exc:
        raise SystemExit(f"Administrator could not be created: {exc}") from exc
    print(f"Administrator created (id={user_id}). Store the password securely.")

if __name__ == "__main__":
    main()
