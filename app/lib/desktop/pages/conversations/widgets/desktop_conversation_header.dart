import 'package:flutter/material.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopConversationHeader extends StatefulWidget {
  const DesktopConversationHeader({super.key});

  @override
  State<DesktopConversationHeader> createState() => _DesktopConversationHeaderState();
}

class _DesktopConversationHeaderState extends State<DesktopConversationHeader> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;

  @override
  void initState() {
    super.initState();

    _controller = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeOut),
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.3),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));

    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return SlideTransition(
      position: _slideAnimation,
      child: FadeTransition(
        opacity: _fadeAnimation,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Welcome back section
            Container(
              padding: EdgeInsets.only(
                bottom: responsive.spacing(baseSpacing: 8),
              ),
              child: Text(
                'Welcome back',
                style: TextStyle(
                  fontSize: responsive.responsiveFontSize(baseFontSize: 16),
                  fontWeight: FontWeight.w500,
                  color: ResponsiveHelper.textTertiary,
                ),
              ),
            ),

            // Main title
            Text(
              'Your Conversations',
              style: TextStyle(
                fontSize: responsive.responsiveFontSize(baseFontSize: 32),
                fontWeight: FontWeight.w600,
                color: ResponsiveHelper.textPrimary,
                letterSpacing: -0.5,
                height: 1.1,
              ),
            ),

            SizedBox(height: responsive.spacing(baseSpacing: 8)),

            // Subtitle
            Text(
              'Review and manage your captured conversations',
              style: TextStyle(
                fontSize: responsive.responsiveFontSize(baseFontSize: 16),
                color: ResponsiveHelper.textSecondary,
                height: 1.4,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
