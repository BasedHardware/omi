import { createElement } from "react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const state = vi.hoisted(() => ({
  scopes: [] as string[],
  updateOrganization: vi.fn(
    async (_id: string, _body: Record<string, unknown>) => ({})
  ),
  createOrganization: vi.fn(async (_data: Record<string, unknown>) => ({})),
}));

vi.mock("@/hooks/useOrganizations", () => ({
  useOrganizations: () => ({
    organizations: [
      {
        id: "org1",
        organisation_name: "Acme",
        website: "",
        added_on: null,
        is_active: true,
        employees: [],
      },
    ],
    loading: false,
    error: null,
    createOrganization: state.createOrganization,
    toggleOrganizationStatus: vi.fn(async () => ({})),
    updateOrganization: state.updateOrganization,
  }),
}));
vi.mock("@/hooks/useAdminAccess", () => ({
  useAdminAccess: () => ({
    access: { uid: "u", scopes: state.scopes },
    isLoading: false,
    error: null,
    can: (scope: string) => state.scopes.includes(scope),
  }),
}));
vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import OrganizationsPage from "@/app/(protected)/dashboard/organizations/page";

/**
 * The Stripe payment field is billing: the server treats its presence in a
 * PATCH as a billing change needing finance:write, while the edit form kept
 * an empty string around for it. An editor holding only partners:write must
 * therefore neither see the field nor send it — otherwise every ordinary
 * metadata edit fails with 403.
 */

async function editOrganization() {
  render(createElement(OrganizationsPage));
  fireEvent.click(await screen.findByRole("button", { name: /edit/i }));
  await screen.findByText("Edit Organization");
  fireEvent.click(screen.getByRole("button", { name: /update organization/i }));
}

beforeAll(() => {
  // The org page's Switch measures itself; jsdom has no observer.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
});

beforeEach(() => {
  state.updateOrganization.mockClear();
});

afterEach(() => {
  cleanup();
  state.scopes = [];
});

describe("the organization edit dialog", () => {
  it("sends no billing field, and shows none, without finance:write", async () => {
    state.scopes = ["partners:read", "partners:write"];
    await editOrganization();

    expect(state.updateOrganization).toHaveBeenCalledTimes(1);
    const [id, body] = state.updateOrganization.mock.calls[0];
    expect(id).toBe("org1");
    expect(body).not.toHaveProperty("stripe_payment_id");
    expect(body).toMatchObject({ organisation_name: "Acme" });
    expect(screen.queryByText("Stripe Payment ID")).toBeNull();
  });

  it("sends no billing field to an editor who can write but not read billing", async () => {
    state.scopes = ["partners:read", "partners:write", "finance:write"];
    await editOrganization();

    const [, body] = state.updateOrganization.mock.calls[0];
    expect(body).not.toHaveProperty("stripe_payment_id");
    expect(screen.queryByText("Stripe Payment ID")).toBeNull();
  });

  it("keeps the billing field for an editor who holds finance:read and finance:write", async () => {
    state.scopes = [
      "partners:read",
      "partners:write",
      "finance:read",
      "finance:write",
    ];
    await editOrganization();

    expect(screen.getByText("Stripe Payment ID")).toBeTruthy();
    const [, body] = state.updateOrganization.mock.calls[0];
    expect(body).toHaveProperty("stripe_payment_id");
  });
});
