import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:hotkey_manager/hotkey_manager.dart';
import 'package:omi/desktop/services/chat_overlay_service.dart';

class HotkeyWrapper extends StatefulWidget {
  final Widget child;
  
  const HotkeyWrapper({
    super.key,
    required this.child,
  });

  @override
  State<HotkeyWrapper> createState() => _HotkeyWrapperState();
}

class _HotkeyWrapperState extends State<HotkeyWrapper> {
  static const _overlayChannel = MethodChannel('overlayPlatform');
  late ChatOverlayService _chatService;

  @override
  void initState() {
    super.initState();
    print('🔧 HotkeyWrapper initState() called');
    _chatService = ChatOverlayService();
    _initializeServices();
    _registerHotkey();
    _setupMethodChannelHandlers();
    print('🔧 HotkeyWrapper initialization complete');
  }

  Future<void> _initializeServices() async {
    try {
      await ChatOverlayService.initialize();
      print('🔧 HotkeyWrapper: ChatOverlayService initialized successfully');
    } catch (e) {
      print('❌ HotkeyWrapper: Failed to initialize ChatOverlayService: $e');
    }
  }

  @override
  void dispose() {
    HotKeyManager.instance.unregisterAll();
    _chatService.dispose();
    super.dispose();
  }

  void _registerHotkey() async {
    await HotKeyManager.instance.unregisterAll();
    final hotKey = HotKey(
      key: LogicalKeyboardKey.space,
      modifiers: [HotKeyModifier.alt], // Option+Space
      scope: HotKeyScope.system,
    );
    HotKeyManager.instance.register(
      hotKey,
      keyDownHandler: (hotKey) {
        _showShortcutTriggered();
      },
    );
  }

  void _setupMethodChannelHandlers() {
    print('🔧 Setting up method channel handlers for overlayPlatform');
    _overlayChannel.setMethodCallHandler((call) async {
      print('🔧 Method channel received call: ${call.method}');
      switch (call.method) {
        case 'onChatCheck':
          print('🔵 RECEIVED CHECKMARK EVENT FROM NATIVE');
          debugPrint('');
          debugPrint('🔵 ================================================');
          debugPrint('🔵 CHECKMARK PRESSED: Starting transcription...');
          debugPrint('🔵 ================================================');
          await _chatService.processRecording();
          break;
        case 'onChatSend':
          final transcript = call.arguments['transcript'] as String?;
          if (transcript != null) {
            await _chatService.sendTranscript();
          }
          break;
        case 'onChatRetry':
          await _chatService.retryRecording();
          break;
        case 'onChatOverlayHidden':
          // Ensure recording stops and overlay state is updated when hidden
          await _chatService.stopRecording();
          _chatService.markOverlayHidden(); // Update state in case it's out of sync
          break;
        default:
          debugPrint('🔧 Method channel received unknown call: ${call.method}');
          break;
      }
    });
  }

  void _showShortcutTriggered() async {
    try {
      await _chatService.toggleOverlay();
      debugPrint('Hotkey triggered: Custom chat overlay toggled');
    } catch (e) {
      debugPrint('Error toggling custom chat overlay from hotkey: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return widget.child;
  }
}