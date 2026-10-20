import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";

describe("LogSanitizer app shell", () => {
  it("shows the development-only warning", () => {
    render(<App />);
    expect(screen.getByText(/Noch nicht für echte Logdaten freigegeben/i)).toBeInTheDocument();
  });
  it("offers local help topics", async () => {
    render(<App />);
    screen.getByRole("button", { name: "Hilfe" }).click();
    expect(await screen.findByRole("heading", { name: "Hilfe und Grundlagen" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Erste Schritte" })).toBeInTheDocument();
  });
});
