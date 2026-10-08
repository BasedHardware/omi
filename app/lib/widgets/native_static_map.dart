import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/widgets/omi_map_preview.dart';

/// The largest PNG a native map row receives.
const int kNativeStaticMapMaxBytes = 16 * 1024 * 1024;

const _fetchTimeout = Duration(seconds: 30);
const _filePrefix = 'omi_native_map_';
int _lastStamp = 0;

/// Builds the image provider that loads the static map. Production uses the same
/// [CachedNetworkImageProvider] path as [OmiMapPreview], so both share one cache and no new client.
typedef NativeStaticMapImageProvider = ImageProvider Function(String url, Map<String, String> headers);

/// The signature of [resolveNativeStaticMapFile], injectable where a page fetches a map.
typedef NativeStaticMapResolver = Future<String?> Function({
  required List<OmiMapPin> pins,
  required int width,
  required int height,
  required Brightness brightness,
  required bool Function() current,
});

/// Fetches the static map for [pins] through the app's authenticated proxy and writes it as a
/// temporary PNG for a native image row. Native code never fetches `/v1/static-map` itself, because
/// the request carries the app's Authorization header; it only receives this file.
///
/// Answers the file URI, or null when there is nothing to show (no pins, no session, a failed or
/// oversized image). Whenever [current] turns false the work is abandoned, and a file already
/// written is deleted. The caller owns the returned file and deletes it with
/// [deleteNativeStaticMapFile] on dispose, on a brightness or session change, and when it arrives
/// after the caller stopped wanting it. Coordinates are never logged.
Future<String?> resolveNativeStaticMapFile({
  required List<OmiMapPin> pins,
  required int width,
  required int height,
  required Brightness brightness,
  required bool Function() current,
  @visibleForTesting OmiMapAuthHeaderResolver? authHeaderProvider,
  @visibleForTesting NativeStaticMapImageProvider? imageProvider,
  @visibleForTesting Future<Directory> Function()? directory,
}) async {
  if (normalizeOmiMapPins(pins).isEmpty || width <= 0 || height <= 0) return null;
  File? file;
  try {
    final header = await (authHeaderProvider ?? getAuthHeader)();
    if (!current() || header == null || header.isEmpty) return null;
    final url = buildOmiStaticMapUrl(pins: pins, width: width, height: height, brightness: brightness);
    final provider = (imageProvider ?? _cachedImage)(url, {'Authorization': header});
    final bytes = await _pngBytes(provider);
    if (!current() || bytes == null || bytes.isEmpty || bytes.length > kNativeStaticMapMaxBytes) return null;
    final folder = await (directory ?? getTemporaryDirectory)();
    if (!current()) return null;
    _lastStamp = math.max(DateTime.now().microsecondsSinceEpoch, _lastStamp + 1);
    file = File('${folder.path}/$_filePrefix$_lastStamp.png');
    await file.writeAsBytes(bytes, flush: true);
    if (!current()) {
      await _delete(file);
      return null;
    }
    return Uri.file(file.path).toString();
  } catch (_) {
    if (file != null) await _delete(file);
    return null;
  }
}

/// Deletes a file [resolveNativeStaticMapFile] wrote. Anything else is left alone.
Future<void> deleteNativeStaticMapFile(String? uri) async {
  if (uri == null) return;
  try {
    final parsed = Uri.parse(uri);
    if (parsed.scheme != 'file' || parsed.pathSegments.isEmpty) return;
    if (!parsed.pathSegments.last.startsWith(_filePrefix)) return;
    await _delete(File(parsed.toFilePath()));
  } catch (_) {/* Not a file this owner wrote. */}
}

Future<void> _delete(File file) async {
  try {
    if (await file.exists()) await file.delete();
  } catch (_) {/* Temporary file already reclaimed. */}
}

ImageProvider _cachedImage(String url, Map<String, String> headers) =>
    CachedNetworkImageProvider(url, headers: headers);

Future<Uint8List?> _pngBytes(ImageProvider provider) async {
  final stream = provider.resolve(ImageConfiguration.empty);
  final ready = Completer<ui.Image>();
  final listener = ImageStreamListener((info, _) {
    if (!ready.isCompleted) ready.complete(info.image.clone());
    info.dispose();
  }, onError: (Object error, StackTrace? stack) {
    if (!ready.isCompleted) ready.completeError(error, stack);
  });
  stream.addListener(listener);
  ui.Image? image;
  try {
    image = await ready.future.timeout(_fetchTimeout);
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    return data?.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
  } finally {
    stream.removeListener(listener);
    image?.dispose();
  }
}

/// The one temporary static-map file a native presentation shows, with its cleanup.
///
/// [show] fetches the map for a set of pins, a size and a brightness; asking again for the same
/// map does nothing, and asking for a different one (a brightness change, say) deletes the current
/// file first. A fetch that completes after a newer request, after [dispose] or after an account
/// session change is discarded and its file deleted. A session change also deletes the current file
/// and stops fetching for good: the native surface of the previous owner never shows again.
class NativeStaticMap extends ChangeNotifier {
  NativeStaticMap({NativeStaticMapResolver? resolver}) : _resolver = resolver ?? resolveNativeStaticMapFile {
    _session = AuthService.instance.sessionGenerationEvents.listen((_) {
      if (_ended || _sessionCurrent()) return;
      _ended = true;
      _withdraw();
      notifyListeners();
    });
  }

  /// The account session this map belongs to.
  final _owner = AuthService.instance.captureSessionSnapshot();
  final NativeStaticMapResolver _resolver;
  late final StreamSubscription<int> _session;
  String? _key;
  String? _uri;
  int _generation = 0;
  bool _loading = false;
  bool _ended = false;
  bool _disposed = false;

  /// The current map file, once fetched.
  String? get uri => _uri;

  /// The latest request is still being fetched.
  bool get loading => _loading;

  /// The latest request completed without a map.
  bool get failed => _key != null && !_loading && _uri == null;

  /// Fetches the map unless it is already current. Safe to call from build: it never notifies
  /// synchronously.
  void show({required List<OmiMapPin> pins, required int width, required int height, required Brightness brightness}) {
    if (_disposed || _ended || !_sessionCurrent()) return;
    // A non-finite coordinate can never be drawn; it is dropped rather than sent to the proxy.
    final normalized = normalizeOmiMapPins([
      for (final pin in pins)
        if (pin.latitude.isFinite && pin.longitude.isFinite) pin
    ]);
    final key = [
      for (final pin in normalized) '${pin.latitude},${pin.longitude}',
      '${width}x$height',
      brightness.name,
    ].join('|');
    if (key == _key) return;
    _withdraw();
    _key = key;
    _loading = true;
    final generation = _generation;
    bool current() => !_disposed && !_ended && generation == _generation && _sessionCurrent();
    unawaited(_resolver(pins: normalized, width: width, height: height, brightness: brightness, current: current)
        .catchError((Object _) => null)
        .then((value) async {
      if (!current()) {
        await deleteNativeStaticMapFile(value);
        return;
      }
      _uri = value;
      _loading = false;
      notifyListeners();
    }));
  }

  bool _sessionCurrent() {
    final owner = _owner;
    return owner != null && AuthService.instance.isSessionSnapshotCurrent(owner);
  }

  /// Abandons the current request and deletes the current file.
  void _withdraw() {
    _generation++;
    final uri = _uri;
    _uri = null;
    _key = null;
    _loading = false;
    unawaited(deleteNativeStaticMapFile(uri));
  }

  @override
  void dispose() {
    _disposed = true;
    _withdraw();
    unawaited(_session.cancel());
    super.dispose();
  }
}
