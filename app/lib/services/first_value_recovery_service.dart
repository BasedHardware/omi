// Home presentation for server-claimed first-value prompts; account epochs fence every surface.
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/first_value.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/ui/feedback/omi_dialogs.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Joins server-paid-start claims to the shipped Home dialog and deep links.
class FirstValueRecoveryService {
  FirstValueRecoveryService._();

  static final FirstValueRecoveryService instance = FirstValueRecoveryService._();

  FirstValueApi? _debugApi;
  FirstValueApi get _api => _debugApi ??= FirstValueApi();
  bool _checking = false;

  @visibleForTesting
  set debugApi(FirstValueApi api) => _debugApi = api;

  Future<void> checkOnAppOpen() async {
    if (_checking) return;
    _checking = true;
    final identityEpoch = AnalyticsManager.identityEpoch;
    try {
      final result = await _api.prompt();
      if (identityEpoch != AnalyticsManager.identityEpoch || result is! ApiSuccess<FirstValuePrompt?>) return;
      final prompt = result.data;
      if (prompt == null || !AnalyticsManager.identityKnown) return;
      PromptQueue.instance.enqueue(
        'first-value-${prompt.kind}',
        PromptPriority.normal,
        canShowNow: () => identityEpoch == AnalyticsManager.identityEpoch && AnalyticsManager.identityKnown,
        show: (context) async {
          final l10n = context.l10n;
          final capture = prompt.kind == 'capture';
          final confirmed = await showOmiConfirm(
            context,
            title: capture ? l10n.deviceNotConnected : l10n.summaryGenerated,
            message: l10n.captureEveryMoment,
            confirmLabel: capture ? l10n.connectDevice : l10n.open,
          );
          if (confirmed && identityEpoch == AnalyticsManager.identityEpoch) {
            await HomeNavigation.openRoute(prompt.route);
          }
        },
      );
    } finally {
      _checking = false;
    }
  }

  Future<bool> openReadyResultFromPush() async {
    final identityEpoch = AnalyticsManager.identityEpoch;
    final result = await _api.prompt(navigation: true);
    if (identityEpoch != AnalyticsManager.identityEpoch || result is! ApiSuccess<FirstValuePrompt?>) return false;
    final prompt = result.data;
    if (prompt == null || prompt.kind != 'result') return false;
    return HomeNavigation.openRoute(prompt.route);
  }

  Future<void> recordResultOpen(String conversationId) async {
    try {
      await _api.recordResultOpen(conversationId);
    } catch (_) {}
  }

  Future<void> recordPendantConnection() async {
    try {
      await _api.recordPendantConnection();
    } catch (_) {}
  }
}
