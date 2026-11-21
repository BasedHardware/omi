import auth, { FirebaseAuthTypes } from '@react-native-firebase/auth';
import { GoogleSignin } from '@react-native-google-signin/google-signin';
import { appleAuth } from '@invertase/react-native-apple-authentication';
import { setAuthToken } from '@/api/omiApi';
import { ENV } from '@/config/env';

/**
 * Firebase-backed auth (mirrors the Flutter app's flow):
 *   Google/Apple -> Firebase credential -> Firebase ID token (Bearer) -> Omi API.
 *
 * Requires a real google-services.json (Android) / GoogleService-Info.plist (iOS)
 * for com.omi.app. Until those are provided, sign-in throws a clear error.
 */

// For Firebase, the Google sign-in must return an idToken. That requires
// offlineAccess:true AND a webClientId (the web OAuth client from
// google-services.json). Without the webClientId the plugin throws
// "offline use requires server web ClientID" at startup and crashes.
GoogleSignin.configure({
  webClientId: ENV.webClientId,
  offlineAccess: true,
});

function randomNonce(length = 32): string {
  const charset = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-._~';
  let out = '';
  const bytes = new Uint8Array(length);
  if (typeof globalThis !== 'undefined' && (globalThis as any).crypto?.getRandomValues) {
    (globalThis as any).crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < length; i++) bytes[i] = Math.floor(Math.random() * 256);
  }
  for (let i = 0; i < length; i++) out += charset[bytes[i]! % charset.length];
  return out;
}

// Minimal pure-JS SHA-256 (RFC 6234) for Apple sign-in nonce.
function sha256(input: string): string {
  const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n));
  const k = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
    0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
    0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
    0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
    0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
    0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
    0xc67178f2,
  ]);
  const utf8 = (s: string) => {
    const out: number[] = [];
    for (let i = 0; i < s.length; i++) {
      let c = s.charCodeAt(i);
      if (c < 0x80) out.push(c);
      else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
      else if (c < 0xd800 || c >= 0xe000) out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
      else {
        i++;
        c = 0x10000 + (((c & 0x3ff) << 10) | (s.charCodeAt(i) & 0x3ff));
        out.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 0x3f), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
      }
    }
    return out;
  };
  const m = utf8(input);
  const bitLen = m.length * 8;
  m.push(0x80);
  while (m.length % 64 !== 56) m.push(0);
  for (let i = 7; i >= 0; i--) m.push((bitLen >>> (i * 8)) & 0xff);

  let h0 = 0x6a09e667, h1 = 0xbb67ae85, h2 = 0x3c6ef372, h3 = 0xa54ff53a;
  let h4 = 0x510e527f, h5 = 0x9b05688c, h6 = 0x1f83d9ab, h7 = 0x5be0cd19;

  const w = new Uint32Array(64);
  for (let i = 0; i < m.length; i += 64) {
    for (let j = 0; j < 16; j++) {
      w[j] = (m[i + j * 4]! << 24) | (m[i + j * 4 + 1]! << 16) | (m[i + j * 4 + 2]! << 8) | m[i + j * 4 + 3]!;
    }
    for (let j = 16; j < 64; j++) {
      const s0 = rotr(w[j - 15]!, 7) ^ rotr(w[j - 15]!, 18) ^ (w[j - 15]! >>> 3);
      const s1 = rotr(w[j - 2]!, 17) ^ rotr(w[j - 2]!, 19) ^ (w[j - 2]! >>> 10);
      w[j] = (w[j - 16]! + s0 + w[j - 7]! + s1) | 0;
    }
    let a = h0, b = h1, c = h2, d = h3, e = h4, f = h5, g = h6, h = h7;
    for (let j = 0; j < 64; j++) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (h + S1 + ch + k[j]! + w[j]!) | 0;
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) | 0;
      h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    h0 = (h0 + a) | 0; h1 = (h1 + b) | 0; h2 = (h2 + c) | 0; h3 = (h3 + d) | 0;
    h4 = (h4 + e) | 0; h5 = (h5 + f) | 0; h6 = (h6 + g) | 0; h7 = (h7 + h) | 0;
  }
  const hex = (n: number) => (n >>> 0).toString(16).padStart(8, '0');
  return hex(h0) + hex(h1) + hex(h2) + hex(h3) + hex(h4) + hex(h5) + hex(h6) + hex(h7);
}

export async function signInWithGoogle(): Promise<string> {
  await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
  const result = await GoogleSignin.signIn();
  // @react-native-google-signin v13 returns { type: 'success', data: User }
  if (!result || (result as any).type === 'cancel') {
    throw new Error('Google sign-in was cancelled');
  }
  const user = (result as any).data ?? result;
  let idToken: string | undefined = user?.idToken ?? (result as any).idToken;
  // Fallback: getTokens() explicitly returns { idToken, accessToken } when
  // offlineAccess is enabled. Defensive against shape differences across versions.
  if (!idToken) {
    try {
      const tokens = await GoogleSignin.getTokens();
      idToken = tokens?.idToken;
    } catch {
      /* ignore, handled below */
    }
  }
  if (!idToken) {
    throw new Error(
      'Google sign-in failed: no idToken. Got keys: ' +
        JSON.stringify(Object.keys(user ?? result ?? {})),
    );
  }
  const googleCredential = auth.GoogleAuthProvider.credential(idToken);
  let userCred;
  try {
    userCred = await auth().signInWithCredential(googleCredential);
  } catch (e: any) {
    console.error('[auth] Firebase signInWithCredential failed:', e?.code, e?.message, JSON.stringify(e));
    throw e;
  }
  const token = await userCred.user.getIdToken();
  setAuthToken(token);
  return token;
}

export async function signInWithApple(): Promise<string> {
  if (!appleAuth.isSupported) throw new Error('Apple sign-in is not supported on this device');
  const rawNonce = randomNonce();
  const nonce = sha256(rawNonce);
  const appleCredential = await appleAuth.performRequest({
    requestedOperation: appleAuth.Operation.LOGIN,
    requestedScopes: [appleAuth.Scope.EMAIL, appleAuth.Scope.FULL_NAME],
    nonce,
  });
  if (!appleCredential.identityToken) throw new Error('Apple sign-in failed: no identity token');
  const oauthCredential = new auth.OAuthProvider('apple.com').credential(
    appleCredential.identityToken,
    rawNonce,
  );
  const userCred = await auth().signInWithCredential(oauthCredential);
  const token = await userCred.user.getIdToken();
  setAuthToken(token);
  return token;
}

export function observeAuth(
  onChange: (uid: string | null, token: string | null) => void,
): () => void {
  return auth().onAuthStateChanged(async (user: FirebaseAuthTypes.User | null) => {
    if (user) {
      const token = await user.getIdToken();
      setAuthToken(token);
      onChange(user.uid, token);
    } else {
      setAuthToken(null);
      onChange(null, null);
    }
  });
}

export async function signOut() {
  try {
    await GoogleSignin.signOut();
  } catch {
    /* ignore */
  }
  await auth().signOut();
  setAuthToken(null);
}

export async function currentUid(): Promise<string | null> {
  return auth().currentUser?.uid ?? null;
}
