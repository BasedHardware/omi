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

function bytesFromBase64(value: string): Uint8Array {
  const binary = globalThis.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

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

export const DEVICE_UPLOAD_LIMITS = {
  maxPendingBytes: 8_388_608,
  maxSessionBytes: 8_388_608,
  maxChunks: 65_536,
  retryDelaysMs: [500, 1000, 2000],
} as const;

type CaptureSession = {
  connectionId: string | null;
  frameStarted: boolean;
  lastPacketSequence: number | null;
  rotationRequested: boolean;
  uploadPaused: boolean;
  journal: RecordingJournal | null;
  journalWork: Promise<void>;
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
        void capture.journalWork.then(release, release);
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
            const device = nativeSnapshotRef.current?.devices.find(
              item => item.id === capture.deviceId,
            );
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
                deviceId: capture.deviceId,
                deviceName: capture.deviceName ?? device?.name,
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
            capture.uploadPaused = true;
            if (capture.stopped) {
              releaseCaptureBuffer(capture, epoch);
              capturesRef.current.delete(capture);
            }
            setDeviceScanMessage(
              'Recording is saved on this device. Upload is paused; reopen the app online to recover it.',
            );
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
          capture.completed = true;
          try {
            await capture.journalWork;
            if (!current()) {
              return;
            }
            await retry(() => completeDeviceSession(backend, capture.id!));
          } catch {
            if (current()) {
              setDeviceScanMessage(
                'Audio was uploaded, but the recording could not be finalized. Its saved status is unconfirmed.',
              );
            }
            return;
          }
          if (!current()) {
            return;
          }
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
                  'Recording saved, but transcription failed. Open its transcript to retry.',
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
                  'Recording saved, but transcription could not finish. Open its transcript to retry.',
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
    [releaseCaptureBuffer],
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
      if (capture.uploadPaused) {
        try {
          await capture.journalWork;
          pendingBytesRef.current -= capture.bufferedBytes;
          capture.bufferedBytes = 0;
          capture.pending = [];
          capturesRef.current.delete(capture);
        } catch {
          failJournal(capture, epoch);
        }
      }
      if (capture.id !== null) {
        await work;
      }
    },
    [failJournal, processCapture],
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
          : bytesFromBase64(event.payloadBase64);
      const startsFrame = bytes !== null && bytes.length > 3 && bytes[2] === 0;
      const sequence =
        bytes !== null && bytes.length > 3
          ? bytes[0]! | (bytes[1]! << 8)
          : null;
      let capture = captureRef.current;
      if (
        capture !== null &&
        capture.rotationRequested &&
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
          connectionId: nativeSnapshotRef.current?.connectionId ?? null,
          frameStarted: false,
          lastPacketSequence: null,
          rotationRequested: false,
          uploadPaused: false,
          journal: null,
          journalWork: Promise.resolve(),
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
    },
    [finishSession],
  );

  useEffect(() => {
    let active = true;
    cancelledRef.current = false;
    setNativeSnapshot(null);
    setDeviceBusy(false);
    setDeviceScanMessage(null);
    const retireSession = () => {
      active = false;
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
              connectionId: null,
              frameStarted: false,
              lastPacketSequence: null,
              rotationRequested: false,
              uploadPaused: false,
              journal: restored.journal,
              journalWork: Promise.resolve(),
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
          await omiNative.disconnectDevice(id);
          if (!enabledRef.current || epoch !== epochRef.current) {
            return;
          }
          if (requestedDeviceRef.current === id) {
            requestedDeviceRef.current = null;
          }
          await finishSession();
        } else {
          await journalReadyRef.current;
          if (!enabledRef.current || epoch !== epochRef.current) {
            return;
          }
          requestedDeviceRef.current = id;
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
    [applySnapshot, finishSession],
  );

  return {
    deviceBusy,
    deviceScanMessage,
    nativeSnapshot,
    scanForOmi,
    toggleDevice,
  };
}
