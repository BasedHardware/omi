import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/services/integrations/apple_health_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Apple Health's brand pink, used only for its own feature icons.
const Color _healthPink = Color(0xFFFF2D55); // omi-ux-allow: color-literal -- Apple Health brand colour

class AppleHealthDetailPage extends StatefulWidget {
  const AppleHealthDetailPage({super.key});

  @override
  State<AppleHealthDetailPage> createState() => _AppleHealthDetailPageState();
}

class _AppleHealthDetailPageState extends State<AppleHealthDetailPage> {
  bool _isConnecting = false;
  bool _isDisconnecting = false;

  Future<void> _connect() async {
    final service = AppleHealthService();
    if (!service.isAvailable) {
      OmiFeedback.error(context, context.l10n.appleHealthNotAvailable);
      return;
    }

    setState(() => _isConnecting = true);
    final integrationProvider = context.read<IntegrationProvider>();

    PlatformManager.instance.analytics.integrationConnectAttempted(integrationName: 'Apple Health');
    final result = await service.connect();

    if (!mounted) return;

    if (result.isSuccess) {
      PlatformManager.instance.analytics.integrationConnectSucceeded(integrationName: 'Apple Health');
      final synced = await service.syncHealthDataToBackend(days: 7);
      if (synced) {
        Logger.debug('✓ Apple Health data synced to backend');
      } else {
        Logger.debug('⚠ Failed to sync Apple Health data, but connection succeeded');
      }
      await integrationProvider.saveConnection(IntegrationApp.appleHealth.key, {});
      if (!mounted) return;
      OmiFeedback.confirm(context, result.message);
    } else {
      PlatformManager.instance.analytics.integrationConnectFailed(integrationName: 'Apple Health');
      if (result == AppleHealthResult.permissionDenied) {
        unawaited(
          showOmiAlert(context,
              title: context.l10n.appleHealthDeniedTitle, message: context.l10n.appleHealthDeniedBody),
        );
      } else {
        OmiFeedback.error(context, result.message);
      }
    }

    if (mounted) setState(() => _isConnecting = false);
  }

  /// Confirms first; the button shows its spinner only while the disconnect itself runs.
  Future<void> _disconnect() async {
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.disconnectAppTitle(IntegrationApp.appleHealth.displayName),
      message: context.l10n.disconnectAppMessage(IntegrationApp.appleHealth.displayName),
      confirmLabel: context.l10n.disconnect,
      destructive: true,
    );
    if (!confirmed || !mounted) return;

    final integrationProvider = context.read<IntegrationProvider>();
    setState(() => _isDisconnecting = true);
    final success = await integrationProvider.deleteConnection(IntegrationApp.appleHealth.key);
    if (!mounted) return;
    setState(() => _isDisconnecting = false);
    if (success) {
      PlatformManager.instance.analytics.integrationDisconnected(integrationName: 'Apple Health');
      OmiFeedback.confirm(context, context.l10n.disconnectedFrom(IntegrationApp.appleHealth.displayName));
    } else {
      OmiFeedback.error(context, context.l10n.failedToDisconnect);
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<IntegrationProvider>();
    final isConnected = provider.isAppConnected(IntegrationApp.appleHealth);

    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton()),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, 0, OmiSpacing.xl, OmiSpacing.xl),
          child: Column(
            children: [
              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    children: [
                      const SizedBox(height: OmiSpacing.lg),
                      _logoPair(),
                      const SizedBox(height: OmiSpacing.xxl),
                      Text(context.l10n.appleHealthConnectCta, style: OmiType.title2, textAlign: TextAlign.center),
                      if (isConnected) ...[
                        const SizedBox(height: 10),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Container(
                              width: 8,
                              height: 8,
                              decoration: const BoxDecoration(color: OmiColors.success, shape: BoxShape.circle),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              context.l10n.appleHealthConnectedBadge,
                              style: OmiType.footnote.copyWith(color: OmiColors.success, fontWeight: FontWeight.w500),
                            ),
                          ],
                        ),
                      ],
                      const SizedBox(height: 48),
                      _buildFeatureRow(
                        icon: Icons.chat_bubble_outline,
                        title: context.l10n.appleHealthFeatureChatTitle,
                        description: context.l10n.appleHealthFeatureChatDesc,
                      ),
                      const SizedBox(height: OmiSpacing.xl),
                      _buildFeatureRow(
                        icon: Icons.lock_outline,
                        title: context.l10n.appleHealthFeatureReadOnlyTitle,
                        description: context.l10n.appleHealthFeatureReadOnlyDesc,
                      ),
                      const SizedBox(height: OmiSpacing.xl),
                      _buildFeatureRow(
                        icon: Icons.cloud_sync_outlined,
                        title: context.l10n.appleHealthFeatureSecureTitle,
                        description: context.l10n.appleHealthFeatureSecureDesc,
                      ),
                      const SizedBox(height: OmiSpacing.xl),
                    ],
                  ),
                ),
              ),
              Text(
                context.l10n.appleHealthManageNote,
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.4),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: OmiSpacing.md),
              if (isConnected)
                OmiButton.destructive(
                  label: context.l10n.appleHealthDisconnectCta,
                  // Not the future: the spinner covers the disconnect, not the confirm dialog.
                  onPressed: _isConnecting ? null : () => unawaited(_disconnect()),
                  isLoading: _isDisconnecting,
                  expand: true,
                )
              else
                OmiButton(
                  label: context.l10n.appleHealthConnectCta,
                  onPressed: _connect,
                  isLoading: _isConnecting,
                  expand: true,
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _logoPair() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const SizedBox(width: 18),
        Container(
          padding: const EdgeInsets.all(10),
          decoration: const BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
          child: Image.asset(Assets.images.herologo.path, width: 36, color: OmiColors.onAccent),
        ),
        Transform.translate(
          offset: const Offset(-18, 0),
          child: Container(
            padding: const EdgeInsets.all(10),
            decoration: const BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
            child: ClipOval(
              child: Image.asset(
                'assets/integration_app_logos/apple-health-logo.png',
                width: 36,
                height: 36,
                fit: BoxFit.contain,
                errorBuilder: (_, __, ___) => Container(
                  width: 36,
                  height: 36,
                  decoration: const BoxDecoration(color: _healthPink, shape: BoxShape.circle),
                  child: const Icon(Icons.favorite, color: OmiColors.textPrimary, size: 22),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildFeatureRow({required IconData icon, required String title, required String description}) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: _healthPink.withValues(alpha: 0.12),
            borderRadius: OmiRadius.smAll,
          ),
          child: Icon(icon, color: _healthPink, size: 22),
        ),
        const SizedBox(width: OmiSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w500)),
              const SizedBox(height: OmiSpacing.xxs),
              Text(description, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.35)),
            ],
          ),
        ),
      ],
    );
  }
}
