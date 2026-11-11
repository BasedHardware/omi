/**
 * Invite mail for the "Add new person" flow on /dashboard/team.
 *
 * The grant itself is the product action; this note only tells the person it
 * happened and which identity to sign in with. It must never be able to fail
 * the grant, so every failure resolves to `{ sent: false }` instead of
 * throwing.
 */

const RESEND_API_URL = "https://api.resend.com/emails";

/**
 * Resend verifies `mail.omi.me`, not the apex `omi.me`, and the backend's
 * transactional mail (`notes@mail.omi.me`, `hello@mail.omi.me`) already sends
 * from it. Sending from an unverified domain is rejected by the provider.
 */
const INVITE_FROM_ADDRESS =
  process.env.ADMIN_INVITE_FROM_ADDRESS || "admin@mail.omi.me";

export const ADMIN_DASHBOARD_URL = "https://admin.omi.me";

export const ADMIN_INVITE_SUBJECT =
  "You now have access to the Omi admin dashboard";

export type InviteEmailResult = {
  sent: boolean;
  /** Only set when `sent` is false, for the server log. */
  reason?: "not-configured" | "rejected" | "unreachable";
};

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inviteBody(email: string, invitedBy?: string | null) {
  const actor =
    invitedBy && invitedBy.includes("@") ? invitedBy : "The Omi team";
  const lines = [
    `${actor} gave you access to the Omi admin dashboard.`,
    "",
    `Open ${ADMIN_DASHBOARD_URL} and sign in with Google using ${email}. That exact address, no other one.`,
    "",
    "If you were not expecting this, reply to this email and we will remove the access.",
  ];
  const text = lines.join("\n");
  const html = [
    `<p>${escapeHtml(actor)} gave you access to the Omi admin dashboard.</p>`,
    `<p>Open <a href="${ADMIN_DASHBOARD_URL}">${ADMIN_DASHBOARD_URL}</a> and sign in with Google using <strong>${escapeHtml(
      email
    )}</strong>. That exact address, no other one.</p>`,
    "<p>If you were not expecting this, reply to this email and we will remove the access.</p>",
  ].join("\n");
  return { text, html };
}

export async function sendAdminInviteEmail({
  email,
  invitedBy,
}: {
  email: string;
  invitedBy?: string | null;
}): Promise<InviteEmailResult> {
  const apiKey = process.env.RESEND_API_KEY;
  if (!apiKey) {
    console.warn(
      "Admin invite email skipped: RESEND_API_KEY is not configured."
    );
    return { sent: false, reason: "not-configured" };
  }

  const { text, html } = inviteBody(email, invitedBy);

  let response: Response;
  try {
    response = await fetch(RESEND_API_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: `Omi <${INVITE_FROM_ADDRESS}>`,
        to: [email],
        reply_to: "team@basedhardware.com",
        subject: ADMIN_INVITE_SUBJECT,
        text,
        html,
      }),
    });
  } catch (error) {
    console.error("Admin invite email could not reach the provider:", error);
    return { sent: false, reason: "unreachable" };
  }

  if (!response.ok) {
    // Status only: the provider echoes the payload back on some errors.
    console.error(
      `Admin invite email rejected by the provider: status=${response.status}`
    );
    return { sent: false, reason: "rejected" };
  }

  return { sent: true };
}
