import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/meta_wearables_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/meta_wearables_device_label.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// Management screen for Meta glasses connected through the Wearables Device
/// Access Toolkit. Lists every paired pair (multi-device), lets the user pick
/// the active one, and drives registration/unregistration with the Meta AI
/// app.
class MetaGlassesPage extends StatefulWidget {
  const MetaGlassesPage({super.key});

  @override
  State<MetaGlassesPage> createState() => _MetaGlassesPageState();
}

class _MetaGlassesPageState extends State<MetaGlassesPage> {
  /// The live preview is opt-in: rendering the stream texture costs real CPU
  /// and made the whole page lag, while photo capture works fine without it.
  bool _showPreview = false;
  MetaGlassesHealth? _dismissedHealthWarning;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        final provider = context.read<MetaWearablesProvider>();
        provider.init().then((_) => provider.refresh());
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0D0D),
        elevation: 0,
        leading: Padding(
          padding: const EdgeInsets.only(left: 12),
          child: GestureDetector(
            onTap: () => Navigator.of(context).pop(),
            child: Container(
              width: 36,
              height: 36,
              decoration: const BoxDecoration(color: Color(0xFF1F1F25), shape: BoxShape.circle),
              child: const Icon(FontAwesomeIcons.chevronLeft, size: 16, color: Colors.white70),
            ),
          ),
        ),
        title: Text(
          context.l10n.metaGlasses,
          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
        centerTitle: true,
      ),
      body: Consumer<MetaWearablesProvider>(
        builder: (context, provider, child) {
          if (provider.health == MetaGlassesHealth.ok) _dismissedHealthWarning = null;
          return ListView(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            children: [
              const SizedBox(height: 24),
              Center(
                child: Image.asset(Assets.images.omiGlass.path, width: 160, height: 160, fit: BoxFit.contain),
              ),
              const SizedBox(height: 16),
              Text(
                context.l10n.pairingTitleMetaGlasses,
                style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w700),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                _statusText(context, provider),
                style: const TextStyle(color: ResponsiveHelper.textTertiary, fontSize: 15, height: 1.4),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              if (provider.isRegistered && provider.hasDevices) ...[
                ..._deviceList(context, provider),
                const SizedBox(height: 16),
                _captureModeSelector(context, provider),
                const SizedBox(height: 12),
                if (provider.captureMode == MetaGlassesCaptureMode.cameraAndMic) ...[
                  _captureFrequencyRow(context, provider),
                  const SizedBox(height: 12),
                ],
                _autoCaptureRow(context, provider),
                const SizedBox(height: 12),
                _gesturesSection(context, provider),
                const SizedBox(height: 12),
                if (provider.isCapturing && provider.previewTextureId != null) ...[
                  _previewToggleRow(context, provider),
                  if (_showPreview) ...[
                    const SizedBox(height: 8),
                    _livePreview(context, provider),
                  ],
                  const SizedBox(height: 12),
                ],
                if (provider.pendingPhotoCount > 0) ...[
                  _pendingPhotosRow(context, provider),
                  const SizedBox(height: 12),
                ],
                if (provider.health != MetaGlassesHealth.ok && _dismissedHealthWarning != provider.health) ...[
                  _healthWarningRow(context, provider),
                  const SizedBox(height: 12),
                ],
                _captureButton(context, provider),
                const SizedBox(height: 16),
              ],
              if (provider.isRegistered && !provider.cameraPermissionGranted) _cameraPermissionCard(context, provider),
              const SizedBox(height: 8),
              _primaryButton(context, provider),
              if (provider.isRegistered) ...[
                const SizedBox(height: 12),
                _unpairButton(context, provider),
              ],
              if (provider.lastError != null) ...[
                const SizedBox(height: 16),
                Text(
                  provider.lastError!,
                  style: const TextStyle(color: Colors.redAccent, fontSize: 13),
                  textAlign: TextAlign.center,
                ),
              ],
              SizedBox(height: MediaQuery.of(context).padding.bottom + 24),
            ],
          );
        },
      ),
    );
  }

  String _statusText(BuildContext context, MetaWearablesProvider provider) {
    switch (provider.registrationState) {
      case RegistrationState.unavailable:
        return context.l10n.metaGlassesUnavailable;
      case RegistrationState.available:
        return context.l10n.pairingDescMetaGlasses;
      case RegistrationState.registering:
        return context.l10n.metaGlassesRegistering;
      case RegistrationState.registered:
        return context.l10n.connected;
    }
  }

  List<Widget> _deviceList(BuildContext context, MetaWearablesProvider provider) {
    return provider.devices.map((device) {
      final selected = provider.isSelected(device);
      final active = provider.isActive(device);
      final needsUpdate = provider.hasCompatibilityUpdateAction(device);
      return GestureDetector(
        onTap: () => provider.selectDevice(device.uuid),
        child: Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: selected ? Colors.white : Colors.transparent, width: 1),
          ),
          child: Row(
            children: [
              Image.asset(Assets.images.omiGlass.path, width: 36, height: 36, fit: BoxFit.contain),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      device.name.isNotEmpty ? device.name : context.l10n.metaGlasses,
                      style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                    ),
                    Text(
                      metaWearablesDeviceKindLabel(context.l10n, device.kind),
                      style: const TextStyle(color: Colors.white54, fontSize: 12),
                    ),
                    Text(
                      _deviceStatusText(context, device),
                      style: TextStyle(color: _deviceStatusColor(device), fontSize: 12),
                    ),
                    if (active)
                      Text(
                        context.l10n.active,
                        style: const TextStyle(color: Colors.greenAccent, fontSize: 12),
                      ),
                    if (needsUpdate)
                      Wrap(
                        crossAxisAlignment: WrapCrossAlignment.center,
                        spacing: 8,
                        children: [
                          Text(
                            context.l10n.firmwareUpdateAvailable,
                            style: const TextStyle(color: Colors.orangeAccent, fontSize: 12),
                          ),
                          TextButton(
                            onPressed: () => provider.openCompatibilityUpdate(device),
                            style: TextButton.styleFrom(
                              foregroundColor: Colors.orangeAccent,
                              minimumSize: Size.zero,
                              padding: EdgeInsets.zero,
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            ),
                            child: Text(context.l10n.update),
                          ),
                        ],
                      ),
                  ],
                ),
              ),
              if (selected) const Icon(Icons.check_circle, color: Colors.white, size: 20),
            ],
          ),
        ),
      );
    }).toList();
  }

  String _deviceStatusText(BuildContext context, DeviceInfo device) {
    switch (device.linkState) {
      case DeviceLinkState.connected:
      case DeviceLinkState.unknown:
        return context.l10n.connected;
      case DeviceLinkState.connecting:
        return context.l10n.searching;
      case DeviceLinkState.disconnected:
        return context.l10n.metaGlassesPairInMetaAI;
    }
  }

  Color _deviceStatusColor(DeviceInfo device) {
    switch (device.linkState) {
      case DeviceLinkState.connected:
      case DeviceLinkState.unknown:
        return Colors.greenAccent;
      case DeviceLinkState.connecting:
        return Colors.white54;
      case DeviceLinkState.disconnected:
        return Colors.orangeAccent;
    }
  }

  Widget _autoCaptureRow(BuildContext context, MetaWearablesProvider provider) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      decoration: BoxDecoration(color: ResponsiveHelper.backgroundTertiary, borderRadius: BorderRadius.circular(16)),
      child: Row(
        children: [
          const Icon(Icons.autorenew, color: Colors.white70, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              context.l10n.metaGlassesAutoCapture,
              style: const TextStyle(color: Colors.white, fontSize: 14),
            ),
          ),
          Switch(
            value: provider.autoCaptureEnabled,
            onChanged: (value) => provider.setAutoCaptureEnabled(value),
            activeThumbColor: Colors.white,
            activeTrackColor: Colors.greenAccent.shade700,
          ),
        ],
      ),
    );
  }

  String _intervalLabel(BuildContext context, MetaGlassesCaptureInterval i) {
    switch (i) {
      case MetaGlassesCaptureInterval.s10:
        return context.l10n.metaGlassesEvery10s;
      case MetaGlassesCaptureInterval.s30:
        return context.l10n.metaGlassesEvery30s;
      case MetaGlassesCaptureInterval.m1:
        return context.l10n.metaGlassesEvery1min;
      case MetaGlassesCaptureInterval.m5:
        return context.l10n.metaGlassesEvery5min;
    }
  }

  Widget _captureFrequencyRow(BuildContext context, MetaWearablesProvider provider) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(color: ResponsiveHelper.backgroundTertiary, borderRadius: BorderRadius.circular(16)),
      child: Row(
        children: [
          const Icon(Icons.timer_outlined, color: Colors.white70, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              context.l10n.metaGlassesCaptureFrequency,
              style: const TextStyle(color: Colors.white, fontSize: 14),
            ),
          ),
          DropdownButton<MetaGlassesCaptureInterval>(
            value: provider.captureInterval,
            dropdownColor: ResponsiveHelper.backgroundTertiary,
            underline: const SizedBox.shrink(),
            style: const TextStyle(color: Colors.white, fontSize: 14),
            icon: const Icon(Icons.arrow_drop_down, color: Colors.white70),
            items: MetaGlassesCaptureInterval.values
                .map((i) => DropdownMenuItem(value: i, child: Text(_intervalLabel(context, i))))
                .toList(),
            onChanged: (value) {
              if (value != null) provider.setCaptureInterval(value);
            },
          ),
        ],
      ),
    );
  }

  Widget _gesturesSection(BuildContext context, MetaWearablesProvider provider) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(color: ResponsiveHelper.backgroundTertiary, borderRadius: BorderRadius.circular(16)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.touch_app_outlined, color: Colors.white70, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.metaGlassesGestures,
                  style: const TextStyle(color: Colors.white, fontSize: 14),
                ),
                const SizedBox(height: 4),
                Text(
                  context.l10n.metaGlassesGestureHint,
                  style: const TextStyle(color: ResponsiveHelper.textTertiary, fontSize: 13),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _previewToggleRow(BuildContext context, MetaWearablesProvider provider) {
    return GestureDetector(
      onTap: () {
        setState(() => _showPreview = !_showPreview);
        provider.setLivePreviewVisible(_showPreview);
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(color: ResponsiveHelper.backgroundTertiary, borderRadius: BorderRadius.circular(16)),
        child: Row(
          children: [
            Icon(_showPreview ? Icons.visibility : Icons.visibility_off, color: Colors.white70, size: 20),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                context.l10n.metaGlassesShowPreview,
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
            Icon(_showPreview ? Icons.expand_less : Icons.expand_more, color: Colors.white38, size: 18),
          ],
        ),
      ),
    );
  }

  Widget _pendingPhotosRow(BuildContext context, MetaWearablesProvider provider) {
    return GestureDetector(
      onTap: () => provider.flushPhotoQueue(),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(color: ResponsiveHelper.backgroundTertiary, borderRadius: BorderRadius.circular(16)),
        child: Row(
          children: [
            const Icon(Icons.cloud_upload_outlined, color: Colors.orangeAccent, size: 20),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                context.l10n.metaGlassesPendingPhotos(provider.pendingPhotoCount),
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
            const Icon(Icons.refresh, color: Colors.white38, size: 18),
          ],
        ),
      ),
    );
  }

  Widget _healthWarningRow(BuildContext context, MetaWearablesProvider provider) {
    final overheating = provider.health == MetaGlassesHealth.overheating;
    final message = overheating ? context.l10n.metaGlassesOverheating : context.l10n.metaGlassesFolded;
    final icon = overheating ? Icons.thermostat : Icons.visibility_off;
    return Dismissible(
      key: ValueKey(provider.health),
      direction: DismissDirection.endToStart,
      onDismissed: (_) => setState(() => _dismissedHealthWarning = provider.health),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: Colors.orangeAccent.withValues(alpha: 0.12),
          border: Border.all(color: Colors.orangeAccent.withValues(alpha: 0.35)),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            Icon(icon, color: Colors.orangeAccent, size: 20),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                message,
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
            const Icon(Icons.close, color: Colors.white38, size: 18),
          ],
        ),
      ),
    );
  }

  Widget _livePreview(BuildContext context, MetaWearablesProvider provider) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Stack(
        alignment: Alignment.bottomRight,
        children: [
          AspectRatio(
            aspectRatio: provider.previewAspectRatio,
            child: Texture(textureId: provider.previewTextureId!),
          ),
          Padding(
            padding: const EdgeInsets.all(10),
            child: GestureDetector(
              onTap: () => provider.captureGlassesPhotoNow(),
              child: Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(color: Colors.black.withValues(alpha: 0.5), shape: BoxShape.circle),
                child: const Icon(Icons.photo_camera, color: Colors.white, size: 22),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _captureModeSelector(BuildContext context, MetaWearablesProvider provider) {
    Widget option(MetaGlassesCaptureMode mode, IconData icon, String label) {
      final selected = provider.captureMode == mode;
      return Expanded(
        child: GestureDetector(
          onTap: () => provider.setCaptureMode(mode),
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(
              color: selected ? Colors.white : Colors.transparent,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              children: [
                Icon(icon, size: 18, color: selected ? Colors.black : Colors.white70),
                const SizedBox(height: 4),
                Text(
                  label,
                  style: TextStyle(
                    color: selected ? Colors.black : Colors.white70,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          context.l10n.metaGlassesCaptureModeLabel,
          style: const TextStyle(color: ResponsiveHelper.textTertiary, fontSize: 13, fontWeight: FontWeight.w500),
        ),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            children: [
              option(
                MetaGlassesCaptureMode.cameraAndMic,
                Icons.photo_camera_outlined,
                context.l10n.metaGlassesModeCameraMic,
              ),
              const SizedBox(width: 4),
              option(MetaGlassesCaptureMode.micOnly, Icons.mic_none, context.l10n.metaGlassesModeMicOnly),
            ],
          ),
        ),
      ],
    );
  }

  Widget _captureButton(BuildContext context, MetaWearablesProvider provider) {
    final capturing = provider.isCapturing;
    return SizedBox(
      width: double.infinity,
      height: 52,
      child: ElevatedButton.icon(
        onPressed: () async {
          if (capturing) {
            await provider.stopCapture();
          } else {
            await provider.startCapture(context.read<CaptureProvider>(), displayStatusText: context.l10n.listening);
          }
        },
        style: ElevatedButton.styleFrom(
          backgroundColor: capturing ? Colors.redAccent : Colors.white,
          foregroundColor: capturing ? Colors.white : Colors.black,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
          elevation: 0,
        ),
        icon: Icon(capturing ? Icons.stop : Icons.fiber_manual_record, size: 18),
        label: Text(
          capturing ? context.l10n.metaGlassesStopCapture : context.l10n.metaGlassesStartCapture,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
      ),
    );
  }

  Widget _cameraPermissionCard(BuildContext context, MetaWearablesProvider provider) {
    return GestureDetector(
      onTap: provider.isRequestingCameraPermission ? null : () => provider.requestCameraPermission(),
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundTertiary,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            provider.isRequestingCameraPermission
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white70),
                  )
                : const Icon(Icons.photo_camera_outlined, color: Colors.white70, size: 20),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                context.l10n.metaGlassesCameraPermission,
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
            if (!provider.isRequestingCameraPermission)
              const Icon(FontAwesomeIcons.chevronRight, size: 14, color: Colors.white38),
          ],
        ),
      ),
    );
  }

  Widget _primaryButton(BuildContext context, MetaWearablesProvider provider) {
    final busy = provider.isRegistering || provider.registrationState == RegistrationState.registering;
    return SizedBox(
      width: double.infinity,
      height: 52,
      child: ElevatedButton(
        onPressed: busy || provider.isRegistered
            ? null
            : () async {
                await provider.startRegistration();
              },
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.white,
          foregroundColor: Colors.black,
          disabledBackgroundColor: Colors.white24,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
          elevation: 0,
        ),
        child: busy
            ? const SizedBox(
                width: 20,
                height: 20,
                child:
                    CircularProgressIndicator(strokeWidth: 2, valueColor: AlwaysStoppedAnimation<Color>(Colors.black)),
              )
            : Text(
                provider.isRegistered ? context.l10n.connected : context.l10n.connect,
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
              ),
      ),
    );
  }

  Widget _unpairButton(BuildContext context, MetaWearablesProvider provider) {
    return SizedBox(
      width: double.infinity,
      height: 52,
      child: OutlinedButton(
        onPressed: () => provider.unregister(),
        style: OutlinedButton.styleFrom(
          foregroundColor: Colors.redAccent,
          side: const BorderSide(color: Colors.redAccent, width: 1),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
        ),
        child: Text(
          context.l10n.unpair,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
      ),
    );
  }
}
