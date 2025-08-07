import 'dart:async';
import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/macos_overlay_bridge.dart';
import 'package:provider/provider.dart';
import 'desktop_home_page.dart';

class DesktopHomePageWrapper extends StatefulWidget {
  final String? navigateToRoute;
  const DesktopHomePageWrapper({super.key, this.navigateToRoute});

  @override
  State<DesktopHomePageWrapper> createState() => _DesktopHomePageWrapperState();
}

class _DesktopHomePageWrapperState extends State<DesktopHomePageWrapper> {
  String? _navigateToRoute;
  Timer? _expansionTimer;

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Check for chat expansion request from macOS overlay
      await _checkForChatExpansionRequest();
      
      if (mounted) {
        context.read<DeviceProvider>().periodicConnect('coming from DesktopHomePageWrapper');
      }
      if (mounted) {
        await context.read<ConversationProvider>().getInitialConversations();
      }
    });
    
    // Also set up a periodic check for expansion requests
    _startExpansionListener();
    
    _navigateToRoute = widget.navigateToRoute;
    super.initState();
  }
  
  @override
  void dispose() {
    _expansionTimer?.cancel();
    super.dispose();
  }
  
  /// Start listening for expansion requests periodically
  void _startExpansionListener() {
    _expansionTimer = Timer.periodic(const Duration(milliseconds: 500), (timer) async {
      if (!mounted) {
        timer.cancel();
        return;
      }
      await _checkForChatExpansionRequest();
    });
  }
  
  /// Check if macOS overlay requested chat expansion
  Future<void> _checkForChatExpansionRequest() async {
    try {
      final shouldExpand = await MacOSOverlayBridge.checkForChatExpansionRequest();
      
      if (shouldExpand && mounted) {
        _expansionTimer?.cancel();
        
        final messages = await MacOSOverlayBridge.getMessagesFromOverlay();
        await Future.delayed(const Duration(milliseconds: 100));
        _navigateToChat(messages);
      }
    } catch (e) {
      debugPrint('❌ Error checking chat expansion request: $e');
    }
  }
  
  /// Navigate to full chat with synced messages
  void _navigateToChat(List<Map<String, dynamic>> messages) {
    try {
      final homeProvider = Provider.of<HomeProvider>(context, listen: false);
      homeProvider.setIndex(1);
      
      if (homeProvider.onSelectedIndexChanged != null) {
        homeProvider.onSelectedIndexChanged!(1);
      }
    } catch (e) {
      debugPrint('❌ Error navigating to chat: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return DesktopHomePage(navigateToRoute: _navigateToRoute);
  }
}
