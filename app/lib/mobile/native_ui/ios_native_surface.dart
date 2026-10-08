import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'ios_native_home.dart';
import 'ios_native_secret.dart';
import 'native_read_session.dart';
import 'native_navigation_chrome.dart';

typedef NativeAction = FutureOr<void> Function(Object? value);

/// The preview flag, or the debug-only hermetic test host ([IosNativeSurface.debugNativeHostForTest]).
/// Release and profile builds reduce this to [iosSwiftUiEnabled].
bool get nativePresentationEnabled => iosSwiftUiEnabled || IosNativeSurface.debugNativeHostForTest;

/// [supportsIosSwiftUi], or true on the debug-only hermetic test host. Flag-off and Android builds
/// answer false without touching a channel.
Future<bool> supportsNativePresentation() async =>
    IosNativeSurface.debugNativeHostForTest || await supportsIosSwiftUi();

/// The snapshot version Swift decodes; a debug host test may publish an unsupported one on purpose.
int get nativeSnapshotVersion => kDebugMode && IosNativeSurface._debugCorruptSnapshot ? 2 : 1;

/// Captures the currently visible native presentation for an explicit share action.
/// No image is cached here; the existing share owner retains its file and privacy lifecycle.
class NativeSurfaceController {
  Future<Uint8List?> Function()? _capture;

  Future<Uint8List?> captureImage() async => _capture?.call();
}

/// Normalize thumbnails already supplied by the existing image/file owner. Unsupported URLs
/// render without a thumbnail; they do not introduce another authenticated API client.
String? nativeImageUri(String? input) {
  if (input == null || input.isEmpty || input.length > 4096) return null;
  final value = input.startsWith('/') ? Uri.file(input).toString() : input;
  if (value.length > 4096) return null;
  final uri = Uri.tryParse(value);
  if (uri == null || uri.userInfo.isNotEmpty) return null;
  if (uri.scheme == 'https' && uri.host.isNotEmpty) return value;
  if (uri.scheme == 'file' && uri.host.isEmpty && uri.path.startsWith('/')) return value;
  return null;
}

/// Only presentation values cross the channel. Callbacks stay with their current owner.
class NativeRow {
  const NativeRow(
    this.id,
    this.title, {
    this.kind = 'button',
    this.subtitle = '',
    this.value,
    this.options = const {},
    this.symbol,
    this.minimumDate,
    this.maximumLength,
    this.keyboard,
    this.optionSearch,
    this.optionClose,
    this.keypadMode,
    this.eraseLabel,
    this.clearLabel,
    this.plainText = false,
    this.imageUri,
    this.level,
    this.maximumValue,
    this.points = const [],
    this.blocks = const [],
    this.action,
    this.onVisible,
    this.onHidden,
    this.destructive = false,
    this.enabled = true,
  });

  final String id, title, kind, subtitle;
  final String? symbol, minimumDate;
  final String? imageUri;
  final int? maximumLength;
  final String? keyboard;
  final String? optionSearch, optionClose;
  final String? keypadMode, eraseLabel, clearLabel;
  final bool plainText;

  /// The existing three-band confidence meter; never a probability or a new score.
  final int? level;
  final double? maximumValue;
  final List<Map<String, Object>> points;
  final List<Map<String, Object>> blocks;
  final Object? value;
  final Map<String, String> options;
  final NativeAction? action, onVisible, onHidden;
  final bool destructive, enabled;

  Map<String, Object?> get projection => {
        'id': id,
        'title': title,
        'kind': kind,
        'subtitle': subtitle,
        'value': value,
        'options': [
          for (final entry in options.entries) {'id': entry.key, 'title': entry.value},
        ],
        'symbol': symbol,
        'minimumDate': minimumDate,
        'maximumLength': maximumLength,
        'keyboard': keyboard,
        'optionSearch': optionSearch,
        'optionClose': optionClose,
        'keypadMode': keypadMode,
        'eraseLabel': eraseLabel,
        'clearLabel': clearLabel,
        'plainText': plainText,
        'imageUri': imageUri,
        'level': level,
        'maximumValue': maximumValue,
        'points': points,
        'blocks': blocks,
        'destructive': destructive,
        'enabled': enabled && action != null,
        'visibilityEnabled': onVisible != null,
        'visibilityHiddenEnabled': onHidden != null,
      };

  bool get valid {
    if (blocks.isNotEmpty &&
        (kind != 'rich_text' ||
            blocks.any((block) =>
                !['text', 'heading', 'quote', 'code', 'table', 'image', 'rule'].contains(block['kind']) ||
                block['text'] is! String ||
                block['indent'] is! int ||
                (block['indent'] as int) < 0 ||
                (block['indent'] as int) > 32 ||
                block['prefix'] is! String ||
                block['kind'] == 'heading' &&
                    (block['level'] is! int || (block['level'] as int) < 1 || (block['level'] as int) > 6) ||
                block['kind'] == 'table' &&
                    (block['cells'] is! List<List<String>> ||
                        (block['cells'] as List<List<String>>).any((row) => row.isEmpty)) ||
                block['kind'] == 'image' &&
                    (block['uri'] is! String || nativeImageUri(block['uri'] as String) == null)))) {
      return false;
    }
    if (id.isEmpty || id.startsWith('_') || options.keys.any((id) => id.isEmpty)) return false;
    if (plainText && !['message_ai', 'message_user'].contains(kind)) return false;
    if (kind != 'keypad' && (keypadMode != null || eraseLabel != null || clearLabel != null)) return false;
    if (level != null && (level! < 0 || level! > 3)) return false;
    if (maximumValue != null &&
        (!['slider', 'progress', 'image'].contains(kind) || !maximumValue!.isFinite || maximumValue! <= 0)) {
      return false;
    }
    if (imageUri != null) {
      final uri = Uri.tryParse(imageUri!);
      if (imageUri!.length > 4096 ||
          uri == null ||
          uri.userInfo.isNotEmpty ||
          !((uri.scheme == 'https' && uri.host.isNotEmpty) ||
              (uri.scheme == 'file' && uri.host.isEmpty && uri.path.startsWith('/')))) {
        return false;
      }
    }
    if (maximumLength != null && (kind != 'text' || maximumLength! < 1 || maximumLength! > 262144)) return false;
    if (keyboard != null &&
        (kind != 'text' || !['phone', 'email', 'url', 'decimal', 'default', 'password'].contains(keyboard))) {
      return false;
    }
    if (optionSearch != null || optionClose != null) {
      if (kind != 'choice' ||
          optionSearch == null ||
          optionSearch!.isEmpty ||
          optionClose == null ||
          optionClose!.isEmpty) {
        return false;
      }
    }
    if (points.length > 10000 ||
        points.map((point) => point['x']).toSet().length != points.length ||
        points.any(
          (point) =>
              point['x'] is! num ||
              point['y'] is! num ||
              point['label'] is! String ||
              !(point['x'] as num).isFinite ||
              !(point['y'] as num).isFinite,
        )) {
      return false;
    }
    if (minimumDate != null && !_validDate(minimumDate!)) return false;
    // A one-time secret carries only its value and the single Copy command.
    if (kind == 'secret' &&
        (imageUri != null ||
            points.isNotEmpty ||
            blocks.isNotEmpty ||
            level != null ||
            maximumValue != null ||
            keyboard != null ||
            maximumLength != null ||
            options.length != 1 ||
            options['copy']?.isNotEmpty != true)) {
      return false;
    }
    if (kind == 'waveform' && points.any((point) => (point['y'] as num).abs() > 1)) return false;
    return switch (kind) {
      'image' => value == null &&
          imageUri != null &&
          Uri.tryParse(imageUri!)?.scheme == 'file' &&
          maximumValue != null &&
          maximumValue! >= 1 &&
          maximumValue! <= 16,
      'slider' || 'progress' => maximumValue != null &&
          value is num &&
          (value as num).isFinite &&
          (value as num) >= 0 &&
          (value as num) <= maximumValue!,
      'keypad' => value is String &&
          (value as String).length <= 10000 &&
          ['dialer', 'dtmf'].contains(keypadMode) &&
          options.length == 12 &&
          options.keys.every('0123456789*#'.contains) &&
          options.keys.every((key) => key.length == 1) &&
          (keypadMode == 'dtmf' || (eraseLabel?.isNotEmpty == true && clearLabel?.isNotEmpty == true)),
      'toggle' || 'task' => value is bool,
      'choice' || 'segmented' => value is String && options.containsKey(value),
      'color' => value is String &&
          options.containsKey(value) &&
          options.keys.every((key) => RegExp(r'^#[0-9A-Fa-f]{6}$').hasMatch(key)),
      'text' => value is String && (value as String).characters.length <= (maximumLength ?? 10000),
      'date' => value is String && ((value as String).isEmpty || _validDate(value as String)),
      'secret' => value is String && nativeSecretValid(value as String),
      'label' ||
      'button' ||
      'navigation' ||
      'transcript' ||
      'rich_text' ||
      'menu' ||
      'message_user' ||
      'message_ai' ||
      'chart' ||
      'waveform' =>
        value == null,
      _ => false,
    };
  }

  static bool _validDate(String value) {
    final milliseconds = int.tryParse(value);
    return milliseconds != null && milliseconds.abs() <= 8640000000000000;
  }

  bool accepts(Object? input) => switch (kind) {
        'slider' => input is num && input.isFinite && input >= 0 && maximumValue != null && input <= maximumValue!,
        'keypad' => input is String &&
            (options.containsKey(input) || keypadMode == 'dialer' && ['+', 'erase', 'clear'].contains(input)),
        'toggle' => input is bool,
        'task' => input is bool || input is String && options.containsKey(input),
        'choice' || 'segmented' || 'color' || 'menu' => input is String && options.containsKey(input),
        'navigation' || 'transcript' || 'rich_text' => input == null || input is String && options.containsKey(input),
        'date' =>
          input is String && _validDate(input) && (minimumDate == null || int.parse(input) >= int.parse(minimumDate!)),
        'text' => input is String && input.characters.length <= (maximumLength ?? 10000),
        'secret' => input == 'copy',
        _ => input == null,
      };
}

/// Dispatches only commands from the current provider projection.
Future<void> dispatchNativeAction(
  MethodCall call, {
  required bool Function() isActive,
  required Iterable<NativeRow> rows,
  NativeAction? refresh,
  NativeAction? search,
}) async {
  if (!isActive()) throw PlatformException(code: 'native_session_ended');
  if (call.method != 'action' || call.arguments is! Map) throw PlatformException(code: 'invalid_native_action');
  final args = call.arguments as Map;
  final id = args['id'];
  final value = args['value'];
  NativeAction? action;
  if (id == '_refresh' && value == null) action = refresh;
  if (id == '_search' && value is String && value.length <= 10000) action = search;
  for (final row in rows) {
    if (id == '_visible:${row.id}' && value == null) action = row.onVisible;
    if (id == '_hidden:${row.id}' && value == null) action = row.onHidden;
    if (row.valid && row.id == id && row.enabled && row.accepts(value)) action = row.action;
  }
  if (action == null) throw PlatformException(code: 'invalid_native_action');
  await action(value);
}

class NativeChat {
  const NativeChat({
    required this.draft,
    required this.placeholder,
    required this.actions,
    this.streaming = false,
    this.followup = '',
  });
  final String draft, placeholder, followup;
  final bool streaming;
  final List<NativeRow> actions;
  Map<String, Object?> get projection => {
        'draft': draft,
        'placeholder': placeholder,
        'followup': followup,
        'streaming': streaming,
        'actions': actions.map((row) => row.projection).toList(),
      };
}

class NativeSection {
  const NativeSection(this.id, this.rows, {this.title = '', this.footer = ''});
  final String id, title, footer;
  final List<NativeRow> rows;
  Map<String, Object?> get projection => {
        'id': id,
        'title': title,
        'footer': footer,
        'rows': rows.map((row) => row.projection).toList(),
      };
}

/// A reading surface shares the existing timeline owner. Scroll commands are
/// restricted to the current row IDs; no position or mutation is inferred natively.
class NativeReader {
  const NativeReader({
    this.currentId,
    this.targetId,
    this.request = 0,
    this.following = false,
    this.footer = const [],
    this.scroll,
  });
  final String? currentId, targetId;
  final int request;
  final bool following;
  final List<NativeRow> footer;
  final NativeRow? scroll;
  Iterable<NativeRow> get actions => [...footer, if (scroll != null) scroll!];

  bool validFor(Iterable<NativeSection> sections) {
    final ids = sections.expand((section) => section.rows).map((row) => row.id).toSet();
    return request >= 0 &&
        (currentId == null || ids.contains(currentId)) &&
        (targetId == null || ids.contains(targetId)) &&
        (scroll == null ||
            scroll!.kind == 'menu' && scroll!.options.keys.every((id) => id == 'suspend' || ids.contains(id)));
  }

  Map<String, Object?> get projection => {
        'currentId': currentId,
        'targetId': targetId,
        'request': request,
        'following': following,
        'footer': footer.map((row) => row.projection).toList(),
        'scroll': scroll?.projection,
      };
}

/// Shared native list/form renderer. Each page supplies its existing callbacks and provider state.
/// A snapshot Swift refuses, or a view without a renderer, restores [fallback] for good: the State
/// never retries, and its route keeps a later surface with the same [title] on the fallback too.
class IosNativeSurface extends StatefulWidget {
  const IosNativeSurface({
    super.key,
    required this.title,
    required this.sections,
    required this.fallback,
    this.toolbar = const [],
    this.largeTitle = false,
    this.loading = false,
    this.failed = false,
    this.errorMessage,
    this.empty = '',
    this.onRefresh,
    this.search,
    this.searchValue = '',
    this.searchPlaceholder = '',
    this.publicSurface = false,
    this.nativeOwner,
    this.nativeWrapper,
    this.chat,
    this.reader,
    this.controller,
    this.navigation,
    this.loadingLabel,
    this.sensitive = false,
  });

  /// Debug-only: while set, every native snapshot (surfaces and Home) carries an unsupported version,
  /// so a host test proves that Swift's rejection restores the complete Flutter presentation.
  static bool get debugCorruptSnapshotForTest => kDebugMode && _debugCorruptSnapshot;
  static set debugCorruptSnapshotForTest(bool value) {
    assert(kDebugMode, 'debugCorruptSnapshotForTest is a debug-only seam');
    _debugCorruptSnapshot = value;
  }

  static bool _debugCorruptSnapshot = false;

  /// Debug-only: hermetic widget tests treat the host as a supported iOS renderer, so surfaces and
  /// presentations exercise their channel contracts against mocked channels.
  static bool get debugNativeHostForTest => kDebugMode && _debugNativeHost;
  static set debugNativeHostForTest(bool value) {
    assert(kDebugMode, 'debugNativeHostForTest is a debug-only seam');
    _debugNativeHost = value;
  }

  static bool _debugNativeHost = false;

  /// The rows the mounted surface [state] dispatches, in projection order, including those its
  /// [NativeNavigationChrome] adds, so a host test looks a row up exactly as Swift's command would.
  @visibleForTesting
  static List<NativeRow> debugDispatchRows(State<IosNativeSurface> state) => (state as _IosNativeSurfaceState)._rows;

  final NativeSurfaceController? controller;

  /// A root tab bar uses the same account-scoped, allowlisted command bridge.
  final NativeRow? navigation;
  final NativeChat? chat;
  final NativeReader? reader;
  final String title, empty, searchValue, searchPlaceholder;
  final String? errorMessage;

  /// Names what is loading; defaults to the generic loading copy.
  final String? loadingLabel;

  /// Holds a one-time secret: the only surface that may carry a 'secret' row. Swift redacts it while
  /// the app is inactive, and [NativeSurfaceController.captureImage] never captures it.
  final bool sensitive;
  final List<NativeSection> sections;
  final List<NativeRow> toolbar;
  final Widget fallback;

  /// Mount an existing service-owning widget only when the native renderer is active.
  /// It receives lifecycle events but contributes no Flutter presentation or animation.
  final Widget? nativeOwner;
  final Widget Function(Widget)? nativeWrapper;
  final bool loading, failed, publicSurface, largeTitle;
  final NativeAction? onRefresh, search;

  @override
  State<IosNativeSurface> createState() => _IosNativeSurfaceState();
}

/// Route-scoped memory of Swift's rejections. A parent that swaps between its classic and native
/// trees (a selection mode, for example) mounts a new surface; the marker keeps that surface on its
/// fallback instead of retrying a refused snapshot. Page storage belongs to the enclosing route, so
/// the marker is released with the route.
bool _rejectionMarked(BuildContext context, String title) =>
    PageStorage.maybeOf(context)?.readState(context, identifier: ('omi.native_ui.rejected', title)) == true;

void _markRejection(BuildContext context, String title) =>
    PageStorage.maybeOf(context)?.writeState(context, true, identifier: ('omi.native_ui.rejected', title));

class _IosNativeSurfaceState extends State<IosNativeSurface> {
  late final Future<bool> _supported = supportsNativePresentation();
  late final NativeReadSession _session;
  StreamSubscription<int>? _auth;
  MethodChannel? _channel;
  int _revision = 0;
  bool _scheduled = false;

  /// Swift refused a snapshot, or the current view has no renderer. The complete Flutter surface
  /// then stays for this State's lifetime (and, through the route marker, for its successors).
  bool _rejected = false;
  List<NativeSection> get _sections => [...?NativeNavigationChrome.of(context)?.sections, ...widget.sections];
  List<NativeRow> get _toolbar => [...?NativeNavigationChrome.of(context)?.toolbar, ...widget.toolbar];
  Widget _fallback() => NativeNavigationChrome.of(context)?.wrapFallback?.call(widget.fallback) ?? widget.fallback;

  /// Every row this surface validates and dispatches, navigation chrome included.
  List<NativeRow> get _rows => [
        ..._toolbar,
        ..._sections.expand((section) => section.rows),
        ...?widget.chat?.actions,
        ...?widget.reader?.actions,
        if (widget.navigation != null) widget.navigation!,
      ];

  /// A secret row appears only once, in a section of a sensitive surface; a sensitive surface is
  /// never public, chat, reader or navigation. Anything else keeps the complete Flutter surface.
  bool get _sensitiveValid {
    bool secret(NativeRow row) => row.kind == 'secret';
    final secrets = _sections.expand((section) => section.rows).where(secret).length;
    if (_toolbar.any(secret) ||
        widget.chat?.actions.any(secret) == true ||
        widget.reader?.actions.any(secret) == true ||
        widget.navigation?.kind == 'secret' ||
        secrets > 1 ||
        secrets == 1 && !widget.sensitive) {
      return false;
    }
    return !widget.sensitive ||
        !widget.publicSurface && widget.chat == null && widget.reader == null && widget.navigation == null;
  }

  @override
  void initState() {
    super.initState();
    widget.controller?._capture = _captureImage;
    if (!nativePresentationEnabled) {
      _session = NativeReadSession(isCurrent: () => false);
      return;
    }
    _rejected = _rejectionMarked(context, widget.title);
    final owner = AuthService.instance.captureSessionSnapshot();
    var publicOwnerValid = true;
    final publicSurface = widget.publicSurface;
    _session = NativeReadSession(
      isCurrent: () =>
          publicSurface ? publicOwnerValid : owner != null && AuthService.instance.isSessionSnapshotCurrent(owner),
    );
    _auth = AuthService.instance.sessionGenerationEvents.listen((_) {
      publicOwnerValid = false;
      if (!_session.active) {
        unawaited(_invalidate());
        if (mounted) setState(() {});
      }
    });
  }

  @override
  void didUpdateWidget(IosNativeSurface oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(widget.controller, oldWidget.controller)) {
      if (oldWidget.controller?._capture == _captureImage) oldWidget.controller?._capture = null;
      widget.controller?._capture = _captureImage;
    }
  }

  Future<Uint8List?> _captureImage() async {
    if (widget.sensitive) return null;
    final channel = _channel;
    if (channel == null || !mounted || !_session.active) return null;
    final image = await channel.invokeMethod<Uint8List>('captureImage');
    if (!mounted || !_session.active || !identical(channel, _channel)) return null;
    return image != null && image.length <= 16 * 1024 * 1024 ? image : null;
  }

  Map<String, Object?> _snapshot() => {
        'version': nativeSnapshotVersion,
        'revision': _revision++,
        'title': widget.title,
        'largeTitle': widget.largeTitle,
        'appearance': context.read<AppearanceProvider>().mode.name,
        'locale': Localizations.localeOf(context).toLanguageTag(),
        'direction': Directionality.of(context).name,
        'loading': widget.loading,
        'failed': widget.failed,
        'empty': widget.empty,
        'sections': _sections.map((section) => section.projection).toList(),
        'toolbar': _toolbar.map((row) => row.projection).toList(),
        'searchEnabled': widget.search != null,
        'searchValue': widget.searchValue,
        'searchPlaceholder': widget.searchPlaceholder,
        'refreshEnabled': widget.onRefresh != null,
        'error': widget.errorMessage ?? context.l10n.connectionErrorDesc,
        'retry': context.l10n.retry,
        'loadingLabel': widget.loadingLabel ?? context.l10n.loading,
        'chat': widget.chat?.projection,
        'reader': widget.reader?.projection,
        'navigation': widget.navigation?.projection,
        'sensitive': widget.sensitive,
      };

  Future<Object?> _handle(MethodCall call) async {
    await dispatchNativeAction(
      call,
      isActive: () => _session.active && mounted,
      rows: _rows,
      refresh: widget.onRefresh,
      search: widget.search,
    );
    if (mounted && _session.active) _schedule();
    return null;
  }

  void _schedule() {
    if (_scheduled || !mounted) return;
    _scheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scheduled = false;
      if (mounted) unawaited(_publish());
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  Future<void> _publish() async {
    final channel = _channel;
    if (channel == null) return;
    try {
      await channel.invokeMethod<void>(
        _session.active ? 'update' : 'invalidate',
        _session.active ? _snapshot() : null,
      );
    } on PlatformException catch (error) {
      // Swift refused the snapshot, whatever its revision: never leave a blank native view.
      if (error.code != 'invalid_native_snapshot') rethrow;
      _reject();
    } on MissingPluginException {
      // A replaced or detached view loses its handler first; only the current view has no renderer.
      if (identical(channel, _channel)) _reject();
    }
  }

  void _reject() {
    if (_rejected) return;
    _rejected = true;
    if (mounted) _markRejection(context, widget.title);
    unawaited(_invalidate());
    if (mounted) setState(() {});
  }

  Future<void> _invalidate() async {
    final channel = _channel;
    _channel = null;
    if (channel == null) return;
    channel.setMethodCallHandler(null);
    try {
      await channel.invokeMethod<void>('invalidate');
    } on MissingPluginException {
      /* Already detached. */
    }
  }

  @override
  Widget build(BuildContext context) {
    final rows = _rows;
    if (!nativePresentationEnabled ||
        _rejected ||
        !_sensitiveValid ||
        widget.navigation != null &&
            (widget.navigation!.id != 'main_destination' ||
                widget.navigation!.kind != 'segmented' ||
                widget.navigation!.options.length != 5 ||
                !widget.navigation!.options.keys.every(['home', 'tasks', 'memories', 'apps', 'settings'].contains) ||
                _sections.isNotEmpty ||
                _toolbar.isNotEmpty ||
                widget.chat != null ||
                widget.reader != null ||
                widget.search != null ||
                widget.onRefresh != null) ||
        widget.chat != null && widget.reader != null ||
        widget.reader?.validFor(_sections) == false ||
        rows.any((row) => !row.valid) ||
        rows.map((row) => row.id).toSet().length != rows.length ||
        _sections.map((section) => section.id).toSet().length != _sections.length) {
      unawaited(_invalidate());
      return _fallback();
    }
    context.watch<AppearanceProvider>();
    _schedule();
    return FutureBuilder<bool>(
      future: _supported,
      builder: (context, support) {
        if (support.hasError) return _fallback();
        if (support.connectionState != ConnectionState.done) return const OmiLoadingState();
        if (support.data != true) return _fallback();
        if (!_session.active) return const SizedBox.shrink();
        final platformView = UiKitView(
          viewType: 'com.omi.native_ui/surface',
          // The independent system tab bar must receive its touch sequence
          // immediately instead of waiting on the surrounding Flutter arena.
          gestureRecognizers: widget.navigation == null
              ? const {}
              : {Factory<OneSequenceGestureRecognizer>(() => EagerGestureRecognizer())},
          creationParams: _snapshot(),
          creationParamsCodec: const StandardMessageCodec(),
          onPlatformViewCreated: (id) {
            final channel = MethodChannel('com.omi.native_ui/surface/$id');
            if (!mounted || !_session.active || _rejected) {
              unawaited(_invalidateDetached(channel));
              return;
            }
            unawaited(_invalidate());
            _channel = channel..setMethodCallHandler(_handle);
            _schedule();
          },
        );
        final view = widget.nativeWrapper?.call(platformView) ?? platformView;
        return widget.nativeOwner == null
            ? view
            : Stack(
                fit: StackFit.expand,
                children: [
                  view,
                  Offstage(
                    child: TickerMode(
                      enabled: false,
                      child: widget.nativeOwner!,
                    ),
                  ),
                ],
              );
      },
    );
  }

  Future<void> _invalidateDetached(MethodChannel channel) async {
    try {
      await channel.invokeMethod<void>('invalidate');
    } on MissingPluginException {
      /* View detached. */
    }
  }

  @override
  void dispose() {
    if (widget.controller?._capture == _captureImage) widget.controller?._capture = null;
    _session.dispose();
    unawaited(_invalidate());
    unawaited(_auth?.cancel());
    super.dispose();
  }
}
