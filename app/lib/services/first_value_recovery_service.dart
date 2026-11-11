/// Coordinates EXP-005 prompts; identity epochs reject stale responses and prompt CTAs never count as result opens.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/first_value.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/services/notifications/notification_service.dart';
import 'package:omi/ui/feedback/omi_dialogs.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Joins server-paid-start claims to the shipped Home dialog and deep links.
class FirstValueRecoveryService {
  FirstValueRecoveryService._();

  static final FirstValueRecoveryService instance = FirstValueRecoveryService._();

  FirstValueApi? _injectedApi;
  FirstValueApi get _api => _injectedApi ??= FirstValueApi();
  bool _checking = false;
  bool get _identityReady => AnalyticsManager.identityKnown && (AnalyticsManager.currentIdentity?.isNotEmpty ?? false);

  @visibleForTesting
  set debugApi(FirstValueApi api) => _injectedApi = api;

  @visibleForTesting
  Future<bool> Function()? debugNotificationPermission;

  @visibleForTesting
  Future<String> Function()? debugTimeZone;

  Future<Map<String, String?>> _clientCapability() async {
    bool? authorized;
    String? timeZone;
    try {
      authorized =
          await (debugNotificationPermission?.call() ?? NotificationService.instance.hasNotificationPermissions());
    } catch (_) {}
    try {
      timeZone = await (debugTimeZone?.call() ?? NotificationService.instance.getTimeZone());
    } catch (_) {}
    return {
      'notificationPermission': authorized == null ? null : (authorized ? 'granted' : 'denied'),
      'timeZone': timeZone,
    };
  }

  Future<void> checkOnAppOpen() async {
    if (_checking || !_identityReady) return;
    _checking = true;
    final identityEpoch = AnalyticsManager.identityEpoch;
    try {
      final capability = await _clientCapability();
      if (identityEpoch != AnalyticsManager.identityEpoch || !_identityReady) return;
      // Consent-governed observation is independent of delivery/intake. Dark
      // client releases must be measurable before the activation-volume gate.
      AnalyticsManager().track('First Value Recovery Client Capability', properties: {
        'protocol': 1,
        'notification_permission': capability['notificationPermission'] ?? 'unknown',
        if (capability['timeZone'] != null) 'time_zone': capability['timeZone'],
      });
      PromptQueue.instance.enqueue(
        'first-value-recovery',
        PromptPriority.normal,
        canShowNow: () => identityEpoch == AnalyticsManager.identityEpoch && _identityReady,
        show: (context) async {
          // Do not consume the durable claim while a higher-priority prompt
          // blocks the queue, or after the authenticated identity changes.
          if (identityEpoch != AnalyticsManager.identityEpoch || !_identityReady) return;
          final result = await _api.prompt(
            notificationPermission: capability['notificationPermission'],
            timeZone: capability['timeZone'],
          );
          if (!context.mounted ||
              identityEpoch != AnalyticsManager.identityEpoch ||
              result is! ApiSuccess<FirstValuePrompt?>) return;
          final prompt = result.data;
          if (prompt == null || !_identityReady) return;
          final l10n = context.l10n;
          final capture = prompt.kind == 'capture';
          final confirmed = await showOmiConfirm(
            context,
            title: capture ? l10n.deviceNotConnected : l10n.summaryGenerated,
            message: capture ? l10n.captureEveryMoment : l10n.reviewAndManageConversations,
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
    if (!_identityReady) return false;
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
      final capability = await _clientCapability();
      await _api.recordPendantConnection(
        notificationPermission: capability['notificationPermission'],
        timeZone: capability['timeZone'],
      );
    } catch (_) {}
  }
}
