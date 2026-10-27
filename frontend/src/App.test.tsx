import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "./App";

// Vitest runs without global afterEach by default; clean up between renders.
afterEach(() => cleanup());

describe("LogSanitizer app shell", () => {
  it("shows the development-only warning", () => {
    render(<App />);
    expect(screen.getByText(/Noch nicht für echte Logdaten freigegeben/i)).toBeInTheDocument();
  });

  it("offers local help topics", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Hilfe" }));
    expect(await screen.findByRole("heading", { name: "Hilfe und Grundlagen" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Erste Schritte" })).toBeInTheDocument();
  });
});
