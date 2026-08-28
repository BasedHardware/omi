// The activate switch is the prompts kill switch — a failed PATCH must never
// leave the UI claiming a prompt was enabled or disabled when it was not.
export async function patchPromptActive(
  fetchImpl: (url: string, init?: RequestInit) => Promise<Response>,
  promptId: string,
  active: boolean,
): Promise<{ ok: boolean; error?: string }> {
  try {
    const response = await fetchImpl(`/api/omi/desktop-prompts/${promptId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active }),
    });
    if (!response.ok) {
      return { ok: false, error: `toggle failed (${response.status})` };
    }
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "toggle failed",
    };
  }
}
