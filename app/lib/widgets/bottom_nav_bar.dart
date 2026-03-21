import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/theme/app_theme.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/logger.dart';

/// Apple HIG Tab Bar Constants
class _TabBarConstants {
  /// Standard tab bar content height (Apple HIG: 49pt)
  static const double contentHeight = 49.0;

  /// Gradient fade height above the tab bar
  static const double gradientFadeHeight = 20.0;

  /// Tab bar icon size (Apple HIG recommends 25-31pt)
  static const double iconSize = 26.0;

  /// Center record button size
  static const double recordButtonSize = 80.0;

  /// Horizontal padding for the tab bar
  static const double horizontalPadding = 20.0;
}

class BottomNavBar extends StatelessWidget {
  const BottomNavBar({super.key, required this.onTabTap, this.showCenterButton = true});

  final void Function(int index, bool isRepeat) onTabTap;
  final bool showCenterButton;

  @override
  Widget build(BuildContext context) {
    // Get the bottom safe area (home indicator area on notched devices)
    final bottomSafeArea = MediaQuery.of(context).padding.bottom;
    // Total height: gradient fade + content height + safe area
    final totalHeight = _TabBarConstants.gradientFadeHeight + _TabBarConstants.contentHeight + bottomSafeArea;

    return Consumer2<HomeProvider, DeviceProvider>(
      builder: (context, home, deviceProvider, child) {
        final isOmiDeviceConnected = deviceProvider.isConnected && deviceProvider.connectedDevice != null;

        return Stack(
          children: [
            Align(
              alignment: Alignment.bottomCenter,
              child: Container(
                width: double.infinity,
                height: totalHeight,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    stops: const [0.0, 0.30, 1.0],
                    colors: [
                      Colors.transparent,
                      const Color.fromARGB(255, 15, 15, 15),
                      const Color.fromARGB(255, 15, 15, 15),
                    ],
                  ),
                ),
                child: Padding(
                  padding: EdgeInsets.only(
                    left: _TabBarConstants.horizontalPadding,
                    right: _TabBarConstants.horizontalPadding,
                    top: _TabBarConstants.gradientFadeHeight,
                    bottom: bottomSafeArea, // Safe area for home indicator
                  ),
                  child: Row(
                    children: [
                      // Home tab
                      _buildTabItem(
                        icon: FontAwesomeIcons.house,
                        isSelected: home.selectedIndex == 0,
                        onTap: () {
                          HapticFeedback.mediumImpact();
                          MixpanelManager().bottomNavigationTabClicked('Home');
                          primaryFocus?.unfocus();
                          onTabTap(0, home.selectedIndex == 0);
                        },
                      ),
                      // Action Items tab
                      _buildTabItem(
                        icon: FontAwesomeIcons.listCheck,
                        isSelected: home.selectedIndex == 1,
                        onTap: () {
                          HapticFeedback.mediumImpact();
                          MixpanelManager().bottomNavigationTabClicked('Action Items');
                          primaryFocus?.unfocus();
                          onTabTap(1, home.selectedIndex == 1);
                        },
                      ),
                      // Center space for record button - only when no OMI device is connected
                      if (showCenterButton && !isOmiDeviceConnected)
                        const SizedBox(width: _TabBarConstants.recordButtonSize),
                      // Memories tab
                      _buildTabItem(
                        icon: FontAwesomeIcons.brain,
                        isSelected: home.selectedIndex == 2,
                        onTap: () {
                          HapticFeedback.mediumImpact();
                          MixpanelManager().bottomNavigationTabClicked('Memories');
                          primaryFocus?.unfocus();
                          onTabTap(2, home.selectedIndex == 2);
                        },
                      ),
                      // Apps tab
                      _buildTabItem(
                        icon: FontAwesomeIcons.puzzlePiece,
                        isSelected: home.selectedIndex == 3,
                        onTap: () {
                          HapticFeedback.mediumImpact();
                          MixpanelManager().bottomNavigationTabClicked('Apps');
                          primaryFocus?.unfocus();
                          onTabTap(3, home.selectedIndex == 3);
                        },
                      ),
                    ],
                  ),
                ),
              ),
            ),
            // Central Record Button - Only show when no OMI device is connected
            if (!isOmiDeviceConnected)
              Positioned(
                left: MediaQuery.of(context).size.width / 2 - 40,
                bottom: MediaQuery.of(context).padding.bottom + 8,
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
                        width: _TabBarConstants.recordButtonSize,
                        height: _TabBarConstants.recordButtonSize,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: isRecording ? Colors.red : context.primaryColor,
                          border: Border.all(
                            color: Colors.black,
                            width: 5,
                          ),
                        ),
                        child: isInitializing
                            ? const CircularProgressIndicator(color: Colors.white, strokeWidth: 2)
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

  /// Builds a single tab item with proper touch target sizing (Apple HIG: 44pt minimum)
  Widget _buildTabItem({
    required IconData icon,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        child: SizedBox(
          height: _TabBarConstants.contentHeight, // 49pt - Apple HIG standard
          child: Center(
            child: Icon(
              icon,
              color: isSelected ? Colors.white : Colors.grey,
              size: _TabBarConstants.iconSize,
            ),
          ),
        ),
      ),
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
          MaterialPageRoute(builder: (context) => ConversationCapturingPage(topConversationId: topConvoId)),
        );
      }
    }
  }
}
