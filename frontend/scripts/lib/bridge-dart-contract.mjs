import { readFileSync } from "node:fs";

export const STREAM_SOURCE_REL = "contracts/src/bridge/stream.ts";
export const STAGING_SOURCE_REL = "contracts/src/bridge/chat-attachment-staging.ts";
export const APP_CONTRACT_SOURCE_REL = "contracts/ratified/src/projections/synthesized.ts";

function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^[ \t]*\/\/.*$/gm, "");
}

function quotedConstant(source, name) {
  const match = source.match(new RegExp(`export const ${name}\\s*=\\s*"([^"]+)"`));
  if (!match) throw new Error(`could not extract ${name}`);
  return match[1];
}

function typeBody(source, name) {
  const match = source.match(new RegExp(`export type ${name}\\s*=([\\s\\S]*?);\\s*(?=export )`));
  if (!match) throw new Error(`could not extract ${name}`);
  return match[1];
}

function interfaceFields(source, name) {
  const match = source.match(new RegExp(`export interface ${name}\\s*\\{([\\s\\S]*?)\\n\\}`));
  if (!match) throw new Error(`could not extract ${name}`);
  const fields = [...match[1].matchAll(/^\s*(?:readonly\s+)?([A-Za-z_$][\w$]*)(?:\?)?\s*:/gm)].map((item) => item[1]);
  if (fields.length === 0) throw new Error(`${name} extracted with no fields`);
  return fields;
}

function discriminatedVariants(source, name) {
  const body = typeBody(source, name);
  const variants = new Map();
  for (const object of body.matchAll(/\{([^{}]+)\}/g)) {
    const discriminator = object[1].match(/\bt\s*:\s*"([^"]+)"/);
    if (!discriminator) continue;
    const fields = [...object[1].matchAll(/(?:^|;)\s*([A-Za-z_$][\w$]*)(?:\?)?\s*:/g)].map((item) => item[1]);
    variants.set(discriminator[1], fields);
  }
  if (variants.size === 0) throw new Error(`${name} extracted with no discriminated variants`);
  return variants;
}

function stringLiterals(source, name) {
  const values = [...typeBody(source, name).matchAll(/"([^"]+)"/g)].map((item) => item[1]);
  if (values.length === 0) throw new Error(`${name} extracted with no string literals`);
  return values;
}

function wireFields(source, name) {
  const match = source.match(new RegExp(`export type ${name}\\s*=.*?&\\s*\\{([^}]+)\\}`));
  if (!match) throw new Error(`could not extract ${name}`);
  const fields = [...match[1].matchAll(/([A-Za-z_$][\w$]*)\s*:/g)].map((item) => item[1]);
  if (fields.length === 0) throw new Error(`${name} extracted with no added fields`);
  return fields;
}

export function readBridgeDartContracts(root) {
  const stream = stripComments(readFileSync(new URL(`../../${STREAM_SOURCE_REL}`, root), "utf8"));
  const staging = stripComments(readFileSync(new URL(`../../${STAGING_SOURCE_REL}`, root), "utf8"));
  const appContract = stripComments(readFileSync(new URL(`../../${APP_CONTRACT_SOURCE_REL}`, root), "utf8"));

  const toShell = discriminatedVariants(stream, "StreamToShell");
  const fromShell = discriminatedVariants(stream, "StreamFromShell");
  const toShellWireFields = wireFields(stream, "StreamToShellWire");
  const fromShellWireFields = wireFields(stream, "StreamFromShellWire");
  for (const fields of toShell.values()) fields.push(...toShellWireFields.filter((field) => !fields.includes(field)));
  for (const fields of fromShell.values()) fields.push(...fromShellWireFields.filter((field) => !fields.includes(field)));

  const descriptorFields = interfaceFields(staging, "StagedChatAttachment");
  const stateMatch = staging.match(/export interface StagedChatAttachment[\s\S]*?\bstate\s*:\s*"([^"]+)"/);
  if (!stateMatch) throw new Error("could not extract StagedChatAttachment.state");
  const requestFields = interfaceFields(staging, "BridgeChatAttachmentStagingRequest");
  const requestMessage = staging.match(/export interface BridgeChatAttachmentStagingRequest[\s\S]*?\bt\s*:\s*"([^"]+)"/);
  if (!requestMessage) throw new Error("could not extract BridgeChatAttachmentStagingRequest.t");

  return {
    streamChannel: quotedConstant(stream, "BRIDGE_STREAM_MESSAGE_CHANNEL"),
    streamSink: quotedConstant(stream, "BRIDGE_STREAM_SINK_FUNCTION"),
    chatGenerationChannel: quotedConstant(stream, "CHAT_GENERATION_STREAM_CHANNEL"),
    chatAgentRunChannel: quotedConstant(stream, "CHAT_AGENT_RUN_STREAM_CHANNEL"),
    chatGenerationParameterFields: interfaceFields(stream, "ChatGenerationStreamParams"),
    chatAgentRunParameterFields: interfaceFields(stream, "ChatAgentRunStreamParams"),
    toShell,
    fromShell,
    stagingChannel: quotedConstant(staging, "BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL"),
    stagingReply: quotedConstant(staging, "BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION"),
    stagingRequestMessage: requestMessage[1],
    stagingRequestFields: requestFields,
    stagingFailureReasons: stringLiterals(staging, "BridgeChatAttachmentStagingFailureReason"),
    descriptorFields,
    stagedState: stateMatch[1],
    appContractHeader: quotedConstant(appContract, "APP_CONTRACT_VERSION_HEADER"),
    appContractVersion: quotedConstant(appContract, "SYNTHESIZED_READ_CONTRACT_VERSION"),
  };
}
