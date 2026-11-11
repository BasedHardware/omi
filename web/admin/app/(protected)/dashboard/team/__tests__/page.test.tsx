import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  teamMembers: [] as any[],
  viewer: null as any,
  proposals: [] as any[],
  entries: [] as any[],
  proposalsError: null as Error | null,
  auditError: null as Error | null,
  fetchWithAuth: vi.fn(),
  toast: vi.fn(),
}));

vi.mock("@/hooks/useTeamMembers", () => ({
  useTeamMembers: () => ({
    teamMembers: state.teamMembers,
    viewer: state.viewer,
    isLoading: false,
    error: null,
    mutate: vi.fn(),
  }),
  useTeamProposals: () => ({
    proposals: state.proposals,
    error: state.proposalsError,
    mutate: vi.fn(),
  }),
  useTeamAudit: () => ({
    entries: state.entries,
    error: state.auditError,
    mutate: vi.fn(),
  }),
}));

vi.mock("@/hooks/useAuthToken", () => ({
  useAuthFetch: () => ({ fetchWithAuth: state.fetchWithAuth }),
}));

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: state.toast }),
}));

import TeamPage from "../page";

const member = (overrides: Record<string, unknown>) => ({
  id: "uid-000000000",
  uidPrefix: "uid-0000",
  name: "Person",
  email: "person@example.com",
  role: "Admin",
  roleLabel: "Admin (legacy, full access)",
  accessRole: null,
  accessKind: "legacy",
  scopes: [],
  scopeOverrides: {},
  owner: false,
  createdAt: "2026-01-01T00:00:00.000Z",
  lastSignInAt: null,
  duplicateEmail: false,
  ...overrides,
});

const OWNER_VIEWER = {
  uid: "owner-uid",
  isOwner: true,
  canManage: true,
  canInvite: true,
  canRemove: true,
  scopes: [],
};

beforeEach(() => {
  state.teamMembers = [];
  state.viewer = null;
  state.proposals = [];
  state.entries = [];
  state.proposalsError = null;
  state.auditError = null;
  state.toast.mockReset();
  state.fetchWithAuth
    .mockReset()
    .mockResolvedValue(new Response("{}", { status: 200 }));
});

describe("TeamPage", () => {
  it("keeps the add-person action visible and opens its email and role form", () => {
    render(<TeamPage />);

    fireEvent.click(screen.getByRole("button", { name: "Add new person" }));

    expect(screen.getByRole("dialog", { name: "Add new person" })).toBeTruthy();
    expect(screen.getByLabelText("Email").getAttribute("type")).toBe("email");
    expect((screen.getByLabelText("Role") as HTMLSelectElement).value).toBe(
      "viewer"
    );
    expect(screen.queryByRole("option", { name: "Deputy owner" })).toBeNull();
  });

  it("tells same-email records apart by uid prefix, dates and a duplicate badge", () => {
    state.viewer = OWNER_VIEWER;
    state.teamMembers = [
      member({ id: "aaaaaaaa1", uidPrefix: "aaaaaaaa", duplicateEmail: true }),
      member({
        id: "bbbbbbbb2",
        uidPrefix: "bbbbbbbb",
        duplicateEmail: true,
        lastSignInAt: "2026-10-20T10:00:00.000Z",
      }),
    ];
    render(<TeamPage />);
    expect(screen.getByText("aaaaaaaa")).toBeTruthy();
    expect(screen.getByText("bbbbbbbb")).toBeTruthy();
    expect(screen.getAllByText("Duplicate email")).toHaveLength(2);
    expect(screen.getByText(/2 people have no assigned role/)).toBeTruthy();
  });

  it("lets the owner change a role after confirming the scope diff", async () => {
    state.viewer = OWNER_VIEWER;
    state.teamMembers = [
      member({ scopes: ["analytics:read", "finance:read"] }),
    ];
    render(<TeamPage />);

    fireEvent.change(screen.getByLabelText("Role for person@example.com"), {
      target: { value: "viewer" },
    });
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText(/− finance:read/)).toBeTruthy();
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Change role" })
    );

    await waitFor(() => expect(state.fetchWithAuth).toHaveBeenCalled());
    const [url, init] = state.fetchWithAuth.mock.calls[0];
    expect(url).toBe("/api/omi/team-members");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({
      uid: "uid-000000000",
      accessRole: "viewer",
    });
  });

  it("shows no role or remove controls to someone without team:manage", () => {
    state.viewer = {
      ...OWNER_VIEWER,
      uid: "x",
      isOwner: false,
      canManage: false,
      canRemove: false,
    };
    state.teamMembers = [member({})];
    render(<TeamPage />);
    expect(screen.queryByLabelText("Role for person@example.com")).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove Person" })).toBeNull();
  });

  it("never offers to change the owner or a deputy unless you are the owner", () => {
    state.viewer = { ...OWNER_VIEWER, uid: "deputy-uid", isOwner: false };
    state.teamMembers = [
      member({
        id: "owner",
        email: "owner@example.com",
        owner: true,
        accessKind: "owner",
        roleLabel: "Owner",
      }),
      member({
        id: "d2",
        email: "d2@example.com",
        accessRole: "deputy",
        accessKind: "role",
      }),
      member({
        id: "a",
        email: "a@example.com",
        accessRole: "admin",
        accessKind: "role",
      }),
    ];
    render(<TeamPage />);
    expect(screen.queryByLabelText("Role for owner@example.com")).toBeNull();
    expect(screen.queryByLabelText("Role for d2@example.com")).toBeNull();
    const select = screen.getByLabelText("Role for a@example.com");
    expect(
      within(select).queryByRole("option", { name: "Deputy owner" })
    ).toBeNull();
  });

  it("approves an agent proposal in one click, showing the diff and who proposed it", async () => {
    state.viewer = OWNER_VIEWER;
    state.proposals = [
      {
        id: "p1",
        kind: "set_role",
        status: "pending",
        proposedBy: { type: "agent", email: "agent@x.iam.gserviceaccount.com" },
        reason: "moved to support",
        createdAt: "2026-10-22T00:00:00.000Z",
        expiresAt: "2026-10-25T00:00:00.000Z",
        target: { uid: "uid-000000000", email: "person@example.com" },
        before: {
          roleLabel: "Admin (legacy, full access)",
          scopes: ["finance:read", "users:read"],
        },
        after: { roleLabel: "Support", scopes: ["users:read"] },
        change: { accessRole: "support" },
      },
      {
        id: "p0",
        kind: "remove_member",
        status: "expired",
        target: {},
        proposedBy: {},
      },
    ];
    render(<TeamPage />);

    const card = screen.getByTestId("proposal-p1");
    expect(
      within(card).getByText(/agent@x.iam.gserviceaccount.com/)
    ).toBeTruthy();
    expect(within(card).getByText(/− finance:read/)).toBeTruthy();
    expect(screen.queryByTestId("proposal-p0")).toBeNull();

    fireEvent.click(
      within(card).getByRole("button", { name: /Approve Change role/ })
    );
    await waitFor(() => expect(state.fetchWithAuth).toHaveBeenCalled());
    const [url, init] = state.fetchWithAuth.mock.calls[0];
    expect(url).toBe("/api/omi/team-members/proposals/p1");
    expect(JSON.parse(init.body)).toEqual({ decision: "approve" });
  });

  it("warns the approver when an approved add-person invite email fails", async () => {
    state.viewer = OWNER_VIEWER;
    state.proposals = [
      {
        id: "p2",
        kind: "add_member",
        status: "pending",
        proposedBy: { type: "agent", email: "agent@x.iam.gserviceaccount.com" },
        reason: "new hire",
        createdAt: "2026-10-22T00:00:00.000Z",
        expiresAt: "2026-10-25T00:00:00.000Z",
        target: { uid: null, email: "new@example.com" },
        before: null,
        after: { roleLabel: "Support", scopes: ["users:read"] },
        change: { accessRole: "support" },
      },
    ];
    state.fetchWithAuth.mockResolvedValue(
      new Response(
        JSON.stringify({
          proposal: { id: "p2", status: "approved", emailSent: false },
        }),
        { status: 200 }
      )
    );
    render(<TeamPage />);

    fireEvent.click(screen.getByRole("button", { name: /Approve Add person/ }));
    await waitFor(() => expect(state.toast).toHaveBeenCalled());
    expect(state.toast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Approved, but the invite email failed",
        description: expect.stringContaining("new@example.com"),
      })
    );
    expect(state.toast).not.toHaveBeenCalledWith(
      expect.objectContaining({ title: "Proposal approved" })
    );
  });

  it("lists audit events with actor, target and before/after", () => {
    state.viewer = OWNER_VIEWER;
    state.entries = [
      {
        id: "e1",
        at: "2026-10-22T00:00:00.000Z",
        action: "member.role_changed",
        actor: { type: "human", id: "owner-uid", email: "owner@example.com" },
        target: { uid: "uid-000000000", email: "person@example.com" },
        before: { roleLabel: "Admin (legacy, full access)", scopes: [] },
        after: { roleLabel: "Support", scopes: [] },
        proposedBy: "agent@x.iam.gserviceaccount.com",
      },
    ];
    render(<TeamPage />);
    expect(screen.getByText("Role changed")).toBeTruthy();
    expect(screen.getByText("owner@example.com")).toBeTruthy();
    expect(screen.getByText(/proposed by agent@x/)).toBeTruthy();
    expect(screen.getByText("Support")).toBeTruthy();
  });

  it("says when proposals or the audit log failed to load, instead of showing them empty", () => {
    state.viewer = OWNER_VIEWER;
    state.proposalsError = new Error("502");
    state.auditError = new Error("502");
    render(<TeamPage />);
    expect(screen.getByText(/Could not load agent proposals/)).toBeTruthy();
    expect(screen.getByText("Could not load the audit log.")).toBeTruthy();
    expect(screen.queryByText("No events yet.")).toBeNull();
  });
});
