import { useRef, useState } from 'react'
import {
  FlaskConical,
  Play,
  Plus,
  Trash2,
  Loader2,
  Star,
  Sparkles,
  RotateCcw,
  Save,
  ChevronDown,
  ChevronUp
} from 'lucide-react'
import { auth } from '../lib/firebase'
import { cn } from '../lib/utils'

const OMI_BASE = import.meta.env.VITE_OMI_API_BASE as string

const DEFAULT_FLOATING =
  'You are Omi, a personal AI assistant. Be concise and helpful — answer in 1-3 sentences unless more detail is asked for.'

const DEFAULT_MAIN = `You are Omi, a personal AI wearable assistant. You have access to the user's memories, conversations, tasks, and screen context.

Your role:
- Answer questions about the user's experiences and history
- Help with tasks, scheduling, and planning
- Provide context-aware suggestions based on what the user is doing
- Be warm, concise, and highly personalized

Always prioritize the user's privacy and be transparent about what data you reference.`

const DEFAULT_QUESTIONS = [
  'What did I talk about most recently?',
  'What are my open tasks right now?',
  'Summarize my key memories from this week.',
]

const GRADE_PROMPT =
  'You are an evaluator. Rate the following AI assistant response on a scale of 0–5 for quality, relevance, and conciseness. Respond with only a single number (0–5). No explanation.'

const STORE_KEY = 'omi.chatlab.v1'

type EvalRow = {
  id: string
  question: string
  response: string
  aiScore: number | null
  humanStars: number | null
  running: boolean
}

type HistoryEntry = {
  id: string
  ts: number
  floatingPrompt: string
  mainPrompt: string
  avgAi: number | null
  avgHuman: number | null
  questionCount: number
}

function loadStore(): { floating: string; main: string; history: HistoryEntry[] } {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    if (raw) return JSON.parse(raw) as { floating: string; main: string; history: HistoryEntry[] }
  } catch {}
  return { floating: DEFAULT_FLOATING, main: DEFAULT_MAIN, history: [] }
}

function saveStore(data: { floating: string; main: string; history: HistoryEntry[] }): void {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(data)) } catch {}
}

function StarPicker({ value, onChange }: { value: number | null; onChange: (v: number) => void }): React.JSX.Element {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} onClick={() => onChange(n)} className="rounded p-0.5 transition-colors hover:scale-110">
          <Star
            className={cn('h-3.5 w-3.5', (value ?? 0) >= n ? 'text-amber-400' : 'text-white/20')}
            strokeWidth={(value ?? 0) >= n ? 0 : 1.5}
            fill={(value ?? 0) >= n ? 'currentColor' : 'none'}
          />
        </button>
      ))}
    </div>
  )
}

function AiScoreBadge({ score }: { score: number | null }): React.JSX.Element {
  if (score === null) return <span className="text-[11px] text-white/25">—</span>
  const color = score >= 4 ? 'text-green-400' : score >= 2.5 ? 'text-amber-400' : 'text-rose-400'
  return <span className={cn('font-mono text-xs font-semibold tabular-nums', color)}>{score.toFixed(1)}</span>
}

export function ChatLab(): React.JSX.Element {
  const stored = loadStore()
  const [floatingPrompt, setFloatingPrompt] = useState(stored.floating)
  const [mainPrompt, setMainPrompt] = useState(stored.main)
  const [history, setHistory] = useState<HistoryEntry[]>(stored.history)
  const [questions, setQuestions] = useState<string[]>(DEFAULT_QUESTIONS)
  const [newQ, setNewQ] = useState('')
  const [rows, setRows] = useState<EvalRow[]>([])
  const [runningAll, setRunningAll] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [saveFlash, setSaveFlash] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const abortRef = useRef(false)

  const savePrompts = (): void => {
    const data = { floating: floatingPrompt, main: mainPrompt, history }
    saveStore(data)
    setSaveFlash(true)
    setTimeout(() => setSaveFlash(false), 1200)
  }

  const resetPrompts = (): void => {
    setFloatingPrompt(DEFAULT_FLOATING)
    setMainPrompt(DEFAULT_MAIN)
  }

  const addQuestion = (): void => {
    const t = newQ.trim()
    if (!t) return
    setQuestions((q) => [...q, t])
    setNewQ('')
  }

  const removeQuestion = (i: number): void => setQuestions((q) => q.filter((_, j) => j !== i))

  // Run a single question through the current main prompt
  const runOne = async (question: string): Promise<{ response: string; aiScore: number | null }> => {
    const token = await auth.currentUser?.getIdToken()
    const res = await fetch(`${OMI_BASE}/v2/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ text: question, system_prompt_override: mainPrompt })
    })
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

    let text = ''
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line || line.startsWith('done:')) continue
        const content = line.startsWith('data:') ? line.slice(5).replace(/^ /, '') : line
        if (content.startsWith('think:')) continue
        text += content.replace(/__CRLF__/g, '\n')
      }
    }

    // Grade with the same backend
    let aiScore: number | null = null
    try {
      const gradeRes = await fetch(`${OMI_BASE}/v2/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          text: `${GRADE_PROMPT}\n\nQuestion: ${question}\nResponse: ${text}`
        })
      })
      if (gradeRes.ok && gradeRes.body) {
        let gradeText = ''
        const gr = gradeRes.body.getReader()
        const gd = new TextDecoder()
        let gb = ''
        while (true) {
          const { done, value } = await gr.read()
          if (done) break
          gb += gd.decode(value, { stream: true })
          const gl = gb.split('\n')
          gb = gl.pop() ?? ''
          for (const l of gl) {
            if (!l || l.startsWith('done:')) continue
            const c = l.startsWith('data:') ? l.slice(5).replace(/^ /, '') : l
            if (!c.startsWith('think:')) gradeText += c.replace(/__CRLF__/g, '\n')
          }
        }
        const parsed = parseFloat(gradeText.trim().match(/\d+(\.\d+)?/)?.[0] ?? '')
        if (!isNaN(parsed) && parsed >= 0 && parsed <= 5) aiScore = parsed
      }
    } catch {}

    return { response: text, aiScore }
  }

  const runAll = async (): Promise<void> => {
    if (runningAll) return
    setRunningAll(true)
    abortRef.current = false
    const initial: EvalRow[] = questions.map((q, i) => ({
      id: String(i),
      question: q,
      response: '',
      aiScore: null,
      humanStars: null,
      running: true
    }))
    setRows(initial)

    for (let i = 0; i < questions.length; i++) {
      if (abortRef.current) break
      try {
        const { response, aiScore } = await runOne(questions[i])
        setRows((r) => {
          const next = [...r]
          next[i] = { ...next[i], response, aiScore, running: false }
          return next
        })
      } catch {
        setRows((r) => {
          const next = [...r]
          next[i] = { ...next[i], response: '(error)', aiScore: null, running: false }
          return next
        })
      }
    }
    setRunningAll(false)
  }

  const setHumanStars = (i: number, v: number): void => {
    setRows((r) => {
      const next = [...r]
      next[i] = { ...next[i], humanStars: v }
      return next
    })
  }

  const saveVersion = (): void => {
    const finished = rows.filter((r) => !r.running && r.response)
    const aiScores = finished.map((r) => r.aiScore).filter((s): s is number => s !== null)
    const humanScores = finished.map((r) => r.humanStars).filter((s): s is number => s !== null)
    const entry: HistoryEntry = {
      id: crypto.randomUUID(),
      ts: Date.now(),
      floatingPrompt,
      mainPrompt,
      avgAi: aiScores.length ? aiScores.reduce((a, b) => a + b, 0) / aiScores.length : null,
      avgHuman: humanScores.length ? humanScores.reduce((a, b) => a + b, 0) / humanScores.length : null,
      questionCount: questions.length
    }
    const newHistory = [entry, ...history].slice(0, 20)
    setHistory(newHistory)
    saveStore({ floating: floatingPrompt, main: mainPrompt, history: newHistory })
  }

  const generateImproved = async (): Promise<void> => {
    if (generating || rows.length === 0) return
    setGenerating(true)
    try {
      const token = await auth.currentUser?.getIdToken()
      const evalSummary = rows
        .filter((r) => r.response)
        .map((r) => `Q: ${r.question}\nA: ${r.response.slice(0, 200)}\nAI Score: ${r.aiScore ?? 'N/A'}/5`)
        .join('\n\n')
      const metaPrompt = `You are an AI prompt engineer. The following system prompt is being evaluated:\n\n---\n${mainPrompt}\n---\n\nEvaluation results:\n${evalSummary}\n\nGenerate an improved version of the system prompt that addresses the weaknesses shown in the evaluation. Return ONLY the improved system prompt text, nothing else.`
      const res = await fetch(`${OMI_BASE}/v2/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ text: metaPrompt })
      })
      if (!res.ok || !res.body) return
      let improved = ''
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''
        for (const line of lines) {
          if (!line || line.startsWith('done:')) continue
          const c = line.startsWith('data:') ? line.slice(5).replace(/^ /, '') : line
          if (!c.startsWith('think:')) improved += c.replace(/__CRLF__/g, '\n')
        }
      }
      if (improved.trim()) setMainPrompt(improved.trim())
    } catch {} finally {
      setGenerating(false)
    }
  }

  const avgAi = rows.length
    ? rows.map((r) => r.aiScore).filter((s): s is number => s !== null).reduce((a, b, _, arr) => a + b / arr.length, 0) || null
    : null
  const avgHuman = rows.length
    ? rows.map((r) => r.humanStars).filter((s): s is number => s !== null).reduce((a, b, _, arr) => a + b / arr.length, 0) || null
    : null

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {/* Header */}
      <div className="flex shrink-0 items-center gap-3 border-b border-white/[0.07] px-6 py-4">
        <FlaskConical className="h-5 w-5 text-[color:var(--accent)]" strokeWidth={1.75} />
        <h1 className="text-base font-semibold text-text-primary">ChatLab</h1>
        <span className="rounded-full border border-white/10 bg-white/[0.05] px-2 py-0.5 text-[10px] text-white/40">
          Prompt Engineering
        </span>
      </div>

      <div className="flex min-h-0 flex-1 gap-0 overflow-hidden">
        {/* Left: Prompts */}
        <div className="flex w-[45%] shrink-0 flex-col gap-4 overflow-y-auto border-r border-white/[0.06] p-5">
          <section>
            <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-white/40">
              Floating Bar System Prompt
            </p>
            <textarea
              value={floatingPrompt}
              onChange={(e) => setFloatingPrompt(e.target.value)}
              rows={4}
              className="w-full resize-none rounded-xl border border-white/[0.08] bg-white/[0.04] p-3 font-mono text-[12px] leading-relaxed text-white/80 placeholder:text-white/25 focus:border-white/20 focus:outline-none"
              placeholder="Short prompt for the floating overlay bar…"
            />
          </section>
          <section>
            <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-white/40">
              Main System Prompt
            </p>
            <textarea
              value={mainPrompt}
              onChange={(e) => setMainPrompt(e.target.value)}
              rows={14}
              className="w-full resize-none rounded-xl border border-white/[0.08] bg-white/[0.04] p-3 font-mono text-[12px] leading-relaxed text-white/80 placeholder:text-white/25 focus:border-white/20 focus:outline-none"
              placeholder="Full desktop chat system prompt…"
            />
          </section>
          <div className="flex gap-2">
            <button
              onClick={savePrompts}
              className={cn(
                'flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-medium transition-colors',
                saveFlash ? 'bg-green-500/20 text-green-400' : 'bg-[color:var(--accent)]/15 text-[color:var(--accent)] hover:bg-[color:var(--accent)]/25'
              )}
            >
              <Save className="h-3.5 w-3.5" />
              {saveFlash ? 'Saved!' : 'Save'}
            </button>
            <button
              onClick={resetPrompts}
              className="flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-medium text-white/40 transition-colors hover:bg-white/[0.06] hover:text-white/70"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reset
            </button>
          </div>

          {/* Version History */}
          <div className="mt-2 rounded-xl border border-white/[0.06] bg-white/[0.02]">
            <button
              onClick={() => setHistoryOpen((v) => !v)}
              className="flex w-full items-center justify-between px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-white/40"
            >
              <span>Version History ({history.length})</span>
              {historyOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
            {historyOpen && (
              <div className="border-t border-white/[0.06] px-2 pb-2">
                {history.length === 0 ? (
                  <p className="py-4 text-center text-xs text-white/30">No saved versions yet. Save after an eval run.</p>
                ) : (
                  history.map((h, i) => (
                    <div
                      key={h.id}
                      className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-white/[0.04]"
                      onClick={() => { setMainPrompt(h.mainPrompt); setFloatingPrompt(h.floatingPrompt) }}
                    >
                      <span className="shrink-0 text-xs font-mono text-white/35">v{history.length - i}</span>
                      <span className="flex-1 truncate text-xs text-white/60">
                        {new Date(h.ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                        {' · '}{h.questionCount}q
                      </span>
                      {h.avgAi !== null && (
                        <span className="font-mono text-[10px] text-white/40">AI {h.avgAi.toFixed(1)}</span>
                      )}
                      {h.avgHuman !== null && (
                        <span className="font-mono text-[10px] text-amber-400/70">⭐ {h.avgHuman.toFixed(1)}</span>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right: Evaluation */}
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <div className="flex shrink-0 flex-col gap-3 border-b border-white/[0.06] p-5">
            <div className="flex items-center gap-2">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
                Test Questions
              </p>
              <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-white/40">
                {questions.length}
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {questions.map((q, i) => (
                <div
                  key={i}
                  className="group flex max-w-xs items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-xs text-white/70"
                >
                  <span className="line-clamp-1 flex-1">{q}</span>
                  <button
                    onClick={() => removeQuestion(i)}
                    className="shrink-0 rounded p-0.5 text-white/20 opacity-0 transition-opacity hover:text-rose-400 group-hover:opacity-100"
                  >
                    <Trash2 className="h-3 w-3" strokeWidth={1.75} />
                  </button>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                value={newQ}
                onChange={(e) => setNewQ(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') addQuestion() }}
                placeholder="Add a test question…"
                className="flex-1 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-xs text-white/80 placeholder:text-white/30 focus:border-white/20 focus:outline-none"
              />
              <button
                onClick={addQuestion}
                disabled={!newQ.trim()}
                className="flex items-center gap-1.5 rounded-xl bg-white/[0.06] px-3 py-2 text-xs text-white/70 transition-colors hover:bg-white/[0.10] disabled:opacity-40"
              >
                <Plus className="h-3.5 w-3.5" />
                Add
              </button>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => void runAll()}
                disabled={runningAll || questions.length === 0}
                className="flex items-center gap-2 rounded-xl bg-[color:var(--accent)]/15 px-4 py-2 text-sm font-medium text-[color:var(--accent)] transition-colors hover:bg-[color:var(--accent)]/25 disabled:opacity-40"
              >
                {runningAll ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Run All
              </button>
              {rows.length > 0 && !runningAll && (
                <>
                  <button
                    onClick={saveVersion}
                    className="flex items-center gap-2 rounded-xl bg-white/[0.06] px-4 py-2 text-sm font-medium text-white/70 transition-colors hover:bg-white/[0.10]"
                  >
                    <Save className="h-4 w-4" />
                    Save Version
                  </button>
                  <button
                    onClick={() => void generateImproved()}
                    disabled={generating}
                    className="flex items-center gap-2 rounded-xl bg-[color:var(--accent)]/10 px-4 py-2 text-sm font-medium text-[color:var(--accent)]/70 transition-colors hover:bg-[color:var(--accent)]/20 disabled:opacity-40"
                  >
                    {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                    Generate v{history.length + 2}
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Results */}
          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            {rows.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
                <FlaskConical className="h-10 w-10 text-white/10" strokeWidth={1.5} />
                <p className="text-sm text-white/30">Run an evaluation to see results</p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {/* Summary bar */}
                <div className="flex gap-4 rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3">
                  <div className="flex flex-col">
                    <span className="text-[10px] text-white/35">Avg AI Score</span>
                    <span className="font-mono text-sm font-semibold text-white/80">
                      {avgAi !== null ? `${avgAi.toFixed(1)} / 5` : '—'}
                    </span>
                  </div>
                  <div className="h-full w-px bg-white/[0.06]" />
                  <div className="flex flex-col">
                    <span className="text-[10px] text-white/35">Avg Human Rating</span>
                    <span className="font-mono text-sm font-semibold text-amber-400">
                      {avgHuman !== null ? `${avgHuman.toFixed(1)} / 5` : '—'}
                    </span>
                  </div>
                  <div className="h-full w-px bg-white/[0.06]" />
                  <div className="flex flex-col">
                    <span className="text-[10px] text-white/35">Questions</span>
                    <span className="font-mono text-sm font-semibold text-white/80">{rows.length}</span>
                  </div>
                </div>

                {/* Result rows */}
                {rows.map((row, i) => (
                  <div
                    key={row.id}
                    className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4"
                  >
                    <div className="mb-2 flex items-start justify-between gap-3">
                      <p className="text-xs font-semibold text-white/70">{row.question}</p>
                      <div className="flex shrink-0 items-center gap-3">
                        {row.running ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-white/30" />
                        ) : (
                          <>
                            <div className="flex items-center gap-1">
                              <span className="text-[10px] text-white/30">AI</span>
                              <AiScoreBadge score={row.aiScore} />
                            </div>
                            <StarPicker value={row.humanStars} onChange={(v) => setHumanStars(i, v)} />
                          </>
                        )}
                      </div>
                    </div>
                    {row.running ? (
                      <div className="h-6 animate-pulse rounded bg-white/[0.04]" />
                    ) : (
                      <p className="line-clamp-4 text-[12px] leading-relaxed text-white/50">
                        {row.response || '(no response)'}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
