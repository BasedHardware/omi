import type { Hono } from "hono";

import {
  APP_CONTRACT_VERSION_HEADER,
  resolveDeclaredContractVersion,
} from "@omi-core/ratified-contracts/projections/synthesized";

import type { DevPrincipal } from "../auth/dev-token";
import {
  ATTACHMENT_STAGING_TTL_MS,
  CHAT_MAX_ATTACHMENT_BYTES,
  MAIN_CHAT_ATTACHMENT_SCOPE,
  type AllowedChatAttachmentMimeType,
} from "../chat/attachment-policy";
import type { ChatAttachmentsStore } from "../stores/chat-attachments-store";

export const CHAT_ATTACHMENTS_PATH = "/v1/chat-attachments";
export const CHAT_ATTACHMENT_MAX_DISPLAY_NAME_BYTES = 255;
const MAX_MULTIPART_ENVELOPE_BYTES = CHAT_MAX_ATTACHMENT_BYTES + 65_536;
const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

export interface ChatAttachmentsRouteDependencies {
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  readonly attachments: ChatAttachmentsStore;
  readonly nowEpochMilliseconds: () => number;
  readonly attachmentId: () => string;
  readonly contentReference: () => string;
}

const errorBody = (code: string, action: string): string =>
  JSON.stringify({ error: { code, retryable: false, action } });

const response = (
  value: unknown,
  status: number,
  extraHeaders: Readonly<Record<string, string>> = {},
): Response => new Response(
  typeof value === "string" ? value : JSON.stringify(value),
  { status, headers: { ...JSON_HEADERS, ...extraHeaders } },
);

const unauthorized = (): Response => response(errorBody("unauthorized", "reauthenticate"), 401);
const badRequest = (): Response => response(errorBody("bad_request", "edit_request"), 400);
const validation = (): Response => response(errorBody("validation", "edit_request"), 422);
const unavailable = (): Response => response(
  JSON.stringify({ error: { code: "service_unavailable", retryable: true, action: "retry" } }),
  503,
  { "retry-after": "60" },
);

const principalFrom = (
  authorization: string | undefined,
  resolvePrincipal: ChatAttachmentsRouteDependencies["resolvePrincipal"],
): DevPrincipal | null => {
  if (authorization === undefined || !authorization.startsWith("Bearer ")) return null;
  const token = authorization.slice("Bearer ".length);
  return token.length === 0 ? null : resolvePrincipal(token);
};

const normalizedDisplayName = (raw: unknown): string | null => {
  if (typeof raw !== "string") return null;
  const displayName = (raw.replaceAll("\\", "/").split("/").at(-1) ?? "")
    .normalize("NFC")
    .trim();
  if (displayName.length === 0 || displayName === "." || displayName === ".."
    || /[\u0000-\u001f\u007f]/u.test(displayName)
    || new TextEncoder().encode(displayName).byteLength > CHAT_ATTACHMENT_MAX_DISPLAY_NAME_BYTES) {
    return null;
  }
  return displayName;
};

const begins = (bytes: Uint8Array, expected: readonly number[]): boolean =>
  bytes.byteLength >= expected.length && expected.every((value, index) => bytes[index] === value);

const asciiAt = (bytes: Uint8Array, offset: number, value: string): boolean =>
  begins(bytes.subarray(offset), [...value].map((character) => character.charCodeAt(0)));

const indexOfBytes = (bytes: Uint8Array, needle: Uint8Array, from: number): number => {
  outer: for (let index = from; index <= bytes.byteLength - needle.byteLength; index += 1) {
    for (let offset = 0; offset < needle.byteLength; offset += 1) {
      if (bytes[index + offset] !== needle[offset]) continue outer;
    }
    return index;
  }
  return -1;
};

interface ParsedMultipartFile {
  readonly fieldName: string;
  readonly name: string;
  readonly declaredMimeType: string;
  readonly content: Uint8Array;
}

const unquoteDispositionValue = (value: string): string =>
  value.replace(/\\"/gu, "\"").replace(/\\\\/gu, "\\");

const parseSingleFileMultipart = (
  contentType: string,
  body: Uint8Array,
): ParsedMultipartFile | null => {
  const boundaryMatch = /(?:^|;)\s*boundary=(?:"([^"]{1,200})"|([^;\s]{1,200}))/iu
    .exec(contentType);
  const boundary = boundaryMatch?.[1] ?? boundaryMatch?.[2];
  if (boundary === undefined) return null;
  const encoder = new TextEncoder();
  const delimiter = encoder.encode(`--${boundary}`);
  const nextDelimiter = encoder.encode(`\r\n--${boundary}`);
  const headerTerminator = encoder.encode("\r\n\r\n");
  if (!begins(body, [...delimiter, 0x0d, 0x0a])) return null;

  const parts: ParsedMultipartFile[] = [];
  let cursor = delimiter.byteLength + 2;
  for (;;) {
    const headerEnd = indexOfBytes(body, headerTerminator, cursor);
    if (headerEnd < cursor || headerEnd - cursor > 16_384) return null;
    let headerText: string;
    try {
      headerText = new TextDecoder("utf-8", { fatal: true }).decode(body.subarray(cursor, headerEnd));
    } catch {
      return null;
    }
    const headers = new Map<string, string>();
    for (const line of headerText.split("\r\n")) {
      const separator = line.indexOf(":");
      if (separator <= 0) return null;
      const name = line.slice(0, separator).trim().toLowerCase();
      if (headers.has(name)) return null;
      headers.set(name, line.slice(separator + 1).trim());
    }
    const disposition = headers.get("content-disposition");
    const fieldMatch = disposition === undefined
      ? null
      : /(?:^|;)\s*name="((?:\\.|[^"])*)"/iu.exec(disposition);
    const filenameMatch = disposition === undefined
      ? null
      : /(?:^|;)\s*filename="((?:\\.|[^"])*)"/iu.exec(disposition);
    if (disposition === undefined || !/^form-data(?:;|$)/iu.test(disposition)
      || fieldMatch === null || filenameMatch === null) return null;

    const contentStart = headerEnd + headerTerminator.byteLength;
    const contentEnd = indexOfBytes(body, nextDelimiter, contentStart);
    if (contentEnd < contentStart) return null;
    const declaredMimeType = (headers.get("content-type") ?? "")
      .split(";", 1)[0]!.trim().toLowerCase();
    parts.push(Object.freeze({
      fieldName: unquoteDispositionValue(fieldMatch[1]!),
      name: unquoteDispositionValue(filenameMatch[1]!),
      declaredMimeType,
      content: new Uint8Array(body.slice(contentStart, contentEnd)),
    }));

    cursor = contentEnd + nextDelimiter.byteLength;
    if (body[cursor] === 0x2d && body[cursor + 1] === 0x2d) {
      cursor += 2;
      if (body[cursor] === 0x0d && body[cursor + 1] === 0x0a) cursor += 2;
      if (cursor !== body.byteLength) return null;
      break;
    }
    if (body[cursor] !== 0x0d || body[cursor + 1] !== 0x0a) return null;
    cursor += 2;
  }
  if (parts.length !== 1 || parts[0]?.fieldName !== "file") return null;
  return parts[0] ?? null;
};

const validText = (bytes: Uint8Array): string | null => {
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
  if (text.includes("\0") || /[\u0001-\u0008\u000b\u000e-\u001f\u007f]/u.test(text)) return null;
  return text;
};

const looksLikeMarkdown = (text: string): boolean => {
  const lines = text.split(/\r?\n/u);
  return lines.some((line) => /^(?:#{1,6}\s|>\s|[-*+]\s|\d+[.)]\s|```|~~~)/u.test(line))
    || /\[[^\]\r\n]+\]\([^\s)]+\)/u.test(text)
    || /(?:^|\s)(?:\*\*|__)[^\r\n]+(?:\*\*|__)(?:\s|$)/u.test(text);
};

/** Conservative magic/content detector. Multipart metadata never selects the result. */
export const sniffChatAttachmentMimeType = (
  bytes: Uint8Array,
): AllowedChatAttachmentMimeType | null => {
  if (begins(bytes, [0xff, 0xd8, 0xff])) return "image/jpeg";
  if (begins(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return "image/png";
  if (asciiAt(bytes, 0, "GIF87a") || asciiAt(bytes, 0, "GIF89a")) return "image/gif";
  if (asciiAt(bytes, 0, "RIFF") && asciiAt(bytes, 8, "WEBP")
    && ["VP8 ", "VP8L", "VP8X"].some((chunk) => asciiAt(bytes, 12, chunk))) {
    return "image/webp";
  }
  if (asciiAt(bytes, 0, "%PDF-")) return "application/pdf";
  const text = validText(bytes);
  if (text === null) return null;
  return looksLikeMarkdown(text) ? "text/markdown" : "text/plain";
};

export const registerChatAttachmentsRoute = (
  app: Hono,
  deps: ChatAttachmentsRouteDependencies,
): void => {
  app.post(CHAT_ATTACHMENTS_PATH, async (context) => {
    const principal = principalFrom(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) return unauthorized();
    void resolveDeclaredContractVersion(context.req.header(APP_CONTRACT_VERSION_HEADER));

    const contentType = context.req.header("content-type") ?? "";
    if (!/^multipart\/form-data(?:;|$)/iu.test(contentType)) return badRequest();
    const contentLength = context.req.header("content-length");
    if (contentLength !== undefined) {
      if (!/^\d+$/u.test(contentLength)) return badRequest();
      if (Number(contentLength) > MAX_MULTIPART_ENVELOPE_BYTES) return validation();
    }

    let multipartBody: Uint8Array;
    try {
      multipartBody = new Uint8Array(await context.req.arrayBuffer());
    } catch {
      return badRequest();
    }
    if (multipartBody.byteLength > MAX_MULTIPART_ENVELOPE_BYTES) return validation();
    const file = parseSingleFileMultipart(contentType, multipartBody);
    if (file === null) return validation();
    const displayName = normalizedDisplayName(file.name);
    if (displayName === null || file.content.byteLength === 0
      || file.content.byteLength > CHAT_MAX_ATTACHMENT_BYTES) {
      return validation();
    }
    const content = file.content;
    if (content.byteLength === 0 || content.byteLength > CHAT_MAX_ATTACHMENT_BYTES) return validation();
    const mimeType = sniffChatAttachmentMimeType(content);
    const declaredMimeType = file.declaredMimeType;
    if (mimeType === null || (declaredMimeType !== "" && declaredMimeType !== mimeType)) {
      return validation();
    }

    try {
      const stagedAt = deps.nowEpochMilliseconds();
      const staged = deps.attachments.stage({
        id: deps.attachmentId(),
        contentReference: deps.contentReference(),
        accountId: principal.uid,
        scope: MAIN_CHAT_ATTACHMENT_SCOPE,
        displayName,
        mimeType,
        content,
        stagedAt,
        stageExpiresAt: stagedAt + ATTACHMENT_STAGING_TTL_MS,
      });
      return response({
        attachment: {
          id: staged.id,
          mimeType: staged.mimeType,
          sizeBytes: staged.sizeBytes,
          state: "staged",
          expiresAt: new Date(staged.stageExpiresAt).toISOString(),
        },
      }, 201);
    } catch {
      return unavailable();
    }
  });
};
