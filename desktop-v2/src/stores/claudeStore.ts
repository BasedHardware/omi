/**
 * Claude OAuth store — manages the Claude access token for direct API use.
 *
 * Uses the Tauri `claude_oauth` commands (PKCE flow with localhost callback).
 * The token enables local tool-use chat via the Anthropic SDK.
 */

import { create } from "zustand";
import { invoke } from "@tauri-apps/api/core";

interface ClaudeAuthResult {
  access_token: string;
  expires_at: number | null;
}

interface ClaudeState {
  accessToken: string | null;
  isSignedIn: boolean;
  isSigningIn: boolean;
  error: string | null;

  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  restoreSession: () => Promise<void>;
}

export const useClaudeStore = create<ClaudeState>((set) => ({
  accessToken: null,
  isSignedIn: false,
  isSigningIn: false,
  error: null,

  signIn: async () => {
    set({ isSigningIn: true, error: null });
    try {
      const result = await invoke<ClaudeAuthResult>("claude_sign_in");
      set({
        accessToken: result.access_token,
        isSignedIn: true,
        isSigningIn: false,
      });
    } catch (err) {
      set({
        error: String(err),
        isSigningIn: false,
      });
    }
  },

  signOut: async () => {
    try {
      await invoke("claude_sign_out");
    } catch {
      // ignore
    }
    set({ accessToken: null, isSignedIn: false, error: null });
  },

  restoreSession: async () => {
    try {
      const result = await invoke<ClaudeAuthResult | null>("claude_restore_session");
      if (result) {
        set({ accessToken: result.access_token, isSignedIn: true });
      }
    } catch {
      // No session to restore
    }
  },
}));
