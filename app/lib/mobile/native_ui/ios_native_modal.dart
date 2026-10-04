import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'ios_native_home.dart';
import 'ios_native_surface.dart';

/// A native presentation returns input to the existing Dart owner; it never saves it itself.
class NativeModalResult {
  const NativeModalResult(this.action, this.values);
  final String? action;
  final Map<String, Object?> values;
}

const _presentationChannel = MethodChannel('com.omi.native_ui/config');
int _nextPresentationId = 0;

Future<NativeModalResult?> showIosNativeModal(
  BuildContext context, {
  required String title,
  required List<NativeRow> actions,
  List<NativeSection> sections = const [],
  String cancelId = 'cancel',
  bool alert = false,
  bool dismissible = true,
  bool guardEdits = false,
}) async {
  if (!iosSwiftUiEnabled || !await supportsIosSwiftUi()) return null;
  if (!context.mounted) return const NativeModalResult(null, {});
  final rows = [...actions, ...sections.expand((section) => section.rows)];
  if (rows.any((row) => !row.valid) || rows.map((row) => row.id).toSet().length != rows.length) {
    throw ArgumentError('Invalid native presentation');
  }
  final id = _nextPresentationId++;
  final owner = AuthService.instance.captureSessionSnapshot();
  var sessionValid = true;
  final subscription = AuthService.instance.sessionGenerationEvents.listen((_) {
    sessionValid = false;
    unawaited(_dismiss(id));
  });
  try {
    final l10n = context.l10n;
    final response = await _presentationChannel.invokeMapMethod<String, Object?>('present', {
      'requestId': id,
      'cancelId': cancelId,
      'alert': alert,
      'dismissible': dismissible,
      'guardEdits': guardEdits,
      'discard': {
        'title': l10n.discardChangesTitle,
        'message': l10n.discardChangesMessage,
        'confirm': l10n.discard,
        'cancel': l10n.keepEditing,
      },
      'snapshot': {
        'version': 1,
        'revision': 0,
        'title': title,
        'appearance': context.read<AppearanceProvider>().mode.name,
        'locale': Localizations.localeOf(context).toLanguageTag(),
        'direction': Directionality.of(context).name,
        'loading': false,
        'failed': false,
        'empty': '',
        'sections': [
          for (final section in sections)
            {
              ...section.projection,
              'rows': [
                for (final row in section.rows) {...row.projection, 'enabled': row.enabled}
              ],
            },
        ],
        'toolbar': actions.map((row) => {...row.projection, 'enabled': row.enabled}).toList(),
        'searchEnabled': false,
        'searchValue': '',
        'searchPlaceholder': '',
        'refreshEnabled': false,
        'error': l10n.failedToSaveCheckConnection,
        'retry': l10n.retry,
        'loadingLabel': l10n.loading,
      },
    });
    if (!context.mounted || !sessionValid || owner != null && !AuthService.instance.isSessionSnapshotCurrent(owner)) {
      return const NativeModalResult(null, {});
    }
    if (response == null) return const NativeModalResult(null, {});
    final action = response['action'];
    final values = response['values'];
    if (action is! String || !actions.any((row) => row.id == action && row.enabled) || values is! Map) {
      throw PlatformException(code: 'invalid_native_presentation_result');
    }
    final accepted = <String, Object?>{};
    for (final row in sections.expand((section) => section.rows)) {
      if (!['text', 'toggle', 'choice', 'color', 'date'].contains(row.kind)) continue;
      if (!values.containsKey(row.id) || !row.accepts(values[row.id])) {
        throw PlatformException(code: 'invalid_native_presentation_value');
      }
      accepted[row.id] = values[row.id];
    }
    return NativeModalResult(action == cancelId ? null : action, accepted);
  } on MissingPluginException {
    // An older installed host retains its complete existing dialog.
    return null;
  } finally {
    await subscription.cancel();
  }
}

Future<void> _dismiss(int id) async {
  try {
    await _presentationChannel.invokeMethod<void>('dismissPresentation', id);
  } on MissingPluginException {
    // An older host has no temporary native presentation to dismiss.
  }
}
