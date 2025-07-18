import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

enum OmiChatBubbleType { incoming, outgoing }

class OmiChatBubble extends AdaptiveWidget {
  final OmiChatBubbleType type;
  final Widget child;
  final EdgeInsets padding;

  const OmiChatBubble({
    super.key,
    required this.type,
    required this.child,
    this.padding = const EdgeInsets.all(16),
  });

  @override
  Widget buildDesktop(BuildContext context) => _base();

  @override
  Widget buildMobile(BuildContext context) => _base();

  Widget _base() {
    final isIncoming = type == OmiChatBubbleType.incoming;
    return Container(
      decoration: BoxDecoration(
        color: isIncoming
            ? const Color.fromARGB(255, 255, 255, 255).withOpacity(0.05)
            : ResponsiveHelper.purplePrimary.withOpacity(0.15),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      padding: padding,
      child: child,
    );
  }
}
