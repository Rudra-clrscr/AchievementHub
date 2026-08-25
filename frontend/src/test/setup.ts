import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

// The api client reads VITE_API_BASE at module load. Pin it so URL assertions
// do not depend on whatever is in the developer's .env.
vi.stubEnv("VITE_API_BASE", "http://api.test");

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});

afterEach(() => {
  cleanup();
});
