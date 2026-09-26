import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/extensions/string.dart';

// The app store's shared actions. Every surface that enables or disables an app goes through
// these, so an app reads and behaves the same in the store lists, the chat drawer and its
// detail page:
//
// * enabling an app that works outside Omi asks once, with [confirmAppDataAccess];
// * disabling is immediate with a 5 s Undo, via [disableAppWithUndo];
// * a list row's button is [AppListActionButton]: Open / Enable / View.

/// Whether enabling [app] needs more than a tap: a paid app the reader has not bought, or an
/// integration with setup steps. Those are enabled from the app's detail page.
bool appNeedsDetailToEnable(App app) {
  if (app.isPaid && !app.isUserPaid) return true;
  final integration = app.externalIntegration;
  if (integration == null) return false;
  return integration.authSteps.isNotEmpty || (integration.setupInstructionsFilePath?.isNotEmpty ?? false);
}

/// The one consent question before an app that works outside Omi receives the reader's data.
///
/// Resolves `true` straight away for apps that stay inside Omi. Otherwise asks
/// "Allow {app} Access?" with what leaves Omi and where it goes, and resolves `true` only when the
/// reader chose Enable.
Future<bool> confirmAppDataAccess(BuildContext context, App app) async {
  if (!app.worksExternally()) return true;
  final l10n = context.l10n;
  final name = app.name.decodeString;
  return showOmiConfirm(
    context,
    title: l10n.appDataAccessTitle(name),
    message: l10n.appDataAccessMessage(name),
    confirmLabel: l10n.enable,
  );
}

/// Disables [app] with a 5 s Undo toast instead of a confirmation (docs/ux-contract.md §4).
///
/// [onHidden] runs at once so the surface can show the app as disabled; [onRestored] runs when the
/// reader taps Undo or the server refuses. The server call is made only when the toast resolves
/// without Undo. Returns whether the app ended up disabled.
Future<bool> disableAppWithUndo(
  BuildContext context,
  App app, {
  VoidCallback? onHidden,
  VoidCallback? onRestored,
}) async {
  final provider = context.read<AppProvider>();
  provider.pendingDisables.add(app.id);
  onHidden?.call();
  final undone = await OmiFeedback.undo(
    context,
    context.l10n.appDisabledNamed(app.name.decodeString),
    onUndo: () {},
  );
  // Enabled again inside the Undo window (e.g. the detail page's Enable): that choice wins.
  if (!provider.pendingDisables.remove(app.id)) return false;
  if (undone) {
    onRestored?.call();
    return false;
  }
  final disabled = await provider.toggleApp(app.id, false, null);
  if (!disabled) onRestored?.call();
  return disabled;
}

/// The action button on an app row in the store, the same everywhere a row appears.
///
/// * enabled → **Open**, which opens the app ([onOpen]);
/// * can be enabled with a tap → **Enable**, which asks for data access when the app works outside
///   Omi ([confirmAppDataAccess]) and enables it in place, spinning until the server answers;
/// * needs payment or setup ([appNeedsDetailToEnable]) → **View**, which opens the app's detail
///   page where that happens.
///
/// The button is compact (36 pt tall in a 48 pt target) and as wide as its label.
class AppListActionButton extends StatefulWidget {
  const AppListActionButton({super.key, required this.app, required this.onOpen, this.loadingIndex});

  final App app;

  /// Opens the app's detail page (each list decides how it navigates).
  final VoidCallback onOpen;

  /// The row's slot in [AppProvider.appLoading], when the list tracks per-row loading.
  final int? loadingIndex;

  @override
  State<AppListActionButton> createState() => _AppListActionButtonState();
}

class _AppListActionButtonState extends State<AppListActionButton> {
  // Spins only while the server enables the app — not while the consent question is open.
  bool _enabling = false;

  Future<void> _enable() async {
    final provider = context.read<AppProvider>();
    if (!await confirmAppDataAccess(context, widget.app)) return;
    if (!mounted) return;
    setState(() => _enabling = true);
    try {
      await provider.toggleApp(widget.app.id, true, widget.loadingIndex);
    } finally {
      if (mounted) setState(() => _enabling = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final app = widget.app;
    final state = context.select<AppProvider, ({bool enabled, bool loading})>((provider) {
      final current = provider.apps.firstWhereOrNull((a) => a.id == app.id) ?? app;
      final index = widget.loadingIndex;
      final loading = index != null && index >= 0 && index < provider.appLoading.length && provider.appLoading[index];
      return (enabled: current.enabled, loading: loading);
    });

    if (state.enabled) {
      return OmiButton.secondary(label: l10n.open, onPressed: widget.onOpen, size: OmiButtonSize.compact);
    }
    if (appNeedsDetailToEnable(app)) {
      return OmiButton.secondary(label: l10n.view, onPressed: widget.onOpen, size: OmiButtonSize.compact);
    }
    return OmiButton(
      label: l10n.enable,
      size: OmiButtonSize.compact,
      isLoading: _enabling || state.loading,
      onPressed: () {
        _enable();
      },
    );
  }
}
