import React from 'react'
import { useSettings } from '../../stores/settings'

export function HelpPage() {
  const { settings } = useSettings()
  const hotkey = (settings?.hotkey || 'Ctrl+Shift+Space').replace(/Control/g, 'Ctrl')
  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '44px 26px 26px', maxWidth: 640 }}>
      <div style={{ fontSize: 19, fontWeight: 700, marginBottom: 18 }}>Help</div>

      <div className="section" style={{ padding: 16, marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Quick start</div>
        <ul style={{ fontSize: 13, color: 'var(--text-tertiary)', lineHeight: 1.8, paddingLeft: 18 }}>
          <li>
            Press <b style={{ color: 'var(--text-secondary)' }}>{hotkey}</b> anywhere to ask Omi from the floating bar.
          </li>
          <li>Start a recording on the Conversations page, Omi transcribes, summarizes and extracts tasks.</li>
          <li>Turn on Rewind to make everything you see searchable.</li>
          <li>Ctrl+1…8 switch pages, like Cmd+1…6 on the Mac app.</li>
        </ul>
      </div>

      <div className="section" style={{ padding: 16, marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Community & support</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn-secondary" style={{ fontSize: 12.5 }} onClick={() => window.omi.system.openExternal('https://discord.gg/omi')}>
            Discord
          </button>
          <button className="btn-secondary" style={{ fontSize: 12.5 }} onClick={() => window.omi.system.openExternal('https://github.com/BasedHardware/omi/issues')}>
            GitHub Issues
          </button>
          <button className="btn-secondary" style={{ fontSize: 12.5 }} onClick={() => window.omi.system.openExternal('https://docs.omi.me')}>
            Docs
          </button>
        </div>
      </div>
    </div>
  )
}
