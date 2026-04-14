import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/services/apple_health_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/widgets/animated_loading_button.dart';

class AppleHealthDetailPage extends StatefulWidget {
  const AppleHealthDetailPage({super.key});

  @override
  State<AppleHealthDetailPage> createState() => _AppleHealthDetailPageState();
}

class _AppleHealthDetailPageState extends State<AppleHealthDetailPage> {
  bool _isConnecting = false;

  Future<void> _connect() async {
    final service = AppleHealthService();
    if (!service.isAvailable) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(context.l10n.appleHealthNotAvailable),
          backgroundColor: Colors.red,
          duration: const Duration(seconds: 3),
        ),
      );
      return;
    }

    setState(() => _isConnecting = true);
    final scaffoldMessenger = ScaffoldMessenger.of(context);
    final integrationProvider = context.read<IntegrationProvider>();

    MixpanelManager().integrationConnectAttempted(integrationName: 'Apple Health');
    final result = await service.connect();

    if (!mounted) return;

    if (result.isSuccess) {
      MixpanelManager().integrationConnectSucceeded(integrationName: 'Apple Health');
      final synced = await service.syncHealthDataToBackend(days: 7);
      if (synced) {
        Logger.debug('✓ Apple Health data synced to backend');
      } else {
        Logger.debug('⚠ Failed to sync Apple Health data, but connection succeeded');
      }
      await integrationProvider.saveConnection(IntegrationApp.appleHealth.key, {});
      if (!mounted) return;
      scaffoldMessenger.showSnackBar(
        SnackBar(content: Text(result.message), duration: const Duration(seconds: 2)),
      );
    } else {
      MixpanelManager().integrationConnectFailed(integrationName: 'Apple Health');
      if (result == AppleHealthResult.permissionDenied) {
        _showDeniedDialog();
      } else {
        scaffoldMessenger.showSnackBar(
          SnackBar(
            content: Text(result.message),
            backgroundColor: Colors.red,
            duration: const Duration(seconds: 3),
          ),
        );
      }
    }

    if (mounted) setState(() => _isConnecting = false);
  }

  Future<void> _showDeniedDialog() async {
    await showDialog<void>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Text(
            context.l10n.appleHealthDeniedTitle,
            style: const TextStyle(color: Colors.white),
          ),
          content: Text(
            context.l10n.appleHealthDeniedBody,
            style: const TextStyle(color: Color(0xFF8E8E93), height: 1.4),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text(context.l10n.ok, style: const TextStyle(color: Colors.white)),
            ),
          ],
        );
      },
    );
  }

  Future<void> _disconnect() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Text(
            context.l10n.disconnectAppTitle(IntegrationApp.appleHealth.displayName),
            style: const TextStyle(color: Colors.white),
          ),
          content: Text(
            context.l10n.disconnectAppMessage(IntegrationApp.appleHealth.displayName),
            style: const TextStyle(color: Color(0xFF8E8E93)),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: Text(context.l10n.cancel, style: const TextStyle(color: Color(0xFF8E8E93))),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: Text(context.l10n.disconnect, style: const TextStyle(color: Colors.red)),
            ),
          ],
        );
      },
    );
    if (confirmed != true || !mounted) return;

    final integrationProvider = context.read<IntegrationProvider>();
    final scaffoldMessenger = ScaffoldMessenger.of(context);

    final success = await integrationProvider.deleteConnection(IntegrationApp.appleHealth.key);
    if (!mounted) return;
    if (success) {
      MixpanelManager().integrationDisconnected(integrationName: 'Apple Health');
      scaffoldMessenger.showSnackBar(
        SnackBar(
          content: Text(context.l10n.disconnectedFrom(IntegrationApp.appleHealth.displayName)),
          duration: const Duration(seconds: 2),
        ),
      );
    } else {
      scaffoldMessenger.showSnackBar(
        SnackBar(
          content: Text(context.l10n.failedToDisconnect),
          backgroundColor: Colors.red,
          duration: const Duration(seconds: 3),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<IntegrationProvider>();
    final isConnected = provider.isAppConnected(IntegrationApp.appleHealth);

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
          child: Column(
            children: [
              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    children: [
                      const SizedBox(height: 20),
                      _logoPair(),
                      const SizedBox(height: 32),
                      Text(
                        context.l10n.appleHealthConnectCta,
                        style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Colors.white),
                        textAlign: TextAlign.center,
                      ),
                      if (isConnected) ...[
                        const SizedBox(height: 10),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Container(
                              width: 8,
                              height: 8,
                              decoration: const BoxDecoration(color: Colors.greenAccent, shape: BoxShape.circle),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              context.l10n.appleHealthConnectedBadge,
                              style: const TextStyle(
                                color: Colors.greenAccent,
                                fontSize: 13,
                                fontWeight: FontWeight.w500,
                              ),
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
                      const SizedBox(height: 24),
                      _buildFeatureRow(
                        icon: Icons.lock_outline,
                        title: context.l10n.appleHealthFeatureReadOnlyTitle,
                        description: context.l10n.appleHealthFeatureReadOnlyDesc,
                      ),
                      const SizedBox(height: 24),
                      _buildFeatureRow(
                        icon: Icons.cloud_sync_outlined,
                        title: context.l10n.appleHealthFeatureSecureTitle,
                        description: context.l10n.appleHealthFeatureSecureDesc,
                      ),
                      const SizedBox(height: 24),
                    ],
                  ),
                ),
              ),
              Text(
                context.l10n.appleHealthManageNote,
                style: TextStyle(color: Colors.grey[400], fontSize: 13, height: 1.4),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              AnimatedLoadingButton(
                text: isConnected ? context.l10n.appleHealthDisconnectCta : context.l10n.appleHealthConnectCta,
                loaderColor: isConnected ? Colors.white : Colors.black,
                color: isConnected ? Colors.red.withOpacity(0.15) : Colors.white,
                textStyle: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: isConnected ? Colors.red : Colors.black,
                ),
                width: MediaQuery.of(context).size.width * 0.8,
                onPressed: _isConnecting ? () async {} : (isConnected ? _disconnect : _connect),
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
          decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
          child: Image.asset(Assets.images.herologo.path, width: 36, color: Colors.black),
        ),
        Transform.translate(
          offset: const Offset(-18, 0),
          child: Container(
            padding: const EdgeInsets.all(10),
            decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
            child: ClipOval(
              child: Image.asset(
                'assets/integration_app_logos/apple-health-logo.png',
                width: 36,
                height: 36,
                fit: BoxFit.contain,
                errorBuilder: (_, __, ___) => Container(
                  width: 36,
                  height: 36,
                  decoration: const BoxDecoration(color: Color(0xFFFF2D55), shape: BoxShape.circle),
                  child: const Icon(Icons.favorite, color: Colors.white, size: 22),
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
            color: const Color(0xFFFF2D55).withOpacity(0.12),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(icon, color: const Color(0xFFFF2D55), size: 22),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w500, color: Colors.white),
              ),
              const SizedBox(height: 4),
              Text(description, style: TextStyle(fontSize: 14, color: Colors.grey[400], height: 1.35)),
            ],
          ),
        ),
      ],
    );
  }
}
