// Temp diagnostic: map which Omi host actually serves /v4/listen and what auth
// class it enforces. Delete after debugging.
//
// The production app authenticates with a **Firebase ID token** (Google sign-in
// → auth.currentUser.getIdToken()), NOT the omi_dev_ API key. To reproduce the
// app's real connect, give this script a token via one of:
//
//   OMI_ID_TOKEN=<jwt>        one-off; ID tokens expire after ~1h
//   OMI_REFRESH_TOKEN=<tok>   script exchanges it for a fresh ID token each run
//
// Grab either from the RUNNING app's renderer DevTools console (the app stores
// both in IndexedDB under browserLocalPersistence):
//
//   const db = await new Promise(r => { const q = indexedDB.open('firebaseLocalStorageDb'); q.onsuccess = () => r(q.result) })
//   const all = await new Promise(r => { const q = db.transaction('firebaseLocalStorage').objectStore('firebaseLocalStorage').getAll(); q.onsuccess = () => r(q.result) })
//   const u = all.find(x => x.fbase_key?.startsWith('firebase:authUser'))?.value
//   console.log('ID TOKEN:', u.stsTokenManager.accessToken)
//   console.log('REFRESH TOKEN:', u.stsTokenManager.refreshToken)
//
// Put it in .env (OMI_REFRESH_TOKEN=...) or pass inline:
//   OMI_REFRESH_TOKEN=xxx node scripts/diag-listen-probe.mjs
import fs from 'node:fs'
import WebSocket from 'ws'

const env = {}
for (const line of fs.readFileSync(new URL('../.env', import.meta.url), 'utf8').split('\n')) {
  const m = line.match(/^([A-Z_]+)=(.*)$/)
  if (m) env[m[1]] = m[2].trim()
}

// Legacy probe params (uid in query) for the no-auth / dev-key paths.
const QS = 'language=en&sample_rate=16000&codec=pcm16&channels=1&uid=dummy-uid-test'
// The app's REAL connect params (src/main/ipc/omiListen.ts). With a Firebase
// token the backend derives uid from the token, so no uid query is sent.
const APP_QS =
  'language=en&sample_rate=16000&codec=linear16&channels=1' +
  '&include_speech_profile=true&source=desktop&speaker_auto_assign=enabled'
const KEY = env.VITE_OMI_API_KEY

const hosts = [
  ['api.omi.me (prod)     ', 'wss://api.omi.me'],
  // based-hardware-dev backend-listen service: serves /v4/listen, public invoke,
  // verifies tokens against the PROD based-hardware Firebase project (same as the
  // app), and its logs live in a project we can actually read.
  ['backend-listen (dev)  ', 'wss://backend-listen-dt5lrfkkoa-uc.a.run.app'],
  ['backend (dev)         ', 'wss://backend-dt5lrfkkoa-uc.a.run.app'],
  ['desktop-backend       ', 'wss://desktop-backend-hhibjajaja-uc.a.run.app']
]

function decodeJwt(tok) {
  try {
    const payload = tok.split('.')[1]
    return JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'))
  } catch {
    return null
  }
}

// Resolve a Firebase ID token from OMI_ID_TOKEN, or by exchanging
// OMI_REFRESH_TOKEN via the Firebase secure-token REST API.
async function resolveIdToken() {
  const direct = process.env.OMI_ID_TOKEN || env.OMI_ID_TOKEN
  if (direct) return { token: direct.trim(), source: 'OMI_ID_TOKEN' }

  const refresh = process.env.OMI_REFRESH_TOKEN || env.OMI_REFRESH_TOKEN
  if (!refresh) return null

  const apiKey = env.VITE_FIREBASE_API_KEY
  if (!apiKey) throw new Error('VITE_FIREBASE_API_KEY missing from .env')
  const res = await fetch(`https://securetoken.googleapis.com/v1/token?key=${apiKey}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ grant_type: 'refresh_token', refresh_token: refresh.trim() })
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(`securetoken exchange failed: HTTP ${res.status} ${JSON.stringify(data).slice(0, 200)}`)
  }
  return { token: data.id_token, source: 'OMI_REFRESH_TOKEN → securetoken exchange' }
}

// waitForClose: after a 101 OPEN, linger briefly to catch an immediate close
// (e.g. 1008 trial_expired / freemium_threshold_reached) so we can tell
// "auth OK, stays connected" from "auth OK but quota exhausted".
function probe(label, base, headers, tag, qs = QS, waitForClose = false) {
  return new Promise((resolve) => {
    const t0 = Date.now()
    const ws = new WebSocket(`${base}/v4/listen?${qs}`, { headers })
    let opened = false
    const done = (r) => {
      try { ws.terminate() } catch {}
      resolve(`${label}[${tag}] -> ${r} (${Date.now() - t0}ms)`)
    }
    ws.on('open', () => {
      opened = true
      if (!waitForClose) return done('OPEN ✅ (101)')
      // Stay up to 2.5s; if no close arrives, the socket is healthy.
      setTimeout(() => done('OPEN ✅ (101) — stayed connected 2.5s'), 2500)
    })
    ws.on('unexpected-response', (_q, res) => {
      let body = ''
      res.on('data', (c) => { body += c })
      res.on('end', () => done(`HTTP ${res.statusCode} body=${JSON.stringify(body.slice(0, 150))}`))
    })
    ws.on('message', (data, isBinary) => {
      if (isBinary || !waitForClose) return
      const text = data.toString().trim()
      if (text && text !== 'ping') console.log(`        ${label}[${tag}] msg: ${text.slice(0, 160)}`)
    })
    ws.on('close', (code, reasonBuf) => {
      if (opened && waitForClose) done(`OPEN then CLOSED (${code}) ${reasonBuf.toString() || '(no reason)'}`)
    })
    ws.on('error', (e) => done(`error: ${e.message}`))
    setTimeout(() => done('TIMEOUT'), 8000)
  })
}

let firebase = null
try {
  firebase = await resolveIdToken()
} catch (e) {
  console.log(`\n⚠️  Firebase token unavailable: ${e.message}`)
}

if (firebase) {
  const claims = decodeJwt(firebase.token)
  const expIn = claims?.exp ? Math.round(claims.exp - Date.now() / 1000) : null
  console.log(`\n🔑 Firebase ID token via ${firebase.source}`)
  if (claims) {
    console.log(`   uid=${claims.user_id || claims.sub} email=${claims.email || '(none)'} aud=${claims.aud}`)
    console.log(`   expires in ${expIn}s${expIn !== null && expIn <= 0 ? ' ⚠️  EXPIRED — refresh it' : ''}`)
  } else {
    console.log('   (could not decode JWT payload — token may be malformed)')
  }
} else {
  console.log('\nℹ️  No Firebase token provided (set OMI_ID_TOKEN or OMI_REFRESH_TOKEN) — skipping the app-faithful auth probe.')
}

console.log('\n=== host map for /v4/listen ===')
for (const [label, base] of hosts) {
  console.log(await probe(label, base, {}, 'no-auth'))
  console.log(await probe(label, base, { Authorization: `Bearer ${KEY}` }, 'dev-key'))
  if (firebase) {
    // App-faithful: Firebase Bearer token + the app's real query params, and
    // linger to surface an immediate quota close.
    console.log(
      await probe(label, base, { Authorization: `Bearer ${firebase.token}` }, 'fb-token', APP_QS, true)
    )
  }
}
console.log('===============================\n')
process.exit(0)
