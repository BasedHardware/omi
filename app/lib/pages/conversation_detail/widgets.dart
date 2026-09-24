import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:tuple/tuple.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';
import 'package:omi/pages/conversation_detail/share.dart';
import 'package:omi/pages/conversation_detail/widgets/calendar_event_sheets.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_markdown_widget.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/pages/conversations/widgets/move_to_folder_sheet.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/folders/folder_icon_mapper.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/widgets/omi_map_preview.dart';
import 'maps_util.dart';

/// The detail page's length label: the same rule and format as the conversation list row
/// ([ServerConversation.getDurationInSeconds], [OmiDuration.compact]), so both always agree.
/// Empty when there is no measurable length.
String conversationDurationLabel(ServerConversation conversation, [AppLocalizations? l10n]) {
  final seconds = conversation.getDurationInSeconds();
  if (seconds <= 0) return '';
  return OmiDuration.compact(seconds, l10n);
}

class GetSummaryWidgets extends StatelessWidget {
  final String searchQuery;
  const GetSummaryWidgets({super.key, this.searchQuery = ''});

  void _showCalendarEventDetails(BuildContext context, CalendarEventLink calendarEvent) {
    final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
    showCalendarEventDetailsSheet(context, calendarEvent, onUnlink: provider.unlinkCalendarEvent);
  }

  Widget _buildInfoChips(BuildContext context, ServerConversation conversation) {
    final dates = OmiDateFormat.of(context);
    final start = conversation.startedAt ?? conversation.createdAt;
    final hasCalendarEvent = conversation.calendarEvent != null;
    final duration = conversationDurationLabel(conversation, context.l10n);

    return Consumer<FolderProvider>(
      builder: (context, folderProvider, _) {
        final folder = conversation.folderId != null ? folderProvider.getFolderById(conversation.folderId!) : null;

        return Wrap(
          spacing: OmiSpacing.xs,
          runSpacing: OmiSpacing.xs,
          children: [
            // Date & time; the Google Calendar logo and a tap target when an event is linked.
            _buildChip(
              label: '${dates.dayHeader(start)}, ${dates.time(start)}',
              icon: hasCalendarEvent ? null : Icons.calendar_today,
              leadingWidget: hasCalendarEvent
                  ? ClipRRect(
                      borderRadius: const BorderRadius.all(Radius.circular(3)),
                      child: Image.asset(
                        'assets/integration_app_logos/google-calendar.png',
                        width: 14,
                        height: 14,
                        fit: BoxFit.cover,
                      ),
                    )
                  : null,
              onTap: hasCalendarEvent ? () => _showCalendarEventDetails(context, conversation.calendarEvent!) : null,
            ),
            if (duration.isNotEmpty)
              _buildChip(
                label: duration,
                icon: Icons.timelapse,
                semanticsLabel: OmiDuration.long(conversation.getDurationInSeconds(), context.l10n),
              ),
            if (hasCalendarEvent && conversation.calendarEvent!.attendees.isNotEmpty)
              _buildChip(
                label: formatAttendeesLabel(conversation.calendarEvent!.attendees),
                icon: Icons.people,
                onTap: () => _showCalendarEventDetails(context, conversation.calendarEvent!),
              ),
            _buildFolderChip(
              context: context,
              folder: folder,
              conversationId: conversation.id,
              currentFolderId: conversation.folderId,
            ),
            // Visibility chip — needs its own Selector to detect mutation on the same object
            Selector<ConversationDetailProvider, ConversationVisibility>(
              selector: (_, provider) => provider.conversation.visibility,
              builder: (context, _, __) {
                return _buildVisibilityChip(
                  context: context,
                  conversation: context.read<ConversationDetailProvider>().conversation,
                );
              },
            ),
          ],
        );
      },
    );
  }

  Widget _buildFolderChip({
    required BuildContext context,
    required Folder? folder,
    required String conversationId,
    required String? currentFolderId,
  }) {
    final color = folder != null ? folder.colorValue : OmiColors.textSecondary;
    return _buildMenuChip(
      color: color,
      background: folder != null ? folder.colorValue.withValues(alpha: 0.2) : OmiColors.surface2,
      leading: FaIcon(folderIconToFa(folder?.icon), size: 12, color: color),
      label: folder?.name ?? context.l10n.noFolder,
      onTap: () async {
        OmiHaptics.selection();
        PlatformManager.instance.analytics.conversationDetailFolderChipClicked(
          conversationId: conversationId,
          currentFolderId: currentFolderId,
        );

        final folderProvider = Provider.of<FolderProvider>(context, listen: false);
        if (folderProvider.folders.isEmpty) {
          await folderProvider.loadFolders();
        }
        if (!context.mounted) return;
        final newFolderId = await showMoveToFolderSheet(
          context,
          conversationId: conversationId,
          currentFolderId: currentFolderId,
        );
        // If folder was changed, update locally immediately for instant UI feedback
        if (newFolderId != null && context.mounted) {
          context.read<ConversationDetailProvider>().updateFolderIdLocally(newFolderId);
          PlatformManager.instance.analytics.conversationMovedToFolder(
            conversationId: conversationId,
            fromFolderId: currentFolderId,
            toFolderId: newFolderId,
            source: 'detail_page_sheet',
          );
        }
      },
    );
  }

  Widget _buildVisibilityChip({required BuildContext context, required ServerConversation conversation}) {
    final isPrivate = conversation.visibility == ConversationVisibility.private_;
    final color = isPrivate ? OmiColors.textSecondary : OmiColors.success;
    return _buildMenuChip(
      color: color,
      background: isPrivate ? OmiColors.surface2 : OmiColors.successSurface,
      leading: Icon(isPrivate ? Icons.lock_outline : Icons.public, size: 14, color: color),
      label: isPrivate ? context.l10n.private : context.l10n.shared,
      onTap: () {
        OmiHaptics.selection();
        _showVisibilitySheet(context, conversation);
      },
    );
  }

  /// A chip that opens a picker: pill, leading glyph, label and a drop-down caret.
  Widget _buildMenuChip({
    required Color color,
    required Color background,
    required Widget leading,
    required String label,
    required VoidCallback onTap,
  }) {
    return Semantics(
      button: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: OmiRadius.pillAll,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 6),
          decoration: BoxDecoration(color: background, borderRadius: OmiRadius.pillAll),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              leading,
              const SizedBox(width: 6),
              Text(label, style: OmiType.footnote.copyWith(color: color, fontWeight: FontWeight.w500)),
              const SizedBox(width: OmiSpacing.xxs),
              Icon(Icons.arrow_drop_down, size: 16, color: color),
            ],
          ),
        ),
      ),
    );
  }

  void _showVisibilitySheet(BuildContext context, ServerConversation conversation) {
    final provider = context.read<ConversationDetailProvider>();

    Future<void> choose(BuildContext sheetContext, ConversationVisibility visibility) async {
      if (conversation.visibility == visibility) {
        Navigator.pop(sheetContext);
        return;
      }
      final previousVisibility = conversation.visibility;
      provider.updateVisibilityLocally(visibility);
      Navigator.pop(sheetContext);
      final success = await setConversationVisibility(conversation.id, visibility: visibility.value);
      if (!success) {
        provider.updateVisibilityLocally(previousVisibility);
        return;
      }
      PlatformManager.instance.analytics.conversationVisibilityChanged(
        conversationId: conversation.id,
        fromVisibility: previousVisibility.value,
        toVisibility: visibility.value,
      );
      if (visibility == ConversationVisibility.shared && context.mounted) shareConversationLink(conversation);
    }

    showOmiSheet<void>(
      context: context,
      title: context.l10n.visibility,
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      builder: (sheetContext) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildVisibilityOption(
            icon: Icons.lock_outline,
            label: context.l10n.private,
            description: context.l10n.onlyYouCanSeeConversation,
            isSelected: conversation.visibility == ConversationVisibility.private_,
            onTap: () => choose(sheetContext, ConversationVisibility.private_),
          ),
          _buildVisibilityOption(
            icon: Icons.public,
            label: context.l10n.shared,
            description: context.l10n.anyoneWithLinkCanView,
            isSelected: conversation.visibility == ConversationVisibility.shared,
            onTap: () => choose(sheetContext, ConversationVisibility.shared),
          ),
        ],
      ),
    );
  }

  Widget _buildVisibilityOption({
    required IconData icon,
    required String label,
    required String description,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Semantics(
      button: true,
      selected: isSelected,
      child: InkWell(
        onTap: onTap,
        borderRadius: OmiRadius.mdAll,
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xxs),
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
          decoration: BoxDecoration(
            color: isSelected ? OmiColors.surface2 : Colors.transparent,
            borderRadius: OmiRadius.mdAll,
            border: isSelected ? Border.all(color: OmiColors.border) : null,
          ),
          child: Row(
            children: [
              Icon(icon, size: 22, color: isSelected ? OmiColors.textPrimary : OmiColors.textTertiary),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label, style: OmiType.callout.copyWith(fontWeight: FontWeight.w500)),
                    const SizedBox(height: 2),
                    Text(description, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                  ],
                ),
              ),
              if (isSelected) const Icon(Icons.check_circle, color: OmiColors.textPrimary, size: 22),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildChip({
    required String label,
    IconData? icon,
    Widget? leadingWidget,
    VoidCallback? onTap,
    String? semanticsLabel,
  }) {
    final chip = Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.xs),
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (leadingWidget != null)
            leadingWidget
          else if (icon != null)
            Icon(icon, size: 14, color: OmiColors.textSecondary),
          const SizedBox(width: 6),
          Text(
            label,
            semanticsLabel: semanticsLabel,
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );

    if (onTap == null) return chip;
    return Semantics(
      button: true,
      child: InkWell(onTap: onTap, borderRadius: OmiRadius.mdAll, child: chip),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Selector<ConversationDetailProvider, Tuple3<ServerConversation, TextEditingController?, FocusNode?>>(
      selector: (context, provider) => Tuple3(provider.conversation, provider.titleController, provider.titleFocusNode),
      builder: (context, data, child) {
        ServerConversation conversation = data.item1;
        return Column(
          mainAxisAlignment: MainAxisAlignment.start,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: OmiSpacing.xs),
            conversation.discarded
                ? Text(context.l10n.discardedConversation, style: OmiType.title1)
                : ConversationTitleField(
                    focusNode: data.item3,
                    controller: data.item2,
                    style: OmiType.title1,
                  ),
            const SizedBox(height: OmiSpacing.md),
            _buildInfoChips(context, conversation),
            const SizedBox(height: OmiSpacing.md),
            conversation.discarded ? const SizedBox.shrink() : const SizedBox(height: OmiSpacing.xs),
          ],
        );
      },
    );
  }
}

/// The conversation title, edited in place.
///
/// One line with a Done key; an empty title shows the "Untitled Conversation" placeholder. The
/// edit is saved when editing ends — Done, or tapping away — and the outcome is announced
/// ("Saved" / an error that restores the old title). Blank or unchanged text is not saved.
class ConversationTitleField extends StatefulWidget {
  final TextStyle style;
  final TextEditingController? controller;
  final FocusNode? focusNode;

  const ConversationTitleField({super.key, required this.style, required this.controller, required this.focusNode});

  @override
  State<ConversationTitleField> createState() => _ConversationTitleFieldState();
}

class _ConversationTitleFieldState extends State<ConversationTitleField> {
  @override
  void initState() {
    super.initState();
    widget.focusNode?.addListener(_onFocusChanged);
  }

  @override
  void didUpdateWidget(ConversationTitleField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.focusNode != widget.focusNode) {
      oldWidget.focusNode?.removeListener(_onFocusChanged);
      widget.focusNode?.addListener(_onFocusChanged);
    }
  }

  @override
  void dispose() {
    widget.focusNode?.removeListener(_onFocusChanged);
    super.dispose();
  }

  void _onFocusChanged() {
    if (widget.focusNode?.hasFocus ?? true) return;
    _save();
  }

  Future<void> _save() async {
    final controller = widget.controller;
    if (controller == null) return;
    final l10n = context.l10n;
    final saved = await context.read<ConversationDetailProvider>().saveTitle(controller.text);
    if (!mounted || saved == null) return;
    if (saved) {
      OmiFeedback.confirm(context, l10n.saved);
    } else {
      OmiFeedback.error(context, l10n.failedToUpdateConversationTitle);
    }
  }

  @override
  Widget build(BuildContext context) {
    return TextField(
      keyboardType: TextInputType.text,
      textInputAction: TextInputAction.done,
      maxLines: 1,
      focusNode: widget.focusNode,
      controller: widget.controller,
      onSubmitted: (_) => widget.focusNode?.unfocus(),
      decoration: InputDecoration(
        border: const OutlineInputBorder(borderSide: BorderSide.none),
        contentPadding: EdgeInsets.zero,
        hintText: context.l10n.untitledConversation,
        hintStyle: widget.style.copyWith(color: OmiColors.textTertiary),
      ),
      style: widget.style,
    );
  }
}

class ReprocessDiscardedWidget extends StatelessWidget {
  const ReprocessDiscardedWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        if (provider.loadingReprocessConversation && provider.reprocessConversationId == provider.conversation.id) {
          return Padding(
            padding: const EdgeInsets.only(top: 18.0),
            child: OmiLoadingState(
              label: provider.conversation.discarded
                  ? context.l10n.summarizingConversation
                  : context.l10n.resummarizingConversation,
            ),
          );
        }
        return _SummaryCallToAction(
          message: context.l10n.nothingInterestingRetry,
          actionLabel: context.l10n.summarize,
          onPressed: () => provider.reprocessConversation(),
        );
      },
    );
  }
}

/// A centred sentence with one secondary button under it ("Summarize", "Generate Summary").
class _SummaryCallToAction extends StatelessWidget {
  const _SummaryCallToAction({required this.message, required this.actionLabel, required this.onPressed});

  final String message;
  final String actionLabel;
  final Future<void> Function() onPressed;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xxl),
      child: Column(
        children: [
          Text(message, style: OmiType.title3, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.xl),
          OmiButton.secondary(label: actionLabel, onPressed: onPressed),
        ],
      ),
    );
  }
}

class AppResultDetailWidget extends StatefulWidget {
  final ConversationSummarySelection summarySelection;
  final App? app;
  final ServerConversation conversation;
  final String searchQuery;
  final int currentResultIndex;
  final void Function(ConversationSummarySelection selection, String newContent)? onSaveSummarySelection;
  final void Function(ConversationSummarySelection selection)? onEditStarted;
  final void Function(ConversationSummarySelection selection)? onEditCancelled;
  final bool Function()? canStartEditing;
  final bool asSliver;

  const AppResultDetailWidget({
    super.key,
    required this.summarySelection,
    required this.app,
    required this.conversation,
    this.searchQuery = '',
    this.currentResultIndex = -1,
    this.onSaveSummarySelection,
    this.onEditStarted,
    this.onEditCancelled,
    this.canStartEditing,
    this.asSliver = false,
  });

  @override
  State<AppResultDetailWidget> createState() => _AppResultDetailWidgetState();
}

class _AppResultDetailWidgetState extends State<AppResultDetailWidget> {
  bool _isEditing = false;
  TextEditingController? _controller;
  FocusNode? _focusNode;
  ConversationSummarySelection? _editingSelection;
  String? _editingOriginalContent;

  @override
  void dispose() {
    _controller?.dispose();
    _focusNode?.dispose();
    super.dispose();
  }

  void _startEditing(String currentContent) {
    final selection = widget.summarySelection;
    if (!selection.canEdit(widget.conversation)) return;
    if (widget.canStartEditing != null && !widget.canStartEditing!()) return;
    OmiHaptics.medium();
    final controller = TextEditingController(text: currentContent);
    final focusNode = FocusNode();
    setState(() {
      _controller = controller;
      _focusNode = focusNode;
      _isEditing = true;
      _editingSelection = selection;
      _editingOriginalContent = currentContent;
    });
    widget.onEditStarted?.call(selection);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      focusNode.requestFocus();
    });
  }

  void _exitEditing({bool cancelled = false}) {
    final controller = _controller;
    final focusNode = _focusNode;
    final selection = _editingSelection ?? widget.summarySelection;
    setState(() {
      _isEditing = false;
      _controller = null;
      _focusNode = null;
      _editingSelection = null;
      _editingOriginalContent = null;
    });
    controller?.dispose();
    focusNode?.dispose();
    if (cancelled) widget.onEditCancelled?.call(selection);
  }

  void _save() {
    final newContent = _controller?.text.trim() ?? '';
    final selection = _editingSelection ?? widget.summarySelection;
    final original = _editingOriginalContent ?? selection.content;
    if (newContent.isNotEmpty && newContent != original.trim()) {
      widget.onSaveSummarySelection?.call(selection, newContent);
    }
    _exitEditing();
  }

  /// Attribution label for the summary source. The selected non-app summary is
  /// Omi's own "Summary" — the same name the bottom pill and desktop use;
  /// "Unknown App" is reserved for an app result whose catalog lookup failed
  /// (SCA-359), including legacy results without an app id.
  String _summarySourceLabel(BuildContext context, ConversationSummarySelection selection) {
    if (widget.app != null) return widget.app!.name.decodeString;
    return selection.isApp ? context.l10n.unknownApp : context.l10n.summary;
  }

  Widget _buildNoSummaryForApp(BuildContext context) {
    return Semantics(
      button: true,
      child: GestureDetector(
        onTap: () => showSummarizedAppsSheet(context),
        child: Text(context.l10n.noSummaryForApp, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final selection = widget.summarySelection;
    final String content = selection.content.decodeString;

    if (widget.asSliver) {
      return _buildSliver(context, content, selection);
    }

    return Container(
      margin: const EdgeInsets.only(bottom: OmiSpacing.lg),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
            child: content.isEmpty
                ? _buildNoSummaryForApp(context)
                : _isEditing
                    ? _buildEditor(context)
                    : GestureDetector(
                        onDoubleTap: widget.onSaveSummarySelection == null || !selection.canEdit(widget.conversation)
                            ? null
                            : () => _startEditing(content),
                        child: ConversationMarkdownWidget(
                          content: content,
                          searchQuery: widget.searchQuery,
                          currentResultIndex: widget.currentResultIndex,
                        ),
                      ),
          ),
          if (content.isNotEmpty && !_isEditing) _buildAppAttribution(context, selection),
        ],
      ),
    );
  }

  Widget _buildEditor(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _controller,
          focusNode: _focusNode,
          minLines: 6,
          maxLines: 12,
          maxLength: 10000,
          style: OmiType.callout.copyWith(height: 1.5),
          decoration: InputDecoration(
            filled: true,
            fillColor: OmiColors.surface1,
            border: const OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none),
            contentPadding: const EdgeInsets.all(14),
            counterStyle: OmiType.caption.copyWith(color: OmiColors.textTertiary),
          ),
        ),
        const SizedBox(height: OmiSpacing.sm),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            OmiButton.tertiary(
              label: context.l10n.cancel,
              size: OmiButtonSize.compact,
              onPressed: () => _exitEditing(cancelled: true),
            ),
            const SizedBox(width: OmiSpacing.xs),
            OmiButton(label: context.l10n.save, size: OmiButtonSize.compact, onPressed: _save),
          ],
        ),
      ],
    );
  }
}

class GetAppsWidgets extends StatelessWidget {
  final String searchQuery;
  final int currentResultIndex;
  final void Function(ConversationSummarySelection selection, String newContent)? onSaveSummarySelection;
  final void Function(ConversationSummarySelection selection)? onEditStarted;
  final void Function(ConversationSummarySelection selection)? onEditCancelled;
  final bool Function()? canStartEditing;
  const GetAppsWidgets({
    super.key,
    this.searchQuery = '',
    this.currentResultIndex = -1,
    this.onSaveSummarySelection,
    this.onEditStarted,
    this.onEditCancelled,
    this.canStartEditing,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        final selection = provider.getSummarySelection();
        if (selection.kind == ConversationSummaryKind.empty) {
          return SliverToBoxAdapter(child: child!);
        }

        return SliverMainAxisGroup(
          slivers: [
            if (!provider.conversation.discarded)
              AppResultDetailWidget(
                summarySelection: selection,
                app: selection.isApp ? provider.findAppById(selection.appId) : null,
                conversation: provider.conversation,
                searchQuery: searchQuery,
                currentResultIndex: currentResultIndex,
                canStartEditing: canStartEditing,
                onEditStarted: onEditStarted == null ? null : (_) => onEditStarted!(selection),
                onEditCancelled: onEditCancelled == null ? null : (_) => onEditCancelled!(selection),
                onSaveSummarySelection: onSaveSummarySelection,
                asSliver: true,
              ),
            const SliverToBoxAdapter(child: SizedBox(height: OmiSpacing.xs)),
          ],
        );
      },
      child: _SummaryCallToAction(
        message: context.l10n.noSummaryForConversation,
        actionLabel: context.l10n.generateSummary,
        onPressed: () => showSummarizedAppsSheet(context),
      ),
    );
  }
}

class GetGeolocationWidgets extends StatelessWidget {
  const GetGeolocationWidgets({super.key});

  // Helper function to shorten address - show only neighborhood/area and city
  String _getShortAddress(BuildContext context, String? fullAddress) {
    if (fullAddress == null || fullAddress.isEmpty) {
      return context.l10n.unknownLocation;
    }

    // Split address by commas
    final parts = fullAddress.split(',').map((e) => e.trim()).toList();

    // If address has multiple parts, take the last 2-3 meaningful parts
    if (parts.length >= 3) {
      // Take neighborhood/area and city (skip street address and zip code)
      return '${parts[parts.length - 3]}, ${parts[parts.length - 2]}';
    } else if (parts.length == 2) {
      return '${parts[0]}, ${parts[1]}';
    }

    return fullAddress;
  }

  @override
  Widget build(BuildContext context) {
    return Selector<ConversationDetailProvider, Geolocation?>(
      selector: (context, provider) {
        if (provider.conversation.discarded) return null;
        return provider.conversation.geolocation;
      },
      builder: (context, geolocation, child) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: geolocation == null
              ? []
              : [
                  const SizedBox(height: 12),
                  GestureDetector(
                    onTap: () async {
                      MapsUtil.launchMap(geolocation.latitude!, geolocation.longitude!);
                    },
                    child: ClipRRect(
                      borderRadius: OmiRadius.lgAll,
                      child: SizedBox(
                        height: 200,
                        child: Stack(
                          children: [
                            // Map Image — served by the backend static-map
                            // proxy through the shared preview widget; offline
                            // or on failure it renders the pin-dot canvas.
                            OmiMapPreview(
                              key: const ValueKey('conversation_location_map'),
                              pins: [OmiMapPin(latitude: geolocation.latitude!, longitude: geolocation.longitude!)],
                              backgroundColor: OmiColors.surface2,
                            ),
                            // Gradient blur overlay from bottom
                            Positioned(
                              bottom: 0,
                              left: 0,
                              right: 0,
                              child: Container(
                                height: 80,
                                decoration: BoxDecoration(
                                  gradient: LinearGradient(
                                    begin: Alignment.bottomCenter,
                                    end: Alignment.topCenter,
                                    colors: [Colors.black.withValues(alpha: 0.6), Colors.black.withValues(alpha: 0.0)],
                                  ),
                                ),
                              ),
                            ),
                            // Location text at bottom left
                            Positioned(
                              bottom: 16,
                              left: 16,
                              right: 16,
                              child: Text(
                                _getShortAddress(context, geolocation.address?.decodeString),
                                style: OmiType.subhead.copyWith(
                                  fontWeight: FontWeight.w500,
                                  shadows: const [Shadow(offset: Offset(0, 1), blurRadius: 2, color: Colors.black)],
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                ],
        );
      },
    );
  }
}

extension _AppResultDetailWidgetSliver on _AppResultDetailWidgetState {
  Widget _buildSliver(BuildContext context, String content, ConversationSummarySelection selection) {
    if (content.isEmpty || _isEditing) {
      return SliverMainAxisGroup(
        slivers: [
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
              child: content.isEmpty ? _buildNoSummaryForApp(context) : _buildEditor(context),
            ),
          ),
          const SliverToBoxAdapter(child: SizedBox(height: OmiSpacing.lg)),
        ],
      );
    }

    return SliverMainAxisGroup(
      slivers: [
        SliverPadding(
          padding: const EdgeInsets.only(bottom: OmiSpacing.lg),
          sliver: ConversationMarkdownSliver(
            content: content,
            searchQuery: widget.searchQuery,
            currentResultIndex: widget.currentResultIndex,
            onDoubleTap: widget.onSaveSummarySelection == null || !selection.canEdit(widget.conversation)
                ? null
                : () => _startEditing(content),
          ),
        ),
        SliverToBoxAdapter(child: _buildAppAttribution(context, selection)),
      ],
    );
  }

  Widget _buildAppAttribution(BuildContext context, ConversationSummarySelection selection) {
    const avatarRadius = 12.0;
    final app = widget.app;
    final Widget avatar;
    if (app != null) {
      avatar = CachedNetworkImage(
        imageUrl: app.getImageUrl(),
        imageBuilder: (context, imageProvider) =>
            CircleAvatar(backgroundColor: OmiColors.textPrimary, radius: avatarRadius, backgroundImage: imageProvider),
        errorWidget: (context, url, error) => const CircleAvatar(
          backgroundColor: OmiColors.textPrimary,
          radius: avatarRadius,
          child: Icon(Icons.error_outline_rounded, size: 12),
        ),
        progressIndicatorBuilder: (context, url, progress) => const CircleAvatar(
          backgroundColor: OmiColors.surface2,
          radius: avatarRadius,
          child: OmiSpinner(size: OmiSpinnerSize.small),
        ),
      );
    } else {
      avatar = Container(
        decoration: BoxDecoration(
          image: DecorationImage(image: AssetImage(Assets.images.background.path), fit: BoxFit.cover),
          borderRadius: OmiRadius.mdAll,
        ),
        height: 24,
        width: 24,
        alignment: Alignment.center,
        child: Image.asset(Assets.images.herologo.path, height: 16, width: 16),
      );
    }

    return Semantics(
      button: app != null,
      child: GestureDetector(
        onTap: () async {
          if (app != null) {
            PlatformManager.instance.analytics.pageOpened('App Detail');
            await routeToPage(context, AppDetailPage(app: app));
          }
        },
        child: Padding(
          padding: const EdgeInsets.only(top: OmiSpacing.sm, left: OmiSpacing.xxs),
          child: Row(
            children: [
              avatar,
              const SizedBox(width: OmiSpacing.xs),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _summarySourceLabel(context, selection),
                      maxLines: 1,
                      style: OmiType.footnote.copyWith(fontWeight: FontWeight.w500),
                    ),
                    if (app != null)
                      Text(
                        app.description.decodeString,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                      ),
                  ],
                ),
              ),
              const SizedBox(
                width: 42,
                child: Icon(Icons.arrow_forward_ios, color: OmiColors.textPrimary, size: 20),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
