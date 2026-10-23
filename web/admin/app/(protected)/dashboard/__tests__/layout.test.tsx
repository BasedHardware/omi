import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  access: null as { scopes: string[] } | null,
  pathname: "/dashboard/announcements",
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({ user: { uid: "u" }, isAdmin: true, loading: false }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => state.pathname,
}));
vi.mock("@/hooks/useAdminAccess", () => ({
  useAdminAccess: () => ({ access: state.access }),
}));
vi.mock("@/components/dashboard/sidebar", () => ({
  DashboardSidebar: () => null,
}));
vi.mock("@/components/dashboard/header", () => ({
  DashboardHeader: () => null,
}));

import DashboardLayout from "../layout";

beforeEach(() => {
  state.pathname = "/dashboard/announcements";
});

describe("DashboardLayout", () => {
  it("tells a member who can read a page but not change it that the page is read-only", () => {
    state.access = { scopes: ["content:read"] };
    render(
      <DashboardLayout>
        <p>Announcements</p>
      </DashboardLayout>
    );
    expect(screen.getByText(/Read-only for your role/)).toBeTruthy();
    expect(screen.getByText(/content:write/)).toBeTruthy();
    expect(screen.getByText("Announcements")).toBeTruthy();
  });

  it("shows no read-only notice when the member has the write scope", () => {
    state.access = { scopes: ["content:read", "content:write"] };
    render(
      <DashboardLayout>
        <p>Announcements</p>
      </DashboardLayout>
    );
    expect(screen.queryByText(/Read-only for your role/)).toBeNull();
  });

  it("hides a page whose read scope the member lacks", () => {
    state.access = { scopes: ["analytics:read"] };
    render(
      <DashboardLayout>
        <p>Announcements</p>
      </DashboardLayout>
    );
    expect(screen.getByText(/does not include this page/)).toBeTruthy();
    expect(screen.queryByText("Announcements")).toBeNull();
  });
});
