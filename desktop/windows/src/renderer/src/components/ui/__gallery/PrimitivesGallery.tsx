import { useState } from 'react'
import { Activity, Bell, Zap } from 'lucide-react'
import { Button } from '../Button'
import { Card } from '../Card'
import { Toggle } from '../Toggle'
import { Badge } from '../Badge'
import { Pill } from '../Pill'
import { Modal } from '../Modal'

// Dev-only visual harness (mounted at #/__ui-gallery, DEV-gated in App.tsx). Not
// a shipped surface — it renders every ui/* primitive across its states so a
// skeptical reviewer can screenshot Fluent-native correctness + focus/DPI.

function Section(props: { title: string; children: React.ReactNode }): React.JSX.Element {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-white/40">
        {props.title}
      </h2>
      {props.children}
    </section>
  )
}

function Row(props: { label?: string; children: React.ReactNode }): React.JSX.Element {
  return (
    <div className="flex flex-col gap-2">
      {props.label && <span className="text-[11px] text-white/35">{props.label}</span>}
      <div className="flex flex-wrap items-center gap-3">{props.children}</div>
    </div>
  )
}

export function PrimitivesGallery(): React.JSX.Element {
  const [toggles, setToggles] = useState({ a: true, b: false })
  const [modalOpen, setModalOpen] = useState(false)
  const [blockingOpen, setBlockingOpen] = useState(false)

  return (
    <div className="min-h-screen w-full overflow-y-auto bg-[var(--bg-primary)] px-8 py-10 text-white">
      <div className="mx-auto flex max-w-5xl flex-col gap-12">
        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold">UI Primitives</h1>
          <p className="text-sm text-white/45">Fluent-native shared controls · components/ui/*</p>
        </header>

        <Section title="Button">
          <Row label="primary / secondary / ghost / danger — size md">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Danger</Button>
          </Row>
          <Row label="size sm">
            <Button size="sm" variant="primary">
              Primary
            </Button>
            <Button size="sm" variant="secondary">
              Secondary
            </Button>
            <Button size="sm" variant="ghost">
              Ghost
            </Button>
            <Button size="sm" variant="danger">
              Danger
            </Button>
          </Row>
          <Row label="disabled / loading">
            <Button disabled>Disabled</Button>
            <Button variant="secondary" disabled>
              Disabled
            </Button>
            <Button loading>Saving</Button>
            <Button variant="secondary" loading>
              Loading
            </Button>
          </Row>
          <Row label="with icon">
            <Button variant="primary">
              <Zap className="h-4 w-4" /> Run
            </Button>
          </Row>
        </Section>

        <Section title="Card">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Card>
              <p className="text-sm font-medium text-white">Flat card</p>
              <p className="mt-1 text-[13px] text-white/45">
                Raised token surface with a hairline.
              </p>
            </Card>
            <Card interactive>
              <p className="text-sm font-medium text-white">Interactive</p>
              <p className="mt-1 text-[13px] text-white/45">Hover to lift the fill + border.</p>
            </Card>
            <Card padding="lg">
              <p className="text-sm font-medium text-white">Large padding</p>
              <p className="mt-1 text-[13px] text-white/45">padding=&quot;lg&quot;</p>
            </Card>
          </div>
        </Section>

        <Section title="Toggle">
          <Row label="on / off / disabled">
            <Toggle
              checked={toggles.a}
              onChange={(v) => setToggles((t) => ({ ...t, a: v }))}
              label="A"
            />
            <Toggle
              checked={toggles.b}
              onChange={(v) => setToggles((t) => ({ ...t, b: v }))}
              label="B"
            />
            <Toggle checked onChange={() => {}} disabled label="on-disabled" />
            <Toggle checked={false} onChange={() => {}} disabled label="off-disabled" />
          </Row>
        </Section>

        <Section title="Badge">
          <Row label="tones — size sm">
            <Badge tone="neutral">Neutral</Badge>
            <Badge tone="success">Success</Badge>
            <Badge tone="warning">Warning</Badge>
            <Badge tone="error">Error</Badge>
            <Badge tone="info">Info</Badge>
          </Row>
          <Row label="size xs">
            <Badge tone="neutral" size="xs">
              12
            </Badge>
            <Badge tone="success" size="xs">
              New
            </Badge>
            <Badge tone="error" size="xs">
              3
            </Badge>
          </Row>
        </Section>

        <Section title="Pill">
          <Row label="static / dot / icon / interactive">
            <Pill>Label</Pill>
            <Pill dot="var(--success)">Online</Pill>
            <Pill icon={Activity}>Recording</Pill>
            <Pill dot icon={Bell} onClick={() => {}}>
              Interactive
            </Pill>
          </Row>
        </Section>

        <Section title="Modal">
          <Row label="dismissible / blocking">
            <Button variant="secondary" onClick={() => setModalOpen(true)}>
              Open modal
            </Button>
            <Button variant="danger" onClick={() => setBlockingOpen(true)}>
              Open blocking
            </Button>
          </Row>
        </Section>
      </div>

      <Modal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title="Rename conversation"
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => setModalOpen(false)}>
              Save
            </Button>
          </>
        }
      >
        Give this conversation a new name. Press Save to confirm, or dismiss with Esc / outside
        click.
      </Modal>

      <Modal
        open={blockingOpen}
        onOpenChange={setBlockingOpen}
        title="Delete account?"
        dismissible={false}
        footer={
          <>
            <Button variant="ghost" onClick={() => setBlockingOpen(false)}>
              Keep
            </Button>
            <Button variant="danger" onClick={() => setBlockingOpen(false)}>
              Delete
            </Button>
          </>
        }
      >
        This cannot be undone. Outside-click and Esc are blocked — choose a button.
      </Modal>
    </div>
  )
}
