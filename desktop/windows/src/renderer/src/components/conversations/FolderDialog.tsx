import { useState } from 'react'
import { Check, Loader2, Trash2 } from 'lucide-react'
import type { ConversationFolder } from '../../../../shared/types'
import { createFolder, updateFolder, deleteFolder } from '../../lib/conversations/folders'
import { ModalShell } from './ModalShell'
import { FOLDER_COLORS, DEFAULT_FOLDER_COLOR } from './folderColors'

// Create / edit / delete a conversation folder. Windows-native centered modal
// (per the Track 4 ruling — not a Mac titlebar sheet). Edit mode exposes a Delete
// action that confirms in-place; deleting leaves the folder's conversations
// unfiled (no move target).
export function FolderDialog({
  folder,
  onClose,
  onSaved,
  onDeleted
}: {
  /** Present = edit an existing folder; absent = create a new one. */
  folder?: ConversationFolder
  onClose: () => void
  onSaved: (folder: ConversationFolder) => void
  onDeleted: (id: string) => void
}): React.JSX.Element {
  const editing = !!folder
  const [name, setName] = useState(folder?.name ?? '')
  const [color, setColor] = useState(folder?.color ?? DEFAULT_FOLDER_COLOR)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  const save = async (): Promise<void> => {
    const trimmed = name.trim()
    if (!trimmed || busy) return
    setBusy(true)
    setError(null)
    try {
      const saved =
        editing && folder
          ? await updateFolder(folder.id, { name: trimmed, color })
          : await createFolder({ name: trimmed, color })
      onSaved(saved)
    } catch (e) {
      setError((e as Error).message || 'Could not save folder')
      setBusy(false)
    }
  }

  const remove = async (): Promise<void> => {
    if (!folder || busy) return
    setBusy(true)
    setError(null)
    try {
      await deleteFolder(folder.id)
      onDeleted(folder.id)
    } catch (e) {
      setError((e as Error).message || 'Could not delete folder')
      setBusy(false)
    }
  }

  if (confirmingDelete && folder) {
    return (
      <ModalShell onClose={onClose} labelledBy="folder-delete-title">
        <h2 id="folder-delete-title" className="text-lg font-semibold text-text-primary">
          Delete “{folder.name}”?
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-text-tertiary">
          The folder will be removed. Its conversations won’t be deleted — they’ll just be unfiled.
        </p>
        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={() => setConfirmingDelete(false)} disabled={busy} className="btn-ghost">
            Cancel
          </button>
          <button onClick={() => void remove()} disabled={busy} className="btn-danger">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            Delete folder
          </button>
        </div>
      </ModalShell>
    )
  }

  return (
    <ModalShell onClose={onClose} labelledBy="folder-dialog-title">
      <h2 id="folder-dialog-title" className="text-lg font-semibold text-text-primary">
        {editing ? 'Edit folder' : 'New folder'}
      </h2>

      <label className="mt-4 block text-xs font-medium text-white/50">Name</label>
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void save()
        }}
        placeholder="Folder name"
        maxLength={60}
        className="input-field mt-1.5"
      />

      <div className="mt-4 text-xs font-medium text-white/50">Color</div>
      <div className="mt-2 flex flex-wrap gap-2">
        {FOLDER_COLORS.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setColor(c)}
            aria-label={`Color ${c}`}
            className={`flex h-8 w-8 items-center justify-center rounded-full transition-transform hover:scale-110 ${
              color === c ? 'ring-2 ring-white ring-offset-2 ring-offset-black/40' : ''
            }`}
            style={{ backgroundColor: c }}
          >
            {color === c && <Check className="h-4 w-4 text-white drop-shadow" />}
          </button>
        ))}
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <div className="mt-6 flex items-center justify-between">
        {editing ? (
          <button
            onClick={() => setConfirmingDelete(true)}
            disabled={busy}
            className="text-sm font-medium text-red-400 transition-colors hover:text-red-300"
          >
            Delete
          </button>
        ) : (
          <span />
        )}
        <div className="flex gap-2">
          <button onClick={onClose} disabled={busy} className="btn-ghost">
            Cancel
          </button>
          <button
            onClick={() => void save()}
            disabled={busy || !name.trim()}
            className="btn-primary"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {editing ? 'Save' : 'Create'}
          </button>
        </div>
      </div>
    </ModalShell>
  )
}
