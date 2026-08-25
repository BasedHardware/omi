// Track 3 — IPC surface for the local-first task sync engine (main process). The
// engine (../tasks/taskSyncEngine.ts) owns local SQLite + backend REST; the
// renderer drives everything through these channels and never calls the backend
// for tasks directly. The renderer wave (Tasks.tsx etc.) consumes this contract
// verbatim — see the preload (`window.omi.tasks*`) and OmiBridgeApi in
// shared/types.ts for the typed client.
//
// ┌───────────────────────────────────────────────────────────────────────────┐
// │ CHANNEL (ipcMain.handle unless noted)  PAYLOAD               → RESULT       │
// ├───────────────────────────────────────────────────────────────────────────┤
// │ tasks:listIncomplete   { limit?, offset? }        → ActionItemRecord[]      │
// │ tasks:listCompleted    { limit?, offset? }        → ActionItemRecord[]      │
// │ tasks:listDeleted      { limit?, offset? }        → ActionItemRecord[] (see │
// │                                                     engine note: currently  │
// │                                                     [] — no deleted reader) │
// │ tasks:dashboardSlices  (none)                     → TaskDashboardSlices     │
// │                                                     { overdue, today, noDue}│
// │ tasks:create           TaskCreateFields           → ActionItemRecord        │
// │ tasks:toggle           { backendId, completed }   → void                    │
// │ tasks:update           { backendId, fields }      → void                    │
// │ tasks:delete           { backendId }              → void                    │
// │ tasks:reconcile        (none)                      → void                    │
// ├───────────────────────────────────────────────────────────────────────────┤
// │ tasks:changed          main → renderer event (no payload) — the local store │
// │                        changed (optimistic write or background sync landed);│
// │                        the renderer re-fetches. Subscribe via onTasksChanged│
// └───────────────────────────────────────────────────────────────────────────┘
//
// Reads are LOCAL-FIRST: they return the local rows instantly and kick a background
// sync, then fire `tasks:changed` when the store updates. The engine reads the
// SHARED backend session (assistants/core/session.ts, relayed by the renderer); no
// session is passed per call.
import { ipcMain, type IpcMainInvokeEvent } from 'electron'
import {
  createTask,
  dashboardSlices,
  deleteTask,
  listCompleted,
  listDeleted,
  listIncomplete,
  reconcile,
  toggleTask,
  updateTask
} from '../tasks/taskSyncEngine'
import type {
  ActionItemRecord,
  TaskCreateFields,
  TaskDashboardSlices,
  TaskUpdateFields
} from '../../shared/types'

// --- Arg validation (defense-in-depth at the IPC boundary) -------------------
// The renderer is first-party, but validating here rejects a malformed call with a
// clear Error over the invoke instead of letting a bad shape reach the DB/REST.

type ListOpts = { limit?: number; offset?: number }

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}

function parseListOpts(v: unknown): ListOpts {
  if (v === undefined || v === null) return {}
  if (!isRecord(v)) throw new Error('tasks: list opts must be an object')
  const opts: ListOpts = {}
  if (v.limit !== undefined) {
    if (typeof v.limit !== 'number' || !Number.isInteger(v.limit))
      throw new Error('tasks: limit must be an integer')
    opts.limit = v.limit
  }
  if (v.offset !== undefined) {
    if (typeof v.offset !== 'number' || !Number.isInteger(v.offset))
      throw new Error('tasks: offset must be an integer')
    opts.offset = v.offset
  }
  return opts
}

function parseCreateFields(v: unknown): TaskCreateFields {
  if (!isRecord(v) || typeof v.description !== 'string' || v.description.trim().length === 0) {
    throw new Error('tasks: create requires a non-empty description')
  }
  // Pass through the known fields only; the engine + storage default the rest.
  return v as unknown as TaskCreateFields
}

function assertBackendId(v: unknown): asserts v is string {
  if (typeof v !== 'string' || v.length === 0)
    throw new Error('tasks: backendId must be a non-empty string')
}

export function registerTaskHandlers(): void {
  // Reads — return local rows immediately; a background sync fires `tasks:changed`.
  ipcMain.handle(
    'tasks:listIncomplete',
    (_e: IpcMainInvokeEvent, opts?: unknown): ActionItemRecord[] =>
      listIncomplete(parseListOpts(opts))
  )
  ipcMain.handle(
    'tasks:listCompleted',
    (_e: IpcMainInvokeEvent, opts?: unknown): ActionItemRecord[] =>
      listCompleted(parseListOpts(opts))
  )
  ipcMain.handle(
    'tasks:listDeleted',
    (_e: IpcMainInvokeEvent, opts?: unknown): ActionItemRecord[] => listDeleted(parseListOpts(opts))
  )
  ipcMain.handle('tasks:dashboardSlices', (): TaskDashboardSlices => dashboardSlices())

  // Writes — optimistic local-first, background REST reconcile/revert.
  ipcMain.handle(
    'tasks:create',
    (_e: IpcMainInvokeEvent, fields: unknown): ActionItemRecord =>
      createTask(parseCreateFields(fields))
  )
  ipcMain.handle('tasks:toggle', (_e: IpcMainInvokeEvent, args: unknown): void => {
    if (!isRecord(args)) throw new Error('tasks: toggle requires { backendId, completed }')
    assertBackendId(args.backendId)
    if (typeof args.completed !== 'boolean') throw new Error('tasks: completed must be a boolean')
    toggleTask(args.backendId, args.completed)
  })
  ipcMain.handle('tasks:update', (_e: IpcMainInvokeEvent, args: unknown): void => {
    if (!isRecord(args)) throw new Error('tasks: update requires { backendId, fields }')
    assertBackendId(args.backendId)
    if (!isRecord(args.fields)) throw new Error('tasks: fields must be an object')
    updateTask(args.backendId, args.fields as unknown as TaskUpdateFields)
  })
  ipcMain.handle('tasks:delete', (_e: IpcMainInvokeEvent, args: unknown): void => {
    if (!isRecord(args)) throw new Error('tasks: delete requires { backendId }')
    assertBackendId(args.backendId)
    deleteTask(args.backendId)
  })
  ipcMain.handle('tasks:reconcile', (): Promise<void> => reconcile())
}
