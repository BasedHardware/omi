// Derived by python3 tool/perf_shell.py from main.dart. Do not hand edit.
// Extracted shell SHA256 (imports, telemetry field, builder chain): c493dd9098cd21e93eaf0006850fc3cf7f4009e6880a4d3f9554ac7c75232324
// ignore_for_file: unused_import, unnecessary_import
import 'package:omi/services/on_device/on_device_background.dart';
import 'package:omi/services/onboarding_sync_runtime.dart';
import 'package:omi/env/physical_qualification.dart';
import 'dart:async';
import 'package:omi/services/telemetry/client_telemetry.dart';
import 'package:omi/services/telemetry/client_telemetry_flags.dart';
import 'package:omi/services/telemetry/client_telemetry_transport.dart';
import 'dart:ui';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/services/dev_controls/semantic_controls.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/services/account_cutover/account_cutover_runtime.dart';
import 'package:omi/widgets/bluetooth_guidance_listener.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:talker_flutter/talker_flutter.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/backend/http/conversation_api_contract.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/coordinators/provider_capture_external_actions.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/env/backend_url_override.dart';
import 'package:omi/env/dev_env.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/env/prod_env.dart';
import 'package:omi/firebase_options_local.dart' as local;
import 'package:omi/firebase_options_prod.dart' as prod;
import 'package:omi/flavors.dart';
import 'package:omi/startup_auth.dart';
import 'package:omi/startup_failure_app.dart';
import 'package:omi/startup_firebase.dart';
import 'package:omi/startup_routing.dart';
import 'package:omi/startup/boot_crash_handlers.dart';
import 'package:omi/startup/boot_journal.dart';
import 'package:omi/startup/boot_recovery.dart';
import 'package:omi/startup/boot_recovery_app.dart';
import 'package:omi/startup/startup_error_router.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/backend/http/action_items_api_contract.dart';
import 'package:omi/providers/announcement_provider.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/services/siri_integration.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/messaging_channels_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/locale_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/omi_theme.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/notifications/action_item_notification_handler.dart';
import 'package:omi/services/notifications/chat_answer_notification_handler.dart';
import 'package:omi/services/notifications/important_conversation_notification_handler.dart';
import 'package:omi/services/notifications/merge_notification_handler.dart';
import 'package:omi/services/devices/connectors/limitless_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/analytics/app_session_telemetry.dart';
import 'package:omi/utils/analytics/phone_battery_sample_telemetry.dart';
import 'package:omi/utils/analytics/mobile_performance_telemetry.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/debugging/crashlytics_manager.dart';
import 'package:omi/utils/environment_detector.dart';
import 'package:omi/utils/analytics/rage_click_context_tracker.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/notification_channel_strings.dart';
import 'package:omi/main.dart' show MyApp, CustomErrorWidget;

/// The exact production builder chain, with an inert seeded page boundary.
/// Force the iOS + configured analytics arm on hosts; no analytics keys required.
class PerfProductionShell extends StatefulWidget {
  const PerfProductionShell({super.key, required this.page, this.iosAnalytics = true});
  final Widget page;
  final bool iosAnalytics;
  @override
  State<PerfProductionShell> createState() => _PerfProductionShellState();
}

class _PerfProductionShellState extends State<PerfProductionShell> {
  late final MobilePerformanceTelemetry _performanceTelemetry = MobilePerformanceTelemetry(
    emit: (name, properties) {
      DebugLogManager.logEvent('mobile_render_diagnostic', {
        for (final entry in properties.entries) entry.key: entry.value,
      });
    },
    identityEpoch: () => AnalyticsManager.identityEpoch,
    diagnosticsEnabled: () => SharedPreferencesUtil().devLogsToFileEnabled,
  );
  @override
  void initState() {
    super.initState();
    _performanceTelemetry.attach();
  }

  @override
  void dispose() {
    _performanceTelemetry.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AppearanceProvider()),
          ChangeNotifierProvider(create: (_) => LocaleProvider()),
        ],
        builder: (context, child) {
          final mode = context.watch<AppearanceProvider>().mode;
          final platformBrightness = WidgetsBinding.instance.platformDispatcher.platformBrightness;
          final brightness = resolveAppearanceBrightness(mode, platformBrightness);
          OmiColors.active = OmiColors.forBrightness(brightness);
          return WithForegroundTask(
            child: MaterialApp(
              debugShowCheckedModeBanner: F.env == Environment.dev,
              title: F.title,
              navigatorKey: MyApp.navigatorKey,
              navigatorObservers: [if (!PhysicalQualification.enabled) _performanceTelemetry],
              locale: context.watch<LocaleProvider>().locale,
              localizationsDelegates: const [
                AppLocalizations.delegate,
                GlobalMaterialLocalizations.delegate,
                GlobalWidgetsLocalizations.delegate,
                GlobalCupertinoLocalizations.delegate,
              ],
              supportedLocales: AppLocalizations.supportedLocales,
              theme: buildOmiTheme(brightness: Brightness.light),
              darkTheme: buildOmiTheme(brightness: Brightness.dark),
              themeMode: mode,
              builder: (context, child) {
                syncIntlDefaultLocale(Localizations.localeOf(context));
                ErrorWidget.builder = (errorDetails) {
                  return CustomErrorWidget(errorMessage: errorDetails.exceptionAsString());
                };
                final content = AnnotatedRegion<SystemUiOverlayStyle>(
                  value: brightness == Brightness.dark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
                  child: KeyedSubtree(key: ValueKey(brightness), child: child!),
                );
                final guidedContent = BluetoothGuidanceListener(child: content);
                return widget.iosAnalytics ? RageClickContextTracker(child: guidedContent) : guidedContent;
              },
              home: TalkerWrapper(
                talker: Logger.instance.talker,
                options: const TalkerWrapperOptions(enableErrorAlerts: false, enableExceptionAlerts: false),
                child: widget.page,
              ),
            ),
          );
        },
      );
}
