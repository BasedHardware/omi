import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/services/apple_reminders_service.dart';
import 'package:omi/services/apple_notes_service.dart';
import 'package:omi/services/apple_calendar_service.dart';
import 'package:omi/models/action_item_integration.dart';
import 'package:omi/utils/platform/platform_service.dart';

import 'edit_action_item_sheet.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/backend/preferences.dart';

class ActionItemTileWidget extends StatefulWidget {
  final ActionItem actionItem;
  final String conversationId;
  final int itemIndexInConversation;
  final bool hasRoundedCorners;
  final bool isLastInGroup;
  final bool isInGroup;
  final Set<String> exportedToAppleReminders;
  final VoidCallback? onExportedToAppleReminders;

  const ActionItemTileWidget({
    super.key,
    required this.actionItem,
    required this.conversationId,
    required this.itemIndexInConversation,
    this.hasRoundedCorners = true,
    this.isLastInGroup = false,
    this.isInGroup = false,
    this.exportedToAppleReminders = const <String>{},
    this.onExportedToAppleReminders,
  });

  @override
  State<ActionItemTileWidget> createState() => _ActionItemTileWidgetState();
}

class _ActionItemTileWidgetState extends State<ActionItemTileWidget> {
  static final Map<String, bool> _pendingStates = {}; // Track pending states by description
  
  // Integration selection
  ActionItemIntegration _selectedIntegration = ActionItemIntegration.appleReminders;
  final Map<String, Set<String>> _exportedItems = {
    'reminders': <String>{},
    'notes': <String>{},
    'calendar': <String>{},
  };

  // Track in-flight export requests keyed by "integration:description"
  final Set<String> _pendingExports = <String>{};

  bool get _isPendingForCurrent {
    final key = '${_selectedIntegration.name}:${widget.actionItem.description}';
    return _pendingExports.contains(key);
  }

  // Check if this action item is exported to Apple Reminders
  bool get _isExportedToAppleReminders => widget.exportedToAppleReminders.contains(widget.actionItem.description);
  
  // Check if exported to current integration
  bool get _isExportedToCurrent {
    if (_selectedIntegration == ActionItemIntegration.appleReminders) {
      return _isExportedToAppleReminders;
    } else if (_selectedIntegration == ActionItemIntegration.appleNotes) {
      return _exportedItems['notes']?.contains(widget.actionItem.description) ?? false;
    } else if (_selectedIntegration == ActionItemIntegration.appleCalendar) {
      return _exportedItems['calendar']?.contains(widget.actionItem.description) ?? false;
    }
    return false;
  }

  @override
  void initState() {
    super.initState();
    _loadSavedIntegration();
  }
  
  @override
  void dispose() {
    // Clean up any pending state for this item when widget is disposed
    _pendingStates.remove(widget.actionItem.description);
    super.dispose();
  }
  
  Future<void> _loadSavedIntegration() async {
    try {
      final prefs = SharedPreferencesUtil();
      final savedName = prefs.taskExportDestination;
      if (savedName.isNotEmpty) {
        final integration = ActionItemIntegration.values.firstWhere(
          (e) => e.name == savedName,
          orElse: () => ActionItemIntegration.appleReminders,
        );
        if (mounted) {
          setState(() => _selectedIntegration = integration);
        }
      }
    } catch (_) {
      // If reading prefs fails, fall back to default without crashing UI
    }
  }
  
  Future<void> _saveIntegration(ActionItemIntegration integration) async {
    try {
      final prefs = SharedPreferencesUtil();
      prefs.taskExportDestination = integration.name;
    } catch (_) {
      // Non-fatal: selection persists in memory even if prefs write fails
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<ConversationProvider>(context, listen: false);
    final conversation = provider.conversations.firstWhere(
      (c) => c.id == widget.conversationId,
      orElse: () => provider.searchedConversations.firstWhere((c) => c.id == widget.conversationId),
    );

    // Check if this specific item has a pending state change
    final isCompleted = _pendingStates.containsKey(widget.actionItem.description)
        ? _pendingStates[widget.actionItem.description]!
        : widget.actionItem.completed;

    BorderRadius borderRadius;
    if (widget.hasRoundedCorners) {
      borderRadius = BorderRadius.circular(16);
    } else if (widget.isLastInGroup) {
      borderRadius = const BorderRadius.only(
        bottomLeft: Radius.circular(16),
        bottomRight: Radius.circular(16),
      );
    } else {
      borderRadius = BorderRadius.zero;
    }

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: borderRadius,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 4,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      // ClipRRect to enforce rounded corners throughout the dismissible animation
      clipBehavior: Clip.antiAlias,
      child: Dismissible(
        key: Key("${widget.conversationId}_${widget.itemIndexInConversation}"),
        // Allow horizontal swipe in both directions
        direction: DismissDirection.horizontal,

        // Background for complete action (swipe right, startToEnd)
        background: Container(
          alignment: Alignment.centerLeft,
          color: Colors.green,
          child: const Padding(
            padding: EdgeInsets.only(left: 20),
            child: Row(
              children: [
                Icon(
                  Icons.check_circle,
                  color: Colors.white,
                  size: 30,
                ),
              ],
            ),
          ),
        ),

        // Background for delete action (swipe left, endToStart)
        secondaryBackground: Container(
          alignment: Alignment.centerRight,
          color: Colors.red,
          child: const Padding(
            padding: EdgeInsets.only(right: 20),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Icon(
                  Icons.delete,
                  color: Colors.white,
                  size: 30,
                ),
              ],
            ),
          ),
        ),

        confirmDismiss: (direction) async {
          if (direction == DismissDirection.endToStart) {
            final prefsUtil = SharedPreferencesUtil();
            bool dontAskAgain = !(prefsUtil.showActionItemDeleteConfirmation);

            if (dontAskAgain) {
              context.read<ConversationProvider>().deleteActionItemAndUpdateLocally(
                    widget.conversationId,
                    widget.itemIndexInConversation,
                    widget.actionItem,
                  );
              return true;
            }

            // Delete action (swipe left) - show confirmation dialog
            return await showDialog<bool>(
                  context: context,
                  builder: (context) => ConfirmationDialog(
                    title: 'Delete Action Item',
                    description: 'Are you sure you want to delete this action item?',
                    checkboxText: "Don't ask again",
                    checkboxValue: dontAskAgain,
                    onCheckboxChanged: (value) {
                      prefsUtil.showActionItemDeleteConfirmation = !value;
                    },
                    confirmText: 'Delete',
                    cancelText: 'Cancel',
                    onConfirm: () {
                      context.read<ConversationProvider>().deleteActionItemAndUpdateLocally(
                            widget.conversationId,
                            widget.itemIndexInConversation,
                            widget.actionItem,
                          );
                      Navigator.pop(context, true);
                    },
                    onCancel: () => Navigator.pop(context, false),
                  ),
                ) ??
                false;
          } else if (direction == DismissDirection.startToEnd) {
            // Complete action (swipe right) - use same logic as tap
            _toggleCompletion(context, conversation);
            return false;
          }
          return false;
        },

        onDismissed: (direction) {},

        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {
              HapticFeedback.lightImpact();
              MixpanelManager().actionItemTappedForEditOnActionItemsPage(
                conversationId: widget.conversationId,
                actionItemDescription: widget.actionItem.description,
              );
              _showEditActionItemBottomSheet(context, widget.actionItem);
            },
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 16.0, horizontal: 16.0),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 20,
                    height: 20,
                    child: Transform.translate(
                      offset: const Offset(0, 2),
                      child: GestureDetector(
                        onTap: () => _toggleCompletion(context, conversation),
                        child: AnimatedOpacity(
                          opacity: 1.0,
                          duration: const Duration(milliseconds: 300),
                          child: AnimatedContainer(
                            duration: const Duration(milliseconds: 200),
                            height: 20,
                            width: 20,
                            decoration: BoxDecoration(
                              color: isCompleted ? Colors.green : Colors.transparent,
                              border: Border.all(
                                color: isCompleted ? Colors.green : Colors.grey[400]!,
                                width: 1.5,
                              ),
                              borderRadius: BorderRadius.circular(5),
                            ),
                            child: isCompleted
                                ? const Icon(
                                    Icons.check,
                                    size: 14,
                                    color: Colors.white,
                                  )
                                : null,
                          ),
                        ),
                      ),
                    ),
                  ),

                  // Content
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.only(left: 14.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  widget.actionItem.description,
                                  style: TextStyle(
                                    color: isCompleted ? Colors.grey.shade500 : Colors.white,
                                    decoration: isCompleted ? TextDecoration.lineThrough : null,
                                    decorationColor: Colors.grey.shade600,
                                    fontSize: 16,
                                    height: 1.3,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ),
                              // Export button with dropdown (only show on Apple platforms and if not completed)
                              if (PlatformService.isApple && !isCompleted)
                                Padding(
                                  padding: const EdgeInsets.only(left: 8.0),
                                  child: _buildExportButton(context),
                                ),
                            ],
                          ),

                          // Optional date/time for tasks
                          if (widget.actionItem.description.toLowerCase().contains('february') ||
                              widget.actionItem.description.toLowerCase().contains('masterclass'))
                            Padding(
                              padding: const EdgeInsets.only(top: 8.0),
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                decoration: BoxDecoration(
                                  color: Color(0xFF35343B),
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Icon(
                                      Icons.notifications_outlined,
                                      size: 14,
                                      color: Colors.grey.shade400,
                                    ),
                                    const SizedBox(width: 6),
                                    Text(
                                      'February 28 - 11:00am',
                                      style: TextStyle(
                                        color: Colors.grey.shade400,
                                        fontSize: 13,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _toggleCompletion(BuildContext context, conversation) async {
    // Haptic feedback
    HapticFeedback.lightImpact();

    final newValue = !widget.actionItem.completed;
    final itemDescription = widget.actionItem.description;

    // Update pending state immediately for instant visual feedback
    setState(() {
      _pendingStates[itemDescription] = newValue;
    });

    try {
      // Update global state immediately
      await context.read<ConversationProvider>().updateGlobalActionItemState(
            conversation,
            itemDescription,
            newValue,
          );

      // Wait for 200ms before clearing pending state (allows user to see the change before item moves)
      Future.delayed(const Duration(milliseconds: 200), () {
        if (mounted) {
          setState(() {
            _pendingStates.remove(itemDescription); // Clear pending state so item moves to correct section
          });
        }
      });

      // Sync with Apple Reminders if item was exported and is being marked as completed
      if (newValue && _isExportedToAppleReminders && PlatformService.isApple) {
        try {
          final service = AppleRemindersService();
          final success = await service.completeReminder(itemDescription);
          if (success) {
            debugPrint('Successfully completed reminder in Apple Reminders: $itemDescription');
          } else {
            debugPrint('Failed to complete reminder in Apple Reminders: $itemDescription');
          }
        } catch (e) {
          debugPrint('Error syncing completion to Apple Reminders: $e');
        }
      }

      // Track analytics
      MixpanelManager().actionItemToggledCompletionOnActionItemsPage(
        conversationId: widget.conversationId,
        actionItemDescription: itemDescription,
        isCompleted: newValue,
      );
    } catch (e) {
      // If there's an error, revert pending state
      if (mounted) {
        setState(() {
          _pendingStates.remove(itemDescription);
        });
      }
      debugPrint('Error updating action item state: $e');
    }
  }

  void _showEditActionItemBottomSheet(BuildContext context, ActionItem item) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) {
        return EditActionItemBottomSheet(
          actionItem: item,
          conversationId: widget.conversationId,
          itemIndex: widget.itemIndexInConversation,
        );
      },
    );
  }

  Future<void> _exportToAppleReminders(BuildContext context) async {
    HapticFeedback.lightImpact();

    final service = AppleRemindersService();
    final result = await service.addActionItem(widget.actionItem.description);

    if (!mounted) return;

    // If successful, notify parent to refresh the exported state
    if (result.isSuccess) {
      widget.onExportedToAppleReminders?.call();
    }

    // Show feedback to user
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Row(
          children: [
            Icon(
              result.isSuccess ? Icons.check_circle : Icons.error,
              color: result.isSuccess ? Colors.green : Colors.red,
              size: 20,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                result.message,
                style: const TextStyle(fontSize: 14),
              ),
            ),
          ],
        ),
        backgroundColor: Colors.grey[900],
        behavior: SnackBarBehavior.floating,
        margin: const EdgeInsets.all(16),
        duration: const Duration(seconds: 3),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
        ),
      ),
    );

    // Track analytics
    MixpanelManager().track('Action Item Exported to Apple Reminders', properties: {
      'conversationId': widget.conversationId,
      'success': result.isSuccess,
      'result': result.name,
    });
  }

  Widget _buildExportButton(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Main export button with original Apple logo style
        GestureDetector(
          onTap: (_isExportedToCurrent || _isPendingForCurrent) ? null : () => _exportActionItem(context),
          child: Container(
            width: 28,
            height: 28,
            child: Stack(
              children: [
                Center(
                  child: _selectedIntegration.isSvg
                      ? SvgPicture.asset(
                          _selectedIntegration.fullAssetPath!,
                          width: 24,
                          height: 24,
                        )
                      : Image.asset(
                          _selectedIntegration.fullAssetPath!,
                          width: 24,
                          height: 24,
                        ),
                ),
                // Status indicator (checkmark or plus) - same as original
                _isExportedToCurrent
                    ? Positioned(
                        bottom: 0,
                        right: 0,
                        child: Container(
                          width: 12,
                          height: 12,
                          decoration: BoxDecoration(
                            color: Colors.green,
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: const Color(0xFF1F1F25),
                              width: 1,
                            ),
                          ),
                          child: const Icon(
                            Icons.check,
                            size: 8,
                            color: Colors.white,
                          ),
                        ),
                      )
                    : Positioned(
                        bottom: 0,
                        right: 0,
                        child: Container(
                          width: 12,
                          height: 12,
                          decoration: BoxDecoration(
                            color: Colors.yellow,
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: const Color(0xFF1F1F25),
                              width: 1,
                            ),
                          ),
                          child: const Icon(
                            Icons.add,
                            size: 8,
                            color: Colors.black,
                          ),
                        ),
                      ),
              ],
            ),
          ),
        ),
        // Small dropdown arrow
        const SizedBox(width: 2),
        GestureDetector(
          onTap: () => _showIntegrationPicker(context),
          child: Icon(
            Icons.arrow_drop_down,
            size: 16,
            color: Colors.grey[500],
          ),
        ),
      ],
    );
  }

  void _showIntegrationPicker(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1F1F25),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.all(16.0),
              child: Text(
                'Export to',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            ...ActionItemIntegration.values.map((integration) {
              final isSelected = integration == _selectedIntegration;
              return ListTile(
                leading: integration.isSvg
                    ? SvgPicture.asset(
                        integration.fullAssetPath!,
                        width: 24,
                        height: 24,
                      )
                    : Image.asset(
                        integration.fullAssetPath!,
                        width: 24,
                        height: 24,
                      ),
                title: Text(
                  integration.displayName,
                  style: TextStyle(
                    color: isSelected ? Colors.blue : Colors.white,
                  ),
                ),
                trailing: isSelected
                    ? const Icon(Icons.check, color: Colors.blue)
                    : null,
                onTap: () {
                  setState(() => _selectedIntegration = integration);
                  _saveIntegration(integration);
                  Navigator.pop(context);
                },
              );
            }),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }

  Future<void> _exportActionItem(BuildContext context) async {
    HapticFeedback.lightImpact();

    if (_isExportedToCurrent || _isPendingForCurrent) {
      return;
    }

    final key = '${_selectedIntegration.name}:${widget.actionItem.description}';
    setState(() {
      _pendingExports.add(key);
    });

    try {
      if (_selectedIntegration == ActionItemIntegration.appleReminders) {
        await _exportToAppleReminders(context);
      } else if (_selectedIntegration == ActionItemIntegration.appleNotes) {
        await _exportToAppleNotes(context);
      } else if (_selectedIntegration == ActionItemIntegration.appleCalendar) {
        await _exportToAppleCalendar(context);
      }
    } finally {
      if (mounted) {
        setState(() {
          _pendingExports.remove(key);
        });
      }
    }
  }

  Future<void> _exportToAppleNotes(BuildContext context) async {
    final service = AppleNotesService();
    final result = await service.shareActionItem(widget.actionItem.description);

    if (!mounted) return;

    if (result.isSuccess) {
      (_exportedItems['notes'] ??= <String>{})
          .add(widget.actionItem.description);
      setState(() {});
      
      // Show consistent feedback like Reminders
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              Icon(
                Icons.check_circle,
                color: Colors.green,
                size: 20,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  result.message,
                  style: const TextStyle(fontSize: 14),
                ),
              ),
            ],
          ),
          backgroundColor: Colors.grey[900],
          behavior: SnackBarBehavior.floating,
          margin: const EdgeInsets.all(16),
          duration: const Duration(seconds: 2),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
        ),
      );
      
      // Track analytics
      MixpanelManager().track('Action Item Exported to Apple Notes', properties: {
        'conversationId': widget.conversationId,
        'success': true,
      });
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              Icon(
                Icons.error,
                color: Colors.red,
                size: 20,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  result.message,
                  style: const TextStyle(fontSize: 14),
                ),
              ),
            ],
          ),
          backgroundColor: Colors.grey[900],
          behavior: SnackBarBehavior.floating,
          margin: const EdgeInsets.all(16),
          duration: const Duration(seconds: 3),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
        ),
      );
    }
  }

  Future<void> _exportToAppleCalendar(BuildContext context) async {
    final service = AppleCalendarService();
    final result = await service.createEvent(widget.actionItem.description);

    if (!mounted) return;

    if (result.isSuccess) {
      _exportedItems['calendar'] ??= <String>{};
      _exportedItems['calendar']!.add(widget.actionItem.description);
      setState(() {});
      
      // Show consistent feedback
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              Icon(
                Icons.check_circle,
                color: Colors.green,
                size: 20,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  result.message,
                  style: const TextStyle(fontSize: 14),
                ),
              ),
            ],
          ),
          backgroundColor: Colors.grey[900],
          behavior: SnackBarBehavior.floating,
          margin: const EdgeInsets.all(16),
          duration: const Duration(seconds: 2),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
        ),
      );
      
      // Track analytics
      MixpanelManager().track('Action Item Exported to Apple Calendar', properties: {
        'conversationId': widget.conversationId,
        'success': true,
      });
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              Icon(
                Icons.error,
                color: Colors.red,
                size: 20,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  result.message,
                  style: const TextStyle(fontSize: 14),
                ),
              ),
            ],
          ),
          backgroundColor: Colors.grey[900],
          behavior: SnackBarBehavior.floating,
          margin: const EdgeInsets.all(16),
          duration: const Duration(seconds: 3),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
        ),
      );
    }
  }
}
