import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/services/shortcut_service.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopShortcutsPage extends StatefulWidget {
  const DesktopShortcutsPage({super.key});

  @override
  State<DesktopShortcutsPage> createState() => _DesktopShortcutsPageState();
}

class _DesktopShortcutsPageState extends State<DesktopShortcutsPage> {
  ShortcutInfo? _askAIShortcut;
  ShortcutInfo? _toggleControlBarShortcut;
  bool _isLoading = true;
  String? _recordingFor; // null or 'askAI'

  @override
  void initState() {
    super.initState();
    _loadShortcuts();
  }

  Future<void> _loadShortcuts() async {
    setState(() => _isLoading = true);
    try {
      final askAI = await ShortcutService.getAskAIShortcut();
      final toggleControlBar = await ShortcutService.getToggleControlBarShortcut();
      setState(() {
        _askAIShortcut = askAI;
        _toggleControlBarShortcut = toggleControlBar;
        _isLoading = false;
      });
    } catch (e) {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ResponsiveHelper.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: ResponsiveHelper.backgroundPrimary,
        elevation: 0,
        title: const Text(
          'Keyboard Shortcuts',
          style: TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: ResponsiveHelper.textPrimary),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: _isLoading
          ? const Center(
              child: CircularProgressIndicator(
                color: ResponsiveHelper.purplePrimary,
              ),
            )
          : SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 500),
                  child: Container(
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.backgroundSecondary,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                      ),
                    ),
                    child: Column(
                      children: [
                        _buildShortcutRow(
                          title: 'Toggle Control Bar',
                          shortcut: _toggleControlBarShortcut?.displayString ?? '⌘\\',
                          isEditable: false,
                        ),
                        Container(
                          height: 1,
                          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                        ),
                        _buildShortcutRow(
                          title: 'Ask Omi',
                          shortcut: _askAIShortcut?.displayString ?? '⌘↩︎',
                          isEditable: true,
                          isRecording: _recordingFor == 'askAI',
                          onTap: () => _startRecording('askAI'),
                          onReset: _resetAskAIShortcut,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
    );
  }

  Widget _buildShortcutRow({
    required String title,
    required String shortcut,
    required bool isEditable,
    bool isRecording = false,
    VoidCallback? onTap,
    VoidCallback? onReset,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              style: TextStyle(
                color: isEditable ? ResponsiveHelper.textPrimary : ResponsiveHelper.textSecondary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          if (isEditable && !isRecording)
            PopupMenuButton<String>(
              icon: Icon(Icons.more_horiz, color: ResponsiveHelper.textTertiary, size: 20),
              color: ResponsiveHelper.backgroundSecondary,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              onSelected: (value) {
                if (value == 'reset') onReset?.call();
              },
              itemBuilder: (context) => [
                PopupMenuItem(
                  value: 'reset',
                  child: Text('Reset to default', style: TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 13)),
                ),
              ],
            ),
          const SizedBox(width: 4),
          isRecording
              ? _ShortcutRecorderBadge(
                  onRecorded: (keyCode, modifiers) => _saveShortcut(keyCode, modifiers),
                  onCancel: () => setState(() => _recordingFor = null),
                )
              : GestureDetector(
                  onTap: isEditable ? onTap : null,
                  child: MouseRegion(
                    cursor: isEditable ? SystemMouseCursors.click : SystemMouseCursors.basic,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.backgroundTertiary,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        shortcut,
                        style: TextStyle(
                          color: isEditable ? ResponsiveHelper.textPrimary : ResponsiveHelper.textTertiary,
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                          fontFamily: 'SF Mono',
                          letterSpacing: 0.5,
                        ),
                      ),
                    ),
                  ),
                ),
        ],
      ),
    );
  }

  void _startRecording(String id) {
    setState(() => _recordingFor = id);
  }

  Future<void> _saveShortcut(int keyCode, int modifiers) async {
    final success = await ShortcutService.setAskAIShortcut(keyCode, modifiers);
    setState(() => _recordingFor = null);
    if (success) {
      _loadShortcuts();
    }
  }

  Future<void> _resetAskAIShortcut() async {
    final success = await ShortcutService.resetAskAIShortcut();
    if (success) {
      _loadShortcuts();
    }
  }
}

// Inline shortcut recorder badge
class _ShortcutRecorderBadge extends StatefulWidget {
  final void Function(int keyCode, int modifiers) onRecorded;
  final VoidCallback onCancel;

  const _ShortcutRecorderBadge({required this.onRecorded, required this.onCancel});

  @override
  State<_ShortcutRecorderBadge> createState() => _ShortcutRecorderBadgeState();
}

class _ShortcutRecorderBadgeState extends State<_ShortcutRecorderBadge> {
  final FocusNode _focusNode = FocusNode();
  String _displayText = 'Press keys...';
  int? _keyCode;
  int? _modifiers;
  bool _isValid = false;

  static const int cmdKey = 0x100;
  static const int shiftKey = 0x200;
  static const int optionKey = 0x800;
  static const int controlKey = 0x1000;

  static final Map<int, int> _physicalKeyToCarbonKeyCode = {
    0x04: 0,
    0x05: 11,
    0x06: 8,
    0x07: 2,
    0x08: 14,
    0x09: 3,
    0x0A: 5,
    0x0B: 4,
    0x0C: 34,
    0x0D: 38,
    0x0E: 40,
    0x0F: 37,
    0x10: 46,
    0x11: 45,
    0x12: 31,
    0x13: 35,
    0x14: 12,
    0x15: 15,
    0x16: 1,
    0x17: 17,
    0x18: 32,
    0x19: 9,
    0x1A: 13,
    0x1B: 7,
    0x1C: 16,
    0x1D: 6,
    0x1E: 18,
    0x1F: 19,
    0x20: 20,
    0x21: 21,
    0x22: 23,
    0x23: 22,
    0x24: 26,
    0x25: 28,
    0x26: 25,
    0x27: 29,
    0x28: 36,
    0x2C: 49,
    0x31: 42,
  };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _focusNode.requestFocus());
  }

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }

  void _handleKeyEvent(KeyEvent event) {
    if (event is! KeyDownEvent) return;

    // Escape cancels
    if (event.logicalKey == LogicalKeyboardKey.escape) {
      widget.onCancel();
      return;
    }

    // Skip modifier-only
    if (_isModifierKey(event.logicalKey)) return;

    final isCommand = HardwareKeyboard.instance.isMetaPressed;
    if (!isCommand) {
      setState(() {
        _displayText = '⌘ required';
        _isValid = false;
      });
      return;
    }

    final isShift = HardwareKeyboard.instance.isShiftPressed;
    final isOption = HardwareKeyboard.instance.isAltPressed;
    final isControl = HardwareKeyboard.instance.isControlPressed;

    int modifiers = cmdKey;
    if (isShift) modifiers |= shiftKey;
    if (isOption) modifiers |= optionKey;
    if (isControl) modifiers |= controlKey;

    final usbHidUsage = event.physicalKey.usbHidUsage & 0xFF;
    final carbonKeyCode = _physicalKeyToCarbonKeyCode[usbHidUsage];

    if (carbonKeyCode == null) {
      setState(() {
        _displayText = 'Invalid key';
        _isValid = false;
      });
      return;
    }

    final parts = <String>[];
    if (isControl) parts.add('⌃');
    if (isOption) parts.add('⌥');
    if (isShift) parts.add('⇧');
    parts.add('⌘');
    parts.add(_getKeyName(event.logicalKey));

    setState(() {
      _keyCode = carbonKeyCode;
      _modifiers = modifiers;
      _displayText = parts.join();
      _isValid = true;
    });

    // Auto-save after short delay
    Future.delayed(const Duration(milliseconds: 300), () {
      if (_isValid && mounted) {
        widget.onRecorded(_keyCode!, _modifiers!);
      }
    });
  }

  bool _isModifierKey(LogicalKeyboardKey key) {
    return key == LogicalKeyboardKey.meta ||
        key == LogicalKeyboardKey.metaLeft ||
        key == LogicalKeyboardKey.metaRight ||
        key == LogicalKeyboardKey.shift ||
        key == LogicalKeyboardKey.shiftLeft ||
        key == LogicalKeyboardKey.shiftRight ||
        key == LogicalKeyboardKey.alt ||
        key == LogicalKeyboardKey.altLeft ||
        key == LogicalKeyboardKey.altRight ||
        key == LogicalKeyboardKey.control ||
        key == LogicalKeyboardKey.controlLeft ||
        key == LogicalKeyboardKey.controlRight;
  }

  String _getKeyName(LogicalKeyboardKey key) {
    if (key == LogicalKeyboardKey.enter || key == LogicalKeyboardKey.numpadEnter) return '↩︎';
    if (key == LogicalKeyboardKey.space) return 'Space';
    if (key == LogicalKeyboardKey.backslash) return '\\';
    final label = key.keyLabel;
    return label.length == 1 ? label.toUpperCase() : label;
  }

  @override
  Widget build(BuildContext context) {
    return KeyboardListener(
      focusNode: _focusNode,
      onKeyEvent: _handleKeyEvent,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: ResponsiveHelper.purplePrimary, width: 1.5),
        ),
        child: Text(
          _displayText,
          style: TextStyle(
            color: _isValid ? ResponsiveHelper.textPrimary : ResponsiveHelper.purplePrimary,
            fontSize: 13,
            fontWeight: FontWeight.w500,
            fontFamily: 'SF Mono',
            letterSpacing: 0.5,
          ),
        ),
      ),
    );
  }
}
