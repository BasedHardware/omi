import 'dart:async';
import 'dart:ui';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
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
    final provenanceLabel = memoryProvenanceLabel(context, memory);
    final temporalLabel = memoryTemporalLabel(context, memory);
    final editable = memoryIsEditable(memory);
    final Widget memoryWidget = GestureDetector(
      // Every memory opens: editable ones into the edit sheet, the rest read-only.
      onTap:
          editable ? () => onTap(context, memory, provider) : () => showMemoryQuickEditSheet(context, memory, provider),
      // A locked row's content is behind the paywall overlay; the row menu would show it in full.
      onLongPress: memory.isLocked ? null : () => _showRowMenu(context, editable),
      child: AnimatedContainer(
        duration: OmiMotion.of(context).standard,
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.fromLTRB(18, 18, 16, 18),
        decoration: BoxDecoration(
          color: highlighted ? OmiColors.surface3 : OmiColors.surface1,
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
                                    ? OmiColors.textPrimary.withValues(alpha: 0.6)
                                    : OmiColors.textPrimary,
                              ),
                            ),
                          ],
                          Expanded(
                            child: Text(
                              memory.content.decodeString,
                              style: OmiType.subhead.copyWith(height: 1.4),
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
                    if (memoryCanReviewLedgerRow(memory)) ...[
                      _buildReviewButton(context, accepted: true),
                      const SizedBox(width: AppStyles.spacingS),
                      _buildReviewButton(context, accepted: false),
                      const SizedBox(width: AppStyles.spacingS),
                    ],
                    if (provider.memoryBeliefEnabled && memoryCanSetUse(memory)) ...[
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
                      onTap: () => _openLockedMemory(context, memory, provider),
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
        decoration: BoxDecoration(
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

  Widget _buildConversationLinkButton(BuildContext context) {
    return OmiIconButton.filled(
      icon: const FaIcon(FontAwesomeIcons.message, size: 16),
      label: context.l10n.openConversation,
      color: OmiColors.textSecondary,
      fillColor: OmiColors.surface2,
      onPressed: () => openMemoryConversation(context, memory),
    );
  }
}

IconData _ledgerIcon(Memory memory) {
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

/// The SF Symbol for a knowledge-ledger row's kind (the row's [_ledgerIcon]), or null when the
/// memory is not a ledger row.
String? memoryLedgerSymbol(Memory memory) {
  if (!memory.isKnowledgeLedger) return null;
  if (memory.isHistoricalKnowledgeLedgerRow) return 'clock.arrow.circlepath';
  switch (memory.ledgerKind) {
    case KnowledgeLedgerKind.fact:
      return 'person';
    case KnowledgeLedgerKind.document:
      return 'book';
    case KnowledgeLedgerKind.trigger:
      return 'bolt';
    case null:
      return 'memorychip';
  }
}

/// "Current · date" for a current fact, the bare as-of date otherwise, or null without one.
String? memoryTemporalLabel(BuildContext context, Memory memory) {
  final asOf = memory.asOf;
  if (asOf == null) return null;
  final date = asOf.toLocal().toIso8601String().split('T').first;
  if (memory.currencyBand == 'current') {
    return '${context.l10n.current} · $date';
  }
  return date;
}

/// The capturing device as a localized label, or null when it is unknown.
String? memoryProvenanceLabel(BuildContext context, Memory memory) {
  final type = ClientDeviceService.instance.deviceProvenanceType(
    primaryCaptureDevice: memory.primaryCaptureDevice,
  );
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

/// A current, unlocked knowledge-ledger row takes a right/wrong verdict.
bool memoryCanReviewLedgerRow(Memory memory) {
  return memory.isKnowledgeLedger &&
      !memory.isLocked &&
      memory.invalidAt == null &&
      (memory.supersededBy == null || memory.supersededBy!.trim().isEmpty);
}

/// A live, current memory can be allowed or kept out of use.
bool memoryCanSetUse(Memory memory) {
  if (memory.isLocked || memory.deleted || memory.invalidAt != null) return false;
  if ((memory.supersededBy ?? '').trim().isNotEmpty) return false;
  if (memory.ledgerStatus != null && memory.ledgerStatus != 'active') return false;
  if (memory.isKnowledgeLedger && !memory.isCurrentKnowledgeLedgerRow) return false;
  return true;
}

/// A locked row opens the plan page with its upgrade dialog, or read-only without a plan to offer.
void _openLockedMemory(BuildContext context, Memory memory, MemoriesProvider provider) {
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
}

/// A row tap: locked memories go to the paywall (or read-only), editable ones to [onEdit] and the
/// rest open read-only.
void openMemoryRow(BuildContext context, Memory memory, MemoriesProvider provider,
    {required Function(BuildContext, Memory, MemoriesProvider) onEdit}) {
  if (memory.isLocked) {
    _openLockedMemory(context, memory, provider);
  } else if (memoryIsEditable(memory)) {
    onEdit(context, memory, provider);
  } else {
    showMemoryQuickEditSheet(context, memory, provider);
  }
}

/// Opens the conversation a memory came from, with a blocking activity while it loads.
Future<void> openMemoryConversation(BuildContext context, Memory memory) async {
  final conversationId = memory.conversationId;
  if (conversationId == null) return;

  // The native activity when the renderer shows one; the Flutter spinner otherwise.
  final activity = nativePresentationEnabled ? await showIosNativeActivity(context, label: context.l10n.loading) : null;
  if (!context.mounted) {
    await activity?.dismiss();
    return;
  }
  if (activity == null) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => const Center(child: OmiSpinner(size: OmiSpinnerSize.large)),
    );
  }

  final ServerConversation? conversation;
  try {
    conversation = await getConversationById(conversationId);
  } finally {
    // The overlay leaves before any route is pushed beneath it.
    await activity?.dismiss();
  }

  if (!context.mounted) return;
  if (activity == null) Navigator.of(context).pop();

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

/// The native list row for [memory]. A locked row carries only the upgrade title: its content,
/// subtitle and actions never cross the bridge. Options repeat the Flutter row's controls.
NativeRow memoryNativeRow(BuildContext context, Memory memory, MemoriesProvider provider,
    {required Function(BuildContext, Memory, MemoriesProvider) onEdit}) {
  final l10n = context.l10n;
  void open(Object? _) => openMemoryRow(context, memory, provider, onEdit: onEdit);
  if (memory.isLocked) {
    // The upgrade copy only where the plan page can offer one, as the classic overlay shows it.
    final title = context.read<UsageProvider>().showSubscriptionUI ? l10n.upgradeToUnlimited : l10n.memoryDetailsTitle;
    return NativeRow('memory_${memory.id}', title,
        kind: 'navigation', symbol: memoryLedgerSymbol(memory), action: open);
  }
  final editable = memoryIsEditable(memory);
  final reviewable = memoryCanReviewLedgerRow(memory);
  final applyingUse = provider.isApplyingMemoryUse(memory.id);
  final reverting = provider.isRevertingMemory(memory.id);
  final suppressed = memory.memoryUseSuppressed == true;
  final canUse = provider.memoryBeliefEnabled && memoryCanSetUse(memory) && !applyingUse;
  final canRevert = provider.canRevertSupersededFact(memory) && !reverting;
  final slot = memory.ledgerSlot?.trim() ?? '';
  final body = memory.isLedgerPlaybook ? (memory.ledgerBody ?? '').trim() : '';
  final provenance = memoryProvenanceLabel(context, memory);
  final temporal = memoryTemporalLabel(context, memory);
  final details = [
    if (slot.isNotEmpty) memory.ledgerSlot!,
    if (provenance != null) provenance,
    if (temporal != null) temporal,
    if (memory.isBaseline) l10n.baselineMemory,
  ].join(' · ');
  return NativeRow(
    'memory_${memory.id}',
    memory.content.decodeString,
    kind: 'navigation',
    symbol: memoryLedgerSymbol(memory),
    subtitle: [if (details.isNotEmpty) details, if (body.isNotEmpty) body].join('\n'),
    options: {
      'open': l10n.open,
      if (editable) ...{'edit': l10n.edit, 'delete': l10n.delete},
      if (memory.conversationId != null) 'open_conversation': l10n.openConversation,
      if (reviewable && memory.userReview != true) 'review_right': l10n.memoryReviewRight,
      if (reviewable && memory.userReview != false) 'review_wrong': l10n.memoryReviewWrong,
      if (canUse && suppressed) 'use_allow': l10n.memoryAllowUse,
      if (canUse && !suppressed) 'use_suppress': l10n.memoryDontUse,
      if (canRevert) 'revert': l10n.undo,
    },
    swipeTrailing: editable ? const ['delete'] : const [],
    enabled: !applyingUse && !reverting,
    action: (value) async {
      Future<void> report(Future<bool> mutation) async {
        if (!await mutation && context.mounted) OmiFeedback.error(context, l10n.somethingWentWrong);
      }

      switch (value) {
        case null:
          open(value);
        case 'open':
          await showMemoryQuickEditSheet(context, memory, provider, readOnly: true);
        case 'edit':
          onEdit(context, memory, provider);
        case 'delete':
          OmiHaptics.medium();
          // Fire and forget, as the classic row does: the row must not stay pending for the Undo toast.
          unawaited(deleteMemoryWithUndo(context, provider, memory));
        case 'open_conversation':
          await openMemoryConversation(context, memory);
        case 'review_right' || 'review_wrong':
          await report(provider.reviewMemory(memory, value == 'review_right'));
        case 'use_allow':
          await report(provider.setMemoryUse(memory, MemoryUseAction.allow));
        case 'use_suppress':
          await report(provider.setMemoryUse(memory, MemoryUseAction.suppress));
        case 'revert':
          await report(provider.revertSupersededFact(memory));
      }
    },
  );
}
