import { create } from "zustand";
import { invoke } from "@tauri-apps/api/core";

interface AuthState {
  isSignedIn: boolean;
  isLoading: boolean;
  isSigningIn: boolean;
  error: string | null;
  userId: string | null;
  userEmail: string | null;
  idToken: string | null;
  signIn: (provider: "google" | "apple") => Promise<void>;
  signOut: () => Promise<void>;
  restoreSession: () => Promise<void>;
  /** Ask the Rust side to refresh the Firebase ID token and update in-memory state. */
  refreshToken: () => Promise<boolean>;
}

export const useAuthStore = create<AuthState>((set) => ({
  isSignedIn: false,
  isLoading: true,
  isSigningIn: false,
  error: null,
  userId: null,
  userEmail: null,
  idToken: null,

  signIn: async (provider: "google" | "apple") => {
    set({ isSigningIn: true, error: null });
    try {
      const result = await invoke<{
        user_id: string;
        email: string;
        id_token: string;
      }>("sign_in", { provider });

      set({
        isSignedIn: true,
        isSigningIn: false,
        userId: result.user_id,
        userEmail: result.email,
        idToken: result.id_token,
      });
    } catch (error) {
      console.error("Sign in failed:", error);
      set({
        isSigningIn: false,
        error: typeof error === "string" ? error : "Sign in failed",
      });
    }
  },

  signOut: async () => {
    try {
      await invoke("sign_out");
    } catch {
      // best-effort
    }
    set({
      isSignedIn: false,
      userId: null,
      userEmail: null,
      idToken: null,
    });
  },

  restoreSession: async () => {
    try {
      const result = await invoke<{
        user_id: string;
        email: string;
        id_token: string;
      } | null>("restore_session");

      if (result) {
        set({
          isSignedIn: true,
          userId: result.user_id,
          userEmail: result.email,
          idToken: result.id_token,
          isLoading: false,
        });
      } else {
        set({ isLoading: false });
      }
    } catch {
      set({ isLoading: false });
    }
  },

  refreshToken: async () => {
    try {
      const result = await invoke<{
        user_id: string;
        email: string;
        id_token: string;
      } | null>("force_refresh_token");
      if (result) {
        set({
          isSignedIn: true,
          userId: result.user_id,
          userEmail: result.email,
          idToken: result.id_token,
        });
        return true;
      }
      return false;
    } catch (err) {
      console.warn("[auth] force_refresh_token failed:", err);
      return false;
    }
  },
}));
