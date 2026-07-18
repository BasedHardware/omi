import { useState } from 'react'
import { User, LogOut } from 'lucide-react'
import { auth, signOutUser } from '../../../lib/firebase'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { LANGUAGES, languageLabel } from '../../../lib/languages'
import { syncLanguage, setDisplayName } from '../../../lib/userProfile'
import { toast } from '../../../lib/toast'
import { SettingRow } from '../SettingRow'

export function AccountTab(): React.JSX.Element {
  const prefs = getPreferences()
  const [name, setName] = useState(prefs.displayName ?? '')
  const [language, setLanguage] = useState(prefs.language)

  const saveProfile = (): void => {
    setPreferences({ displayName: name.trim(), language })
    void setDisplayName(name.trim()).catch(() => toast('Name sync failed', { tone: 'warn' }))
    void syncLanguage(language).catch(() => toast('Language sync failed', { tone: 'warn' }))
    toast('Profile saved', { tone: 'success' })
  }

  return (
    <>
      <SettingRow
        icon={User}
        title="Profile"
        subtitle="Your name and transcription language."
        keywords="name language transcription profile"
      >
        <div className="space-y-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            className="glass-subtle w-full rounded-lg px-4 py-3 text-sm text-text-secondary focus:outline-none"
          />
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="glass-subtle w-full rounded-lg px-4 py-3 text-sm text-text-secondary focus:outline-none"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code} className="bg-neutral-900">
                {l.label}
              </option>
            ))}
          </select>
          <button onClick={saveProfile} className="btn-ghost">
            Save · {languageLabel(language)}
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
