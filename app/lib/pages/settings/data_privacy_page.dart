import 'dart:async';
import 'dart:io';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/services/siri_integration.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

class DataPrivacyPage extends StatefulWidget {
  const DataPrivacyPage({super.key});

  /// Debug-only: the iOS gates a non-iOS test host cannot report. Release and profile builds ignore it.
  @visibleForTesting
  static ({bool ios, bool shortcutsHint, bool searchHint})? debugPlatformForTest;

  static ({bool ios, bool shortcutsHint, bool searchHint})? get _debugPlatform =>
      kDebugMode ? debugPlatformForTest : null;

  @override
  State<DataPrivacyPage> createState() => _DataPrivacyPageState();
}

class _DataPrivacyPageState extends State<DataPrivacyPage> {
  bool _siriEnabled = true;
  int _siriRevision = 0;

  // App Shortcuts and the native Shortcuts button require iOS 16; the
  // searchInApp schema requires iOS 27. Older systems keep the index switch.
  late final bool _isIOS = DataPrivacyPage._debugPlatform?.ios ?? Platform.isIOS;
  late final bool _shortcutsHintSupported =
      DataPrivacyPage._debugPlatform?.shortcutsHint ?? PlatformService.isIOSAtLeast(16);
  late final bool _searchHintSupported = DataPrivacyPage._debugPlatform?.searchHint ?? PlatformService.isIOSAtLeast(27);

  // The native omi/shortcuts_button platform view is registered only by the
  // Siri toolchain (Xcode 27). Stable-compiler (Xcode 26.6) builds compile the
  // registration out, so requesting the view there cannot render; gate the
  // section on the native capability probe. Fail closed: only render once the
  // bridge confirms availability.
  bool _appShortcutsAvailable = false;

  // The native list draws Apple's ShortcutsLink itself only when this host compiled it in; it is
  // resolved once. Until then, and without it, the Shortcuts card keeps the classic page.
  bool _shortcutsLinkCapable = false;
  late final Future<bool> _shortcutsLinkCapability = _shortcutsHintSupported
      ? nativeUiCapabilities().then((capabilities) => capabilities.contains('shortcuts_link'))
      : Future.value(false);

  Future<void> _loadAppShortcutsAvailability() async {
    final revision = _siriRevision;
    try {
      final available = await SiriIntegration.current.appShortcutsAvailable();
      // Both answers land together, so the card never flips between the classic and native lists.
      final linkCapable = await _shortcutsLinkCapability;
      if (mounted && revision == _siriRevision) {
        setState(() {
          _appShortcutsAvailable = available;
          _shortcutsLinkCapable = linkCapable;
        });
      }
    } catch (_) {
      // Fail closed: leave the card hidden when the bridge cannot answer.
    }
  }

  Future<void> _loadSiriSetting() async {
    final revision = _siriRevision;
    try {
      final enabled = await SiriIntegration.current.isEnabled();
      if (mounted && revision == _siriRevision) setState(() => _siriEnabled = enabled);
    } catch (_) {/* Keep the default until native state is available. */}
  }

  void _setSiriEnabled(bool enabled) {
    final revision = ++_siriRevision;
    final previous = _siriEnabled;
    setState(() => _siriEnabled = enabled);
    unawaited(SiriIntegration.current.setEnabled(enabled).catchError((Object _) {
      if (mounted && revision == _siriRevision) setState(() => _siriEnabled = previous);
    }));
  }

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.dataPrivacyPageOpened();
    if (_isIOS) _loadSiriSetting();
    if (_shortcutsHintSupported) _loadAppShortcutsAvailability();
  }

  Widget _buildEncryptionBanner(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        border: Border.all(color: OmiColors.border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
            child: Icon(Icons.lock_outline, color: OmiColors.textPrimary, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: RichText(
              text: TextSpan(
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.5),
                children: [
                  TextSpan(text: '${context.l10n.dataEncryptedBanner} '),
                  TextSpan(
                    text: context.l10n.learnMore,
                    style: TextStyle(
                      color: OmiColors.textPrimary,
                      decoration: TextDecoration.underline,
                      decorationColor: OmiColors.textPrimary,
                    ),
                    recognizer: TapGestureRecognizer()
                      ..onTap = () async {
                        final url = Uri.parse('https://www.omi.me/pages/privacy');
                        if (await canLaunchUrl(url)) {
                          await launchUrl(url, mode: LaunchMode.externalApplication);
                        }
                      },
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _shortcutsHint(BuildContext context) => _searchHintSupported
      ? '${context.l10n.siriShortcutsSetupHint('Ask Omi', 'Question for Omi')}'
          '${context.l10n.siriShortcutsSearchHint('Search Omi')}'
      : context.l10n.siriShortcutsSetupHint('Ask Omi', 'Question for Omi');

  String _getAccessDescription(BuildContext context, App app) {
    List<String> accessTypes = [];
    if (app.hasConversationsAccess()) {
      accessTypes.add(context.l10n.conversations);
    }
    if (app.hasMemoriesAccess()) {
      accessTypes.add(context.l10n.memories);
    }

    String accessDescription = '';
    if (accessTypes.isNotEmpty) {
      accessDescription = context.l10n.accessesDataTypes(accessTypes.join(' & '));
    }

    final trigger = app.externalIntegration?.getTriggerOnString();
    String triggerDescription = '';
    if (trigger != null && trigger != 'Unknown') {
      triggerDescription = context.l10n.triggeredByType(trigger.toLowerCase());
    }

    if (accessDescription.isNotEmpty && triggerDescription.isNotEmpty) {
      return context.l10n.accessesAndTriggeredBy(accessDescription, triggerDescription);
    }
    if (accessDescription.isNotEmpty) {
      return '$accessDescription.';
    }
    if (triggerDescription.isNotEmpty) {
      return context.l10n.isTriggeredBy(triggerDescription);
    }

    return context.l10n.noSpecificDataAccessConfigured;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<UserProvider>(
      builder: (context, provider, child) {
        final isLoading = provider.isLoading;
        final isMigrating = provider.isMigrating;

        final classic = Scaffold(
          appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.dataPrivacy)),
          body: Stack(
            children: [
              ListView(
                padding: const EdgeInsets.all(OmiSpacing.md),
                children: [
                  _buildEncryptionBanner(context),
                  if (_isIOS) ...[
                    const SizedBox(height: OmiSpacing.xxl),
                    Container(
                      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
                      child: SwitchListTile(
                        title: Text(context.l10n.siriIndexSetting),
                        subtitle: Text(context.l10n.siriIndexSettingDescription),
                        value: _siriEnabled,
                        onChanged: _setSiriEnabled,
                      ),
                    ),
                    if (_shortcutsHintSupported && _appShortcutsAvailable) ...[
                      const SizedBox(height: OmiSpacing.md),
                      Container(
                        key: const Key('siri_shortcuts_settings'),
                        padding: const EdgeInsets.all(OmiSpacing.md),
                        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(context.l10n.askOmi, style: OmiType.body),
                            const SizedBox(height: OmiSpacing.xs),
                            Text(
                              _shortcutsHint(context),
                              style: OmiType.body.copyWith(color: OmiColors.textSecondary),
                            ),
                            const SizedBox(height: OmiSpacing.md),
                            const SizedBox(height: 50, child: UiKitView(viewType: 'omi/shortcuts_button')),
                          ],
                        ),
                      ),
                    ],
                  ],
                  const SizedBox(height: OmiSpacing.xxl),
                  Consumer<AppProvider>(
                    builder: (context, appProvider, child) {
                      final appsWithDataAccess =
                          appProvider.apps.where((app) => app.enabled && app.worksExternally()).toList();

                      if (appsWithDataAccess.isEmpty) {
                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            OmiSectionHeader(context.l10n.appAccess, subtitle: context.l10n.appAccessDesc),
                            Container(
                              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
                              child: OmiEmptyState(icon: Icons.apps_outlined, title: context.l10n.noAppsExternalAccess),
                            ),
                          ],
                        );
                      }
                      return OmiSettingsGroup(
                        header: context.l10n.appAccess,
                        headerSubtitle: context.l10n.appAccessDesc,
                        children: [
                          for (final app in appsWithDataAccess)
                            OmiSettingsRow(
                              leading: CircleAvatar(radius: 16, backgroundImage: NetworkImage(app.getImageUrl())),
                              title: app.getName(),
                              subtitle: _getAccessDescription(context, app),
                              onTap: () {
                                routeToPage(context, AppDetailPage(app: app, preventAutoOpenHomePage: true));
                              },
                            ),
                        ],
                      );
                    },
                  ),
                  const SizedBox(height: OmiSpacing.xxl),
                ],
              ),
              if (isLoading && !isMigrating)
                Container(
                  color: Colors.black.withValues(alpha: 0.5),
                  child: const Center(child: OmiSpinner(size: OmiSpinnerSize.large)),
                ),
            ],
          ),
        );
        final shortcutsCard = _shortcutsHintSupported && _appShortcutsAvailable;
        // The UIKit Shortcuts button lives in the classic page; the native list carries it only as the
        // host's own ShortcutsLink.
        if (shortcutsCard && !_shortcutsLinkCapable) return classic;
        final l10n = context.l10n;
        final apps = context.watch<AppProvider>().apps.where((app) => app.enabled && app.worksExternally()).toList();
        return IosNativeSurface(
            title: l10n.dataPrivacy,
            fallback: classic,
            loading: isLoading && !isMigrating,
            toolbar: [
              NativeRow('privacy_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).pop())
            ],
            sections: [
              NativeSection('encryption', [
                NativeRow('encryption_info', l10n.dataEncryptedBanner, kind: 'label'),
                NativeRow('privacy_policy', l10n.learnMore, action: (_) async {
                  final url = Uri.parse('https://www.omi.me/pages/privacy');
                  if (await canLaunchUrl(url)) await launchUrl(url, mode: LaunchMode.externalApplication);
                }),
              ]),
              if (_isIOS)
                NativeSection('siri', [
                  NativeRow('siri_index', l10n.siriIndexSetting,
                      kind: 'toggle',
                      subtitle: l10n.siriIndexSettingDescription,
                      value: _siriEnabled,
                      enabled: !isLoading || isMigrating,
                      action: (value) => _setSiriEnabled(value as bool)),
                ]),
              if (_isIOS && shortcutsCard && _shortcutsLinkCapable)
                NativeSection('siri_shortcuts', [
                  NativeRow('siri_shortcuts_hint', l10n.askOmi, kind: 'label', subtitle: _shortcutsHint(context)),
                  NativeRow('siri_shortcuts_link', l10n.askOmi, kind: 'shortcuts_link'),
                ]),
              NativeSection(
                  'app_access',
                  [
                    if (apps.isEmpty) NativeRow('app_access_empty', l10n.noAppsExternalAccess, kind: 'label'),
                    for (final app in apps)
                      NativeRow('app_${app.id}', app.getName(),
                          subtitle: _getAccessDescription(context, app),
                          enabled: !isLoading || isMigrating,
                          action: (_) => routeToPage(context, AppDetailPage(app: app, preventAutoOpenHomePage: true))),
                  ],
                  title: l10n.appAccess,
                  footer: l10n.appAccessDesc),
            ]);
      },
    );
  }
}
