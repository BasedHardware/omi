import React, { useState } from 'react'
import { IconExternal, IconKey } from '../../components/Icons'
import { api } from '../../api/client'

// Counterpart of the Mac AppsPage: integrations and the MCP key flow that connects
// Omi memories to Claude / ChatGPT / any MCP client.

export function AppsPage() {
  const [mcpKey, setMcpKey] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [indexing, setIndexing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const createKey = async () => {
    setCreating(true)
    setError(null)
    try {
      const res = await api.createMcpKey('windows-desktop')
      setMcpKey(res.key)
    } catch (e) {
      setError(String(e))
    } finally {
      setCreating(false)
    }
  }

  const apps: { title: string; desc: string; action: string; onClick: () => void; icon?: React.ReactNode }[] = [
    {
      title: 'Claude / ChatGPT (MCP)',
      desc: 'Give any MCP client access to your Omi memories and conversations.',
      action: creating ? 'Creating…' : 'Create MCP key',
      onClick: () => void createKey(),
      icon: <IconKey size={16} />
    },
    {
      title: 'Omi Mobile App',
      desc: 'Capture conversations on the go, same account, same memory.',
      action: 'Get the app',
      onClick: () => window.omi.system.openExternal('https://www.omi.me')
    },
    {
      title: 'Discord Community',
      desc: '10k+ builders sharing apps, prompts and integrations.',
      action: 'Join',
      onClick: () => window.omi.system.openExternal('https://discord.gg/omi')
    },
    {
      title: 'Index my files',
      desc: 'Scan Downloads/Documents/Desktop to give Omi context on what you work on (a summary memory, stays private).',
      action: indexing ? 'Indexing…' : 'Scan files',
      onClick: async () => {
        setIndexing(true)
        const r = await window.omi.files.index()
        setIndexing(false)
        window.alert(r.ok ? 'Indexed, added a summary memory about your files.' : `Could not index: ${r.error}`)
      }
    },
    {
      title: 'Import from X (Twitter)',
      desc: 'Bring your posts and likes into Omi as memories.',
      action: 'Connect',
      onClick: () => window.omi.system.openExternal('https://www.omi.me/apps')
    },
    {
      title: 'App Marketplace',
      desc: 'Browse community apps and integrations for Omi.',
      action: 'Browse',
      onClick: () => window.omi.system.openExternal('https://www.omi.me/apps')
    }
  ]

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '44px 26px 26px' }}>
      <div style={{ fontSize: 19, fontWeight: 700, marginBottom: 4 }}>Apps</div>
      <div style={{ fontSize: 12.5, color: 'var(--text-quaternary)', marginBottom: 20 }}>
        Connect Omi to the tools you already use
      </div>

      {mcpKey && (
        <div className="section" style={{ padding: 14, marginBottom: 16, borderColor: 'rgba(16,185,129,0.45)' }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--success)', marginBottom: 6 }}>
            MCP key created, copy it now, it won't be shown again
          </div>
          <code
            className="text-selectable"
            style={{
              display: 'block',
              fontSize: 12,
              background: 'var(--bg-tertiary)',
              padding: '8px 10px',
              borderRadius: 8,
              wordBreak: 'break-all'
            }}
          >
            {mcpKey}
          </code>
          <button
            className="btn-secondary"
            style={{ marginTop: 10, fontSize: 12, padding: '6px 12px' }}
            onClick={() => void navigator.clipboard.writeText(mcpKey)}
          >
            Copy to clipboard
          </button>
        </div>
      )}
      {error && <div style={{ fontSize: 12.5, color: 'var(--error)', marginBottom: 14 }}>{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
        {apps.map((a) => (
          <div key={a.title} className="card" style={{ padding: 18 }}>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
              {a.icon}
              {a.title}
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--text-tertiary)', lineHeight: 1.5, marginBottom: 14, minHeight: 38 }}>
              {a.desc}
            </div>
            <button className="btn-secondary" style={{ fontSize: 12.5 }} onClick={a.onClick}>
              {a.action} <IconExternal size={12} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
