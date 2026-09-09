import {decodeBase64} from '../base64';
import {useCallback, useEffect, useRef, useState} from 'react';
import {
  appendDeviceSessionAudio,
  completeDeviceSession,
  isTransientDeviceSessionError,
  openDeviceSession,
  transcribeDeviceSession,
} from '../deviceSessionClient';
import {
  browserScanErrorMessage,
  omiBackend,
  omiNative,
  requestBluetoothScanPermission,
  subscribeOmiNativeEvents,
  type PlatformNativeSnapshot,
} from '../omiNative';
import type {OmiNativeEvent, RecordingJournal} from '../omiNativeTypes';
import {
  createRecordingJournal,
  hasRecordingJournal,
  recordingJournalBackend,
  restoreRecording,
} from '../recordingJournalClient';

function mergeDiscovery(
  snapshot: PlatformNativeSnapshot,
  event: Extract<OmiNativeEvent, {type: 'discovery'}>,
): PlatformNativeSnapshot {
  const devices = snapshot.devices.filter(
    device => device.id !== event.device.id,
  );
  return {
    ...snapshot,
    devices: [...devices, event.device].sort((left, right) =>
      left.id.localeCompare(right.id),
    ),
  };
}

function mergeBattery(
  snapshot: PlatformNativeSnapshot,
  event: Extract<OmiNativeEvent, {type: 'battery'}>,
): PlatformNativeSnapshot {
  return {
    ...snapshot,
    devices: snapshot.devices.map(device =>
      device.id === event.deviceId
        ? {...device, battery: event.battery}
        : device,
    ),
  };
}

const pausedUploadMessage =
  'Recording is saved on this device. Upload is paused and will retry automatically.';

export const DEVICE_UPLOAD_LIMITS = {
  maxPendingBytes: 8_388_608,
  maxSessionBytes: 8_388_608,
  maxChunks: 65_536,
  retryDelaysMs: [500, 1000, 2000],
  resumeDelaysMs: [5000, 10000, 20000, 30000],
} as const;

type CaptureSession = {
  capturedAtMs?: number;
  connectionId: string | null;
  frameStarted: boolean;
  lastPacketSequence: number | null;
  rotationRequested: boolean;
  uploadPaused: boolean;
  journal: RecordingJournal | null;
  journalWork: Promise<void>;
  bufferRelease: Promise<void>;
  deviceName?: string;
  transcriptionRevision: number;
  captureId: string | null;
  id: string | null;
  deviceId: string;
  codec: number;
  pending: Uint8Array[];
  bufferedBytes: number;
  totalBytes: number;
  chunkIndex: number;
  work: Promise<void> | null;
  stopped: boolean;
  failed: boolean;
  completed: boolean;
};

export function useNativeDevices(options?: {enabled?: boolean}) {
  const enabled = options?.enabled ?? true;
  const [nativeSnapshot, setNativeSnapshot] =
    useState<PlatformNativeSnapshot | null>(null);
  const [rememberedDevice, setRememberedDevice] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const rememberedOperationRef = useRef(0);
  const rememberedConnectionRef = useRef<string | null>(null);
  const rememberIntentRef = useRef<string | null>(null);
  const [rememberedBusy, setRememberedBusy] = useState(false);
  const [deviceBusy, setDeviceBusy] = useState(false);
  const [deviceScanMessage, setDeviceScanMessage] = useState<string | null>(
    null,
  );
  const nativeSnapshotRef = useRef<PlatformNativeSnapshot | null>(null);
  const captureRef = useRef<CaptureSession | null>(null);
  const requestedDeviceRef = useRef<string | null>(null);
  const cancelledRef = useRef(false);
  const pendingBytesRef = useRef(0);
  const capturesRef = useRef(new Set<CaptureSession>());
  const retryWaitsRef = useRef(new Set<() => void>());
  const pausedRetryRef = useRef({scheduled: false, running: false, attempt: 0});
  const journalReadyRef = useRef<Promise<void> | null>(null);
  const epochRef = useRef(0);
  const transcriptionRevisionRef = useRef(0);
  const enabledRef = useRef(enabled);

  enabledRef.current = enabled;
  nativeSnapshotRef.current = nativeSnapshot;

  const releaseCaptureBuffer = useCallback(
    (capture: CaptureSession, epoch: number) => {
      const retainedBytes = capture.bufferedBytes;
      capture.bufferedBytes = 0;
      capture.pending = [];
      const release = () => {
        if (enabledRef.current && epoch === epochRef.current)
          pendingBytesRef.current -= retainedBytes;
      };
      if (omiBackend != null && hasRecordingJournal(omiBackend)) {
        capture.bufferRelease = Promise.all([
          capture.bufferRelease,
          capture.journalWork.then(release, release),
        ]).then(() => undefined);
      } else release();
    },
    [],
  );

  const failJournal = useCallback(
    (capture: CaptureSession, epoch: number) => {
      if (!enabledRef.current || epoch !== epochRef.current || capture.failed) {
        return;
      }
      capture.failed = true;
      releaseCaptureBuffer(capture, epoch);
      capturesRef.current.delete(capture);
      setDeviceScanMessage(
        'Recording storage failed. Capture stopped; previously saved audio is retained on this device.',
      );
      if (captureRef.current === capture)
        void omiNative
          ?.disconnectDevice(capture.deviceId)
          .catch(() => undefined);
    },
    [releaseCaptureBuffer],
  );

  const processCapture = useCallback(
    (capture: CaptureSession, epoch: number): Promise<void> => {
      if (capture.work !== null) {
        return capture.work;
      }
      if (
        capture.failed ||
        capture.uploadPaused ||
        capture.completed ||
        !enabledRef.current ||
        epoch !== epochRef.current ||
        omiBackend == null
      ) {
        return Promise.resolve();
      }
      let backend = omiBackend;
      const current = () => enabledRef.current && epoch === epochRef.current;
      const retry = async (action: () => Promise<unknown>) => {
        for (let attempt = 0; current() && !capture.failed; attempt += 1) {
          try {
            await action();
            return;
          } catch (error) {
            if (!current() || capture.failed) {
              return;
            }
            const delay = DEVICE_UPLOAD_LIMITS.retryDelaysMs[attempt];
            if (!isTransientDeviceSessionError(error) || delay === undefined) {
              throw error;
            }
            await new Promise<void>(resolve => {
              const stop = () => {
                clearTimeout(timer);
                retryWaitsRef.current.delete(stop);
                resolve();
              };
              const timer = setTimeout(stop, delay);
              retryWaitsRef.current.add(stop);
            });
          }
        }
      };
      const scheduleResume = () => {
        const state = pausedRetryRef.current;
        if (
          !current() ||
          state.scheduled ||
          state.running ||
          ![...capturesRef.current].some(
            item => item.uploadPaused && !item.failed,
          )
        )
          return;
        state.scheduled = true;
        const delays = DEVICE_UPLOAD_LIMITS.resumeDelaysMs;
        const delay = delays[Math.min(state.attempt++, delays.length - 1)]!;
        const cancel = () => {
          clearTimeout(timer);
          state.scheduled = false;
          retryWaitsRef.current.delete(cancel);
        };
        const timer = setTimeout(() => {
          cancel();
          if (!current()) return;
          state.running = true;
          void (async () => {
            for (const paused of [...capturesRef.current]) {
              if (!current()) return;
              if (paused.failed || !capturesRef.current.has(paused)) continue;
              if (
                !paused.uploadPaused ||
                paused.failed ||
                paused.journal === null
              )
                continue;
              try {
                await paused.journalWork;
                if (!current()) return;
                if (paused.failed || !capturesRef.current.has(paused)) continue;
                if (paused.stopped) {
                  await paused.journalWork;
                  await paused.bufferRelease;
                  if (!current()) return;
                  if (paused.failed || !capturesRef.current.has(paused))
                    continue;
                  const restored = restoreRecording(
                    await omiBackend!.readRecordingJournal!(
                      paused.journal.handle,
                    ),
                  );
                  if (!current()) return;
                  if (paused.failed || !capturesRef.current.has(paused))
                    continue;
                  const bytes = restored.pending.reduce(
                    (sum, packet) => sum + packet.length,
                    0,
                  );
                  if (
                    pendingBytesRef.current + bytes >
                    DEVICE_UPLOAD_LIMITS.maxPendingBytes
                  )
                    continue;
                  paused.journal = restored.journal;
                  paused.id = restored.journal.sessionId;
                  paused.chunkIndex = restored.acknowledged;
                  paused.pending = restored.pending;
                  paused.bufferedBytes = bytes;
                  pendingBytesRef.current += bytes;
                }
                paused.uploadPaused = false;
                await processCapture(paused, epoch);
              } catch {
                if (current()) failJournal(paused, epoch);
              }
            }
          })().finally(() => {
            state.running = false;
            if (current()) {
              if (
                ![...capturesRef.current].some(
                  item => item.uploadPaused && !item.failed,
                )
              ) {
                state.attempt = 0;
                setDeviceScanMessage(message =>
                  message === pausedUploadMessage ? null : message,
                );
              }
              scheduleResume();
            }
          });
        }, delay);
        retryWaitsRef.current.add(cancel);
      };
      const pauseUpload = () => {
        capture.uploadPaused = true;
        if (capture.stopped) releaseCaptureBuffer(capture, epoch);
        setDeviceScanMessage(pausedUploadMessage);
        scheduleResume();
      };
      const work = (async () => {
        try {
          await capture.journalWork;
          if (!current() || capture.failed) {
            return;
          }
          if (capture.journal !== null) {
            backend = recordingJournalBackend(
              omiBackend!,
              capture.journal.handle,
            );
          }
          if (capture.id === null) {
            if (capture.captureId === null) {
              if (backend.createRecordingId === undefined) {
                throw new Error('Native recording identity is unavailable');
              }
              const captureId = await backend.createRecordingId();
              if (!current() || capture.failed) {
                return;
              }
              if (
                !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
                  captureId,
                )
              ) {
                throw new Error('Native recording identity is invalid');
              }
              capture.captureId = captureId;
            }
            const captureId = capture.captureId;
            await retry(async () => {
              const session = await openDeviceSession(backend, {
                captureId,
                ...(capture.capturedAtMs === undefined
                  ? {}
                  : {capturedAtMs: capture.capturedAtMs}),
                deviceId: capture.deviceId,
                deviceName: capture.deviceName,
                codec: capture.codec,
              });
              if (current() && !capture.failed) {
                capture.id = session.id;
              }
            });
            if (!current() || capture.failed || capture.id === null) {
              return;
            }
          }
          while (current() && !capture.failed && capture.pending.length > 0) {
            const batch: Uint8Array[] = [];
            let batchBytes = 0;
            for (const packet of capture.pending) {
              if (batch.length >= 128 || batchBytes + packet.length > 1048576) {
                break;
              }
              batch.push(packet);
              batchBytes += packet.length;
            }
            const durableBatch = capture.journalWork;
            await durableBatch;
            if (!current() || capture.failed) return;
            await retry(() =>
              appendDeviceSessionAudio(
                backend,
                capture.id!,
                batch,
                capture.chunkIndex,
              ),
            );
            if (!current() || capture.failed) {
              return;
            }
            if (capture.journal !== null) {
              const journal = capture.journal;
              const acknowledged = capture.chunkIndex + batch.length;
              capture.journalWork = capture.journalWork.then(async () => {
                if (!current() || capture.failed)
                  throw new Error('Recording retired');
                await omiBackend!.appendRecordingJournal!(
                  journal.handle,
                  JSON.stringify(['a', acknowledged]),
                );
              });
              await capture.journalWork;
              if (!current() || capture.failed) {
                return;
              }
            }
            capture.pending.splice(0, batch.length);
            capture.bufferedBytes -= batchBytes;
            pendingBytesRef.current -= batchBytes;
            capture.chunkIndex += batch.length;
          }
        } catch (error) {
          if (!current() || capture.failed) {
            return;
          }
          if (
            capture.journal !== null &&
            isTransientDeviceSessionError(error)
          ) {
            pauseUpload();
            return;
          }
          capture.failed = true;
          releaseCaptureBuffer(capture, epoch);
          if (capture.journal !== null && captureRef.current === capture) {
            void omiNative
              ?.disconnectDevice(capture.deviceId)
              .catch(() => undefined);
          }
          setDeviceScanMessage(
            capture.journal !== null
              ? 'Recording upload paused. Saved audio is retained on this device for recovery when you reopen the app.'
              : capture.id === null
              ? 'Audio upload could not start. Reconnect your Omi to start a new recording.'
              : 'Audio upload was interrupted. This recording could not be saved completely. Reconnect your Omi to start a new recording.',
          );
          return;
        }
        if (current() && !capture.failed && capture.stopped) {
          try {
            await capture.journalWork;
            if (!current()) {
              return;
            }
            await retry(() => completeDeviceSession(backend, capture.id!));
          } catch (error) {
            if (current()) {
              if (
                capture.journal !== null &&
                isTransientDeviceSessionError(error)
              )
                pauseUpload();
              else {
                capture.failed = true;
                setDeviceScanMessage(
                  'Audio was uploaded, but the recording could not be finalized. Its saved status is unconfirmed.',
                );
              }
            }
            return;
          }
          if (!current()) {
            return;
          }
          capture.completed = true;
          const revision = capture.transcriptionRevision;
          const canReport = () =>
            current() && revision === transcriptionRevisionRef.current;
          if (canReport()) {
            setDeviceScanMessage(
              'Recording saved. Transcription is in progress.',
            );
          }
          void (async () => {
            try {
              const transcript = await transcribeDeviceSession(
                backend,
                capture.id!,
              );
              if (!canReport()) {
                return;
              }
              if (transcript.state === 'failed') {
                setDeviceScanMessage(
                  'Recording saved, but transcription failed. Open its transcript for details.',
                );
              } else if (transcript.state !== 'completed') {
                setDeviceScanMessage(
                  'Recording saved. Transcription is pending; open its transcript to check or resume.',
                );
              } else {
                setDeviceScanMessage(null);
              }
            } catch {
              if (canReport()) {
                setDeviceScanMessage(
                  'Recording saved, but transcription could not finish. Open its transcript to check its status.',
                );
              }
            } finally {
              if (current() && capture.journal !== null) {
                try {
                  await omiBackend!.removeRecordingJournal!(
                    capture.journal.handle,
                  );
                } catch {
                  if (canReport()) {
                    setDeviceScanMessage(
                      'Recording saved. Local recovery data could not be cleared.',
                    );
                  }
                }
              }
            }
          })();
        }
      })();
      capture.work = work;
      void work.finally(() => {
        capture.work = null;
        if (capture.failed || capture.completed) {
          capturesRef.current.delete(capture);
        }
        if (
          current() &&
          !capture.failed &&
          !capture.uploadPaused &&
          !capture.completed &&
          (capture.pending.length > 0 || capture.stopped)
        ) {
          void processCapture(capture, epoch);
        }
      });
      return work;
    },
    [releaseCaptureBuffer, failJournal],
  );

  const finishSession = useCallback(
    async (continueRecording = false) => {
      const epoch = epochRef.current;
      cancelledRef.current = !continueRecording;
      const capture = captureRef.current;
      captureRef.current = null;
      if (capture === null) {
        return;
      }
      capture.stopped = true;
      if (
        omiBackend !== null &&
        omiBackend !== undefined &&
        hasRecordingJournal(omiBackend)
      ) {
        capture.journalWork = capture.journalWork.then(async () => {
          if (capture.journal !== null) {
            await omiBackend!.appendRecordingJournal!(
              capture.journal.handle,
              JSON.stringify(['s']),
            );
          }
        });
        void capture.journalWork.catch(() => failJournal(capture, epoch));
      }
      const work = processCapture(capture, epoch);
      if (capture.uploadPaused) releaseCaptureBuffer(capture, epoch);
      if (capture.id !== null) {
        await work;
      }
    },
    [failJournal, processCapture, releaseCaptureBuffer],
  );

  const persistAudio = useCallback(
    async (event: Extract<OmiNativeEvent, {type: 'audio'}>) => {
      if (!enabledRef.current || omiBackend == null || cancelledRef.current) {
        return;
      }
      if (
        event.connectionId.length === 0 ||
        event.connectionId !== nativeSnapshotRef.current?.connectionId
      )
        return;
      const size = Math.floor((event.payloadBase64.length * 3) / 4);
      const bytes =
        size > DEVICE_UPLOAD_LIMITS.maxPendingBytes
          ? null
          : decodeBase64(event.payloadBase64);
      const startsFrame = bytes !== null && bytes.length > 3 && bytes[2] === 0;
      const sequence =
        bytes !== null && bytes.length > 3
          ? bytes[0]! | (bytes[1]! << 8)
          : null;
      let capture = captureRef.current;
      if (
        capture !== null &&
        (capture.rotationRequested ||
          (capture.frameStarted &&
            (capture.totalBytes >=
              DEVICE_UPLOAD_LIMITS.maxSessionBytes - 62_208 ||
              capture.chunkIndex + capture.pending.length >=
                DEVICE_UPLOAD_LIMITS.maxChunks - 256))) &&
        !capture.failed &&
        !capture.stopped &&
        !capture.completed &&
        startsFrame &&
        capture.deviceId === event.deviceId &&
        capture.codec === event.codec &&
        capture.connectionId === nativeSnapshotRef.current?.connectionId
      ) {
        if (
          capture.lastPacketSequence !== null &&
          sequence === ((capture.lastPacketSequence + 1) & 0xffff)
        ) {
          void finishSession(true);
          capture = null;
        } else {
          capture.rotationRequested = false;
          setDeviceScanMessage(
            'Audio packet loss was detected. The recording was not split.',
          );
        }
      }
      if (capture === null) {
        transcriptionRevisionRef.current++;
        capture = {
          ...(event.capturedAtMs === undefined
            ? {}
            : {capturedAtMs: event.capturedAtMs}),
          connectionId: nativeSnapshotRef.current?.connectionId ?? null,
          frameStarted: false,
          lastPacketSequence: null,
          rotationRequested: false,
          uploadPaused: false,
          journal: null,
          journalWork: Promise.resolve(),
          bufferRelease: Promise.resolve(),
          deviceName: nativeSnapshotRef.current?.devices.find(
            item => item.id === event.deviceId,
          )?.name,
          transcriptionRevision: transcriptionRevisionRef.current,
          captureId: null,
          id: null,
          deviceId: event.deviceId,
          codec: event.codec,
          pending: [],
          bufferedBytes: 0,
          totalBytes: 0,
          chunkIndex: 0,
          work: null,
          stopped: false,
          failed: false,
          completed: false,
        };
        captureRef.current = capture;
        capturesRef.current.add(capture);
        if (hasRecordingJournal(omiBackend)) {
          const target = capture;
          const epoch = epochRef.current;
          target.journalWork = createRecordingJournal(omiBackend, {
            ...(target.capturedAtMs === undefined
              ? {}
              : {capturedAtMs: target.capturedAtMs}),
            deviceId: target.deviceId,
            deviceName: target.deviceName,
            codec: target.codec,
          }).then(journal => {
            if (!enabledRef.current || epoch !== epochRef.current) {
              throw new Error('Recording retired');
            }
            target.journal = journal;
            target.captureId = journal.captureId;
          });
          void target.journalWork.catch(() => failJournal(target, epoch));
        }
      }
      if (
        capture.failed ||
        capture.connectionId !== event.connectionId ||
        capture.deviceId !== event.deviceId ||
        capture.codec !== event.codec
      ) {
        return;
      }
      if (
        bytes === null ||
        pendingBytesRef.current + bytes.length >
          DEVICE_UPLOAD_LIMITS.maxPendingBytes ||
        capture.totalBytes + bytes.length >
          DEVICE_UPLOAD_LIMITS.maxSessionBytes ||
        capture.chunkIndex + capture.pending.length >=
          DEVICE_UPLOAD_LIMITS.maxChunks
      ) {
        capture.failed = true;
        releaseCaptureBuffer(capture, epochRef.current);
        capturesRef.current.delete(capture);
        if (hasRecordingJournal(omiBackend)) {
          void omiNative
            ?.disconnectDevice(capture.deviceId)
            .catch(() => undefined);
        }
        setDeviceScanMessage(
          'Recording storage limit reached. This recording could not be saved completely. Reconnect your Omi to start a new recording.',
        );
        return;
      }
      if (hasRecordingJournal(omiBackend)) {
        const target = capture;
        const epoch = epochRef.current;
        target.journalWork = target.journalWork.then(async () => {
          if (
            !enabledRef.current ||
            epoch !== epochRef.current ||
            target.journal === null
          ) {
            throw new Error('Recording retired');
          }
          await omiBackend!.appendRecordingJournal!(
            target.journal.handle,
            JSON.stringify(['p', event.payloadBase64]),
          );
        });
        void target.journalWork.catch(() => failJournal(target, epoch));
      }
      capture.frameStarted ||= startsFrame;
      capture.lastPacketSequence = sequence;
      capture.pending.push(bytes);
      capture.bufferedBytes += bytes.length;
      capture.totalBytes += bytes.length;
      pendingBytesRef.current += bytes.length;
      await processCapture(capture, epochRef.current);
    },
    [failJournal, finishSession, processCapture, releaseCaptureBuffer],
  );

  const applySnapshot = useCallback(
    (snapshot: PlatformNativeSnapshot) => {
      const previous = nativeSnapshotRef.current;
      nativeSnapshotRef.current = snapshot;
      if (snapshot.capture !== 'recording' && captureRef.current !== null) {
        void finishSession();
      } else if (
        snapshot.capture === 'recording' &&
        previous?.capture !== 'recording'
      ) {
        cancelledRef.current = false;
      }
      setNativeSnapshot(snapshot);
      if (
        enabledRef.current &&
        snapshot.phase === 'connected' &&
        snapshot.capture === 'recording' &&
        snapshot.connectionId &&
        snapshot.connectedDeviceId === requestedDeviceRef.current &&
        snapshot.connectedDeviceId === rememberIntentRef.current &&
        rememberedConnectionRef.current !== snapshot.connectionId &&
        omiNative?.rememberConnectedDevice
      ) {
        const connection = snapshot.connectionId;
        const epoch = epochRef.current;
        const operation = ++rememberedOperationRef.current;
        rememberedConnectionRef.current = connection;
        rememberIntentRef.current = null;
        setRememberedBusy(true);
        void omiNative
          .rememberConnectedDevice()
          .then(device => {
            if (
              enabledRef.current &&
              epoch === epochRef.current &&
              operation === rememberedOperationRef.current
            )
              setRememberedDevice(device);
          })
          .catch(() => {
            if (
              enabledRef.current &&
              epoch === epochRef.current &&
              operation === rememberedOperationRef.current
            )
              setDeviceScanMessage(
                'Connected, but the device shortcut could not be saved.',
              );
          })
          .finally(() => {
            if (
              enabledRef.current &&
              epoch === epochRef.current &&
              operation === rememberedOperationRef.current
            )
              setRememberedBusy(false);
          });
      }
    },
    [finishSession],
  );

  useEffect(() => {
    let active = true;
    cancelledRef.current = false;
    setNativeSnapshot(null);
    setDeviceBusy(false);
    setRememberedDevice(null);
    setRememberedBusy(false);
    rememberedConnectionRef.current = null;
    rememberIntentRef.current = null;
    const rememberedOperation = ++rememberedOperationRef.current;
    setDeviceScanMessage(null);
    const retireSession = () => {
      active = false;
      rememberedOperationRef.current++;
      rememberIntentRef.current = null;
      const deviceIds = new Set([
        requestedDeviceRef.current,
        nativeSnapshotRef.current?.connectedDeviceId,
        ...(nativeSnapshotRef.current?.devices
          .filter(device => device.connected)
          .map(device => device.id) ?? []),
      ]);
      requestedDeviceRef.current = null;
      journalReadyRef.current = null;
      epochRef.current += 1;
      captureRef.current = null;
      for (const capture of capturesRef.current) {
        capture.pending = [];
        capture.bufferedBytes = 0;
      }
      capturesRef.current.clear();
      pendingBytesRef.current = 0;
      for (const stop of retryWaitsRef.current) {
        stop();
      }
      pausedRetryRef.current = {scheduled: false, running: false, attempt: 0};
      cancelledRef.current = true;
      nativeSnapshotRef.current = null;
      const native = omiNative;
      if (enabled && native != null) {
        const cleanup = (operation: () => Promise<void>) => {
          try {
            void operation().catch(() => undefined);
          } catch {}
        };
        cleanup(() => native.stopScan());
        for (const id of deviceIds) {
          if (id) {
            cleanup(() => native.disconnectDevice(id));
          }
        }
      }
    };
    if (!enabled || omiNative === undefined || omiNative === null) {
      return retireSession;
    }
    if (omiNative.getRememberedDevice) {
      void omiNative
        .getRememberedDevice()
        .then(device => {
          if (active && rememberedOperation === rememberedOperationRef.current)
            setRememberedDevice(device);
        })
        .catch(() => {
          if (active && rememberedOperation === rememberedOperationRef.current)
            setDeviceScanMessage(
              'The saved device shortcut could not be loaded. You can still scan for your Omi.',
            );
        });
    }
    if (omiBackend != null && hasRecordingJournal(omiBackend)) {
      const backend = omiBackend;
      const epoch = epochRef.current;
      const ready = backend.listRecordingJournals!().then(descriptors => {
        if (!active) {
          return;
        }
        void (async () => {
          for (const descriptor of descriptors) {
            if (!active) {
              return;
            }
            const restored = restoreRecording(
              await backend.readRecordingJournal!(descriptor.handle),
            );
            if (!active) {
              return;
            }
            if (restored.totalBytes === 0) {
              await backend.removeRecordingJournal!(restored.journal.handle);
              continue;
            }
            const capture: CaptureSession = {
              ...(restored.journal.capturedAtMs === undefined
                ? {}
                : {capturedAtMs: restored.journal.capturedAtMs}),
              connectionId: null,
              frameStarted: false,
              lastPacketSequence: null,
              rotationRequested: false,
              uploadPaused: false,
              journal: restored.journal,
              journalWork: Promise.resolve(),
              bufferRelease: Promise.resolve(),
              deviceName: restored.journal.deviceName ?? undefined,
              transcriptionRevision: transcriptionRevisionRef.current,
              captureId: restored.journal.captureId,
              id: restored.journal.sessionId,
              deviceId: restored.journal.deviceId,
              codec: restored.journal.codec,
              pending: restored.pending,
              bufferedBytes: restored.pending.reduce(
                (sum, bytes) => sum + bytes.length,
                0,
              ),
              totalBytes: restored.totalBytes,
              chunkIndex: restored.acknowledged,
              work: null,
              stopped: true,
              failed: false,
              completed: false,
            };
            if (
              pendingBytesRef.current + capture.bufferedBytes >
              DEVICE_UPLOAD_LIMITS.maxPendingBytes
            ) {
              throw new Error('Recording recovery memory is full');
            }
            pendingBytesRef.current += capture.bufferedBytes;
            capturesRef.current.add(capture);
            await processCapture(capture, epoch);
          }
        })().catch(() => {
          if (active) {
            setDeviceScanMessage(
              'Saved recordings could not be recovered. Audio remains on this device.',
            );
          }
        });
      });
      journalReadyRef.current = ready;
      void ready.catch(() => {
        if (active) {
          setDeviceScanMessage(
            'Recording ownership could not be verified. Connecting is unavailable until you reopen the app.',
          );
        }
      });
    }
    omiNative
      .getSnapshot()
      .then(snapshot => {
        if (active) {
          applySnapshot(snapshot);
        }
      })
      .catch(() => undefined);
    const unsubscribe = subscribeOmiNativeEvents(event => {
      if (!active) {
        return;
      }
      if (event.type === 'snapshot') {
        applySnapshot(event.snapshot);
        return;
      }
      if (event.type === 'discovery') {
        setNativeSnapshot(current =>
          current === null
            ? {
                bluetooth: 'poweredOn',
                devices: [event.device],
                connectedDeviceId: null,
                phase: 'disconnected',
                capture: 'idle',
                lastEvent: 'Found 1 Omi device',
                microphone: 'unknown',
                notifications: 'unknown',
              }
            : mergeDiscovery(current, event),
        );
        return;
      }
      if (event.type === 'battery') {
        setNativeSnapshot(current =>
          current === null ? current : mergeBattery(current, event),
        );
        return;
      }
      if (event.type === 'button') {
        const snapshot = nativeSnapshotRef.current;
        const capture = captureRef.current;
        if (
          enabledRef.current &&
          !cancelledRef.current &&
          event.action === 'doublePress' &&
          snapshot?.capture === 'recording' &&
          snapshot.phase === 'connected' &&
          snapshot.connectedDeviceId === event.deviceId &&
          snapshot.connectionId === event.connectionId &&
          snapshot.devices.some(
            device =>
              device.id === event.deviceId &&
              device.connected &&
              device.buttonSupported === true,
          ) &&
          capture !== null &&
          capture.connectionId === event.connectionId &&
          capture.deviceId === event.deviceId &&
          capture.frameStarted &&
          capture.totalBytes > 0 &&
          !capture.failed &&
          !capture.stopped &&
          !capture.completed
        ) {
          capture.rotationRequested = true;
        }
        return;
      }
      if (event.type === 'audio') {
        persistAudio(event).catch(() => undefined);
      }
    });
    return () => {
      retireSession();
      unsubscribe();
    };
  }, [applySnapshot, enabled, persistAudio, processCapture]);

  const scanForOmi = useCallback(async () => {
    const epoch = epochRef.current;
    if (!enabledRef.current || omiNative === undefined || omiNative === null) {
      return;
    }
    setDeviceBusy(true);
    setDeviceScanMessage(null);
    try {
      const permitted = await requestBluetoothScanPermission();
      if (!enabledRef.current || epoch !== epochRef.current) {
        return;
      }
      if (!permitted) {
        setDeviceScanMessage(
          'Bluetooth permission is required to find your Omi. Allow it in app settings and try again.',
        );
        return;
      }
      const devices = await omiNative.startScan(8);
      if (!enabledRef.current || epoch !== epochRef.current) {
        return;
      }
      const snapshot = await omiNative.getSnapshot();
      if (!enabledRef.current || epoch !== epochRef.current) {
        return;
      }
      applySnapshot({...snapshot, devices});
    } catch (error) {
      if (!enabledRef.current || epoch !== epochRef.current) {
        return;
      }
      const message = browserScanErrorMessage(error);
      if (message !== null) {
        setDeviceScanMessage(message);
      } else {
        setDeviceScanMessage(
          'Could not scan for your Omi. Check Bluetooth and try again.',
        );
      }
    } finally {
      if (enabledRef.current && epoch === epochRef.current) {
        setDeviceBusy(false);
      }
    }
  }, [applySnapshot]);

  const toggleDevice = useCallback(
    async (id: string, connected: boolean) => {
      const epoch = epochRef.current;
      if (
        !enabledRef.current ||
        omiNative === undefined ||
        omiNative === null
      ) {
        return;
      }
      setDeviceBusy(true);
      setDeviceScanMessage(null);
      try {
        if (connected) {
          rememberIntentRef.current = null;
          await omiNative.disconnectDevice(id);
          if (!enabledRef.current || epoch !== epochRef.current) {
            return;
          }
          if (requestedDeviceRef.current === id) {
            requestedDeviceRef.current = null;
          }
          await finishSession();
        } else {
          if (rememberedDevice?.id === id) {
            const current = await omiNative.getRememberedDevice?.();
            if (!enabledRef.current || epoch !== epochRef.current) return;
            if (current?.id !== id) {
              setRememberedDevice(current ?? null);
              throw new Error('Remembered device ownership changed');
            }
          }
          await journalReadyRef.current;
          if (!enabledRef.current || epoch !== epochRef.current) {
            return;
          }
          requestedDeviceRef.current = id;
          rememberIntentRef.current = id;
          await omiNative.connectDevice(id);
          if (!enabledRef.current || epoch !== epochRef.current) {
            return;
          }
          if (captureRef.current?.failed) {
            captureRef.current = null;
          }
          cancelledRef.current = false;
        }
        if (!enabledRef.current || epoch !== epochRef.current) {
          return;
        }
        const snapshot = await omiNative.getSnapshot();
        if (!enabledRef.current || epoch !== epochRef.current) {
          return;
        }
        applySnapshot(snapshot);
      } catch {
        if (!enabledRef.current || epoch !== epochRef.current) {
          return;
        }
        setDeviceScanMessage(
          connected
            ? 'Could not disconnect your Omi. Try again.'
            : 'Could not connect to your Omi. Keep it nearby and try again.',
        );
        return;
      } finally {
        if (enabledRef.current && epoch === epochRef.current) {
          setDeviceBusy(false);
        }
      }
    },
    [applySnapshot, finishSession, rememberedDevice],
  );

  const forgetRememberedDevice = useCallback(async () => {
    if (!enabledRef.current || !omiNative?.forgetRememberedDevice) return;
    const epoch = epochRef.current;
    const operation = ++rememberedOperationRef.current;
    rememberIntentRef.current = null;
    setRememberedBusy(true);
    try {
      await omiNative.forgetRememberedDevice();
      if (
        enabledRef.current &&
        epoch === epochRef.current &&
        operation === rememberedOperationRef.current
      )
        setRememberedDevice(null);
    } catch {
      if (
        enabledRef.current &&
        epoch === epochRef.current &&
        operation === rememberedOperationRef.current
      )
        setDeviceScanMessage(
          'The device shortcut could not be forgotten. Try again.',
        );
    } finally {
      if (
        enabledRef.current &&
        epoch === epochRef.current &&
        operation === rememberedOperationRef.current
      )
        setRememberedBusy(false);
    }
  }, []);

  return {
    rememberedDevice: enabled ? rememberedDevice : null,
    rememberedBusy,
    forgetRememberedDevice,
    deviceBusy,
    deviceScanMessage,
    nativeSnapshot,
    scanForOmi,
    toggleDevice,
  };
}
