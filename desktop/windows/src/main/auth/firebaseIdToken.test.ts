// Hermetic security suite for verifyFirebaseIdToken — the SIGNATURE check that
// gates the control-plane owner. A test RSA keypair signs Firebase-shaped tokens;
// the Google cert fetch is mocked to serve the matching self-signed x509 cert. No
// network, no real Firebase.
//
// The keypair + cert below are THROWAWAY test fixtures (openssl, self-signed) — not
// a real credential. They exist only so a genuine RS256 signature can be produced
// and verified in-process.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SignJWT, generateKeyPair, importPKCS8 } from 'jose'
import { verifyFirebaseIdToken, __resetFirebaseCertCacheForTests } from './firebaseIdToken'

const PROJECT_ID = 'demo-omi'
const KID = 'test-kid-1'

// Self-signed x509 cert whose key pair is TEST_KEY_PKCS8. Served by the mocked
// Google securetoken endpoint under KID.
const TEST_CERT = `-----BEGIN CERTIFICATE-----
MIIDFzCCAf+gAwIBAgIUKJeTF47X4ruZgaRBPhGOQnQzVC0wDQYJKoZIhvcNAQEL
BQAwGzEZMBcGA1UEAwwQdGVzdC1zZWN1cmV0b2tlbjAeFw0yNjA3MTYwMzM0MDZa
Fw0zNjA3MTMwMzM0MDZaMBsxGTAXBgNVBAMMEHRlc3Qtc2VjdXJldG9rZW4wggEi
MA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCrDeZN/BnctvDA+v5yDpEi++Rv
D0bMcmkgBP08ab0qme4Kllrrq14Odm/3+xJ37HNTVDL1eRri5CwZBOBpU4xMeznT
Sz14N/zXTrn3cTmvEW/mPhioOBc1TPfojI+Mfemmz5G/AjiDC1bvsyPI+RDeasNH
uZ3DSMOZ7k8XIa0NldQxaXc0JHdZtan2n0rIx3e/XxsV4HqoCs0DlAyGXsg7ARXC
Hf6kgXb7mvxk+FQaERuSg3cFSxGm3OfPOiX7t5RKG4m0qiXouPgOnykMO8baiJ7O
cQlP0yLvi/bdULY1Sy4EaM5O49OnucOTWV2LpsFDDrQAuioCgk3pt0rKvHn5AgMB
AAGjUzBRMB0GA1UdDgQWBBTmcXwa48gLe3I4BJpgTotg7u9A4TAfBgNVHSMEGDAW
gBTmcXwa48gLe3I4BJpgTotg7u9A4TAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3
DQEBCwUAA4IBAQAHJldHwul03+2NDHx0QWtGHVM5HmQTFMe0nYKXTUhGNbzywn9D
s7RZcIs3zwwQyVXOBby+s07GC3bdwdPVVQvZZHcKNw63rC7cysBJIhucdhZA/1y0
Tf7+maTEHlUvBeCCGHQTVi8GkB/HZeURoz+ngLHrbb5k7GuP03JNWtnKMjaGxTl4
KNNuK34QNBvgkdT+KIVCEEeyyDyKK0aJ/+0mAq5LawnFWl1i3Rqv5YgDsRhIa4Tx
FIoN0/daVZNIb5uyPoo5hpvHcrRIs8L1FYON7VLwgPm3i2bXdu0GG6LNUVSStEhH
+sd8lOkbUf8qiK2iry96RAABVlo3Kh3aF+7p
-----END CERTIFICATE-----
`

const TEST_KEY_PKCS8 = `-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCrDeZN/BnctvDA
+v5yDpEi++RvD0bMcmkgBP08ab0qme4Kllrrq14Odm/3+xJ37HNTVDL1eRri5CwZ
BOBpU4xMeznTSz14N/zXTrn3cTmvEW/mPhioOBc1TPfojI+Mfemmz5G/AjiDC1bv
syPI+RDeasNHuZ3DSMOZ7k8XIa0NldQxaXc0JHdZtan2n0rIx3e/XxsV4HqoCs0D
lAyGXsg7ARXCHf6kgXb7mvxk+FQaERuSg3cFSxGm3OfPOiX7t5RKG4m0qiXouPgO
nykMO8baiJ7OcQlP0yLvi/bdULY1Sy4EaM5O49OnucOTWV2LpsFDDrQAuioCgk3p
t0rKvHn5AgMBAAECggEABjyCnul/8mJ3ltuXywYBr+A16QAqNUI/F7Ai4PDceRkF
Wxy1+iVkb5vNE4ITf2yPHFTDqlw02RyXSH67ZU+q2+96sVvLBQ7qgJmR0WYPA7Vb
qm3tZXWtD/ALUk7MnYNKMV8cOdXthEaVr/XMqlM9VJSZI8xuRmxI2Fv+RXJAflAe
t/x5TCN4Qus6JCtCdVttUsd/t0t4JPfVKdIIpoYs/yZH4aW1mDy9i51RbHjyBX3d
yaamACMI7OZd8sn4zIBHJkqWcINayszdfN1k9cBOV0XTKWsy3V0QCN+781WZ8nNo
JAWEBg5WeV6hDv22GngLmh71Wr//F16m8RsxcwdA8QKBgQDZo1MY9/90UuXOvTRA
Yw7vuUFBRnegCW8vCLVTGPsYcxUtddQkQGNdWrAvNO1MfZ8QXOy8aOTC5M7MHxy0
XK+fN20TsB8KM7dMrKXc/UN105b+CKaC29fGeT1JF8ZYwILVCOpOBTeotYhkseH9
NSzBkwkl1s22eUzBs2TTuqb0EQKBgQDJNIl8zFrA9Zca+I4MdfAr97ml0LqfWbtp
FugMeABnp1IoIowe4v18Tr3Fe4m2Efbhz5WB469N3iKI5sdjBrH15VlMoxt5i8Rk
5kPwh/UNX17479vg4wO3N6Qn6x1YgjsnGkDuLhJghWgq5B2tATCWEaW/Q/z+rEIk
wNdJhH9vaQKBgA7gm02ZplzNTehUBr5gByVcBJnxtzu5aWBNuBd2HbQOKeRxqY7Q
1/oJuQGBHLed3sG/mG9IvFqWSYyqk8vAikDYCRzPbU/FOUKEitIQfgwP6sJy1O8d
GCL5JrdYaLaockkd0uaCdMuTnT9E6a3ldKnG41ky1d0jbZvQJ5RRrhgBAoGBAKTM
AShUgKi2/pK6ri4KkzKP7mCfu5s09ck3V8yOpVZAt4vj7/yEUrZ0D/8mFj8oK5v8
WCpRAI64uHSFAR5cp3oN5bxdg+1jyvIRn+fsk4vmZ3VhkCh8B9kTG8MOUbTixexb
Fn9/ANJJsm4e9Sd0aAUiYy1rVFaLZImR4UN34KCxAoGBAIiWzoMwmWPsySc380qQ
sx9NUv67gEULAKNMGu1jtoxnS4q0AvZTqZCeXD9pQzA/QT9v3IENZLI/YKK0JcIU
L4rRXxcGN8OpFcJHfPpjSTpMsC9xiAidy5N6xKvSP3VE2/Yya4zibBTQNdyjl2Gh
R+f7eplOTojXVdPthg1ODSg7
-----END PRIVATE KEY-----
`

const ISS = `https://securetoken.google.com/${PROJECT_ID}`

/** A cert-fetch double: serves `certs` as the securetoken x509 JSON. */
function certFetch(
  certs: Record<string, string>,
  opts: { ok?: boolean; cacheControl?: string | null } = {}
): typeof fetch {
  const { ok = true, cacheControl = 'max-age=3600' } = opts
  return vi.fn(async () => ({
    ok,
    json: async () => certs,
    headers: { get: (h: string) => (h.toLowerCase() === 'cache-control' ? cacheControl : null) }
  })) as unknown as typeof fetch
}

const goodCertFetch = (): typeof fetch => certFetch({ [KID]: TEST_CERT })

function claims(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const now = Math.floor(Date.now() / 1000)
  return { sub: 'uid-123', aud: PROJECT_ID, iss: ISS, iat: now, exp: now + 3600, ...overrides }
}

/** Sign with the TEST key (matches the served cert) unless a key is supplied. */
async function sign(
  payload: Record<string, unknown>,
  header: { alg?: string; kid?: string } = {},
  key?: Awaited<ReturnType<typeof importPKCS8>>
): Promise<string> {
  const signingKey = key ?? (await importPKCS8(TEST_KEY_PKCS8, 'RS256'))
  return new SignJWT(payload)
    .setProtectedHeader({ alg: 'RS256', kid: KID, ...header })
    .sign(signingKey)
}

/** Base64url a JSON object (for hand-crafting malformed tokens jose won't emit). */
const b64u = (o: unknown): string => Buffer.from(JSON.stringify(o)).toString('base64url')

beforeEach(() => {
  __resetFirebaseCertCacheForTests()
  vi.stubEnv('VITE_FIREBASE_PROJECT_ID', PROJECT_ID)
})

afterEach(() => {
  vi.unstubAllEnvs()
  __resetFirebaseCertCacheForTests()
})

describe('verifyFirebaseIdToken — genuine tokens', () => {
  it('returns the sub for a correctly-signed token with the right aud/iss/exp', async () => {
    const token = await sign(claims())
    expect(await verifyFirebaseIdToken(token, goodCertFetch())).toBe('uid-123')
  })

  it('reads sub from the actual claim, not a fixed value', async () => {
    const token = await sign(claims({ sub: 'another-uid' }))
    expect(await verifyFirebaseIdToken(token, goodCertFetch())).toBe('another-uid')
  })
})

describe('verifyFirebaseIdToken — forged / wrong-key tokens', () => {
  it('rejects a token signed by a DIFFERENT key (bad signature)', async () => {
    const attacker = await generateKeyPair('RS256')
    // Keeps our KID so the good cert is selected — the signature just won't verify.
    const token = await sign(claims({ sub: 'victim-uid' }), { kid: KID }, attacker.privateKey)
    expect(await verifyFirebaseIdToken(token, goodCertFetch())).toBeNull()
  })

  it('rejects an UNSIGNED token (alg:none) before any key work', async () => {
    const token = `${b64u({ alg: 'none', kid: KID })}.${b64u(claims({ sub: 'victim-uid' }))}.`
    expect(await verifyFirebaseIdToken(token, goodCertFetch())).toBeNull()
  })

  it('rejects an HS256 token (alg-confusion)', async () => {
    const secret = new TextEncoder().encode('x'.repeat(32))
    const token = await new SignJWT(claims({ sub: 'victim-uid' }))
      .setProtectedHeader({ alg: 'HS256', kid: KID })
      .sign(secret)
    expect(await verifyFirebaseIdToken(token, goodCertFetch())).toBeNull()
  })

  it('rejects a garbage / non-JWT token', async () => {
    expect(await verifyFirebaseIdToken('not-a-jwt', goodCertFetch())).toBeNull()
  })

  it('rejects a token whose kid is not in the cert set', async () => {
    const token = await sign(claims(), { kid: 'unknown-kid' })
    expect(await verifyFirebaseIdToken(token, goodCertFetch())).toBeNull()
  })
})

describe('verifyFirebaseIdToken — bad claims', () => {
  it('rejects a wrong audience', async () => {
    const token = await sign(claims({ aud: 'someone-elses-project' }))
    expect(await verifyFirebaseIdToken(token, goodCertFetch())).toBeNull()
  })

  it('rejects a wrong issuer', async () => {
    const token = await sign(
      claims({ iss: 'https://securetoken.google.com/someone-elses-project' })
    )
    expect(await verifyFirebaseIdToken(token, goodCertFetch())).toBeNull()
  })

  it('rejects an expired token', async () => {
    const past = Math.floor(Date.now() / 1000) - 60
    const token = await sign(claims({ iat: past - 3600, exp: past }))
    expect(await verifyFirebaseIdToken(token, goodCertFetch())).toBeNull()
  })

  it('rejects a token with no sub', async () => {
    const c = claims()
    delete c.sub
    const token = await sign(c)
    expect(await verifyFirebaseIdToken(token, goodCertFetch())).toBeNull()
  })

  it('rejects a token with an empty sub', async () => {
    const token = await sign(claims({ sub: '' }))
    expect(await verifyFirebaseIdToken(token, goodCertFetch())).toBeNull()
  })
})

describe('verifyFirebaseIdToken — configuration & cert resilience', () => {
  it('returns null when the project id is unconfigured (fail closed)', async () => {
    vi.stubEnv('VITE_FIREBASE_PROJECT_ID', '')
    const token = await sign(claims())
    expect(await verifyFirebaseIdToken(token, goodCertFetch())).toBeNull()
  })

  it('returns null on a hard cert-fetch failure with no cached certs', async () => {
    const token = await sign(claims())
    expect(await verifyFirebaseIdToken(token, certFetch({}, { ok: false }))).toBeNull()
  })

  it('serves the LAST-GOOD certs when an EXPIRED-cache re-fetch fails (transient blip)', async () => {
    vi.useFakeTimers()
    try {
      const token = await sign(claims())
      // Warm the cache with a 1s TTL, then age past it (token still valid ~1h): the
      // next call re-fetches, that fetch fails, and it must fall back to last-good.
      expect(
        await verifyFirebaseIdToken(
          token,
          certFetch({ [KID]: TEST_CERT }, { cacheControl: 'max-age=1' })
        )
      ).toBe('uid-123')
      vi.advanceTimersByTime(2000)
      const failing = certFetch({}, { ok: false })
      expect(await verifyFirebaseIdToken(token, failing)).toBe('uid-123')
      expect(failing).toHaveBeenCalledTimes(1) // stale cache → it DID try, then fell back
    } finally {
      vi.useRealTimers()
    }
  })

  it('does NOT re-fetch certs while the cache is fresh (hourly-refresh cost)', async () => {
    const token = await sign(claims())
    const fetcher = goodCertFetch()
    await verifyFirebaseIdToken(token, fetcher)
    await verifyFirebaseIdToken(token, fetcher)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
