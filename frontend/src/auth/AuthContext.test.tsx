import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";

const STORAGE_KEY = "achievementhub_session";

function SessionProbe() {
  const { session, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="role">{session ? session.role : "anonymous"}</span>
      <span data-testid="token">{session?.token ?? ""}</span>
      <button onClick={() => login("tok-123", "hod")}>sign in</button>
      <button onClick={logout}>sign out</button>
    </div>
  );
}

describe("AuthProvider", () => {
  it("starts anonymous when nothing is stored", () => {
    render(
      <AuthProvider>
        <SessionProbe />
      </AuthProvider>
    );

    expect(screen.getByTestId("role")).toHaveTextContent("anonymous");
  });

  it("stores the session so a page reload keeps the user signed in", async () => {
    render(
      <AuthProvider>
        <SessionProbe />
      </AuthProvider>
    );

    await userEvent.click(screen.getByText("sign in"));

    expect(screen.getByTestId("role")).toHaveTextContent("hod");
    expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY)!)).toEqual({
      token: "tok-123",
      role: "hod",
    });
  });

  it("restores an existing session on mount", () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ token: "tok-9", role: "admin" }));

    render(
      <AuthProvider>
        <SessionProbe />
      </AuthProvider>
    );

    expect(screen.getByTestId("role")).toHaveTextContent("admin");
    expect(screen.getByTestId("token")).toHaveTextContent("tok-9");
  });

  it("clears the stored session on sign out", async () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ token: "tok-9", role: "admin" }));
    render(
      <AuthProvider>
        <SessionProbe />
      </AuthProvider>
    );

    await userEvent.click(screen.getByText("sign out"));

    expect(screen.getByTestId("role")).toHaveTextContent("anonymous");
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("uses sessionStorage, not localStorage", () => {
    // A shared machine in a college lab is the normal case here: the session
    // should not outlive the browser tab.
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ token: "t", role: "faculty" }));

    render(
      <AuthProvider>
        <SessionProbe />
      </AuthProvider>
    );

    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("refuses to be used outside a provider", () => {
    expect(() => render(<SessionProbe />)).toThrow(/must be used within AuthProvider/);
  });
});
