/**
 * Standalone OAuth flow for Claude authentication.
 * Reimplements the `setup-token` flow from Claude Code CLI
 * without requiring Ink/TTY.
 *
 * Flow:
 * 1. Generate PKCE (code_verifier + code_challenge)
 * 2. Start local HTTP callback server
 * 3. Build authorize URL → caller opens in browser
 * 4. Wait for callback with auth code
 * 5. Exchange code for tokens
 * 6. Store credentials in macOS Keychain
 * 7. Redirect browser to success page
 */

import { createServer, type Server, type IncomingMessage, type ServerResponse } from "http";
import { request as httpsRequest } from "https";
import { randomBytes, createHash } from "crypto";
import { execSync } from "child_process";
import { URL } from "url";
import { userInfo } from "os";

// --- Constants (from Claude Code CLI) ---

const CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e";
const AUTHORIZE_URL = "https://claude.ai/oauth/authorize";
const TOKEN_URL = "https://console.anthropic.com/v1/oauth/token";
const SUCCESS_URL = "https://console.anthropic.com/oauth/code/success?app=claude-code";
const SCOPES = "user:inference";
const KEYCHAIN_SERVICE = "Claude Code-credentials";
const TOKEN_EXPIRY_SECONDS = 31536000; // 1 year

// --- PKCE Helpers ---

function base64url(buf: Buffer): string {
  return buf.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

function generateCodeVerifier(): string {
  return base64url(randomBytes(32));
}

function generateCodeChallenge(verifier: string): string {
  return base64url(createHash("sha256").update(verifier).digest());
}

function generateState(): string {
  return base64url(randomBytes(32));
}

// --- OAuth Flow ---

export interface OAuthResult {
  accessToken: string;
  refreshToken?: string;
  expiresAt?: string;
  scopes: string[];
}

export interface OAuthFlowHandle {
  /** URL to open in the browser */
  authUrl: string;
  /** Resolves when OAuth completes (code exchanged, credentials stored) */
  complete: Promise<OAuthResult>;
  /** Cancel the flow (close server, reject promise) */
  cancel: () => void;
}

/**
 * Start the OAuth flow. Returns the auth URL to open in the browser
 * and a promise that resolves when authentication completes.
 */
export async function startOAuthFlow(logErr: (msg: string) => void): Promise<OAuthFlowHandle> {
  const codeVerifier = generateCodeVerifier();
  const codeChallenge = generateCodeChallenge(codeVerifier);
  const state = generateState();

  // Start local callback server on a random port
  const { server, port } = await startCallbackServer();
  logErr(`OAuth callback server listening on port ${port}`);

  const redirectUri = `http://localhost:${port}/callback`;

  // Build authorization URL
  const authUrl = new URL(AUTHORIZE_URL);
  authUrl.searchParams.set("code", "true");
  authUrl.searchParams.set("client_id", CLIENT_ID);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("redirect_uri", redirectUri);
  authUrl.searchParams.set("scope", SCOPES);
  authUrl.searchParams.set("code_challenge", codeChallenge);
  authUrl.searchParams.set("code_challenge_method", "S256");
  authUrl.searchParams.set("state", state);

  let cancelled = false;
  let cancelReject: ((err: Error) => void) | null = null;

  const complete = new Promise<OAuthResult>((resolve, reject) => {
    cancelReject = reject;

    // Wait for the callback
    waitForCallback(server, state, logErr)
      .then(async (code) => {
        if (cancelled) return;
        logErr("OAuth callback received, exchanging code for token...");

        // Exchange code for token
        const tokens = await exchangeCodeForToken(code, codeVerifier, state, redirectUri, logErr);

        // Store credentials in Keychain
        storeCredentials(tokens, logErr);

        resolve(tokens);
      })
      .catch((err) => {
        if (!cancelled) reject(err);
      })
      .finally(() => {
        server.close();
      });
  });

  return {
    authUrl: authUrl.toString(),
    complete,
    cancel: () => {
      cancelled = true;
      server.close();
      cancelReject?.(new Error("OAuth flow cancelled"));
    },
  };
}

// --- Callback Server ---

async function startCallbackServer(): Promise<{ server: Server; port: number }> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "localhost", () => {
      const addr = server.address();
      if (!addr || typeof addr === "string") {
        reject(new Error("Failed to get server address"));
        return;
      }
      resolve({ server, port: addr.port });
    });
  });
}

function waitForCallback(
  server: Server,
  expectedState: string,
  logErr: (msg: string) => void
): Promise<string> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error("OAuth callback timed out (10 minutes)"));
      server.close();
    }, 10 * 60 * 1000);

    server.on("request", (req: IncomingMessage, res: ServerResponse) => {
      const parsed = new URL(req.url || "", `http://localhost`);

      if (parsed.pathname !== "/callback") {
        res.writeHead(404);
        res.end("Not Found");
        return;
      }

      const code = parsed.searchParams.get("code");
      const state = parsed.searchParams.get("state");

      if (!code) {
        res.writeHead(400);
        res.end("Authorization code not found");
        reject(new Error("No authorization code received"));
        clearTimeout(timeout);
        return;
      }

      if (state !== expectedState) {
        res.writeHead(400);
        res.end("Invalid state parameter");
        reject(new Error("Invalid state parameter"));
        clearTimeout(timeout);
        return;
      }

      logErr("OAuth callback received with valid code");

      // Redirect browser to success page
      res.writeHead(302, { Location: SUCCESS_URL });
      res.end();

      clearTimeout(timeout);
      resolve(code);
    });
  });
}

// --- Token Exchange ---

async function exchangeCodeForToken(
  code: string,
  codeVerifier: string,
  state: string,
  redirectUri: string,
  logErr: (msg: string) => void
): Promise<OAuthResult> {
  const body = {
    grant_type: "authorization_code",
    code,
    redirect_uri: redirectUri,
    client_id: CLIENT_ID,
    code_verifier: codeVerifier,
    state,
    expires_in: TOKEN_EXPIRY_SECONDS,
  };

  const jsonBody = JSON.stringify(body);
  const tokenUrl = new URL(TOKEN_URL);

  const data = await new Promise<{
    access_token: string;
    refresh_token?: string;
    expires_in?: number;
    scope?: string;
  }>((resolve, reject) => {
    const req = httpsRequest(
      {
        hostname: tokenUrl.hostname,
        port: 443,
        path: tokenUrl.pathname,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(jsonBody),
        },
      },
      (res) => {
        let responseBody = "";
        res.on("data", (chunk: Buffer) => {
          responseBody += chunk.toString();
        });
        res.on("end", () => {
          if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
            try {
              resolve(JSON.parse(responseBody));
            } catch (parseErr) {
              reject(new Error(`Failed to parse token response: ${parseErr}`));
            }
          } else if (res.statusCode === 401) {
            reject(new Error("Authentication failed: Invalid authorization code"));
          } else {
            reject(new Error(`Token exchange failed (${res.statusCode}): ${responseBody}`));
          }
        });
      }
    );

    req.on("error", (err) => {
      logErr(`Token exchange network error: ${err.message}`);
      reject(new Error(`Token exchange network error: ${err.message}`));
    });

    req.write(jsonBody);
    req.end();
  });

  logErr("Token exchange successful");

  const expiresAt = data.expires_in
    ? new Date(Date.now() + data.expires_in * 1000).toISOString()
    : undefined;

  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresAt,
    scopes: (data.scope || SCOPES).split(" "),
  };
}

// --- Credential Storage (macOS Keychain) ---

function storeCredentials(tokens: OAuthResult, logErr: (msg: string) => void): void {
  const username = process.env.USER || userInfo().username;

  const credentialData = {
    claudeAiOauth: {
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken || null,
      expiresAt: tokens.expiresAt || null,
      scopes: tokens.scopes,
    },
  };

  const jsonStr = JSON.stringify(credentialData);

  try {
    // Use -U flag to upsert (update if exists, add if not)
    execSync(
      `security add-generic-password -U -a "${username}" -s "${KEYCHAIN_SERVICE}" -w "${jsonStr.replace(/"/g, '\\"')}"`,
      { stdio: "pipe" }
    );
    logErr("Credentials stored in macOS Keychain");
  } catch (err) {
    logErr(`Failed to store in Keychain: ${err}, trying delete+add`);
    try {
      try {
        execSync(`security delete-generic-password -a "${username}" -s "${KEYCHAIN_SERVICE}"`, {
          stdio: "pipe",
        });
      } catch {
        // ignore if not found
      }
      execSync(
        `security add-generic-password -a "${username}" -s "${KEYCHAIN_SERVICE}" -w "${jsonStr.replace(/"/g, '\\"')}"`,
        { stdio: "pipe" }
      );
      logErr("Credentials stored in macOS Keychain (after delete+add)");
    } catch (err2) {
      logErr(`Failed to store credentials: ${err2}`);
    }
  }
}
