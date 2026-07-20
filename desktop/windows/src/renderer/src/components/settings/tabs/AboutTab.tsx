import { MessageCircle } from 'lucide-react'
import { SettingRow } from '../SettingRow'

export function AboutTab(): React.JSX.Element {
  return (
    <SettingRow
      icon={MessageCircle}
      title="Discord"
      subtitle="Join the Omi community for help, feedback, and release updates."
      keywords="discord community support about"
      control={
        <button
          type="button"
          onClick={() => window.open('https://discord.com/invite/8MP3b9ymvx')}
          className="btn-ghost"
        >
          Join Discord
        </button>
      }
    />
  )
}
