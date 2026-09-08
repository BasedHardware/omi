import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useTeamMembers", () => ({
  useTeamMembers: () => ({
    teamMembers: [],
    isLoading: false,
    error: null,
    mutate: vi.fn(),
  }),
}));

vi.mock("@/hooks/useAuthToken", () => ({
  useAuthFetch: () => ({ fetchWithAuth: vi.fn() }),
}));

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import TeamPage from "../page";

describe("TeamPage", () => {
  it("keeps the add-person action visible and opens its email form", () => {
    render(<TeamPage />);

    fireEvent.click(screen.getByRole("button", { name: "Add new person" }));

    expect(screen.getByRole("dialog", { name: "Add new person" })).toBeTruthy();
    expect(screen.getByLabelText("Email").getAttribute("type")).toBe("email");
  });
});
