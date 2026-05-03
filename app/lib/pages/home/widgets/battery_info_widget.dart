import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/pages/phone_calls/phone_calls_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

class BatteryInfoWidget extends StatefulWidget {
  const BatteryInfoWidget({super.key});

  @override
  State<BatteryInfoWidget> createState() => _BatteryInfoWidgetState();
}

class _BatteryInfoWidgetState extends State<BatteryInfoWidget> {
  void _showRecordOptions(BuildContext context) {
    HapticFeedback.lightImpact();
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (sheetContext) => _RecordOptionsSheet(
        onPickPhoneMic: () {
          Navigator.pop(sheetContext);
          _startRecording(context);
        },
        onPickPhoneCall: () {
          Navigator.pop(sheetContext);
          if (!context.mounted) return;
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const PhoneCallsPage()),
          );
        },
      ),
    );
  }

  Future<void> _startRecording(BuildContext context) async {
    HapticFeedback.mediumImpact();
    final captureProvider = context.read<CaptureProvider>();
    if (captureProvider.recordingState == RecordingState.initialising) return;
    if (captureProvider.recordingState == RecordingState.record) {
      await captureProvider.stopStreamRecording();
      captureProvider.forceProcessingCurrentConversation();
      MixpanelManager().phoneMicRecordingStopped();
      return;
    }
    await captureProvider.streamRecording();
    MixpanelManager().phoneMicRecordingStarted();
    if (context.mounted) {
      final topConvoId = (captureProvider.conversationProvider?.conversations ?? []).isNotEmpty
          ? captureProvider.conversationProvider!.conversations.first.id
          : null;
      Navigator.push(
        context,
        MaterialPageRoute(builder: (context) => ConversationCapturingPage(topConversationId: topConvoId)),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Selector<HomeProvider, bool>(
      selector: (context, state) => state.selectedIndex == 0,
      builder: (context, isMemoriesPage, child) {
        // Use Selector to only rebuild when battery level, connected device, or connecting state changes
        // This reduces battery drain by avoiding unnecessary rebuilds during other provider updates
        return Selector<DeviceProvider, (int, BtDevice?, BtDevice?, bool, bool)>(
          selector: (_, provider) => (
            provider.batteryLevel,
            provider.connectedDevice,
            provider.pairedDevice,
            provider.isConnecting,
            provider.isCharging
          ),
          builder: (context, data, child) {
            final (batteryLevel, connectedDevice, pairedDevice, isConnecting, isCharging) = data;
            if (connectedDevice != null) {
              final batteryPill = GestureDetector(
                onTap: () {
                  routeToPage(context, const ConnectedDevice());
                  MixpanelManager().batteryIndicatorClicked();
                },
                child: Container(
                  height: 36,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                  decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(18)),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      // Add device icon
                      SizedBox(
                        width: 16,
                        height: 16,
                        child: Image.asset(
                          DeviceUtils.getDeviceImagePath(
                            deviceType: connectedDevice.type,
                            modelNumber: connectedDevice.modelNumber,
                            deviceName: connectedDevice.name,
                          ),
                          fit: BoxFit.contain,
                        ),
                      ),
                      // Only show battery indicator and percentage when battery level is valid (> 0)
                      if (batteryLevel > 0) ...[
                        const SizedBox(width: 6.0),
                        if (isCharging)
                          const Icon(Icons.bolt, color: Color.fromARGB(255, 0, 255, 8), size: 14)
                        else
                          Container(
                            width: 8,
                            height: 8,
                            decoration: BoxDecoration(
                              color: batteryLevel > 75
                                  ? const Color.fromARGB(255, 0, 255, 8)
                                  : batteryLevel > 20
                                      ? Colors.yellow.shade700
                                      : Colors.red,
                              shape: BoxShape.circle,
                            ),
                          ),
                        const SizedBox(width: 4.0),
                        Text(
                          '$batteryLevel%',
                          style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
                        ),
                      ],
                    ],
                  ),
                ),
              );
              if (!isMemoriesPage) return batteryPill;
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  batteryPill,
                  const SizedBox(width: 8),
                  GestureDetector(
                    onTap: () {
                      HapticFeedback.lightImpact();
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => const PhoneCallsPage()),
                      );
                    },
                    child: Container(
                      height: 36,
                      width: 36,
                      decoration: BoxDecoration(
                        color: const Color(0xFF1F1F25),
                        borderRadius: BorderRadius.circular(18),
                      ),
                      child: const Icon(
                        Icons.phone_in_talk_rounded,
                        color: Colors.white,
                        size: 16,
                      ),
                    ),
                  ),
                ],
              );
            } else if (pairedDevice != null && pairedDevice.id.isNotEmpty) {
              // Device is paired but disconnected
              return GestureDetector(
                onTap: () async {
                  await routeToPage(context, const ConnectedDevice());
                },
                child: Container(
                  height: 36,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                  decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(18)),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      // Device icon with slash line
                      SizedBox(
                        width: 16,
                        height: 16,
                        child: Stack(
                          children: [
                            Image.asset(
                              DeviceUtils.getDeviceImageFromBtDevice(pairedDevice),
                              fit: BoxFit.contain,
                            ),
                            // Slash line across the image
                            Positioned.fill(child: CustomPaint(painter: SlashLinePainter())),
                          ],
                        ),
                      ),
                      const SizedBox(width: 6.0),
                      Text(
                        context.l10n.disconnected,
                        style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white70, fontSize: 12),
                      ),
                    ],
                  ),
                ),
              );
            } else {
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  GestureDetector(
                    onTap: () async {
                      if (SharedPreferencesUtil().btDevice.id.isEmpty) {
                        routeToPage(context, const ConnectDevicePage());
                        MixpanelManager().connectFriendClicked();
                      } else {
                        await routeToPage(context, const ConnectedDevice());
                      }
                    },
                    child: Container(
                      height: 36,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1F1F25),
                        borderRadius: BorderRadius.circular(18),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Image.asset(Assets.images.logoTransparent.path, width: 16, height: 16),
                          isMemoriesPage ? const SizedBox(width: 6) : const SizedBox.shrink(),
                          isConnecting && isMemoriesPage
                              ? Text(
                                  context.l10n.searching,
                                  style: Theme.of(context)
                                      .textTheme
                                      .bodyMedium!
                                      .copyWith(color: Colors.white, fontSize: 12),
                                )
                              : isMemoriesPage
                                  ? Text(
                                      context.l10n.connect,
                                      style: const TextStyle(color: Colors.white, fontSize: 12),
                                    )
                                  : const SizedBox.shrink(),
                        ],
                      ),
                    ),
                  ),
                  if (isMemoriesPage)
                    Consumer<CaptureProvider>(
                      builder: (context, captureProvider, _) {
                        final isRecording = captureProvider.recordingState == RecordingState.record;
                        final isInitialising = captureProvider.recordingState == RecordingState.initialising;
                        final showChevron = !isRecording && !isInitialising;
                        return Padding(
                          padding: const EdgeInsets.only(left: 8),
                          child: AnimatedContainer(
                            duration: const Duration(milliseconds: 200),
                            height: 36,
                            decoration: BoxDecoration(
                              color: isRecording ? Colors.red.shade700 : Colors.deepPurple,
                              borderRadius: BorderRadius.circular(18),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              crossAxisAlignment: CrossAxisAlignment.center,
                              children: [
                                GestureDetector(
                                  behavior: HitTestBehavior.opaque,
                                  onTap: () => _startRecording(context),
                                  child: Container(
                                    height: 36,
                                    alignment: Alignment.center,
                                    padding: EdgeInsets.fromLTRB(12, 0, showChevron ? 10 : 12, 0),
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      crossAxisAlignment: CrossAxisAlignment.center,
                                      children: [
                                        if (isRecording)
                                          const Icon(Icons.stop_rounded, size: 14, color: Colors.white)
                                        else if (isInitialising)
                                          const SizedBox(
                                            width: 12,
                                            height: 12,
                                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                          )
                                        else
                                          const Icon(FontAwesomeIcons.microphone, size: 12, color: Colors.white),
                                        const SizedBox(width: 6),
                                        Text(
                                          isRecording
                                              ? context.l10n.stop
                                              : isInitialising
                                                  ? '...'
                                                  : context.l10n.record,
                                          style: const TextStyle(
                                              color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                                if (showChevron) ...[
                                  Container(
                                    width: 1,
                                    height: 18,
                                    color: Colors.white.withValues(alpha: 0.25),
                                  ),
                                  GestureDetector(
                                    behavior: HitTestBehavior.opaque,
                                    onTap: () => _showRecordOptions(context),
                                    child: Container(
                                      height: 36,
                                      alignment: Alignment.center,
                                      padding: const EdgeInsets.symmetric(horizontal: 8),
                                      child: const Icon(
                                        Icons.keyboard_arrow_down_rounded,
                                        size: 18,
                                        color: Colors.white,
                                      ),
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                ],
              );
            }
          },
        );
      },
    );
  }
}

class SlashLinePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.red
      ..strokeWidth = 2.0
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    // Position the cross at the bottom right
    final crossSize = size.width * 0.2; // Size of the cross
    final centerX = size.width - crossSize / 2 - 2; // Bottom right positioning
    final centerY = size.height - crossSize / 2 - 2;
    final halfCrossSize = crossSize / 2;

    // Draw the X (cross) - two diagonal lines
    canvas.drawLine(
      Offset(centerX - halfCrossSize, centerY - halfCrossSize),
      Offset(centerX + halfCrossSize, centerY + halfCrossSize),
      paint,
    );

    canvas.drawLine(
      Offset(centerX + halfCrossSize, centerY - halfCrossSize),
      Offset(centerX - halfCrossSize, centerY + halfCrossSize),
      paint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _RecordOptionsSheet extends StatelessWidget {
  final VoidCallback onPickPhoneMic;
  final VoidCallback onPickPhoneCall;

  const _RecordOptionsSheet({
    required this.onPickPhoneMic,
    required this.onPickPhoneCall,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(16, 12, 16, MediaQuery.of(context).padding.bottom + 16),
      decoration: const BoxDecoration(
        color: Color(0xFF1F1F25),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.white24,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 18),
          _RecordOption(
            icon: FontAwesomeIcons.microphone,
            title: context.l10n.recordWithPhoneMic,
            subtitle: context.l10n.recordWithPhoneMicSubtitle,
            onTap: onPickPhoneMic,
          ),
          const SizedBox(height: 10),
          _RecordOption(
            icon: Icons.phone_in_talk_rounded,
            title: context.l10n.phoneCall,
            subtitle: context.l10n.phoneCallSubtitle,
            onTap: onPickPhoneCall,
          ),
        ],
      ),
    );
  }
}

class _RecordOption extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _RecordOption({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();
        onTap();
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: const Color(0xFF2A2A33),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [Color(0xFF7B5CFF), Color(0xFF5733E0)],
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.deepPurple.withValues(alpha: 0.35),
                    blurRadius: 14,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Icon(icon, color: Colors.white, size: 18),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: TextStyle(color: Colors.grey[400], fontSize: 12),
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right_rounded, color: Colors.grey[500], size: 22),
          ],
        ),
      ),
    );
  }
}
