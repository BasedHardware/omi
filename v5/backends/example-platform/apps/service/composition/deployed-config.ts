export function readDeployedConfig(env: Readonly<Record<string, string | undefined>>) {
  const required = (key: string) => {
    const value = env[key];
    if (!value || value !== value.trim()) throw new TypeError(`missing_or_invalid_${key}`);
    return value;
  };
  if (env.FIREBASE_AUTH_EMULATOR_HOST !== undefined) throw new TypeError("deployed_auth_emulator_forbidden");
  const hex = (key: string) => {
    const value = required(key);
    if (!/^[a-f0-9]{64}$/.test(value)) throw new TypeError(`invalid_${key}`);
    return value;
  };
  const port = Number(env.PORT ?? "8080");
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535) throw new TypeError("invalid_PORT");
  const databaseUrl = required("OMI_DATABASE_URL");
  const database = new URL(databaseUrl);
  if (!["postgres:", "postgresql:"].includes(database.protocol)) throw new TypeError("invalid_database_url");
  const databaseSocketDirectory = env.OMI_DATABASE_SOCKET_DIRECTORY;
  if (databaseSocketDirectory !== undefined &&
      (!/^\/(?:[a-zA-Z0-9._:-]+\/)*[a-zA-Z0-9._:-]+$/.test(databaseSocketDirectory) ||
       databaseSocketDirectory.split("/").some(part => part === "." || part === ".."))) {
    throw new TypeError("invalid_database_socket_directory");
  }
  const gateway = new URL(required("OMI_LLM_GATEWAY_URL"));
  if (gateway.protocol !== "https:" || gateway.username || gateway.password || gateway.search || gateway.hash) throw new TypeError("invalid_gateway_url");
  const laneId = required("OMI_MEMORY_RENDER_LANE");
  if (!/^omi:auto:[a-z0-9][a-z0-9-]{0,95}$/.test(laneId)) throw new TypeError("invalid_render_lane");
  const accountTimezone = required("OMI_ACCOUNT_TIMEZONE");
  new Intl.DateTimeFormat("en", { timeZone: accountTimezone }).format(0);
  const transcriptionApiKey = required("OMI_TRANSCRIPTION_API_KEY");
  const transcriptionModel = required("OMI_TRANSCRIPTION_MODEL");
  if (!/^[\x21-\x7e]{1,4096}$/.test(transcriptionApiKey) || !/^[a-z0-9][a-z0-9.-]{0,63}$/.test(transcriptionModel)) throw new TypeError("invalid_transcription_configuration");
  return Object.freeze({
    port, databaseUrl, databaseSocketDirectory, accountTimezone, transcriptionApiKey, transcriptionModel,
    projectId: required("OMI_FIREBASE_PROJECT_ID"),
    applicationId: required("OMI_APPLICATION_ID"),
    databaseGeneration: hex("OMI_DATABASE_GENERATION_DIGEST"),
    codecKey: Buffer.from(hex("OMI_CODEC_KEY_HEX"), "hex"),
    cursorKey: Buffer.from(hex("OMI_CURSOR_KEY_HEX"), "hex"),
    gatewayEndpoint: gateway.href.replace(/\/$/, "").endsWith("/v1/chat/completions")
      ? gateway.href.replace(/\/$/, "") : `${gateway.href.replace(/\/$/, "")}/v1/chat/completions`,
    gatewayToken: required("OMI_LLM_GATEWAY_SERVICE_TOKEN"),
    laneId,
  });
}
