import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/logger.dart';

class BottomNavBar extends StatelessWidget {
  const BottomNavBar({
    super.key,
    required this.onTabTap,
    this.showCenterButton = true,
  });

  final void Function(int index, bool isRepeat) onTabTap;
  final bool showCenterButton;

  @override
  Widget build(BuildContext context) {
    return Consumer2<HomeProvider, DeviceProvider>(
      builder: (context, home, deviceProvider, child) {
        final isOmiDeviceConnected = deviceProvider.isConnected && deviceProvider.connectedDevice != null;

        return Stack(
          children: [
            Align(
              alignment: Alignment.bottomCenter,
              child: Container(
                width: double.infinity,
                height: 100,
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    stops: [0.0, 0.30, 1.0],
                    colors: [
                      Colors.transparent,
                      Color.fromARGB(255, 15, 15, 15),
                      Color.fromARGB(255, 15, 15, 15),
                    ],
                  ),
                ),
                child: Row(
                  children: [
                    // Home tab
                    Expanded(
                      child: InkWell(
                        onTap: () {
                          HapticFeedback.mediumImpact();
                          MixpanelManager().bottomNavigationTabClicked('Home');
                          primaryFocus?.unfocus();
                          onTabTap(0, home.selectedIndex == 0);
                        },
                        child: SizedBox(
                          height: 90,
                          child: Center(
                            child: Icon(
                              FontAwesomeIcons.house,
                              color: home.selectedIndex == 0 ? Colors.white : Colors.grey,
                              size: 26,
                            ),
                          ),
                        ),
                      ),
                    ),
                    // Action Items tab
                    Expanded(
                      child: InkWell(
                        onTap: () {
                          HapticFeedback.mediumImpact();
                          MixpanelManager().bottomNavigationTabClicked('Action Items');
                          primaryFocus?.unfocus();
                          onTabTap(1, home.selectedIndex == 1);
                        },
                        child: SizedBox(
                          height: 90,
                          child: Center(
                            child: Icon(
                              FontAwesomeIcons.listCheck,
                              color: home.selectedIndex == 1 ? Colors.white : Colors.grey,
                              size: 26,
                            ),
                          ),
                        ),
                      ),
                    ),
                    // Center space for record button - only when no OMI device is connected
                    if (showCenterButton && !isOmiDeviceConnected) const SizedBox(width: 80),
                    // Memories tab
                    Expanded(
                      child: InkWell(
                        onTap: () {
                          HapticFeedback.mediumImpact();
                          MixpanelManager().bottomNavigationTabClicked('Memories');
                          primaryFocus?.unfocus();
                          onTabTap(2, home.selectedIndex == 2);
                        },
                        child: SizedBox(
                          height: 90,
                          child: Center(
                            child: Icon(
                              FontAwesomeIcons.brain,
                              color: home.selectedIndex == 2 ? Colors.white : Colors.grey,
                              size: 26,
                            ),
                          ),
                        ),
                      ),
                    ),
                    // Apps tab
                    Expanded(
                      child: InkWell(
                        onTap: () {
                          HapticFeedback.mediumImpact();
                          MixpanelManager().bottomNavigationTabClicked('Apps');
                          primaryFocus?.unfocus();
                          onTabTap(3, home.selectedIndex == 3);
                        },
                        child: SizedBox(
                          height: 90,
                          child: Center(
                            child: Icon(
                              FontAwesomeIcons.puzzlePiece,
                              color: home.selectedIndex == 3 ? Colors.white : Colors.grey,
                              size: 26,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            // Central Record Button - Only show when no OMI device is connected
            if (!isOmiDeviceConnected)
              Positioned(
                left: MediaQuery.of(context).size.width / 2 - 40,
                bottom: 40,
                child: Consumer<CaptureProvider>(
                  builder: (context, captureProvider, child) {
                    final isRecording = captureProvider.recordingState == RecordingState.record;
                    final isInitializing = captureProvider.recordingState == RecordingState.initialising;
                    if (!showCenterButton) {
                      return const SizedBox.shrink();
                    }

                    return GestureDetector(
                      onTap: () async {
                        HapticFeedback.heavyImpact();
                        if (isInitializing) return;
                        await _handleRecordButtonPress(context, captureProvider);
                      },
                      child: Container(
                        width: 80,
                        height: 80,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: isRecording ? Colors.red : Colors.deepPurple,
                          border: Border.all(
                            color: Colors.black,
                            width: 5,
                          ),
                        ),
                        child: isInitializing
                            ? const CircularProgressIndicator(
                                color: Colors.white,
                                strokeWidth: 2,
                              )
                            : Icon(
                                isRecording ? FontAwesomeIcons.stop : FontAwesomeIcons.microphone,
                                color: Colors.white,
                                size: 24,
                              ),
                      ),
                    );
                  },
                ),
              ),
          ],
        );
      },
    );
  }

  Future<void> _handleRecordButtonPress(BuildContext context, CaptureProvider captureProvider) async {
    final recordingState = captureProvider.recordingState;

    if (recordingState == RecordingState.record) {
      await captureProvider.stopStreamRecording();
      captureProvider.forceProcessingCurrentConversation();
      MixpanelManager().phoneMicRecordingStopped();
    } else if (recordingState == RecordingState.initialising) {
      Logger.debug('initialising, have to wait');
    } else {
      await captureProvider.streamRecording();
      MixpanelManager().phoneMicRecordingStarted();

      if (context.mounted) {
        final topConvoId = (captureProvider.conversationProvider?.conversations ?? []).isNotEmpty
            ? captureProvider.conversationProvider!.conversations.first.id
            : null;
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => ConversationCapturingPage(topConversationId: topConvoId),
          ),
        );
      }
    }
  }
}
