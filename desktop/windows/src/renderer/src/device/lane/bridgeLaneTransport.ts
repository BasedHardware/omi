/**
 * Binds the wearable listen lane to the real preload bridge: opens a
 * conversation session through main (which owns every WebSocket), feeds PCM on
 * the hot fire-and-forget channel, and demultiplexes backend messages back to
 * the lane.
 */

import { auth } from '../../lib/firebase'
import { getPreferences } from '../../lib/preferences'
import { getWindowsDeviceIdHash } from '../../lib/clientDevice'
import { isLiveMicSessionActive } from '../../capture/liveMicSession'
import type { DeviceLaneTransport } from './deviceListenSession'

let nextSessionId = 1

export function createBridgeLaneTransport(): DeviceLaneTransport {
  return {
    isConversationLaneBusy: async () => {
      // The continuous microphone session, if any, runs in the capture window,
      // so this window asks main whether a conversation socket is already open
      // for this user. isLiveMicSessionActive covers the in-window case (this
      // module is shared) and the bridge query covers the cross-window one.
      if (isLiveMicSessionActive()) return true
      const busy = await window.omi?.listenConversationActive?.()
      return busy === true
    },

    startSession: async ({ sessionId, clientConversationId }) => {
      const user = auth.currentUser
      if (!user) throw new Error('Device transcription requires sign-in.')
      const token = await user.getIdToken()
      const deviceIdHash = await getWindowsDeviceIdHash()
      await window.omi.listenStart({
        sessionId,
        // The backend classifies wearable audio the same way it classifies the
        // laptop microphone: one continuous conversation lane.
        source: 'mic',
        token,
        deviceIdHash,
        language: getPreferences().language,
        mode: 'conversation',
        clientConversationId,
        // Main refuses this start if the microphone lane already holds the
        // slot, which closes the gap between the advisory check above and the
        // socket actually opening.
        requireExclusiveConversation: true
      })
    },

    feed: (sessionId, pcm) => window.omi.listenFeed(sessionId, pcm),

    stopSession: (sessionId) => {
      void window.omi.listenStop(sessionId)
    },

    subscribe: (handlers) => {
      const unsubscribe = window.omi.onListenMessage((msg) => {
        switch (msg.kind) {
          case 'connected':
            handlers.onConnected(msg.sessionId)
            return
          case 'segments':
            handlers.onSegments(msg.sessionId, msg.segments)
            return
          case 'event':
            handlers.onEvent(msg.sessionId, msg.event)
            return
          case 'closed':
            handlers.onClosed(msg.sessionId, msg.code, msg.reason)
            return
          case 'error':
            handlers.onError(msg.sessionId, msg.message)
        }
      })
      return unsubscribe
    },

    sleep: (ms, signal) =>
      new Promise((resolve) => {
        if (signal.aborted) {
          resolve('aborted')
          return
        }
        const timer = setTimeout(() => {
          signal.removeEventListener('abort', onAbort)
          resolve('elapsed')
        }, ms)
        const onAbort = (): void => {
          clearTimeout(timer)
          resolve('aborted')
        }
        signal.addEventListener('abort', onAbort, { once: true })
      }),

    newSessionId: () => `omi-device-${Date.now()}-${nextSessionId++}`,
    // The backend keys the server-side conversation on this id, so a reconnect
    // that re-sends it resumes the same conversation.
    newConversationId: () => crypto.randomUUID()
  }
}
