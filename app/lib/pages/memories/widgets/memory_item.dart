import 'dart:ui';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/services/client_device_service.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'memory_delete_undo.dart';
import 'memory_edit_sheet.dart';

class MemoryItem extends StatelessWidget {
  final Memory memory;
  final MemoriesProvider provider;
  final Function(BuildContext, Memory, MemoriesProvider) onTap;
  final bool showDismissible;
  final bool highlighted;

  /// Invoked after the row deleted its memory (swipe or long-press menu). The row already shows
  /// the Undo toast itself; this is for hosts that track deletes.
  final void Function(String content, Memory memory)? onDeleteNotification;

  const MemoryItem({
    super.key,
    required this.memory,
    required this.provider,
    required this.onTap,
    this.showDismissible = true,
    this.highlighted = false,
    this.onDeleteNotification,
  });

  @override
  Widget build(BuildContext context) {
    final provenanceType = ClientDeviceService.instance.deviceProvenanceType(
      primaryCaptureDevice: memory.primaryCaptureDevice,
    );
    final provenanceLabel = _resolveProvenanceLabel(context, provenanceType);
    final temporalLabel = _temporalLabel(context, memory);
    final editable = memoryIsEditable(memory);
    final Widget memoryWidget = GestureDetector(
      // Every memory opens: editable ones into the edit sheet, the rest read-only.
      onTap:
          editable ? () => onTap(context, memory, provider) : () => showMemoryQuickEditSheet(context, memory, provider),
      onLongPress: () => _showRowMenu(context, editable),
      child: AnimatedContainer(
        duration: OmiMotion.of(context).standard,
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.fromLTRB(18, 18, 16, 18),
        decoration: BoxDecoration(
          color: highlighted ? OmiColors.surface3 : AppStyles.backgroundSecondary,
          borderRadius: OmiRadius.xlAll,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.1),
              blurRadius: 4,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Stack(
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (memory.isKnowledgeLedger) ...[
                            Padding(
                              padding: const EdgeInsets.only(top: 2, right: 8),
                              child: Icon(
                                _ledgerIcon(memory),
                                size: 15,
                                color: memory.isHistoricalKnowledgeLedgerRow
                                    ? AppStyles.textTertiary
                                    : AppStyles.textPrimary,
                              ),
                            ),
                          ],
                          Expanded(
                            child: Text(
                              memory.content.decodeString,
                              style: AppStyles.body,
                            ),
                          ),
                          if (editable)
                            Padding(
                              padding: const EdgeInsetsDirectional.only(start: 12),
                              child: Icon(Icons.edit_outlined,
                                  size: 16, color: OmiColors.textTertiary, semanticLabel: context.l10n.editMemoryTitle),
                            ),
                        ],
                      ),
                      if (memory.ledgerSlot != null && memory.ledgerSlot!.trim().isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            memory.ledgerSlot!,
                            style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                          ),
                        ),
                      if (memory.isLedgerPlaybook && (memory.ledgerBody ?? '').trim().isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text(
                            memory.ledgerBody!.trim(),
                            maxLines: 3,
                            overflow: TextOverflow.ellipsis,
                            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                          ),
                        ),
                      if (provenanceLabel != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            provenanceLabel,
                            style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                          ),
                        ),
                      if (temporalLabel != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            temporalLabel,
                            style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(width: AppStyles.spacingM),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (memory.isBaseline) ...[
                      Icon(Icons.flag,
                          color: OmiColors.textSecondary, size: 20, semanticLabel: context.l10n.baselineMemory),
                      const SizedBox(width: AppStyles.spacingS),
                    ],
                    if (memory.conversationId != null) ...[
                      _buildConversationLinkButton(context),
                      const SizedBox(width: AppStyles.spacingS),
                    ],
                    if (_canReviewLedgerRow(memory)) ...[
                      _buildReviewButton(context, accepted: true),
                      const SizedBox(width: AppStyles.spacingS),
                      _buildReviewButton(context, accepted: false),
                      const SizedBox(width: AppStyles.spacingS),
                    ],
                    if (provider.memoryBeliefEnabled && _canSetMemoryUse(memory)) ...[
                      _buildMemoryUseButton(context),
                      const SizedBox(width: AppStyles.spacingS),
                    ],
                    if (provider.canRevertSupersededFact(memory)) ...[
                      _buildRevertButton(context),
                      const SizedBox(width: AppStyles.spacingS),
                    ],
                    // _buildVisibilityButton(context),
                  ],
                ),
              ],
            ),
            if (memory.isLocked)
              Positioned.fill(
                child: ClipRRect(
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 2.0, sigmaY: 2.0),
                    child: GestureDetector(
                      onTap: () {
                        if (!context.read<UsageProvider>().showSubscriptionUI) {
                          // No upgrade path to offer: still let the reader open what is visible.
                          showMemoryQuickEditSheet(context, memory, provider, readOnly: true);
                          return;
                        }
                        PlatformManager.instance.analytics.paywallOpened(
                          'Action Item',
                        );
                        routeToPage(
                          context,
                          const UsagePage(showUpgradeDialog: true),
                        );
                        return;
                      },
                      child: Container(
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.01),
                          borderRadius: OmiRadius.smAll,
                        ),
                        child: context.watch<UsageProvider>().showSubscriptionUI
                            ? Text(context.l10n.upgradeToUnlimited, style: OmiType.headline)
                            : const SizedBox.shrink(),
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );

    // Swipe-to-delete only where editing is allowed; a delete is immediate with Undo (D5).
    if (!showDismissible || !editable) {
      return memoryWidget;
    }

    return Dismissible(
      key: Key(memory.id),
      direction: DismissDirection.endToStart,
      onDismissed: (direction) => _delete(context),
      background: Container(
        margin: const EdgeInsets.only(bottom: 12),
        decoration: const BoxDecoration(
          color: OmiColors.danger,
          borderRadius: OmiRadius.xlAll,
        ),
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        child: const Icon(Icons.delete_outline, color: Colors.white),
      ),
      child: memoryWidget,
    );
  }

  void _delete(BuildContext context) {
    OmiHaptics.medium();
    deleteMemoryWithUndo(context, provider, memory);
    onDeleteNotification?.call(memory.content.decodeString, memory);
  }

  /// Long-press: Open (read-only), Edit and Delete where editing is allowed — the same menu shape
  /// as conversation and task rows.
  void _showRowMenu(BuildContext context, bool editable) {
    final l10n = context.l10n;
    showOmiRowMenu(
      context,
      title: memory.content.decodeString,
      actions: [
        OmiMenuAction(
          icon: Icons.open_in_full_rounded,
          label: l10n.open,
          onSelected: () => showMemoryQuickEditSheet(context, memory, provider, readOnly: true),
        ),
        if (editable) ...[
          OmiMenuAction(
              icon: Icons.edit_outlined, label: l10n.edit, onSelected: () => onTap(context, memory, provider)),
          OmiMenuAction(
            icon: Icons.delete_outline,
            label: l10n.delete,
            isDestructive: true,
            onSelected: () => _delete(context),
          ),
        ],
      ],
    );
  }

  static IconData _ledgerIcon(Memory memory) {
    if (memory.isHistoricalKnowledgeLedgerRow) return Icons.history;
    switch (memory.ledgerKind) {
      case KnowledgeLedgerKind.fact:
        return Icons.person_outline;
      case KnowledgeLedgerKind.document:
        return Icons.menu_book_outlined;
      case KnowledgeLedgerKind.trigger:
        return Icons.bolt_outlined;
      case null:
        return Icons.memory;
    }
  }

  static String? _temporalLabel(BuildContext context, Memory memory) {
    final asOf = memory.asOf;
    if (asOf == null) return null;
    final date = asOf.toLocal().toIso8601String().split('T').first;
    if (memory.currencyBand == 'current') {
      return '${context.l10n.current} · $date';
    }
    return date;
  }

  static bool _canReviewLedgerRow(Memory memory) {
    return memory.isKnowledgeLedger &&
        !memory.isLocked &&
        memory.invalidAt == null &&
        (memory.supersededBy == null || memory.supersededBy!.trim().isEmpty);
  }

  static bool _canSetMemoryUse(Memory memory) {
    if (memory.isLocked || memory.deleted || memory.invalidAt != null) return false;
    if ((memory.supersededBy ?? '').trim().isNotEmpty) return false;
    if (memory.ledgerStatus != null && memory.ledgerStatus != 'active') return false;
    if (memory.isKnowledgeLedger && !memory.isCurrentKnowledgeLedgerRow) return false;
    return true;
  }

  Widget _buildMemoryUseButton(BuildContext context) {
    return ListenableBuilder(
      listenable: provider,
      builder: (context, _) {
        final suppressed = memory.memoryUseSuppressed == true;
        final inFlight = provider.isApplyingMemoryUse(memory.id);
        // The Allow use control clears suppression. The backend's `useful`
        // receipt is a separate positive rating and intentionally preserves a
        // suppression, so it must never back this control.
        final action = suppressed ? MemoryUseAction.allow : MemoryUseAction.suppress;
        final label = suppressed ? context.l10n.memoryAllowUse : context.l10n.memoryDontUse;
        return Semantics(
          container: true,
          button: true,
          label: label,
          enabled: !inFlight,
          child: TextButton(
            key: Key('memory_use_${action.apiValue}_${memory.id}'),
            onPressed: inFlight
                ? null
                : () async {
                    final persisted = await provider.setMemoryUse(
                      memory,
                      action,
                    );
                    if (!persisted && context.mounted) {
                      OmiFeedback.error(context, context.l10n.somethingWentWrong);
                    }
                  },
            style: TextButton.styleFrom(
              minimumSize: const Size(0, kOmiMinTapTarget),
              padding: const EdgeInsets.symmetric(horizontal: 6),
            ),
            child: inFlight
                ? const OmiSpinner(size: OmiSpinnerSize.small)
                : Text(label, style: OmiType.caption.copyWith(color: OmiColors.textTertiary)),
          ),
        );
      },
    );
  }

  Widget _buildReviewButton(BuildContext context, {required bool accepted}) {
    final selected = memory.userReview == accepted;
    // 44pt targets (they were 32pt side by side). An IconButton rather than OmiIconButton so a
    // cast verdict stays bright while it is not tappable again.
    return IconButton(
      key: Key('memory_review_${accepted ? 'accept' : 'reject'}_${memory.id}'),
      onPressed: selected
          ? null
          : () async {
              final persisted = await provider.reviewMemory(memory, accepted);
              if (!persisted && context.mounted) {
                OmiFeedback.error(context, context.l10n.somethingWentWrong);
              }
            },
      tooltip: accepted ? context.l10n.memoryReviewRight : context.l10n.memoryReviewWrong,
      icon: Icon(
        accepted ? Icons.thumb_up_outlined : Icons.thumb_down_outlined,
        size: 17,
        color: selected ? OmiColors.textPrimary : OmiColors.textTertiary,
      ),
      padding: EdgeInsets.zero,
      constraints: const BoxConstraints(minWidth: kOmiMinTapTarget, minHeight: kOmiMinTapTarget),
    );
  }

  Widget _buildRevertButton(BuildContext context) {
    return ListenableBuilder(
      listenable: provider,
      builder: (context, _) {
        final inFlight = provider.isRevertingMemory(memory.id);
        return Semantics(
          container: true,
          label: context.l10n.undo,
          button: true,
          enabled: !inFlight,
          child: IconButton(
            key: Key('memory_revert_superseded_fact_${memory.id}'),
            onPressed: inFlight
                ? null
                : () async {
                    final persisted = await provider.revertSupersededFact(
                      memory,
                    );
                    if (!persisted && context.mounted) {
                      OmiFeedback.error(context, context.l10n.somethingWentWrong);
                    }
                  },
            tooltip: context.l10n.undo,
            icon: inFlight ? const OmiSpinner(size: OmiSpinnerSize.small) : const Icon(Icons.restore, size: 18),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
          ),
        );
      },
    );
  }

  /// Resolves a [DeviceProvenanceType] to a localized label, or null if none.
  String? _resolveProvenanceLabel(
    BuildContext context,
    DeviceProvenanceType? type,
  ) {
    switch (type) {
      case DeviceProvenanceType.thisDevice:
        return context.l10n.memoryThisDevice;
      case DeviceProvenanceType.thisIphone:
        return context.l10n.memoryThisIphone;
      case DeviceProvenanceType.thisPhone:
        return context.l10n.memoryThisPhone;
      case DeviceProvenanceType.mac:
        return context.l10n.memoryProvenanceMac;
      case DeviceProvenanceType.iphone:
        return context.l10n.memoryProvenanceIphone;
      case DeviceProvenanceType.android:
        return context.l10n.memoryProvenanceAndroid;
      case DeviceProvenanceType.other:
        return null; // Unknown devices show no provenance label.
      case null:
        return null;
    }
  }

  Widget _buildConversationLinkButton(BuildContext context) {
    return OmiIconButton.filled(
      icon: const FaIcon(FontAwesomeIcons.message, size: 16),
      label: context.l10n.openConversation,
      color: OmiColors.textSecondary,
      fillColor: OmiColors.surface2,
      onPressed: () => _navigateToConversation(context),
    );
  }

  Future<void> _navigateToConversation(BuildContext context) async {
    if (memory.conversationId == null) return;

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => const Center(child: OmiSpinner(size: OmiSpinnerSize.large)),
    );

    final conversation = await getConversationById(memory.conversationId!);

    if (!context.mounted) return;
    Navigator.of(context).pop();

    if (conversation != null) {
      final conversationProvider = Provider.of<ConversationProvider>(
        context,
        listen: false,
      );
      final detailProvider = Provider.of<ConversationDetailProvider>(
        context,
        listen: false,
      );

      // One derivation for both the group insert and the selected day, in local
      // time — inserting under the UTC day and selecting another key opened the
      // detail page on a day nothing was grouped under (#10980).
      final conversationDate = conversationProvider.ensureConversationInGroup(
        conversation,
      );
      detailProvider.updateConversation(conversation.id, conversationDate);

      routeToPage(context, ConversationDetailPage(conversation: conversation));
    } else {
      OmiFeedback.error(context, context.l10n.conversationNotFoundOrDeleted);
    }
  }
}
