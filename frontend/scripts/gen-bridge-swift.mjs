#!/usr/bin/env node
// Generates the Swift mirror of the security-bearing constants in the shared
// bridge contracts so the macOS shell cannot drift from their vocabulary.
// `--check` verifies the generated file matches (CI/DoD mode); default rewrites
// it.
//
// Why this exists (wave-7 FG-2): the shell hardcoded the channel name, the
// forbidden-header list, and the failure-reason/status mapping, kept in sync by
// hand. A rename in the contract compiled fine and silently broke the shell at
// runtime — and a wrong forbidden-header list is a credential-forgery hole, not
// a cosmetic bug.
//
// Extraction and the write/check plumbing live in scripts/lib/ and are shared
// with gen-bridge-dart.mjs; only the Swift emitter is here.
import fs from "node:fs";
import path from "node:path";
import { camelCase, emit, readBridgeHttpContract, SOURCE_REL } from "./lib/bridge-http-contract.mjs";

const ROOT = process.env.OMI_CORE_ROOT ?? new URL("..", import.meta.url).pathname;
const STREAM_SOURCE_REL = "contracts/src/bridge/stream.ts";
const STAGING_SOURCE_REL = "contracts/src/bridge/chat-attachment-staging.ts";
const APP_CONTRACT_SOURCE_REL = "contracts/ratified/src/projections/synthesized.ts";
const OUT_REL = {
  path: "shell/Sources/OmiShell/BridgeHttpContract.generated.swift",
  envVar: "OMI_MACOS_SHELL_DIR",
};

// The macOS shell is in-repo at core/shells/macos since the PR-6 promotion.
// Before that it resolved to a sibling tracker checkout that does not exist in
// a worktree, so this gate SKIPped everywhere and drift went uncaught.
const SHELL_DIR = process.env[OUT_REL.envVar] ?? path.join(ROOT, "shells/macos");

const check = process.argv.includes("--check");

function stripped(relative) {
  return fs.readFileSync(path.join(ROOT, relative), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "");
}

function requiredMatch(source, pattern, declaration) {
  const match = source.match(pattern);
  if (!match) throw new Error(`could not extract ${declaration}`);
  return match[1];
}

function stringUnion(source, declaration) {
  const body = requiredMatch(
    source,
    new RegExp(`export type ${declaration}\\s*=([^;]*);`),
    declaration,
  );
  const values = [...body.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
  if (values.length === 0) throw new Error(`${declaration} extracted as empty`);
  return values;
}

function interfaceFields(source, declaration) {
  const body = requiredMatch(
    source,
    new RegExp(`export interface ${declaration}\\s*\\{([\\s\\S]*?)\\n\\}`),
    declaration,
  );
  const fields = [...body.matchAll(/^\s*(\w+)(\?)?\s*:/gm)].map((match) => ({
    name: match[1],
    optional: match[2] === "?",
  }));
  if (fields.length === 0) throw new Error(`${declaration} extracted as empty`);
  return fields;
}

function readNativeChatContract() {
  const stream = stripped(STREAM_SOURCE_REL);
  const staging = stripped(STAGING_SOURCE_REL);
  const appContract = stripped(APP_CONTRACT_SOURCE_REL);
  const appWireVersion = requiredMatch(
    appContract,
    /export const SYNTHESIZED_READ_CONTRACT_VERSION\s*=\s*"([^"]+)"/,
    "SYNTHESIZED_READ_CONTRACT_VERSION",
  );
  if (!/^\d+\.\d+\.\d+$/.test(appWireVersion)) {
    throw new Error("SYNTHESIZED_READ_CONTRACT_VERSION is not a semantic version");
  }

  const streamToShellBody = requiredMatch(
    stream,
    /export type StreamToShell\s*=([\s\S]*?);\s*\n\s*export type StreamFromShell/,
    "StreamToShell",
  );
  const streamFromShellBody = requiredMatch(
    stream,
    /export type StreamFromShell\s*=([\s\S]*?);\s*\n\s*export const BRIDGE_STREAM_MESSAGE_CHANNEL/,
    "StreamFromShell",
  );
  const messageNames = (body, declaration) => {
    const values = [...body.matchAll(/\bt:\s*"([^"]+)"/g)].map((match) => match[1]);
    if (values.length === 0) throw new Error(`${declaration} message names extracted as empty`);
    return values;
  };

  const stagingDescriptor = interfaceFields(staging, "StagedChatAttachment");
  if (stagingDescriptor.some((field) => field.optional)) {
    throw new Error("StagedChatAttachment gained an optional field — native reply must stay exact");
  }
  const stagingRequest = interfaceFields(staging, "BridgeChatAttachmentStagingRequest");
  if (stagingRequest.some((field) => field.optional)) {
    throw new Error("BridgeChatAttachmentStagingRequest gained an optional field");
  }
  const generationParams = interfaceFields(stream, "ChatGenerationStreamParams");

  return {
    streamChannel: requiredMatch(
      stream,
      /export const BRIDGE_STREAM_MESSAGE_CHANNEL\s*=\s*"([^"]+)"/,
      "BRIDGE_STREAM_MESSAGE_CHANNEL",
    ),
    streamSink: requiredMatch(
      stream,
      /export const BRIDGE_STREAM_SINK_FUNCTION\s*=\s*"([^"]+)"/,
      "BRIDGE_STREAM_SINK_FUNCTION",
    ),
    chatGenerationChannel: requiredMatch(
      stream,
      /export const CHAT_GENERATION_STREAM_CHANNEL\s*=\s*"([^"]+)"/,
      "CHAT_GENERATION_STREAM_CHANNEL",
    ),
    streamToShellMessages: messageNames(streamToShellBody, "StreamToShell"),
    streamFromShellMessages: messageNames(streamFromShellBody, "StreamFromShell"),
    generationParams,
    stagingChannel: requiredMatch(
      staging,
      /export const BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL\s*=\s*"([^"]+)"/,
      "BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL",
    ),
    stagingReplyFunction: requiredMatch(
      staging,
      /export const BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION\s*=\s*"([^"]+)"/,
      "BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION",
    ),
    stagingRequestAction: requiredMatch(
      staging,
      /\bt:\s*"([^"]+)";/,
      "BridgeChatAttachmentStagingRequest.t",
    ),
    stagingFailureReasons: stringUnion(staging, "BridgeChatAttachmentStagingFailureReason"),
    stagingDescriptor,
    stagingRequest,
    stagingState: requiredMatch(staging, /\bstate:\s*"([^"]+)";/, "StagedChatAttachment.state"),
    appContractHeader: requiredMatch(
      appContract,
      /export const APP_CONTRACT_VERSION_HEADER\s*=\s*"([^"]+)"/,
      "APP_CONTRACT_VERSION_HEADER",
    ),
    appWireVersion,
  };
}

let contract;
let nativeChat;
try {
  contract = readBridgeHttpContract(path.join(ROOT, SOURCE_REL));
  nativeChat = readNativeChatContract();
} catch (err) {
  console.error(`gen-bridge-swift: ${err.message}`);
  console.error(`  source: ${SOURCE_REL}`);
  process.exit(1);
}
const { channel, forbiddenHeaders, reasons, failureStatus } = contract;
const swiftSet = (values, indent = "    ") => values.map((value) => `${indent}"${value}",`);
const requiredGenerationFields = nativeChat.generationParams.filter((field) => !field.optional).map((field) => field.name);
const optionalGenerationFields = nativeChat.generationParams.filter((field) => field.optional).map((field) => field.name);

const content =
  [
    "// GENERATED by core/scripts/gen-bridge-swift.mjs from the shared bridge and ratified app contracts — do not edit by hand.",
    "// Run `node scripts/gen-bridge-swift.mjs` in core/ after changing those contracts;",
    "// `--check` fails on drift and is part of the core Definition of Done.",
    "",
    "enum BridgeHttpContract {",
    "  /// BRIDGE_HTTP_CHANNEL — the message-handler name the surface feature-detects.",
    `  static let channel = "${channel}"`,
    "",
    "  /// BRIDGE_HTTP_FORBIDDEN_HEADERS — stripped from caller headers, case-insensitively,",
    "  /// BEFORE the shell adds its own credential. Enforced, never trusted.",
    "  static let forbiddenHeaders: Set<String> = [",
    ...forbiddenHeaders.map((h) => `    "${h}",`),
    "  ]",
    "",
    "  /// BridgeHttpFailureReason — the only reasons a shell may report.",
    "  enum FailureReason: String {",
    ...reasons.map((r) => `    case ${camelCase(r)} = "${r}"`),
    "  }",
    "",
    "  /// BRIDGE_HTTP_FAILURE_STATUS — the synthetic status the web binding maps each",
    "  /// reason onto, so `classifyStatus` stays the one place statuses become taxonomy.",
    "  static func syntheticStatus(for reason: FailureReason) -> Int {",
    "    switch reason {",
    ...reasons.map((r) => `    case .${camelCase(r)}: return ${failureStatus.get(r)}`),
    "    }",
    "  }",
    "}",
    "",
    "enum BridgeStreamContract {",
    `  static let channel = "${nativeChat.streamChannel}"`,
    `  static let sinkFunction = "${nativeChat.streamSink}"`,
    `  static let chatGenerationChannel = "${nativeChat.chatGenerationChannel}"`,
    "",
    "  enum ToShellMessage: String {",
    ...nativeChat.streamToShellMessages.map((name) => `    case ${camelCase(name)} = "${name}"`),
    "  }",
    "",
    "  enum FromShellMessage: String {",
    ...nativeChat.streamFromShellMessages.map((name) => `    case ${camelCase(name)} = "${name}"`),
    "  }",
    "",
    "  static let chatGenerationRequiredParameterFields: Set<String> = [",
    ...swiftSet(requiredGenerationFields),
    "  ]",
    "  static let chatGenerationOptionalParameterFields: Set<String> = [",
    ...swiftSet(optionalGenerationFields),
    "  ]",
    "}",
    "",
    "enum BridgeChatAttachmentStagingContract {",
    `  static let channel = "${nativeChat.stagingChannel}"`,
    `  static let replyFunction = "${nativeChat.stagingReplyFunction}"`,
    `  static let requestAction = "${nativeChat.stagingRequestAction}"`,
    `  static let stagedState = "${nativeChat.stagingState}"`,
    "  static let requestFields: Set<String> = [",
    ...swiftSet(nativeChat.stagingRequest.map((field) => field.name)),
    "  ]",
    "  static let descriptorFields: Set<String> = [",
    ...swiftSet(nativeChat.stagingDescriptor.map((field) => field.name)),
    "  ]",
    "",
    "  enum FailureReason: String {",
    ...nativeChat.stagingFailureReasons.map((reason) => `    case ${camelCase(reason)} = "${reason}"`),
    "  }",
    "}",
    "",
    "enum NativeChatRequestContract {",
    `  static let contractVersionHeader = "${nativeChat.appContractHeader}"`,
    `  static let contractVersion = "${nativeChat.appWireVersion}"`,
    "  static let clientIdHeader = \"x-omi-client-id\"",
    "  static let shellIdentity = \"macos\"",
    "}",
    "",
  ].join("\n");

process.exit(
  emit({
    label: "bridge swift",
    shellDir: SHELL_DIR,
    outRel: OUT_REL,
    content,
    check,
    summary: `http=${channel}, stream=${nativeChat.streamChannel}, staging=${nativeChat.stagingChannel}, contract=${nativeChat.appWireVersion}`,
    fs,
    path,
  }),
);
