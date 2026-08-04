export type UserProfile = {
  uid: string;
  raw: Record<string, unknown>;
};

export type IdentityStore = {
  getProfile(uid: string): Promise<UserProfile | null>;
};

export function originIdentityStore(originBase: string, authHeader: string): IdentityStore {
  const base = originBase.replace(/\/$/, "");
  return {
    async getProfile(uid) {
      const res = await fetch(`${base}/v1/users/profile`, {
        headers: { Authorization: authHeader, "x-omi-edge": "identity-origin" },
      });
      if (res.status === 404) return null;
      if (!res.ok) throw new Error(`origin_profile_${res.status}`);
      const raw = (await res.json()) as Record<string, unknown>;
      return { uid: String(raw.uid ?? uid), raw };
    },
  };
}
