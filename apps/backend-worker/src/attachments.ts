import { CHAT_CAPABILITIES, type StagedAttachment } from "./wire";

function isBoundedString(value: unknown, maxLength: number): value is string {
  return (
    typeof value === "string" && value.length > 0 && value.length <= maxLength
  );
}

export const ATTACHMENT_CAPABILITIES = {
  maxAttachmentsPerMessage: CHAT_CAPABILITIES.maxAttachmentsPerMessage,
  maxAttachmentBytes: CHAT_CAPABILITIES.maxAttachmentBytes,
  allowedAttachmentMimeTypes: CHAT_CAPABILITIES.allowedAttachmentMimeTypes,
  stagingTtlMs: 24 * 60 * 60 * 1000,
} as const;

export type AttachmentCapabilities = typeof ATTACHMENT_CAPABILITIES;

export type AttachmentStageRequest = {
  opId: string;
  displayName: string;
  mimeType: string;
  sizeBytes: number;
};

export type UploadContract = {
  method: "PUT";
  url: string | null;
  headers: Record<string, string>;
  key: string;
  expiresAt: string;
};

export type StagingResponse = {
  attachment: StagedAttachment;
  upload: UploadContract;
};

export type StageResult =
  | { kind: "ok"; response: StagingResponse; created: boolean }
  | { kind: "conflict" };

type StoredAttachment = {
  id: string;
  account_id: string;
  op_id: string;
  display_name: string;
  media_type: string;
  size_bytes: number;
  state: string;
  r2_key: string;
  expires_at: number;
  bound_message_id: string | null;
  created_at: number;
  updated_at: number;
};

export type SignedUploadEnv = {
  R2_ACCOUNT_ID?: string;
  R2_BUCKET_NAME?: string;
  R2_ACCESS_KEY_ID?: string;
  R2_SECRET_ACCESS_KEY?: string;
  R2_SIGNED_URL_TTL_SECONDS?: string | number;
};

export type SignedUploadConfig = {
  r2AccountId: string;
  bucketName: string;
  accessKeyId: string;
  secretAccessKey: string;
  ttlSeconds: number;
};

const DEFAULT_SIGNED_URL_TTL_SECONDS = 900;
const MAX_SIGNED_URL_TTL_SECONDS = 86_400;

export function parseSignedUploadConfig(
  env: SignedUploadEnv
): SignedUploadConfig | null {
  if (
    !isBoundedString(env.R2_ACCOUNT_ID, 64) ||
    !/^[0-9A-Za-z_-]+$/.test(env.R2_ACCOUNT_ID) ||
    !isBoundedString(env.R2_BUCKET_NAME, 63) ||
    !/^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/.test(env.R2_BUCKET_NAME) ||
    !isBoundedString(env.R2_ACCESS_KEY_ID, 128) ||
    !/^[0-9A-Za-z+/=_-]+$/.test(env.R2_ACCESS_KEY_ID) ||
    !isBoundedString(env.R2_SECRET_ACCESS_KEY, 128)
  )
    return null;
  const rawTtl = env.R2_SIGNED_URL_TTL_SECONDS;
  let ttlSeconds: number;
  if (rawTtl === undefined || rawTtl === null || rawTtl === "") {
    ttlSeconds = DEFAULT_SIGNED_URL_TTL_SECONDS;
  } else {
    const parsed = typeof rawTtl === "number" ? rawTtl : Number(rawTtl);
    if (
      !Number.isSafeInteger(parsed) ||
      parsed < 1 ||
      parsed > MAX_SIGNED_URL_TTL_SECONDS
    )
      return null;
    ttlSeconds = parsed;
  }
  return {
    r2AccountId: env.R2_ACCOUNT_ID,
    bucketName: env.R2_BUCKET_NAME,
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    ttlSeconds,
  };
}

export type UploadUrlSigner = (
  r2Key: string,
  expiresAtMs: number
) => Promise<string>;

export function makeR2UploadUrlSigner(
  config: SignedUploadConfig
): UploadUrlSigner {
  return async (r2Key) =>
    createPresignedR2Url({
      r2AccountId: config.r2AccountId,
      bucketName: config.bucketName,
      key: r2Key,
      accessKeyId: config.accessKeyId,
      secretAccessKey: config.secretAccessKey,
      expiresIn: config.ttlSeconds,
    });
}

export function parseAttachmentStageRequest(
  body: unknown
): AttachmentStageRequest | null {
  if (body === null || typeof body !== "object" || Array.isArray(body))
    return null;
  const item = body as Record<string, unknown>;
  if (
    !isBoundedString(item["opId"], 128) ||
    !isBoundedString(item["displayName"], 256) ||
    !isBoundedString(item["mimeType"], 128) ||
    !Number.isSafeInteger(item["sizeBytes"]) ||
    (item["sizeBytes"] as number) <= 0
  )
    return null;
  const mimeType = item["mimeType"] as string;
  if (!ATTACHMENT_CAPABILITIES.allowedAttachmentMimeTypes.includes(mimeType))
    return null;
  if (
    (item["sizeBytes"] as number) > ATTACHMENT_CAPABILITIES.maxAttachmentBytes
  )
    return null;
  return {
    opId: item["opId"] as string,
    displayName: item["displayName"] as string,
    mimeType,
    sizeBytes: item["sizeBytes"] as number,
  };
}

export async function stageAttachment(
  db: D1Database,
  accountId: string,
  request: AttachmentStageRequest,
  capabilities: AttachmentCapabilities,
  r2KeyPrefix: string,
  signer?: UploadUrlSigner | null
): Promise<StageResult> {
  const prior = await db
    .prepare(
      "SELECT id, display_name, media_type, size_bytes, state, r2_key, expires_at FROM chat_attachments WHERE account_id = ? AND op_id = ?"
    )
    .bind(accountId, request.opId)
    .first<{
      id: string;
      display_name: string;
      media_type: string;
      size_bytes: number;
      state: string;
      r2_key: string;
      expires_at: number;
    }>();

  if (prior !== null) {
    if (
      prior.display_name !== request.displayName ||
      prior.media_type !== request.mimeType ||
      prior.size_bytes !== request.sizeBytes
    )
      return { kind: "conflict" };
    const url =
      signer === null || signer === undefined
        ? null
        : await signer(prior.r2_key, prior.expires_at);
    return {
      kind: "ok",
      created: false,
      response: stagingResponse(
        prior.id,
        request.displayName,
        request.mimeType,
        prior.size_bytes,
        prior.r2_key,
        prior.expires_at,
        url
      ),
    };
  }

  const id = crypto.randomUUID();
  const r2Key = `${r2KeyPrefix}/${accountId}/${id}`;
  const now = Date.now();
  const expiresAt = now + capabilities.stagingTtlMs;

  await db
    .prepare(
      "INSERT INTO chat_attachments (id, account_id, op_id, display_name, media_type, size_bytes, state, r2_key, expires_at, bound_message_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'staged', ?, ?, NULL, ?, ?)"
    )
    .bind(
      id,
      accountId,
      request.opId,
      request.displayName,
      request.mimeType,
      request.sizeBytes,
      r2Key,
      expiresAt,
      now,
      now
    )
    .run();

  const url =
    signer === null || signer === undefined
      ? null
      : await signer(r2Key, expiresAt);
  return {
    kind: "ok",
    created: true,
    response: stagingResponse(
      id,
      request.displayName,
      request.mimeType,
      request.sizeBytes,
      r2Key,
      expiresAt,
      url
    ),
  };
}

export async function readAttachment(
  db: D1Database,
  accountId: string,
  id: string
): Promise<StoredAttachment | null> {
  const row = await db
    .prepare(
      "SELECT id, account_id, op_id, display_name, media_type, size_bytes, state, r2_key, expires_at, bound_message_id, created_at, updated_at FROM chat_attachments WHERE id = ? AND account_id = ?"
    )
    .bind(id, accountId)
    .first<StoredAttachment>();
  return row;
}

export function stagingResponse(
  id: string,
  displayName: string,
  mimeType: string,
  sizeBytes: number,
  r2Key: string,
  expiresAtMs: number,
  url: string | null
): StagingResponse {
  const expiresAtIso = new Date(expiresAtMs).toISOString();
  return {
    attachment: {
      id,
      mimeType,
      sizeBytes,
      expiresAt: expiresAtIso,
      state: "staged",
    },
    upload: {
      method: "PUT",
      url,
      headers: { "content-type": mimeType },
      key: r2Key,
      expiresAt: expiresAtIso,
    },
  };
}

export type PresignedUrlParams = {
  r2AccountId: string;
  bucketName: string;
  key: string;
  accessKeyId: string;
  secretAccessKey: string;
  expiresIn: number;
};

export async function createPresignedR2Url(
  params: PresignedUrlParams
): Promise<string> {
  const region = "auto";
  const service = "s3";
  const now = new Date();
  const dateStamp = ymd(now);
  const amzDate = amzDateFormat(now);
  const credentialScope = `${dateStamp}/${region}/${service}/aws4_request`;
  const credential = `${encodeURIComponent(
    params.accessKeyId
  )}/${credentialScope}`;
  const signedHeaders = "host";
  const host = `${params.r2AccountId}.r2.cloudflarestorage.com`;

  const queryParams = new URLSearchParams({
    "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
    "X-Amz-Credential": credential,
    "X-Amz-Date": amzDate,
    "X-Amz-Expires": String(params.expiresIn),
    "X-Amz-SignedHeaders": signedHeaders,
  });

  const canonicalUri = `/${params.bucketName}/${params.key}`;
  const canonicalQueryString = queryParams
    .toString()
    .split("&")
    .map((pair) => pair)
    .join("&");
  const canonicalHeaders = `host:${host}\n`;
  const canonicalRequest = `PUT\n${canonicalUri}\n${canonicalQueryString}\n${canonicalHeaders}\n${signedHeaders}\nUNSIGNED-PAYLOAD`;
  const canonicalRequestHash = await sha256Hex(canonicalRequest);
  const stringToSign = `AWS4-HMAC-SHA256\n${amzDate}\n${credentialScope}\n${canonicalRequestHash}`;
  const signingKey = await deriveSigningKey(
    params.secretAccessKey,
    dateStamp,
    region,
    service
  );
  const signature = await hmacSha256Hex(signingKey, stringToSign);
  return `https://${host}${canonicalUri}?${canonicalQueryString}&X-Amz-Signature=${signature}`;
}

async function hmacSha256(
  key: BufferSource,
  message: string
): Promise<ArrayBuffer> {
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    key,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  return crypto.subtle.sign(
    "HMAC",
    cryptoKey,
    new TextEncoder().encode(message)
  );
}

async function hmacSha256Hex(
  key: ArrayBuffer,
  message: string
): Promise<string> {
  const signature = await hmacSha256(key, message);
  return toHex(signature);
}

async function sha256Hex(message: string): Promise<string> {
  const hash = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(message)
  );
  return toHex(hash);
}

async function deriveSigningKey(
  secretAccessKey: string,
  dateStamp: string,
  region: string,
  service: string
): Promise<ArrayBuffer> {
  const kDate = await hmacSha256(
    new TextEncoder().encode(`AWS4${secretAccessKey}`),
    dateStamp
  );
  const kRegion = await hmacSha256(kDate, region);
  const kService = await hmacSha256(kRegion, service);
  return hmacSha256(kService, "aws4_request");
}

function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function ymd(date: Date): string {
  return date.toISOString().slice(0, 10).replaceAll("-", "");
}

function amzDateFormat(date: Date): string {
  return `${ymd(date)}T${date
    .toISOString()
    .slice(11, 19)
    .replaceAll(":", "")}Z`;
}

export type AttachmentState =
  | "staged"
  | "uploaded"
  | "ingesting"
  | "ingested"
  | "invalid"
  | "bound"
  | "expired";

export type AttachmentIngestMessage = {
  attachmentId: string;
  accountId: string;
  r2Key: string;
  mimeType: string;
};

export type R2MetadataProbe = {
  size: number;
  contentType: string | undefined;
} | null;

export type CompleteOutcome =
  | { kind: "accepted"; attachment: AttachmentView }
  | { kind: "queued"; attachment: AttachmentView }
  | { kind: "ingested"; attachment: AttachmentView }
  | { kind: "not_found" }
  | { kind: "expired" }
  | { kind: "absent" }
  | { kind: "mismatch" }
  | { kind: "conflict" };

const INGESTIBLE_STATES: ReadonlySet<AttachmentState> = new Set([
  "staged",
  "uploaded",
  "ingesting",
]);

async function markAttachmentState(
  db: D1Database,
  id: string,
  accountId: string,
  nextState: AttachmentState,
  now: number,
  fromStates: ReadonlySet<AttachmentState>
): Promise<boolean> {
  const placeholders = [...fromStates].map(() => "?").join(", ");
  const result = await db
    .prepare(
      `UPDATE chat_attachments SET state = ?, updated_at = ? WHERE id = ? AND account_id = ? AND state IN (${placeholders})`
    )
    .bind(nextState, now, id, accountId, ...[...fromStates])
    .run();
  const changes = (result.meta as { changes?: number } | undefined)?.changes;
  return typeof changes === "number" ? changes > 0 : false;
}

async function probeR2Metadata(
  r2: R2Bucket,
  r2Key: string
): Promise<R2MetadataProbe> {
  const head = await r2.head(r2Key);
  if (head === null) return null;
  return {
    size: head.size,
    contentType: head.httpMetadata?.contentType,
  };
}

export type AttachmentView = {
  id: string;
  mimeType: string;
  sizeBytes: number;
  expiresAt: string;
  state: AttachmentState;
};

function attachmentView(row: StoredAttachment): AttachmentView {
  return {
    id: row.id,
    mimeType: row.media_type,
    sizeBytes: row.size_bytes,
    expiresAt: new Date(row.expires_at).toISOString(),
    state: row.state as AttachmentState,
  };
}

export async function completeAttachment(
  db: D1Database,
  r2: R2Bucket,
  ingest: Queue<AttachmentIngestMessage>,
  accountId: string,
  attachmentId: string,
  now: number
): Promise<CompleteOutcome> {
  const row = await readAttachment(db, accountId, attachmentId);
  if (row === null) return { kind: "not_found" };

  if (row.state === "ingested")
    return { kind: "ingested", attachment: attachmentView(row) };
  if (row.state === "expired") return { kind: "expired" };
  if (row.state === "invalid") return { kind: "conflict" };
  if (row.state === "bound") return { kind: "conflict" };

  if (now > row.expires_at) {
    await markAttachmentState(
      db,
      row.id,
      accountId,
      "expired",
      now,
      INGESTIBLE_STATES
    );
    return { kind: "expired" };
  }

  if (row.state === "uploaded" || row.state === "ingesting") {
    await ingest.send({
      attachmentId: row.id,
      accountId,
      r2Key: row.r2_key,
      mimeType: row.media_type,
    });
    return { kind: "queued", attachment: attachmentView(row) };
  }

  const probe = await probeR2Metadata(r2, row.r2_key);
  if (probe === null) return { kind: "absent" };
  if (probe.size !== row.size_bytes) {
    await markAttachmentState(
      db,
      row.id,
      accountId,
      "invalid",
      now,
      INGESTIBLE_STATES
    );
    return { kind: "mismatch" };
  }
  if (probe.contentType !== row.media_type) {
    await markAttachmentState(
      db,
      row.id,
      accountId,
      "invalid",
      now,
      INGESTIBLE_STATES
    );
    return { kind: "mismatch" };
  }

  const marked = await markAttachmentState(
    db,
    row.id,
    accountId,
    "uploaded",
    now,
    new Set<AttachmentState>(["staged"])
  );
  if (!marked) {
    const refreshed = await readAttachment(db, accountId, attachmentId);
    if (refreshed === null) return { kind: "not_found" };
    if (refreshed.state === "ingested")
      return { kind: "ingested", attachment: attachmentView(refreshed) };
    if (refreshed.state === "invalid") return { kind: "conflict" };
    if (refreshed.state === "expired") return { kind: "expired" };
    return { kind: "queued", attachment: attachmentView(refreshed) };
  }

  await ingest.send({
    attachmentId: row.id,
    accountId,
    r2Key: row.r2_key,
    mimeType: row.media_type,
  });
  return {
    kind: "accepted",
    attachment: attachmentView({ ...row, state: "uploaded" }),
  };
}

export type IngestOutcome =
  | { kind: "ingested" }
  | { kind: "invalid" }
  | { kind: "expired" }
  | { kind: "skipped" }
  | { kind: "not_found" };

export async function consumeAttachmentIngest(
  db: D1Database,
  r2: R2Bucket,
  message: AttachmentIngestMessage,
  now: number
): Promise<IngestOutcome> {
  const row = await readAttachment(db, message.accountId, message.attachmentId);
  if (row === null) return { kind: "not_found" };
  if (row.account_id !== message.accountId) return { kind: "not_found" };

  if (row.state === "ingested") return { kind: "skipped" };
  if (row.state === "invalid") return { kind: "skipped" };
  if (row.state === "expired") return { kind: "skipped" };
  if (row.state === "bound") return { kind: "skipped" };

  if (now > row.expires_at) {
    await markAttachmentState(
      db,
      row.id,
      row.account_id,
      "expired",
      now,
      INGESTIBLE_STATES
    );
    return { kind: "expired" };
  }

  const probe = await probeR2Metadata(r2, row.r2_key);
  if (probe === null) {
    await markAttachmentState(
      db,
      row.id,
      row.account_id,
      "invalid",
      now,
      INGESTIBLE_STATES
    );
    return { kind: "invalid" };
  }
  if (probe.size !== row.size_bytes || probe.contentType !== row.media_type) {
    await markAttachmentState(
      db,
      row.id,
      row.account_id,
      "invalid",
      now,
      INGESTIBLE_STATES
    );
    return { kind: "invalid" };
  }

  await markAttachmentState(
    db,
    row.id,
    row.account_id,
    "ingesting",
    now,
    new Set<AttachmentState>(["uploaded", "ingesting"])
  );

  const committed = await markAttachmentState(
    db,
    row.id,
    row.account_id,
    "ingested",
    now,
    new Set<AttachmentState>(["uploaded", "ingesting"])
  );
  return committed ? { kind: "ingested" } : { kind: "skipped" };
}
