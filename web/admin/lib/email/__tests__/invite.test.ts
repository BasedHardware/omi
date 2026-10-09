import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ADMIN_INVITE_SUBJECT, sendAdminInviteEmail } from "@/lib/email/invite";

const ORIGINAL_KEY = process.env.RESEND_API_KEY;

describe("sendAdminInviteEmail", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    process.env.RESEND_API_KEY = "re_test_key";
  });

  afterEach(() => {
    if (ORIGINAL_KEY === undefined) delete process.env.RESEND_API_KEY;
    else process.env.RESEND_API_KEY = ORIGINAL_KEY;
  });

  it("sends from the verified Omi domain and names the exact sign-in address", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}", { status: 200 }));

    const result = await sendAdminInviteEmail({
      email: "jan@example.com",
      invitedBy: "kodjima33@gmail.com",
    });

    expect(result).toEqual({ sent: true });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.resend.com/emails");
    const payload = JSON.parse(init.body as string);
    expect(payload.from).toBe("Omi <admin@mail.omi.me>");
    expect(payload.to).toEqual(["jan@example.com"]);
    expect(payload.subject).toBe(ADMIN_INVITE_SUBJECT);
    expect(payload.text).toContain("kodjima33@gmail.com");
    expect(payload.text).toContain("https://admin.omi.me");
    expect(payload.text).toContain("jan@example.com");
  });

  it("falls back to the team when the inviter's email is unknown", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}", { status: 200 }));

    await sendAdminInviteEmail({ email: "jan@example.com", invitedBy: null });

    const payload = JSON.parse(
      (fetchMock.mock.calls[0][1] as RequestInit).body as string
    );
    expect(payload.text).toContain("The Omi team");
  });

  it("reports a provider rejection instead of throwing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{}", { status: 422 })
    );
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});

    await expect(
      sendAdminInviteEmail({ email: "jan@example.com" })
    ).resolves.toEqual({ sent: false, reason: "rejected" });
    expect(errorLog).toHaveBeenCalled();
  });

  it("reports an unreachable provider instead of throwing", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("ECONNRESET"));
    vi.spyOn(console, "error").mockImplementation(() => {});

    await expect(
      sendAdminInviteEmail({ email: "jan@example.com" })
    ).resolves.toEqual({ sent: false, reason: "unreachable" });
  });

  it("skips with a log when no API key is configured", async () => {
    delete process.env.RESEND_API_KEY;
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    await expect(
      sendAdminInviteEmail({ email: "jan@example.com" })
    ).resolves.toEqual({ sent: false, reason: "not-configured" });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalled();
  });
});
