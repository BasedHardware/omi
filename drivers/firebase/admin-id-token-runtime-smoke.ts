import { createFirebaseAdminIdTokenAdapter } from "./admin-id-token.ts";

if (Object.prototype.hasOwnProperty.call(process.env, "FIREBASE_AUTH_EMULATOR_HOST")) {
  throw new Error("runtime smoke requires an emulator-free environment");
}

const handle = await createFirebaseAdminIdTokenAdapter({
  project_id: "omi-firebase-runtime-smoke",
  app_name: `omi-firebase-runtime-smoke-${process.pid}`,
  runtime_mode: "local_test",
});

if (handle.adapter.verification_source !== "firebase_production") {
  throw new Error("runtime smoke selected the wrong verification source");
}
await handle.close();
