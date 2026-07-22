import { useState } from 'react'
import { User, LogOut } from 'lucide-react'
import { auth, signOutUser } from '../../../lib/firebase'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { setDisplayName } from '../../../lib/userProfile'
import { toast } from '../../../lib/toast'
import { SettingRow } from '../SettingRow'

export function AccountTab(): React.JSX.Element {
  const prefs = getPreferences()
  const [name, setName] = useState(prefs.displayName ?? '')

  // Transcription language moved to Settings → Transcription (Mac parity); this
  // row now owns only the display name.
  const saveProfile = (): void => {
    setPreferences({ displayName: name.trim() })
    void setDisplayName(name.trim()).catch(() => toast('Name sync failed', { tone: 'warn' }))
    toast('Profile saved', { tone: 'success' })
  }

  return (
    <>
      <SettingRow
        icon={User}
        title="Profile"
        subtitle="Your display name."
        keywords="name profile display"
      >
        <div className="space-y-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            className="glass-subtle w-full rounded-lg px-4 py-3 text-sm text-text-secondary focus:outline-none"
          />
          <button onClick={saveProfile} className="btn-ghost">
            Save
          </button>
        </div>
      </SettingRow>
      <SettingRow
        icon={LogOut}
        title="Signed in"
        subtitle={auth.currentUser?.email ?? '(not signed in)'}
        keywords="account email sign out logout"
        control={
          <button onClick={signOutUser} className="btn-ghost">
            Sign out
          </button>
        }
      />
    </>
  )
}
