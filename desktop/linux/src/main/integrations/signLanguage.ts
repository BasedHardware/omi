// src/main/integrations/signLanguage.ts
import axios from 'axios'
import { app } from 'electron'
import fs from 'fs/promises'
import path from 'path'
import crypto from 'crypto'
import { rendererBaseUrl, POSES_DIR } from '../rendererServer'

export type SignGloss = {
  gloss: string; // The sign language representation (e.g., "HELLO", "STORE", "GO")
  duration: number; // How long the sign should be held (in seconds)
  timestamp: number; // When the sign starts relative to the audio
  swr?: string; // SignWriting representation (e.g., "SWR:...")
};

export type TranslationResult = {
  originalText: string;
  poseUrl: string; // Now contains Base64 Data URI
  glosses: SignGloss[];
  assetType?: 'video' | 'pose';
  swrFull?: string;
};

/**
 * Translates spoken text into Sign Language Poses and Glosses.
 * Uses the sign.mt API for high-quality skeletal animations.
 */
async function fetchWithRetry(url: string, options: any, retries = 2): Promise<any> {
  try {
    return await axios.get(url, options);
  } catch (error: any) {
    if (retries > 0 && (error.response?.status === 500 || error.response?.status === 503 || error.code === 'ECONNABORTED')) {
      console.log(`[sign-language] Request failed (${error.response?.status || error.code}), retrying... (${retries} left)`);
      await new Promise(res => setTimeout(res, 1000));
      return fetchWithRetry(url, options, retries - 1);
    }
    throw error;
  }
}

// Short-lived negative cache so we don't hammer the (often-down) API on every
// transcript segment / live update. Keyed by language+text; value is the expiry
// timestamp. When present and not expired we skip the network call.
const negativeCache = new Map<string, number>()
const NEGATIVE_TTL_MS = 60_000

/** Default options for live translation calls: serve poses over the local
 * renderer-server so pose-viewer can fetch() them. Poses are written to
 * POSES_DIR (a real writable dir, NOT inside app.asar). */
export function defaultSignOpts() {
  return { baseUrl: rendererBaseUrl(), posesDir: POSES_DIR }
}

/**
 * Produce a URL the renderer can load. In production we write the bytes to a
 * file under the renderer-server root and return an http://localhost URL so
 * pose-viewer's internal fetch() works reliably — fetch() on data:/blob: URIs
 * is broken in this Electron/Linux build and causes "Failed to fetch".
 * Falls back to a data: URI when no local server base URL is available.
 */
async function makePoseUrl(
  bytes: Buffer,
  cacheKey: string,
  posesDir: string | undefined,
  baseUrl: string | null | undefined
): Promise<{ url: string; assetType: 'pose' | 'video' }> {
  if (baseUrl && posesDir) {
    try {
      await fs.mkdir(posesDir, { recursive: true })
      const file = path.join(posesDir, `${cacheKey}.pose`)
      await fs.writeFile(file, bytes)
      return { url: `${baseUrl}/__poses/${cacheKey}.pose`, assetType: 'pose' }
    } catch (e) {
      console.warn('[sign-language] Failed to write local pose file, falling back to data URI:', e)
    }
  }
  const mime = 'application/json'
  const base64 = bytes.toString('base64')
  return { url: `data:${mime};base64,${base64}`, assetType: 'pose' }
}

export async function translateToGlosses(
  text: string,
  spokenLanguage: string = 'en',
  signedLanguage: string = 'ase',
  opts?: { baseUrl?: string | null; posesDir?: string }
): Promise<TranslationResult> {
  let trimmedText = text.trim();
  
  if (!trimmedText) {
    return {
      originalText: text,
      poseUrl: '',
      glosses: []
    };
  }

  if (trimmedText.length > 256) {
    trimmedText = trimmedText.slice(0, 256);
  }
  
  const cacheKey = crypto
    .createHash('sha1')
    .update(`${spokenLanguage}|${signedLanguage}|${trimmedText}`)
    .digest('hex')
  
  const negativeKey = `${spokenLanguage}|${signedLanguage}|${trimmedText}`
  const now = Date.now()
  const negUntil = negativeCache.get(negativeKey)
  if (negUntil && now < negUntil) {
    // API recently failed for this exact text — don't retry yet.
    return {
      originalText: text,
      poseUrl: '',
      assetType: 'pose',
      swrFull: 'TRANSLATION_UNAVAILABLE',
      glosses: []
    }
  }

  const apiPose = 'https://us-central1-sign-mt.cloudfunctions.net/spoken_text_to_signed_pose';
  const apiVideo = 'https://us-central1-sign-mt.cloudfunctions.net/spoken_text_to_signed_video';
  
  const poseUrl = `${apiPose}?text=${encodeURIComponent(trimmedText)}&spoken=${spokenLanguage}&signed=${signedLanguage}`;
  const videoUrl = `${apiVideo}?text=${encodeURIComponent(trimmedText)}&spoken=${spokenLanguage}&signed=${signedLanguage}`;
  
  const poseDir = path.join(app.getPath('temp'), 'omi-sign-poses')
  const posePath = path.join(poseDir, `${cacheKey}.pose`)

  try {
    await fs.mkdir(poseDir, { recursive: true })

    try {
      let poseBytes: Buffer;
      try {
        poseBytes = await fs.readFile(posePath)
      } catch {
        const response = await fetchWithRetry(poseUrl, {
          responseType: 'arraybuffer',
          timeout: 30000,
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
          }
        })
        poseBytes = Buffer.from(response.data)
        await fs.writeFile(posePath, poseBytes)
      }
      
      const { url, assetType } = await makePoseUrl(poseBytes, cacheKey, opts?.posesDir, opts?.baseUrl)
      return {
        originalText: text,
        poseUrl: url,
        assetType,
        glosses: []
      }
    } catch (poseError) {
      console.log('[sign-language] Pose API failed, trying video as last resort:', poseError);
      
      try {
        const videoResponse = await fetchWithRetry(videoUrl, { 
          responseType: 'arraybuffer',
          timeout: 30000,
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
          }
        });
        const videoData = Buffer.from(videoResponse.data);
        let videoUrl_out: string
        if (opts?.baseUrl && opts?.posesDir) {
          try {
            await fs.mkdir(opts.posesDir, { recursive: true })
            const vfile = path.join(opts.posesDir, `${cacheKey}.mp4`)
            await fs.writeFile(vfile, videoData)
            videoUrl_out = `${opts.baseUrl}/__poses/${cacheKey}.mp4`
          } catch (e) {
            console.warn('[sign-language] Failed to write local video file, falling back to data URI:', e)
            videoUrl_out = `data:video/mp4;base64,${videoData.toString('base64')}`
          }
        } else {
          videoUrl_out = `data:video/mp4;base64,${videoData.toString('base64')}`
        }
        
        return {
          originalText: text,
          poseUrl: videoUrl_out,
          assetType: 'video',
          glosses: []
        };
      } catch (videoError) {
        console.error('[sign-language] Both Pose and Video APIs failed:', videoError);
        negativeCache.set(negativeKey, Date.now() + NEGATIVE_TTL_MS);
        return {
          originalText: text,
          poseUrl: '',
          assetType: 'pose',
          swrFull: 'TRANSLATION_UNAVAILABLE',
          glosses: []
        }
      }
    }
  } catch (error) {
    console.error('[sign-language] unexpected failure in translateToGlosses:', error)
    negativeCache.set(negativeKey, Date.now() + NEGATIVE_TTL_MS);
    return {
      originalText: text,
      poseUrl: '',
      assetType: 'pose',
      swrFull: 'TRANSLATION_UNAVAILABLE',
      glosses: []
    }
  }
}



