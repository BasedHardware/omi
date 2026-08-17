import { deleteApp, initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

try {
  const app = initializeApp({ projectId: "omi-production-artifact-verification" }, `artifact-${process.pid}`);
  const auth = getAuth(app);
  if (auth.app !== app) throw new Error("firebase_auth_app_mismatch");
  await deleteApp(app);
  console.log(JSON.stringify({ status: "ok", runtime: typeof Bun === "undefined" ? "node" : "bun" }));
} catch {
  console.error(JSON.stringify({ status: "error", code: "firebase_auth_runtime_verification_failed" }));
  process.exitCode = 1;
}
