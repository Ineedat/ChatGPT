import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { UserManagementPanel } from "./UserManagementPanel";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

const currentUser = { id: 1, username: "admin", roles: ["admin"] };
const existingUsers = [{ id: 1, username: "admin", enabled: true, created_at: 0, external: false, roles: ["admin"] }];

describe("user management navigation", () => {
  it("opens user creation in a separate view and returns to the user list after saving", async () => {
    let users = [...existingUsers];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/auth/users" && init?.method !== "POST") return { ok: true, json: async () => users } as Response;
      if (url === "/api/auth/users" && init?.method === "POST") {
        const created = { id: 2, username: "processor", enabled: true, created_at: 1, external: false, roles: ["operator"] };
        users = [...users, created];
        return { ok: true, json: async () => created } as Response;
      }
      return { ok: true, json: async () => users } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<UserManagementPanel currentUser={currentUser} />);
    expect(await screen.findByText("admin")).toBeInTheDocument();
    expect(screen.queryByLabelText("Benutzername")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Neuen Benutzer anlegen" }));
    expect(screen.getByLabelText("Benutzername")).toBeInTheDocument();
    expect(screen.getByLabelText("Initiales Passwort")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Benutzername"), { target: { value: "processor" } });
    fireEvent.change(screen.getByLabelText("Initiales Passwort"), { target: { value: "processor-password-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Benutzer anlegen" }));
    expect(await screen.findByText(/Benutzer „processor“ wurde angelegt/)).toBeInTheDocument();
    expect(screen.getByText("Vorhandene Benutzer (2)")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/users", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ username: "processor", password: "processor-password-123", roles: ["operator"] })
    }));
  });
});
