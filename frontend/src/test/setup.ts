import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// Mock next/navigation for components that use usePathname
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
  }),
}));
