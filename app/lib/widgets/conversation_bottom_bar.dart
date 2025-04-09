import 'package:flutter/material.dart';

enum ConversationBottomBarMode {
  recording, // During active recording (no summary icon)
  detail // For viewing completed conversations
}

class ConversationBottomBar extends StatelessWidget {
  final ConversationBottomBarMode mode;
  final int selectedTabIndex;
  final Function(int) onTabSelected;
  final VoidCallback onStopPressed;
  final bool hasSegments;

  const ConversationBottomBar({
    super.key,
    required this.mode,
    required this.selectedTabIndex,
    required this.onTabSelected,
    required this.onStopPressed,
    this.hasSegments = true,
  });

  @override
  Widget build(BuildContext context) {
    if (!hasSegments) {
      return const SizedBox();
    }

    // Use a Positioned widget inside a Stack in the parent widget
    return Container(
      child: Center(
        child: Material(
          elevation: 8,
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(28),
          child: Container(
            height: 56,
            width: mode == ConversationBottomBarMode.recording ? 180 : 220,
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: Colors.grey.shade900,
              borderRadius: BorderRadius.circular(28),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.3),
                  spreadRadius: 1,
                  blurRadius: 5,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                // Transcript icon with pill indicator
                _buildTabButton(
                  context: context,
                  icon: Icons.graphic_eq_rounded,
                  isSelected: selectedTabIndex == 0,
                  onTap: () => onTabSelected(0),
                ),

                // Stop button - only show in recording mode
                if (mode == ConversationBottomBarMode.recording)
                  Container(
                    height: 40,
                    width: 40,
                    decoration: BoxDecoration(
                      color: Colors.red,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: Colors.red.withOpacity(0.4),
                          spreadRadius: 1,
                          blurRadius: 4,
                        ),
                      ],
                    ),
                    child: Material(
                      color: Colors.transparent,
                      shape: const CircleBorder(),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(20),
                        onTap: onStopPressed,
                        child: const Icon(
                          Icons.pause_rounded,
                          color: Colors.white,
                          size: 24,
                        ),
                      ),
                    ),
                  ),

                // Summary icon - only show in detail mode
                if (mode == ConversationBottomBarMode.detail)
                  _buildTabButton(
                    context: context,
                    icon: Icons.sticky_note_2,
                    isSelected: selectedTabIndex == 1,
                    onTap: () => onTabSelected(1),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTabButton({
    required BuildContext context,
    required IconData icon,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Container(
      width: 80,
      height: 40,
      decoration: BoxDecoration(
        color: isSelected ? Colors.deepPurple.withOpacity(0.3) : Colors.transparent,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: onTap,
          child: Center(
            child: Icon(
              icon,
              color: isSelected ? Colors.white : Colors.grey.shade400,
              size: 24,
            ),
          ),
        ),
      ),
    );
  }
}
