import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';

import 'ios_native_surface.dart';

/// A credential the native 'secret' row can reveal: 1 to 4096 printable ASCII characters, with no
/// whitespace or line break. Swift validates the same range, so anything else keeps the caller's
/// existing Flutter dialog.
bool nativeSecretValid(String secret) =>
    secret.isNotEmpty && secret.length <= 4096 && secret.codeUnits.every((unit) => unit >= 0x21 && unit <= 0x7E);

/// Reveals a newly created credential once. The caller keeps the credential owner and the copy
/// action ([onCopy] goes through its existing clipboard owner); this only presents.
///
/// [showClassic] (the caller's existing dialog) runs instead when the native presentation is off or
/// unsupported, or when the secret cannot cross the bridge. Otherwise the sheet is fenced to the
/// account session current when this is called: after a session change it never presents, and an
/// open sheet closes. Only Done closes it otherwise. The secret is never logged, never part of a row
/// id and never cached; it crosses the bridge only as the value of its one sensitive row.
Future<void> showIosNativeSecretSheet(
  BuildContext context, {
  required String title,
  String? message,
  String? warning,
  required String secretLabel,
  required String secret,
  required String copyLabel,
  required String doneLabel,
  required VoidCallback onCopy,
  required Future<void> Function() showClassic,
}) async {
  if (!nativePresentationEnabled || !nativeSecretValid(secret)) return showClassic();
  final owner = AuthService.instance.captureSessionSnapshot();
  final supported = await supportsNativePresentation();
  // A session that changed while support was checked gets neither presentation of the key.
  if (!context.mounted || owner != null && !AuthService.instance.isSessionSnapshotCurrent(owner)) return;
  if (!supported) return showClassic();
  // Without a signed-in session there is no owner to fence the sheet to; the caller's dialog runs.
  if (owner == null) return showClassic();
  NativeSecretPage page(bool native) => NativeSecretPage(
        owner: owner,
        native: native,
        title: title,
        message: message,
        warning: warning,
        secretLabel: secretLabel,
        secret: secret,
        copyLabel: copyLabel,
        doneLabel: doneLabel,
        onCopy: onCopy,
      );
  await showOmiSheet<void>(
    context: context,
    title: title,
    showCloseButton: false,
    isDismissible: false,
    enableDrag: false,
    builder: (_) => page(false),
    nativeBuilder: (_) => page(true),
  );
}

/// The sheet body of [showIosNativeSecretSheet]: the sensitive native surface, or (as the classic
/// builder and as that surface's fallback) a minimal Flutter body, so a refused snapshot never
/// loses the one-time key. Public only for tests.
@visibleForTesting
class NativeSecretPage extends StatefulWidget {
  const NativeSecretPage({
    super.key,
    required this.owner,
    required this.native,
    required this.title,
    this.message,
    this.warning,
    required this.secretLabel,
    required this.secret,
    required this.copyLabel,
    required this.doneLabel,
    required this.onCopy,
  });

  final AuthSessionSnapshot owner;
  final bool native;
  final String title, secretLabel, secret, copyLabel, doneLabel;
  final String? message, warning;
  final VoidCallback onCopy;

  @override
  State<NativeSecretPage> createState() => _NativeSecretPageState();
}

class _NativeSecretPageState extends State<NativeSecretPage> {
  StreamSubscription<int>? _auth;
  bool _closed = false;

  bool get _current => AuthService.instance.isSessionSnapshotCurrent(widget.owner);

  @override
  void initState() {
    super.initState();
    _auth = AuthService.instance.sessionGenerationEvents.listen((_) {
      if (!_current) _close();
    });
    // The account can change while the sheet opens; it then closes without showing the key.
    if (!_current) _close();
  }

  /// Withdraws the key and pops this sheet's own route. Both wait for the frame, because a session
  /// change can arrive while another widget builds; any rebuild before then already hides the key.
  void _close() {
    if (_closed || !mounted) return;
    _closed = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      setState(() {});
      final route = ModalRoute.of(context);
      if (route == null || !route.isActive) return;
      if (route.isCurrent) {
        Navigator.of(context).pop();
      } else {
        Navigator.of(context).removeRoute(route);
      }
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  @override
  void dispose() {
    unawaited(_auth?.cancel());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_closed || !_current) return const SizedBox.shrink();
    final body = _SecretBody(
      message: widget.message,
      warning: widget.warning,
      secretLabel: widget.secretLabel,
      secret: widget.secret,
      copyLabel: widget.copyLabel,
      doneLabel: widget.doneLabel,
      onCopy: widget.onCopy,
      onDone: _close,
    );
    return PopScope(
      canPop: false,
      child: !widget.native
          ? body
          : IosNativeSurface(
              sensitive: true,
              title: widget.title,
              fallback: OmiSheetScaffold(title: widget.title, showCloseButton: false, child: body),
              toolbar: [NativeRow('secret_done', widget.doneLabel, symbol: 'checkmark', action: (_) => _close())],
              sections: [
                NativeSection('secret', [
                  if (widget.message?.isNotEmpty == true) NativeRow('secret_message', widget.message!, kind: 'label'),
                  if (widget.warning?.isNotEmpty == true)
                    NativeRow('secret_warning', widget.warning!, kind: 'label', symbol: 'exclamationmark.triangle'),
                  NativeRow('secret_value', widget.secretLabel,
                      kind: 'secret',
                      value: widget.secret,
                      options: {'copy': widget.copyLabel},
                      action: (_) => widget.onCopy()),
                ]),
              ],
            ),
    );
  }
}

/// Monospaced key, Copy and Done, using only the caller's labels.
class _SecretBody extends StatelessWidget {
  const _SecretBody({
    required this.message,
    required this.warning,
    required this.secretLabel,
    required this.secret,
    required this.copyLabel,
    required this.doneLabel,
    required this.onCopy,
    required this.onDone,
  });

  final String? message, warning;
  final String secretLabel, secret, copyLabel, doneLabel;
  final VoidCallback onCopy, onDone;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (message?.isNotEmpty == true) ...[
            Text(message!, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
            const SizedBox(height: OmiSpacing.md),
          ],
          if (warning?.isNotEmpty == true) ...[
            Row(
              children: [
                Icon(Icons.warning_amber_rounded, color: OmiColors.warning, size: 20),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(child: Text(warning!, style: OmiType.footnote.copyWith(color: OmiColors.warning))),
              ],
            ),
            const SizedBox(height: OmiSpacing.md),
          ],
          Text(secretLabel,
              style: OmiType.caption.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600)),
          const SizedBox(height: OmiSpacing.sm),
          SelectableText(secret, style: OmiType.subhead.copyWith(fontFamily: 'monospace', height: 1.4)),
          const SizedBox(height: OmiSpacing.lg),
          Row(
            children: [
              Expanded(
                child: OmiButton.secondary(label: copyLabel, icon: Icons.copy, expand: true, onPressed: onCopy),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(child: OmiButton(label: doneLabel, expand: true, onPressed: onDone)),
            ],
          ),
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
  }
}
