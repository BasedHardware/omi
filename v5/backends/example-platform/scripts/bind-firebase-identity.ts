import { createFirebaseAdminIdTokenAdapter } from "../drivers/firebase/admin-id-token";
import {
  createFirebaseIdentityVerifier,
  type FirebaseIdentityVerifier,
} from "../apps/service/auth/firebase-identity";
import { createPostgresJsTransactionPool } from "../drivers/postgres/postgresjs";
import type { PostgresTransactionPool } from "../drivers/postgres/connection";
import { open, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";

export interface BindingManifest {
  projectId: string;
  uid: string;
  accountId: string;
  principalId: string;
  applicationId: string;
  credentialId: string;
  controlRevision: number;
  controlHash: string;
  credentialHash: string;
  grantHash: string;
  expiresAt: number;
  reasonRef: string;
}

export function parseBindingManifest(
  value: unknown,
  now: number
): BindingManifest {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw Error("invalid_binding_manifest");
  const record = value as Record<string, unknown>;
  const coordinates = [
    "projectId",
    "accountId",
    "principalId",
    "applicationId",
    "credentialId",
    "reasonRef",
  ];
  const hashes = ["controlHash", "credentialHash", "grantHash"];
  const keys = [
    ...coordinates,
    ...hashes,
    "uid",
    "controlRevision",
    "expiresAt",
  ].sort();
  if (
    Object.keys(record).sort().join(",") !== keys.join(",") ||
    coordinates.some(
      (key) =>
        typeof record[key] !== "string" || !/^[!-~]{1,128}$/.test(record[key])
    ) ||
    typeof record.uid !== "string" ||
    record.uid.length < 1 ||
    record.uid.length > 128 ||
    /[\u0000-\u001f\u007f]/.test(record.uid) ||
    hashes.some(
      (key) =>
        typeof record[key] !== "string" || !/^[a-f0-9]{64}$/.test(record[key])
    ) ||
    !Number.isSafeInteger(record.controlRevision) ||
    Number(record.controlRevision) < 0 ||
    !Number.isSafeInteger(record.expiresAt) ||
    Number(record.expiresAt) <= now ||
    Number(record.expiresAt) > now + 900
  )
    throw Error("invalid_binding_manifest");
  return Object.freeze({ ...record }) as unknown as BindingManifest;
}

export async function bindFirebaseIdentity(input: {
  manifest: BindingManifest;
  token: string;
  verifier: FirebaseIdentityVerifier;
  pool: PostgresTransactionPool;
  now: () => number;
  audit: (
    event: "intent" | "bound" | "unchanged" | "failed" | "reconcile_required"
  ) => Promise<void>;
}): Promise<"bound" | "unchanged"> {
  const m = parseBindingManifest(input.manifest, input.now());
  const identity = await input.verifier.resolve(input.token, input.now());
  if (
    !identity ||
    !("firebase_uid" in identity) ||
    identity.firebase_project_id !== m.projectId ||
    identity.firebase_uid !== m.uid
  )
    throw Error("binding_identity_rejected");
  await input.audit("intent");
  let committed = false;
  try {
    const result = await input.pool.withTransaction(
      {
        isolationLevel: "serializable",
        accessMode: "read write",
        signal: AbortSignal.timeout(30000),
      },
      async (connection) => {
        await connection.query({
          name: "firebase_binding.lock",
          text: "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
          values: [JSON.stringify([m.projectId, m.uid])],
        });
        const authority = await connection.query({
          name: "firebase_binding.authority",
          text: `
        SELECT ac.control_revision
        FROM omi_memory.account_control_heads ah
        JOIN omi_memory.account_control_revisions ac ON ac.account_id=ah.account_id AND ac.control_revision=ah.control_revision
        JOIN omi_memory.application_credential_heads ch ON ch.account_id=ac.account_id AND ch.application_id=$3 AND ch.credential_id=$4
        JOIN omi_memory.application_credential_revisions cr ON cr.account_id=ch.account_id AND cr.application_id=ch.application_id AND cr.credential_id=ch.credential_id AND cr.credential_generation=ch.credential_generation
        JOIN omi_memory.application_grant_heads gh ON gh.account_id=ch.account_id AND gh.application_id=ch.application_id AND gh.credential_id=ch.credential_id AND gh.credential_generation=ch.credential_generation AND gh.capability='memories.read'
        JOIN omi_memory.application_grant_revisions gr ON gr.account_id=gh.account_id AND gr.grant_id=gh.grant_id AND gr.grant_version=gh.grant_version AND gr.application_id=gh.application_id AND gr.credential_id=gh.credential_id AND gr.credential_generation=gh.credential_generation AND gr.capability=gh.capability
        WHERE ac.account_id=$1 AND cr.principal_id=$2 AND ac.control_revision=$5
          AND ac.content_hash=$6 AND cr.content_hash=$7 AND gr.content_hash=$8
          AND ac.account_generation='new' AND ac.lifecycle_state='active' AND ac.deletion_epoch IS NULL
          AND ah.conflict_reason IS NULL AND ah.conflict_at_control_revision IS NULL
          AND ah.activated_epoch=ac.account_epoch AND ah.activation_control_revision<=ac.control_revision
          AND cr.credential_kind='firebase' AND cr.authentication_strength='firebase-id-token' AND cr.lifecycle='active'
          AND (cr.expires_at IS NULL OR cr.expires_at>clock_timestamp())
          AND gr.lifecycle='active' AND gr.enabled=true
          AND clock_timestamp()<to_timestamp($9) AND clock_timestamp()<to_timestamp($10)
        FOR UPDATE OF ah, ac, ch, cr, gh, gr`,
          values: [
            m.accountId,
            m.principalId,
            m.applicationId,
            m.credentialId,
            m.controlRevision,
            m.controlHash,
            m.credentialHash,
            m.grantHash,
            m.expiresAt,
            identity.expires_at_epoch_seconds,
          ],
        });
        if (authority.length !== 1)
          throw Error("binding_authority_unavailable");
        const roots = await connection.query({
          name: "firebase_binding.existing_identity",
          text: "SELECT account_id, principal_id, source_control_revision FROM omi_memory.firebase_identity_bindings WHERE firebase_project_id=$1 AND firebase_uid=$2",
          values: [m.projectId, m.uid],
        });
        if (
          roots.length > 1 ||
          (roots.length === 1 &&
            (roots[0]!.account_id !== m.accountId ||
              roots[0]!.principal_id !== m.principalId ||
              String(roots[0]!.source_control_revision) !==
                String(m.controlRevision)))
        )
          throw Error("binding_conflict");
        const bindings = await connection.query({
          name: "firebase_binding.existing_credential",
          text: "SELECT principal_id, credential_id FROM omi_memory.firebase_application_credential_bindings WHERE account_id=$1 AND firebase_project_id=$2 AND firebase_uid=$3 AND application_id=$4",
          values: [m.accountId, m.projectId, m.uid, m.applicationId],
        });
        if (
          bindings.length > 1 ||
          (bindings.length === 1 &&
            (bindings[0]!.principal_id !== m.principalId ||
              bindings[0]!.credential_id !== m.credentialId))
        )
          throw Error("binding_conflict");
        if (!roots.length)
          await connection.execute({
            name: "firebase_binding.insert_identity",
            text: "INSERT INTO omi_memory.firebase_identity_bindings (firebase_project_id,firebase_uid,account_id,principal_id,source_control_revision) VALUES ($1,$2,$3,$4,$5)",
            values: [
              m.projectId,
              m.uid,
              m.accountId,
              m.principalId,
              m.controlRevision,
            ],
          });
        if (!bindings.length)
          await connection.execute({
            name: "firebase_binding.insert_credential",
            text: "INSERT INTO omi_memory.firebase_application_credential_bindings (account_id,firebase_project_id,firebase_uid,principal_id,application_id,credential_id) VALUES ($1,$2,$3,$4,$5,$6)",
            values: [
              m.accountId,
              m.projectId,
              m.uid,
              m.principalId,
              m.applicationId,
              m.credentialId,
            ],
          });
        if (
          input.now() >=
          Math.min(m.expiresAt, identity.expires_at_epoch_seconds)
        )
          throw Error("binding_expired");
        return roots.length && bindings.length
          ? ("unchanged" as const)
          : ("bound" as const);
      }
    );
    committed = true;
    await input.audit(result);
    return result;
  } catch {
    await input.audit(committed ? "reconcile_required" : "failed");
    throw Error("binding_unavailable_or_conflicting");
  }
}

if (import.meta.main) {
  let closeIdentity: (() => Promise<void>) | undefined;
  let closePool: (() => Promise<void>) | undefined;
  let receipt: Awaited<ReturnType<typeof open>> | undefined;
  try {
    const [manifestPath, tokenPath, receiptPath, ...extra] =
      process.argv.slice(2);
    if (!manifestPath || !tokenPath || !receiptPath || extra.length)
      throw Error("invalid_arguments");
    const now = () => Math.floor(Date.now() / 1000);
    const manifest = parseBindingManifest(
      JSON.parse(await readFile(manifestPath, "utf8")),
      now()
    );
    const token = (await readFile(tokenPath, "utf8")).trim();
    const databaseUrl = process.env.OMI_BINDING_OPERATOR_DATABASE_URL;
    if (!databaseUrl) throw Error("operator_database_missing");
    const identity = await createFirebaseAdminIdTokenAdapter({
      project_id: manifest.projectId,
      app_name: "omi-binding-operator",
      runtime_mode: "deployed",
    });
    closeIdentity = () => identity.close();
    const pool = createPostgresJsTransactionPool({
      connectionString: databaseUrl,
      maxConnections: 1,
      connectTimeoutSeconds: 10,
    });
    closePool = () => pool.close();
    receipt = await open(receiptPath, "wx", 0o600);
    const digest = createHash("sha256")
      .update(JSON.stringify(manifest))
      .digest("hex");
    const result = await bindFirebaseIdentity({
      manifest,
      token,
      pool,
      now,
      verifier: createFirebaseIdentityVerifier({
        project_id: manifest.projectId,
        runtime_mode: "deployed",
        adapter: identity.adapter,
      }),
      async audit(event) {
        await receipt!.write(
          `${JSON.stringify({ event, manifestDigest: digest, at: now() })}\n`
        );
        await receipt!.sync();
      },
    });
    console.info(`firebase binding ${result}`);
  } catch {
    console.error(
      "firebase binding unavailable; inspect the private operator receipt and reconcile before retrying"
    );
    process.exitCode = 1;
  } finally {
    await closePool?.();
    await closeIdentity?.();
    await receipt?.close();
  }
}
