import { auth } from './firebase'
import type { FileChat } from './omiApi.generated'

const OMI_BASE = import.meta.env.VITE_OMI_API_BASE as string

/** The bytes + metadata needed to upload one file. */
export type UploadableFile = {
  name: string
  mimeType: string
  bytes: Uint8Array
}

/** Injectable seams so the upload can be unit-tested without firebase/network. */
export type UploadDeps = {
  fetchImpl?: typeof fetch
  /** Resolve the bearer token; defaults to the current firebase user's id token. */
  getToken?: () => Promise<string | undefined>
}

/**
 * Upload a single file to `/v2/files` and return its server record. The endpoint
 * accepts a repeated `files` multipart field and returns one `FileChat` per part
 * (`def upload_file_chat(files: List[UploadFile] = File(...))`). We upload ONE
 * file per request so a single failure only fails that attachment, never the
 * batch. The id to pass in a `/v2/messages` `file_ids` is `FileChat.id` (the
 * server keys chat files by that id), not `openai_file_id`.
 *
 * Headers match what `useChat` already sends (`Authorization: Bearer` +
 * `X-App-Platform: windows`). Content-Type is intentionally NOT set — the
 * browser fills in the multipart boundary.
 */
export async function uploadChatFile(file: UploadableFile, deps: UploadDeps = {}): Promise<FileChat> {
  const doFetch = deps.fetchImpl ?? fetch
  const token = deps.getToken ? await deps.getToken() : await auth.currentUser?.getIdToken()

  const form = new FormData()
  form.append('files', new Blob([file.bytes], { type: file.mimeType }), file.name)

  const res = await doFetch(`${OMI_BASE}/v2/files`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-App-Platform': 'windows'
    },
    body: form
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)

  const files = (await res.json()) as FileChat[]
  const fc = files?.[0]
  if (!fc?.id) throw new Error('upload returned no file id')
  return fc
}
