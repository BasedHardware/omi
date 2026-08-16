"use client";

import { useEffect, useState } from "react";
import { getFirebaseApp } from "@/lib/firebase/client";

const inputs = [
  process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY,
  process.env.NEXT_PUBLIC_PLUGINS_APP_ID,
  process.env.NEXT_PUBLIC_OMI_API_URL,
];

export function PublicBuildCanary() {
  const [status, setStatus] = useState("pending");

  useEffect(() => {
    try {
      const firebaseApp = getFirebaseApp();
      setStatus(
        inputs.every((value) => typeof value === "string" && value.trim()) &&
          firebaseApp.options.apiKey
          ? "ready"
          : "missing",
      );
    } catch {
      setStatus("missing");
    }
  }, []);

  return (
    <span
      aria-hidden="true"
      data-omi-public-build-canary={`admin:${status}`}
      hidden
    />
  );
}
