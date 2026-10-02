import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'api_presentation.dart';
import 'api_result.dart';
import '../../services/dev_controls/addressability_catalog.dart';

export 'package:omi/backend/http/api/action_items.dart' show ActionItemsApi;

/// Production constructor. [main.dart] calls this with no arguments so the
/// shipped app always takes the typed list path. Tests may pass [send]
/// (loopback fixture); they must not skip [ActionItemsApi].
ActionItemsProvider createProductionActionItemsProvider({ApiSend? send}) {
  final baseUrl = Env.apiBaseUrl ?? 'http://127.0.0.1:8000/';
  return ActionItemsProvider(
    actionItemsApi: ActionItemsApi(baseUrl: baseUrl, send: send),
  );
}

/// Test helper that still returns the real provider. Production boot uses
/// [createProductionActionItemsProvider] instead.
ActionItemsProvider composeTypedActionItemsProvider(ActionItemsApi api) => ActionItemsProvider(actionItemsApi: api);

/// Extracted status region used by ActionItemsPage, not a second tasks screen.
/// Builder installs it before the empty-tasks hero in action_items_page.dart.
class ActionItemsApiStatus extends StatelessWidget {
  const ActionItemsApiStatus({super.key, required this.provider});
  final ActionItemsProvider provider;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: provider,
      builder: (context, _) {
        final view = provider.apiViewState;
        final keyName = switch (view.phase) {
          ApiViewPhase.error => 'omi.action_items.error',
          ApiViewPhase.locked => 'omi.action_items.locked',
          ApiViewPhase.terminal => 'omi.action_items.terminal',
          ApiViewPhase.authenticationRequired => 'omi.action_items.auth',
          ApiViewPhase.empty => 'omi.action_items.empty',
          ApiViewPhase.data => null,
        };
        if (keyName == null) return const SizedBox.shrink();
        final copy = switch (view.phase) {
          ApiViewPhase.empty => context.l10n.noTasksYet,
          _ => context.l10n.somethingWentWrong,
        };
        return Semantics(
          container: true,
          liveRegion: view.phase == ApiViewPhase.error,
          label: copy,
          child: Padding(
            key: ValueKey(keyName),
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  copy,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white),
                ),
                if (view.problem?.retryable == true)
                  TextButton(
                    key: OmiKeys.actionItemsRetry,
                    onPressed: () => provider.forceRefreshActionItems(),
                    child: Text(context.l10n.retry),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}
