import * as admin from "firebase-admin";

export type FirebaseAdminCredentialMode =
  | "service-account-key"
  | "application-default";

export interface FirebaseAdminInitPlan {
  mode: FirebaseAdminCredentialMode;
  projectId: string | undefined;
  projectIdSource: string;
}

type Env = Record<string, string | undefined>;

const PROJECT_ID_SOURCES = [
  "FIREBASE_PROJECT_ID",
  "GOOGLE_CLOUD_PROJECT",
  "GCLOUD_PROJECT",
  "NEXT_PUBLIC_FIREBASE_PROJECT_ID",
] as const;

function present(value: string | undefined): value is string {
  return typeof value === "string" && value.trim() !== "";
}

function runtimeEnv(): Env {
  // Next.js inlines NEXT_PUBLIC_* at build time only where the literal
  // `process.env.NEXT_PUBLIC_...` expression appears; the Docker build ARG is
  // not present in the runtime environment.
  return {
    ...process.env,
    NEXT_PUBLIC_FIREBASE_PROJECT_ID:
      process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  };
}

/**
 * Decide how the Admin SDK authenticates, without touching secret material.
 *
 * Production runs keyless: the Cloud Run runtime service account is used via
 * Application Default Credentials. A service-account key in
 * FIREBASE_CLIENT_EMAIL + FIREBASE_PRIVATE_KEY is still honoured so local
 * development against a non-production project keeps working, but supplying
 * only one half is a misconfiguration and fails loudly rather than silently
 * falling back to a different identity.
 */
export function planFirebaseAdminInit(
  env: Env = runtimeEnv()
): FirebaseAdminInitPlan {
  const projectIdSource = PROJECT_ID_SOURCES.find((name) => present(env[name]));
  const projectId = projectIdSource ? env[projectIdSource]!.trim() : undefined;

  const hasEmail = present(env.FIREBASE_CLIENT_EMAIL);
  const hasKey = present(env.FIREBASE_PRIVATE_KEY);
  if (hasEmail !== hasKey) {
    throw new Error(
      "Firebase Admin SDK misconfigured: FIREBASE_CLIENT_EMAIL and FIREBASE_PRIVATE_KEY must be set together, " +
        "or both unset to use the runtime service account."
    );
  }
  if (hasEmail && hasKey) {
    if (!projectId) {
      throw new Error(
        "Firebase Admin SDK misconfigured: a service-account key requires FIREBASE_PROJECT_ID."
      );
    }
    return {
      mode: "service-account-key",
      projectId,
      projectIdSource: projectIdSource!,
    };
  }
  return {
    mode: "application-default",
    projectId,
    projectIdSource: projectIdSource ?? "metadata-server",
  };
}

function ensureInitialized() {
  if (admin.apps.length) return;

  const plan = planFirebaseAdminInit();
  try {
    if (plan.mode === "service-account-key") {
      admin.initializeApp({
        credential: admin.credential.cert({
          projectId: plan.projectId,
          clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
          privateKey: process.env.FIREBASE_PRIVATE_KEY!.replace(/\\n/g, "\n"),
        }),
      });
    } else {
      admin.initializeApp({
        credential: admin.credential.applicationDefault(),
        ...(plan.projectId ? { projectId: plan.projectId } : {}),
      });
    }
    // Names only: never log key material or the client email.
    console.log(
      `Firebase Admin SDK initialized: credential=${plan.mode} project=${
        plan.projectId ?? "(discovered)"
      } ` + `projectSource=${plan.projectIdSource}`
    );
  } catch (error: any) {
    console.error("Firebase Admin SDK initialization error:", error.stack);
    throw error;
  }
}

export function getDb() {
  ensureInitialized();
  return admin.firestore();
}

export function getAdminAuth() {
  ensureInitialized();
  return admin.auth();
}

export const verifyFirebaseToken = async (token: string) => {
  ensureInitialized();
  try {
    const decodedToken = await admin.auth().verifyIdToken(token);
    return decodedToken;
  } catch (error) {
    console.error("Error verifying Firebase ID token:", error);
    return null;
  }
};

export default admin;
