import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'ios_native_home.dart';
import 'native_read_session.dart';

typedef NativeAction = FutureOr<void> Function(Object? value);

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
    this.imageUri,
    this.points = const [],
    this.action,
    this.onVisible,
    this.destructive = false,
    this.enabled = true,
  });

  final String id, title, kind, subtitle;
  final String? symbol, minimumDate;
  final String? imageUri;
  final int? maximumLength;
  final List<Map<String, Object>> points;
  final Object? value;
  final Map<String, String> options;
  final NativeAction? action, onVisible;
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
        'imageUri': imageUri,
        'points': points,
        'destructive': destructive,
        'enabled': enabled && action != null,
      };

  bool get valid {
    if (id.isEmpty || id.startsWith('_') || options.keys.any((id) => id.isEmpty)) return false;
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
    if (maximumLength != null && (kind != 'text' || maximumLength! < 1 || maximumLength! > 10000)) return false;
    if (points.length > 10000 ||
        points.map((point) => point['x']).toSet().length != points.length ||
        points.any(
          (point) =>
              point['x'] is! num ||
              point['y'] is! num ||
              !(point['x'] as num).isFinite ||
              !(point['y'] as num).isFinite,
        )) {
      return false;
    }
    if (minimumDate != null && !_validDate(minimumDate!)) return false;
    if (kind == 'waveform' && points.any((point) => (point['y'] as num).abs() > 1)) return false;
    return switch (kind) {
      'toggle' || 'task' => value is bool,
      'choice' => value is String && options.containsKey(value),
      'text' => value is String && (value as String).characters.length <= (maximumLength ?? 10000),
      'date' => value is String && ((value as String).isEmpty || _validDate(value as String)),
      'label' ||
      'button' ||
      'navigation' ||
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
        'toggle' => input is bool,
        'task' => input is bool || input is String && options.containsKey(input),
        'choice' || 'menu' => input is String && options.containsKey(input),
        'date' =>
          input is String && _validDate(input) && (minimumDate == null || int.parse(input) >= int.parse(minimumDate!)),
        'text' => input is String && input.characters.length <= (maximumLength ?? 10000),
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

/// Shared native list/form renderer. Each page supplies its existing callbacks and provider state.
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
    this.empty = '',
    this.onRefresh,
    this.search,
    this.searchValue = '',
    this.searchPlaceholder = '',
    this.publicSurface = false,
    this.nativeOwner,
    this.chat,
  });

  final NativeChat? chat;
  final String title, empty, searchValue, searchPlaceholder;
  final List<NativeSection> sections;
  final List<NativeRow> toolbar;
  final Widget fallback;

  /// Mount an existing service-owning widget only when the native renderer is active.
  /// It receives lifecycle events but contributes no Flutter presentation or animation.
  final Widget? nativeOwner;
  final bool loading, failed, publicSurface, largeTitle;
  final NativeAction? onRefresh, search;

  @override
  State<IosNativeSurface> createState() => _IosNativeSurfaceState();
}

class _IosNativeSurfaceState extends State<IosNativeSurface> {
  late final Future<bool> _supported = supportsIosSwiftUi();
  late final NativeReadSession _session;
  StreamSubscription<int>? _auth;
  MethodChannel? _channel;
  int _revision = 0;
  bool _scheduled = false;

  @override
  void initState() {
    super.initState();
    if (!iosSwiftUiEnabled) {
      _session = NativeReadSession(isCurrent: () => false);
      return;
    }
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

  Map<String, Object?> _snapshot() => {
        'version': 1,
        'revision': _revision++,
        'title': widget.title,
        'largeTitle': widget.largeTitle,
        'appearance': context.read<AppearanceProvider>().mode.name,
        'locale': Localizations.localeOf(context).toLanguageTag(),
        'direction': Directionality.of(context).name,
        'loading': widget.loading,
        'failed': widget.failed,
        'empty': widget.empty,
        'sections': widget.sections.map((section) => section.projection).toList(),
        'toolbar': widget.toolbar.map((row) => row.projection).toList(),
        'searchEnabled': widget.search != null,
        'searchValue': widget.searchValue,
        'searchPlaceholder': widget.searchPlaceholder,
        'refreshEnabled': widget.onRefresh != null,
        'error': context.l10n.connectionErrorDesc,
        'retry': context.l10n.retry,
        'loadingLabel': context.l10n.loading,
        'chat': widget.chat?.projection,
      };

  Future<Object?> _handle(MethodCall call) async {
    await dispatchNativeAction(
      call,
      isActive: () => _session.active && mounted,
      rows: [
        ...widget.toolbar,
        ...widget.sections.expand((section) => section.rows),
        ...?widget.chat?.actions,
      ],
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
    } on MissingPluginException {
      if (mounted && identical(channel, _channel)) rethrow;
    }
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
    final rows = [
      ...widget.toolbar,
      ...widget.sections.expand((section) => section.rows),
      ...?widget.chat?.actions,
    ];
    if (!iosSwiftUiEnabled ||
        rows.any((row) => !row.valid) ||
        rows.map((row) => row.id).toSet().length != rows.length ||
        widget.sections.map((section) => section.id).toSet().length != widget.sections.length) {
      unawaited(_invalidate());
      return widget.fallback;
    }
    context.watch<AppearanceProvider>();
    _schedule();
    return FutureBuilder<bool>(
      future: _supported,
      builder: (context, support) {
        if (support.hasError) return widget.fallback;
        if (support.connectionState != ConnectionState.done) return const OmiLoadingState();
        if (support.data != true) return widget.fallback;
        if (!_session.active) return const SizedBox.shrink();
        final view = UiKitView(
          viewType: 'com.omi.native_ui/surface',
          creationParams: _snapshot(),
          creationParamsCodec: const StandardMessageCodec(),
          onPlatformViewCreated: (id) {
            final channel = MethodChannel('com.omi.native_ui/surface/$id');
            if (!mounted || !_session.active) {
              unawaited(_invalidateDetached(channel));
              return;
            }
            unawaited(_invalidate());
            _channel = channel..setMethodCallHandler(_handle);
            _schedule();
          },
        );
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
    _session.dispose();
    unawaited(_invalidate());
    unawaited(_auth?.cancel());
    super.dispose();
  }
}
