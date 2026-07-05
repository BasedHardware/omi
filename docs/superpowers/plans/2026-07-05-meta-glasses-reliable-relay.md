# Meta Glasses Reliable Relay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Meta glasses capture reliable for near-term demo/use by treating the iPhone as an invisible camera relay, never a mic source, and making every captured frame durable in OMI history.

**Architecture:** Public DAT iOS 0.8 does not run OMI code on glasses. Glasses stream camera frames to iPhone DAT; iPhone relays frames to an OMI cache endpoint; OMI app history reads back cached photos. Reliability comes from strict session state, durable local queue, idempotent backend cache, watchdog reconnect, and visible diagnostics.

**Tech Stack:** Flutter/Dart app, iOS Swift DAT bridge, Meta Wearables DAT 0.8, FastAPI backend, existing `Env.apiBaseUrl`, Cloudflared/local proxy for demo.

---

## Non-Negotiable Contract

- Phone mic must never start from Meta glasses capture.
- Tap gesture must toggle start/stop capture only.
- Swipe must not pretend to work unless DAT display/gesture callback is real.
- Captured frames must survive app restart and connection restart.
- Backend/cache writes must be idempotent by `device_uuid + captured_at + frame_hash`.
- No GCP fork backend. Piggyback existing OMI API for normal calls.
- Local demo may use Cloudflared proxy, but production path must be the same API shape.

## File Structure

- Modify `app/lib/providers/meta_wearables_provider.dart`: DAT session state machine, capture loop, gesture truth, watchdog hooks.
- Modify `app/lib/services/capture/capture_controller.dart`: durable cache queue entrypoint and UI placeholder reconciliation.
- Modify `app/lib/backend/http/api/conversations.dart`: typed Meta photo-cache API client and idempotency metadata.
- Create `app/lib/services/meta_wearables/meta_capture_queue.dart`: persistent queue for frames waiting to be uploaded.
- Create `app/lib/services/meta_wearables/meta_capture_watchdog.dart`: reconnect/backoff policy.
- Create `app/lib/services/meta_wearables/meta_capture_diagnostics.dart`: in-app/debug state snapshot.
- Modify `app/ios/Runner/MetaWearablesBridge.swift` or current DAT bridge file: expose real stream/session/permission state and real gesture events only.
- Modify `backend/routers/conversations.py`: production cache endpoint.
- Modify `backend/routers/transcribe.py`: make websocket photo ack durable if still used by non-Meta paths.
- Modify `scripts/meta_wearables_demo_proxy.js`: keep local demo compatible with production endpoint.
- Test `app/test/unit/meta_glasses_runtime_regression_test.dart`: no phone mic/listen socket, no fake gestures.
- Test `app/test/unit/meta_glasses_relay_queue_test.dart`: durable queue, retry, idempotency.
- Test `app/test/unit/meta_glasses_watchdog_test.dart`: backoff and no restart while paused.
- Test `backend/tests/unit/test_listen_pipeline.py`: route and durable photo-store ordering.

---

### Task 1: Lock The Phone-Relay Contract

**Files:**
- Modify: `app/test/unit/meta_glasses_runtime_regression_test.dart`
- Modify: `app/lib/providers/meta_wearables_provider.dart`

- [ ] **Step 1: Write failing test for no phone audio/listen socket**

Append:

```dart
test('meta glasses capture never starts phone mic or listen websocket', () async {
  final source = File('lib/providers/meta_wearables_provider.dart').readAsStringSync();

  expect(source, isNot(contains('configureForBluetooth')));
  expect(source, isNot(contains('streamRecording(')));
  expect(source, isNot(contains('stopStreamRecording(')));
  expect(source, isNot(contains('_startMicRecording')));
  expect(source, contains('cacheCapturedImage'));
});
```

- [ ] **Step 2: Run red test**

Run:

```bash
cd app
flutter test test/unit/meta_glasses_runtime_regression_test.dart --plain-name 'meta glasses capture never starts phone mic or listen websocket'
```

Expected before fix: fail on a forbidden phone-audio symbol or missing `cacheCapturedImage`.

- [ ] **Step 3: Remove phone audio path from Meta provider**

In `app/lib/providers/meta_wearables_provider.dart`, the Meta capture start path must do only:

```dart
await _metaWearablesService.startCameraStream(
  frameRate: _captureFrameRate,
  resolution: _captureResolution,
);
_startCaptureLoop();
_startCaptureWatchdog();
```

Do not call audio-session methods. Do not call listen websocket methods.

- [ ] **Step 4: Run green test**

Run:

```bash
cd app
flutter test test/unit/meta_glasses_runtime_regression_test.dart --plain-name 'meta glasses capture never starts phone mic or listen websocket'
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/test/unit/meta_glasses_runtime_regression_test.dart app/lib/providers/meta_wearables_provider.dart
git commit -m "test: lock meta glasses no-phone-audio contract"
```

---

### Task 2: Add Durable Frame Queue

**Files:**
- Create: `app/lib/services/meta_wearables/meta_capture_queue.dart`
- Create: `app/test/unit/meta_glasses_relay_queue_test.dart`
- Modify: `app/lib/providers/meta_wearables_provider.dart`

- [ ] **Step 1: Write failing queue tests**

Create `app/test/unit/meta_glasses_relay_queue_test.dart`:

```dart
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/meta_wearables/meta_capture_queue.dart';

void main() {
  late Directory dir;
  late MetaCaptureQueue queue;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('meta_capture_queue_test_');
    queue = MetaCaptureQueue(rootDirectory: dir);
  });

  tearDown(() async {
    if (await dir.exists()) {
      await dir.delete(recursive: true);
    }
  });

  test('persists pending frames across queue recreation', () async {
    final first = await queue.enqueue(
      bytes: Uint8List.fromList(utf8.encode('frame-a')),
      capturedAt: DateTime.utc(2026, 7, 5, 1, 2, 3),
      deviceUuid: 'glasses-1',
      deviceName: 'Meta Glasses',
    );

    final reopened = MetaCaptureQueue(rootDirectory: dir);
    final pending = await reopened.pending(limit: 10);

    expect(pending, hasLength(1));
    expect(pending.single.id, first.id);
    expect(pending.single.deviceUuid, 'glasses-1');
    expect(pending.single.sha256, isNotEmpty);
  });

  test('markUploaded removes only matching frame', () async {
    final a = await queue.enqueue(
      bytes: Uint8List.fromList([1]),
      capturedAt: DateTime.utc(2026, 7, 5, 1),
      deviceUuid: 'glasses-1',
    );
    final b = await queue.enqueue(
      bytes: Uint8List.fromList([2]),
      capturedAt: DateTime.utc(2026, 7, 5, 2),
      deviceUuid: 'glasses-1',
    );

    await queue.markUploaded(a.id);
    final pending = await queue.pending(limit: 10);

    expect(pending.map((item) => item.id), [b.id]);
  });
}
```

- [ ] **Step 2: Run red tests**

Run:

```bash
cd app
flutter test test/unit/meta_glasses_relay_queue_test.dart
```

Expected: fail because `MetaCaptureQueue` does not exist.

- [ ] **Step 3: Implement queue**

Create `app/lib/services/meta_wearables/meta_capture_queue.dart`:

```dart
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

class MetaCaptureQueueItem {
  final String id;
  final String path;
  final DateTime capturedAt;
  final String? deviceUuid;
  final String? deviceName;
  final String sha256;

  const MetaCaptureQueueItem({
    required this.id,
    required this.path,
    required this.capturedAt,
    required this.sha256,
    this.deviceUuid,
    this.deviceName,
  });

  Map<String, dynamic> toJson() => {
        'id': id,
        'path': path,
        'captured_at': capturedAt.toUtc().toIso8601String(),
        'device_uuid': deviceUuid,
        'device_name': deviceName,
        'sha256': sha256,
      };

  static MetaCaptureQueueItem fromJson(Map<String, dynamic> json) {
    return MetaCaptureQueueItem(
      id: json['id'] as String,
      path: json['path'] as String,
      capturedAt: DateTime.parse(json['captured_at'] as String),
      deviceUuid: json['device_uuid'] as String?,
      deviceName: json['device_name'] as String?,
      sha256: json['sha256'] as String,
    );
  }
}

class MetaCaptureQueue {
  final Directory rootDirectory;

  MetaCaptureQueue({required this.rootDirectory});

  Directory get _framesDirectory => Directory('${rootDirectory.path}/meta_capture_frames');
  File get _indexFile => File('${rootDirectory.path}/meta_capture_queue.jsonl');

  Future<MetaCaptureQueueItem> enqueue({
    required Uint8List bytes,
    required DateTime capturedAt,
    String? deviceUuid,
    String? deviceName,
  }) async {
    await _framesDirectory.create(recursive: true);
    await rootDirectory.create(recursive: true);

    final digest = sha256.convert(bytes).toString();
    final id = 'meta_${capturedAt.toUtc().microsecondsSinceEpoch}_$digest';
    final frameFile = File('${_framesDirectory.path}/$id.jpg');
    await frameFile.writeAsBytes(bytes, flush: true);

    final item = MetaCaptureQueueItem(
      id: id,
      path: frameFile.path,
      capturedAt: capturedAt.toUtc(),
      deviceUuid: deviceUuid,
      deviceName: deviceName,
      sha256: digest,
    );
    await _indexFile.writeAsString('${jsonEncode(item.toJson())}\n', mode: FileMode.append, flush: true);
    return item;
  }

  Future<List<MetaCaptureQueueItem>> pending({int limit = 100}) async {
    if (!await _indexFile.exists()) return [];
    final uploaded = await _uploadedIds();
    final lines = await _indexFile.readAsLines();
    final items = <MetaCaptureQueueItem>[];
    for (final line in lines) {
      if (line.trim().isEmpty) continue;
      final item = MetaCaptureQueueItem.fromJson(jsonDecode(line) as Map<String, dynamic>);
      if (uploaded.contains(item.id)) continue;
      if (!await File(item.path).exists()) continue;
      items.add(item);
      if (items.length >= limit) break;
    }
    items.sort((a, b) => a.capturedAt.compareTo(b.capturedAt));
    return items;
  }

  Future<void> markUploaded(String id) async {
    final uploadedFile = File('${rootDirectory.path}/meta_capture_uploaded.txt');
    await uploadedFile.writeAsString('$id\n', mode: FileMode.append, flush: true);
  }

  Future<Set<String>> _uploadedIds() async {
    final uploadedFile = File('${rootDirectory.path}/meta_capture_uploaded.txt');
    if (!await uploadedFile.exists()) return {};
    return (await uploadedFile.readAsLines()).where((line) => line.trim().isNotEmpty).toSet();
  }
}
```

- [ ] **Step 4: Run green tests**

Run:

```bash
cd app
dart format --line-length 120 lib/services/meta_wearables/meta_capture_queue.dart test/unit/meta_glasses_relay_queue_test.dart
flutter test test/unit/meta_glasses_relay_queue_test.dart
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/lib/services/meta_wearables/meta_capture_queue.dart app/test/unit/meta_glasses_relay_queue_test.dart
git commit -m "feat: add durable meta capture queue"
```

---

### Task 3: Upload Queue To Cache Endpoint

**Files:**
- Modify: `app/lib/backend/http/api/conversations.dart`
- Modify: `app/lib/services/capture/capture_controller.dart`
- Modify: `app/lib/providers/meta_wearables_provider.dart`
- Modify: `app/test/unit/meta_glasses_relay_queue_test.dart`

- [ ] **Step 1: Write failing upload metadata test**

Append:

```dart
test('cache upload payload includes idempotency metadata', () async {
  final source = File('lib/backend/http/api/conversations.dart').readAsStringSync();

  expect(source, contains('device_uuid'));
  expect(source, contains('frame_sha256'));
  expect(source, contains('captured_at'));
  expect(source, contains('conversation_id'));
});
```

- [ ] **Step 2: Run red test**

Run:

```bash
cd app
flutter test test/unit/meta_glasses_relay_queue_test.dart --plain-name 'cache upload payload includes idempotency metadata'
```

Expected: fail until `frame_sha256` is in payload.

- [ ] **Step 3: Extend API client**

In `app/lib/backend/http/api/conversations.dart`, ensure:

```dart
Future<MetaWearablesPhotoCacheResult?> cacheMetaWearablesPhoto(
  Uint8List imageBytes, {
  required DateTime capturedAt,
  String? conversationId,
  String? deviceUuid,
  String? deviceName,
  String? frameSha256,
}) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/meta-wearables/photos/cache',
    headers: await getAuthHeaders(),
    body: jsonEncode({
      'base64': base64Encode(imageBytes),
      'captured_at': capturedAt.toUtc().toIso8601String(),
      if (conversationId != null) 'conversation_id': conversationId,
      if (deviceUuid != null) 'device_uuid': deviceUuid,
      if (deviceName != null) 'device_name': deviceName,
      if (frameSha256 != null) 'frame_sha256': frameSha256,
    }),
  );
  if (response == null || response.statusCode < 200 || response.statusCode >= 300) return null;
  return MetaWearablesPhotoCacheResult.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}
```

- [ ] **Step 4: Use queue in provider**

In `app/lib/providers/meta_wearables_provider.dart`, frame capture path must:

```dart
final queued = await _captureQueue.enqueue(
  bytes: bytes,
  capturedAt: capturedAt,
  deviceUuid: _connectedDeviceUuid,
  deviceName: _connectedDeviceName,
);
await _flushCaptureQueue();
```

Flush:

```dart
Future<void> _flushCaptureQueue() async {
  final pending = await _captureQueue.pending(limit: 25);
  for (final item in pending) {
    final bytes = await File(item.path).readAsBytes();
    final ok = await _captureController.cacheCapturedImage(
      bytes,
      capturedAt: item.capturedAt,
      conversationId: _metaWearablesCaptureConversationId,
      deviceUuid: item.deviceUuid,
      deviceName: item.deviceName,
      frameSha256: item.sha256,
    );
    if (!ok) return;
    await _captureQueue.markUploaded(item.id);
  }
}
```

- [ ] **Step 5: Run green tests**

Run:

```bash
cd app
dart format --line-length 120 lib/backend/http/api/conversations.dart lib/providers/meta_wearables_provider.dart lib/services/capture/capture_controller.dart test/unit/meta_glasses_relay_queue_test.dart
flutter test test/unit/meta_glasses_relay_queue_test.dart
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/lib/backend/http/api/conversations.dart app/lib/services/capture/capture_controller.dart app/lib/providers/meta_wearables_provider.dart app/test/unit/meta_glasses_relay_queue_test.dart
git commit -m "feat: upload meta capture queue to cache endpoint"
```

---

### Task 4: Make Backend Cache Idempotent

**Files:**
- Modify: `backend/routers/conversations.py`
- Modify: `backend/tests/unit/test_listen_pipeline.py`

- [ ] **Step 1: Write failing backend source contract**

Append to `backend/tests/unit/test_listen_pipeline.py`:

```python
def test_meta_wearables_photo_cache_is_idempotent_by_frame_hash():
    source = Path('routers/conversations.py').read_text()

    assert 'frame_sha256' in source
    assert 'device_uuid' in source
    assert 'get_cached_meta_wearables_photo' in source or 'existing_photo_id' in source
    assert 'store_conversation_photos' in source
```

- [ ] **Step 2: Run red test**

Run:

```bash
cd backend
uv run --with pytest pytest tests/unit/test_listen_pipeline.py::test_meta_wearables_photo_cache_is_idempotent_by_frame_hash -q
```

Expected: fail until endpoint checks idempotency.

- [ ] **Step 3: Add request field**

In `backend/routers/conversations.py`:

```python
class MetaWearablesPhotoCacheRequest(BaseModel):
    base64: str
    captured_at: Optional[datetime] = None
    conversation_id: Optional[str] = None
    device_uuid: Optional[str] = None
    device_name: Optional[str] = None
    frame_sha256: Optional[str] = None
```

- [ ] **Step 4: Add deterministic photo id**

Inside endpoint:

```python
photo_basis = f'{uid}:{request.device_uuid or ""}:{request.captured_at.isoformat()}:{request.frame_sha256 or ""}'
photo_id = f'meta_{uuid.uuid5(uuid.NAMESPACE_URL, photo_basis)}'
```

Before storing:

```python
existing_photo_id = photo_id
existing_photos = conversations_db.get_conversation_photos(uid, conversation_id)
if any(photo.id == existing_photo_id for photo in existing_photos):
    return MetaWearablesPhotoCacheResponse(conversation_id=conversation_id, photo_id=existing_photo_id)
```

- [ ] **Step 5: Run backend tests**

Run:

```bash
cd backend
uv run --with black black --line-length 120 --skip-string-normalization routers/conversations.py tests/unit/test_listen_pipeline.py
uv run --with pytest pytest tests/unit/test_listen_pipeline.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/conversations.py backend/tests/unit/test_listen_pipeline.py
git commit -m "feat: make meta photo cache idempotent"
```

---

### Task 5: Fix DAT Session Watchdog

**Files:**
- Create: `app/lib/services/meta_wearables/meta_capture_watchdog.dart`
- Create: `app/test/unit/meta_glasses_watchdog_test.dart`
- Modify: `app/lib/providers/meta_wearables_provider.dart`

- [ ] **Step 1: Write failing watchdog tests**

Create `app/test/unit/meta_glasses_watchdog_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/meta_wearables/meta_capture_watchdog.dart';

void main() {
  test('does not restart while DAT session is paused', () {
    final watchdog = MetaCaptureWatchdog();

    expect(watchdog.nextAction(MetaCaptureHealth.paused), MetaCaptureWatchdogAction.wait);
  });

  test('backs off repeated stopped states', () {
    final watchdog = MetaCaptureWatchdog();

    expect(watchdog.nextDelay(MetaCaptureHealth.stopped), const Duration(seconds: 1));
    watchdog.recordRestartAttempt();
    expect(watchdog.nextDelay(MetaCaptureHealth.stopped), const Duration(seconds: 2));
    watchdog.recordRestartAttempt();
    expect(watchdog.nextDelay(MetaCaptureHealth.stopped), const Duration(seconds: 4));
  });
}
```

- [ ] **Step 2: Run red tests**

Run:

```bash
cd app
flutter test test/unit/meta_glasses_watchdog_test.dart
```

Expected: fail because watchdog does not exist.

- [ ] **Step 3: Implement watchdog**

Create `app/lib/services/meta_wearables/meta_capture_watchdog.dart`:

```dart
enum MetaCaptureHealth { streaming, paused, stopped, stale }

enum MetaCaptureWatchdogAction { wait, restart }

class MetaCaptureWatchdog {
  int _attempts = 0;

  MetaCaptureWatchdogAction nextAction(MetaCaptureHealth health) {
    switch (health) {
      case MetaCaptureHealth.streaming:
      case MetaCaptureHealth.paused:
        return MetaCaptureWatchdogAction.wait;
      case MetaCaptureHealth.stopped:
      case MetaCaptureHealth.stale:
        return MetaCaptureWatchdogAction.restart;
    }
  }

  Duration nextDelay(MetaCaptureHealth health) {
    if (health == MetaCaptureHealth.paused || health == MetaCaptureHealth.streaming) {
      return Duration.zero;
    }
    final seconds = 1 << _attempts.clamp(0, 5);
    return Duration(seconds: seconds);
  }

  void recordRestartAttempt() {
    _attempts += 1;
  }

  void recordHealthyFrame() {
    _attempts = 0;
  }
}
```

- [ ] **Step 4: Wire provider**

In provider:

```dart
if (_watchdog.nextAction(health) == MetaCaptureWatchdogAction.restart) {
  await Future<void>.delayed(_watchdog.nextDelay(health));
  _watchdog.recordRestartAttempt();
  await _restartDatCameraSession(reason: 'watchdog_$health');
}
```

Never restart if DAT session state is `paused`.

- [ ] **Step 5: Run green tests**

Run:

```bash
cd app
dart format --line-length 120 lib/services/meta_wearables/meta_capture_watchdog.dart test/unit/meta_glasses_watchdog_test.dart
flutter test test/unit/meta_glasses_watchdog_test.dart
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/lib/services/meta_wearables/meta_capture_watchdog.dart app/test/unit/meta_glasses_watchdog_test.dart app/lib/providers/meta_wearables_provider.dart
git commit -m "feat: add meta capture watchdog"
```

---

### Task 6: Stop Fake Gestures

**Files:**
- Modify: `app/lib/providers/meta_wearables_provider.dart`
- Modify: `app/ios/Runner/MetaWearablesBridge.swift`
- Modify: `app/test/unit/meta_glasses_runtime_regression_test.dart`

- [ ] **Step 1: Write failing gesture truth test**

Append:

```dart
test('meta gestures use native DAT events only', () {
  final provider = File('lib/providers/meta_wearables_provider.dart').readAsStringSync();
  final bridge = File('ios/Runner/MetaWearablesBridge.swift').readAsStringSync();

  expect(provider, isNot(contains('volume')));
  expect(provider, isNot(contains('fakeGesture')));
  expect(bridge, contains('gesture'));
});
```

- [ ] **Step 2: Run red test**

Run:

```bash
cd app
flutter test test/unit/meta_glasses_runtime_regression_test.dart --plain-name 'meta gestures use native DAT events only'
```

Expected: fail if provider still uses volume/button fake gesture path.

- [ ] **Step 3: Make tap only real start/stop**

Provider behavior:

```dart
Future<void> onMetaGesture(MetaGestureEvent event) async {
  if (event.kind != MetaGestureKind.tap) return;
  if (isCapturing) {
    await stopCapture(reason: 'glasses_tap');
  } else {
    await startCapture(reason: 'glasses_tap');
  }
}
```

Swipe behavior:

```dart
if (event.kind == MetaGestureKind.swipe) {
  _diagnostics.recordIgnoredGesture('swipe_not_supported_by_current_dat_bridge');
  return;
}
```

- [ ] **Step 4: Run green test**

Run:

```bash
cd app
flutter test test/unit/meta_glasses_runtime_regression_test.dart --plain-name 'meta gestures use native DAT events only'
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/lib/providers/meta_wearables_provider.dart app/ios/Runner/MetaWearablesBridge.swift app/test/unit/meta_glasses_runtime_regression_test.dart
git commit -m "fix: use only real meta gesture events"
```

---

### Task 7: Add Diagnostics Screen/Log Snapshot

**Files:**
- Create: `app/lib/services/meta_wearables/meta_capture_diagnostics.dart`
- Modify: `app/lib/providers/meta_wearables_provider.dart`
- Test: `app/test/unit/meta_glasses_runtime_regression_test.dart`

- [ ] **Step 1: Write failing diagnostics test**

Append:

```dart
test('meta capture diagnostics expose relay health fields', () {
  final source = File('lib/services/meta_wearables/meta_capture_diagnostics.dart').readAsStringSync();

  expect(source, contains('lastFrameAt'));
  expect(source, contains('pendingQueueCount'));
  expect(source, contains('lastUploadStatus'));
  expect(source, contains('streamState'));
  expect(source, contains('sessionState'));
});
```

- [ ] **Step 2: Run red test**

Run:

```bash
cd app
flutter test test/unit/meta_glasses_runtime_regression_test.dart --plain-name 'meta capture diagnostics expose relay health fields'
```

Expected: fail because diagnostics file is missing.

- [ ] **Step 3: Implement diagnostics model**

Create `app/lib/services/meta_wearables/meta_capture_diagnostics.dart`:

```dart
class MetaCaptureDiagnostics {
  final DateTime? lastFrameAt;
  final DateTime? lastUploadAt;
  final String? lastUploadStatus;
  final String? streamState;
  final String? sessionState;
  final int pendingQueueCount;
  final int uploadedCount;
  final int failedUploadCount;

  const MetaCaptureDiagnostics({
    this.lastFrameAt,
    this.lastUploadAt,
    this.lastUploadStatus,
    this.streamState,
    this.sessionState,
    this.pendingQueueCount = 0,
    this.uploadedCount = 0,
    this.failedUploadCount = 0,
  });

  Map<String, dynamic> toJson() => {
        'lastFrameAt': lastFrameAt?.toIso8601String(),
        'lastUploadAt': lastUploadAt?.toIso8601String(),
        'lastUploadStatus': lastUploadStatus,
        'streamState': streamState,
        'sessionState': sessionState,
        'pendingQueueCount': pendingQueueCount,
        'uploadedCount': uploadedCount,
        'failedUploadCount': failedUploadCount,
      };
}
```

- [ ] **Step 4: Log diagnostics on state changes**

Provider:

```dart
Logger.debug('Meta capture diagnostics: ${_diagnostics.toJson()}');
```

Log on:
- stream state change
- session state change
- frame enqueued
- upload success
- upload failure
- watchdog restart

- [ ] **Step 5: Run green test**

Run:

```bash
cd app
dart format --line-length 120 lib/services/meta_wearables/meta_capture_diagnostics.dart test/unit/meta_glasses_runtime_regression_test.dart
flutter test test/unit/meta_glasses_runtime_regression_test.dart --plain-name 'meta capture diagnostics expose relay health fields'
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/lib/services/meta_wearables/meta_capture_diagnostics.dart app/lib/providers/meta_wearables_provider.dart app/test/unit/meta_glasses_runtime_regression_test.dart
git commit -m "feat: expose meta capture diagnostics"
```

---

### Task 8: Local Demo Harness With Cloudflared

**Files:**
- Modify: `scripts/meta_wearables_demo_proxy.js`
- Create: `scripts/run-meta-demo-relay.sh`
- Test: `app/test/unit/meta_glasses_relay_queue_test.dart`

- [ ] **Step 1: Write failing source contract**

Append:

```dart
test('local demo script starts proxy and cloudflared', () {
  final source = File('../scripts/run-meta-demo-relay.sh').readAsStringSync();

  expect(source, contains('meta_wearables_demo_proxy.js'));
  expect(source, contains('cloudflared tunnel --url'));
  expect(source, contains('API_BASE_URL='));
});
```

- [ ] **Step 2: Run red test**

Run:

```bash
cd app
flutter test test/unit/meta_glasses_relay_queue_test.dart --plain-name 'local demo script starts proxy and cloudflared'
```

Expected: fail because script does not exist.

- [ ] **Step 3: Create demo runner**

Create `scripts/run-meta-demo-relay.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8787}"
STATE="${OMI_META_DEMO_STATE:-/tmp/omi-meta-demo-cache.json}"
LOG="${OMI_META_DEMO_LOG:-/tmp/omi-meta-demo-relay.log}"

command -v node >/dev/null
command -v cloudflared >/dev/null

pkill -f "meta_wearables_demo_proxy.js" 2>/dev/null || true
pkill -f "cloudflared tunnel --url http://127.0.0.1:${PORT}" 2>/dev/null || true

PORT="$PORT" OMI_META_DEMO_STATE="$STATE" node "$ROOT/scripts/meta_wearables_demo_proxy.js" >"$LOG" 2>&1 &
PROXY_PID=$!

cloudflared tunnel --url "http://127.0.0.1:${PORT}" --no-autoupdate 2>&1 | tee -a "$LOG" &
TUNNEL_PID=$!

echo "proxy_pid=$PROXY_PID"
echo "cloudflared_pid=$TUNNEL_PID"
echo "log=$LOG"
echo "Set app/.dev.env API_BASE_URL to the printed trycloudflare URL, then regenerate env and build."
wait "$TUNNEL_PID"
```

- [ ] **Step 4: Run green source test**

Run:

```bash
chmod +x scripts/run-meta-demo-relay.sh
cd app
flutter test test/unit/meta_glasses_relay_queue_test.dart --plain-name 'local demo script starts proxy and cloudflared'
```

Expected: pass.

- [ ] **Step 5: Smoke tunnel**

Run:

```bash
scripts/run-meta-demo-relay.sh
```

Expected: prints `trycloudflare.com` URL.

In another shell:

```bash
node -e "fetch('https://YOUR.trycloudflare.com/health').then(r=>r.text()).then(console.log)"
```

Expected: JSON with `"ok":true`.

- [ ] **Step 6: Commit**

```bash
git add scripts/meta_wearables_demo_proxy.js scripts/run-meta-demo-relay.sh app/test/unit/meta_glasses_relay_queue_test.dart
git commit -m "chore: add meta glasses local demo relay"
```

---

### Task 9: Real Device Verification

**Files:**
- Modify only if failures are found.

- [ ] **Step 1: Build app against tunnel**

Run:

```bash
cd app
dart run build_runner clean
dart run build_runner build --delete-conflicting-outputs
flutter build ios --profile --flavor dev -t lib/main.dart --no-pub
```

Expected: `Built build/ios/iphoneos/Runner.app`.

- [ ] **Step 2: Install EddyPhone**

Run:

```bash
cd app
xcrun devicectl device install app --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F build/ios/iphoneos/Runner.app
xcrun devicectl device process launch --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F dev.moni11811.omi
```

Expected: installed and launched.

- [ ] **Step 3: Capture with glasses for 60 seconds**

Expected:
- no snapshot sound loop
- no phone mic recording state
- proxy log shows `cache post`
- `/tmp/omi-meta-demo-cache.json` photo count increases
- app conversation list shows `Meta Glasses Demo`

- [ ] **Step 4: Kill and restart app**

Run:

```bash
xcrun devicectl device process signal --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F --signal 9 dev.moni11811.omi || true
xcrun devicectl device process launch --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F dev.moni11811.omi
```

Expected:
- queued frames flush after restart
- no authorization loop unless Meta AI revoked registration
- diagnostics show queue count falling to zero.

- [ ] **Step 5: Commit verification notes**

Create `docs/meta-wearables/reliable-relay-verification-2026-07-05.md`:

```markdown
# Meta Reliable Relay Verification 2026-07-05

- Device: EddyPhone
- Bundle: dev.moni11811.omi
- API base:
- Tunnel:
- Captured duration:
- Proxy cache count before:
- Proxy cache count after:
- Phone mic started: no
- Authorization loop seen: no
- App history showed local Meta conversation: yes
- Known remaining issue:
```

Commit:

```bash
git add docs/meta-wearables/reliable-relay-verification-2026-07-05.md
git commit -m "docs: record meta reliable relay verification"
```

---

## Validation Matrix

- Focused app tests:

```bash
cd app
flutter test test/unit/meta_glasses_runtime_regression_test.dart test/unit/meta_glasses_relay_queue_test.dart test/unit/meta_glasses_watchdog_test.dart
```

- App static check:

```bash
cd app
flutter analyze lib/providers/meta_wearables_provider.dart lib/services/meta_wearables lib/services/capture/capture_controller.dart lib/backend/http/api/conversations.dart
```

- Backend focused tests:

```bash
cd backend
uv run --with pytest pytest tests/unit/test_listen_pipeline.py -q
```

- Real device:

```bash
cd app
flutter build ios --profile --flavor dev -t lib/main.dart --no-pub
xcrun devicectl device install app --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F build/ios/iphoneos/Runner.app
```

## Self-Review

- Spec coverage: covers no-phone-audio, phone relay, durable history, restart reliability, fake gesture removal, local demo, backend cache.
- Placeholder scan: no `TBD`, no vague "handle edge cases" steps.
- Type consistency: queue item uses `sha256`; API payload uses `frame_sha256`; backend request uses `frame_sha256`.

## Stop Conditions

- Stop and report if DAT does not expose real gesture events in current native bridge.
- Stop and report if iOS background execution prevents sustained camera relay while app is backgrounded.
- Stop and report if existing OMI backend cannot accept the cache endpoint and local proxy is the only working target.
