"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import {
  User,
  onAuthStateChanged,
  signOut as firebaseSignOut,
} from "firebase/auth";
import { doc, getDoc } from "firebase/firestore";
import { getFirebaseAuth, getFirebaseDb } from "@/lib/firebase/client";
import {
  DEV_BYPASS_ENABLED,
  DEV_BYPASS_TOKEN,
  DEV_BYPASS_UID,
} from "@/lib/dev-auth";
import { usePathname, useRouter } from "next/navigation"; // Use next/navigation for App Router

interface AuthContextProps {
  user: User | null;
  isAdmin: boolean;
  loading: boolean;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextProps>({
  user: null,
  isAdmin: false,
  loading: true,
  signOut: async () => {},
});

function createBypassUser(): User {
  return {
    uid: DEV_BYPASS_UID,
    getIdToken: async () => DEV_BYPASS_TOKEN,
  } as User;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const bypassAuth = DEV_BYPASS_ENABLED;
  const [user, setUser] = useState<User | null>(
    bypassAuth ? createBypassUser() : null
  );
  const [isAdmin, setIsAdmin] = useState<boolean>(bypassAuth);
  const [loading, setLoading] = useState<boolean>(!bypassAuth);
  const router = useRouter();
  const pathname = usePathname();
  const isTvKiosk = pathname?.startsWith("/tv/view/") ?? false;
  const isTvKioskRef = React.useRef(isTvKiosk);
  isTvKioskRef.current = isTvKiosk;

  const signOut = async () => {
    try {
      await firebaseSignOut(getFirebaseAuth());
      setUser(null);
      setIsAdmin(false);
      router.push("/login"); // Redirect to login after sign out
    } catch (error) {
      console.error("Error signing out:", error);
    }
  };

  useEffect(() => {
    if (bypassAuth) {
      setUser(createBypassUser());
      setIsAdmin(true);
      setLoading(false);
      return;
    }

    const auth = getFirebaseAuth();
    const db = getFirebaseDb();
    const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
      setLoading(true);
      if (currentUser) {
        console.log("currentUser", currentUser);
        // Check if user is an Omi admin by looking for their UID in the specific product path
        const adminDocRef = doc(db, "adminData", currentUser.uid);
        try {
          const adminDoc = await getDoc(adminDocRef);
          if (adminDoc.exists()) {
            setUser(currentUser);
            setIsAdmin(true);
            console.log(`Admin user ${currentUser.email} signed in.`);
          } else {
            console.warn(
              `User ${currentUser.email} is not an admin. Signing out.`
            );
            setUser(null);
            setIsAdmin(false);
            // Kiosk must not sign out or redirect — a TV may share a browser
            // with an admin session, and kiosk→dashboard must not bounce login.
            if (!isTvKioskRef.current) {
              await firebaseSignOut(auth);
              router.push("/login?error=unauthorized");
            }
          }
        } catch (error) {
          console.error("Error checking admin status:", error);
          setUser(null);
          setIsAdmin(false);
          if (!isTvKioskRef.current) {
            await firebaseSignOut(auth);
            router.push("/login?error=check_failed");
          }
        }
      } else {
        setUser(null);
        setIsAdmin(false);
      }
      setLoading(false);
    });

    // Cleanup subscription on unmount
    return () => unsubscribe();
  }, [bypassAuth, router]);

  return (
    <AuthContext.Provider value={{ user, isAdmin, loading, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
