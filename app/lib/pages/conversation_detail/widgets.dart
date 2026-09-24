import 'dart:ui';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/webhooks.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';
import 'package:omi/pages/conversation_detail/test_prompts.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_markdown_widget.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/widgets/omi_map_preview.dart';
import 'package:url_launcher/url_launcher.dart';
import 'maps_util.dart';

// Highlight search matches with current result highlighting
List<TextSpan> highlightSearchMatches(String text, String searchQuery, {int currentResultIndex = -1}) {
  if (searchQuery.isEmpty) {
    return [TextSpan(text: text)];
  }

  final List<TextSpan> spans = [];
  final String lowerText = text.toLowerCase();
  final String lowerQuery = searchQuery.toLowerCase();

  int start = 0;
  int index = lowerText.indexOf(lowerQuery, start);
  int matchCount = 0;

  while (index != -1) {
    if (index > start) {
      spans.add(TextSpan(text: text.substring(start, index)));
    }

    bool isCurrentResult = currentResultIndex >= 0 && matchCount == currentResultIndex;

    spans.add(
      TextSpan(
        text: text.substring(index, index + searchQuery.length),
        style: TextStyle(
          backgroundColor:
              isCurrentResult ? Colors.orange.withValues(alpha: 0.9) : Colors.deepPurple.withValues(alpha: 0.6),
          color: Colors.white,
          fontWeight: FontWeight.bold,
        ),
      ),
    );

    matchCount++;
    start = index + searchQuery.length;
    index = lowerText.indexOf(lowerQuery, start);
  }

  // Add remaining text
  if (start < text.length) {
    spans.add(TextSpan(text: text.substring(start)));
  }

  return spans;
}

class ActionItemsListWidget extends StatelessWidget {
  const ActionItemsListWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        return Column(
          children: [
            provider.conversation.structured.actionItems.isNotEmpty
                ? Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        context.l10n.actionItems,
                        style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
                      ),
                      IconButton(
                        onPressed: () {
                          Clipboard.setData(
                            ClipboardData(
                              text:
                                  '- ${provider.conversation.structured.actionItems.map((e) => e.description.decodeString).join('\n- ')}',
                            ),
                          );
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(context.l10n.actionItemsCopiedToClipboard),
                              duration: const Duration(seconds: 2),
                            ),
                          );
                          PlatformManager.instance.analytics.copiedConversationDetails(
                            provider.conversation,
                            source: 'Action Items',
                          );
                        },
                        icon: const Icon(Icons.copy_rounded, color: Colors.white, size: 20),
                      ),
                    ],
                  )
                : const SizedBox.shrink(),
            ListView.builder(
              itemCount: provider.conversation.structured.actionItems.where((e) => !e.deleted).length,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemBuilder: (context, idx) {
                var item = provider.conversation.structured.actionItems.where((e) => !e.deleted).toList()[idx];
                return Dismissible(
                  key: Key(item.description),
                  direction: DismissDirection.endToStart,
                  background: Container(
                    alignment: Alignment.centerRight,
                    padding: const EdgeInsets.only(right: 20.0),
                    color: Colors.red,
                    child: const Icon(Icons.delete, color: Colors.white),
                  ),
                  onDismissed: (direction) {
                    var tempItem = provider.conversation.structured.actionItems[idx];
                    var tempIdx = idx;
                    provider.deleteActionItem(idx);
                    provider.deleteActionItemPermanently(tempItem, tempIdx);
                    PlatformManager.instance.analytics.deletedActionItem(provider.conversation);
                    // ScaffoldMessenger.of(context)
                    //     .showSnackBar(
                    //       SnackBar(
                    //         content: const Text('Action Item deleted successfully 🗑️'),
                    //         padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                    //         action: SnackBarAction(
                    //           label: 'Undo',
                    //           textColor: Colors.white,
                    //           onPressed: () {
                    //             provider.undoDeleteActionItem(idx);
                    //           },
                    //         ),
                    //       ),
                    //     )
                    //     .closed
                    //     .then((reason) {
                    //   if (reason != SnackBarClosedReason.action) {
                    //     provider.deleteActionItemPermanently(tempItem, tempIdx);
                    //     PlatformManager.instance.analytics.deletedActionItem(provider.conversation);
                    //   }
                    // });
                  },
                  child: Padding(
                    padding: const EdgeInsets.only(top: 10, bottom: 2),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: const EdgeInsets.only(top: 6.0),
                          child: SizedBox(
                            height: 22.0,
                            width: 22.0,
                            child: Checkbox(
                              shape: const CircleBorder(),
                              value: item.completed,
                              onChanged: (value) {
                                if (value != null) {
                                  context.read<ConversationDetailProvider>().updateActionItemState(value, idx);
                                  setConversationActionItemState(provider.conversation.id, [idx], [value]);
                                  if (value) {
                                    PlatformManager.instance.analytics.checkedActionItem(provider.conversation, idx);
                                  } else {
                                    PlatformManager.instance.analytics.uncheckedActionItem(provider.conversation, idx);
                                  }
                                }
                              },
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: SelectionArea(
                            child: Text(
                              item.description.decodeString,
                              style: TextStyle(color: Colors.grey.shade300, fontSize: 16, height: 1.3),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ],
        );
      },
    );
  }
}

class GetEditTextField extends StatefulWidget {
  final String conversationId;
  final String content;
  final TextStyle style;
  final TextEditingController? controller;
  final FocusNode? focusNode;

  const GetEditTextField({
    super.key,
    required this.content,
    required this.style,
    required this.conversationId,
    required this.controller,
    required this.focusNode,
  });

  @override
  State<GetEditTextField> createState() => _GetEditTextFieldState();
}

class _GetEditTextFieldState extends State<GetEditTextField> {
  @override
  Widget build(BuildContext context) {
    return TextField(
      keyboardType: TextInputType.multiline,
      minLines: 1,
      maxLines: 3,
      focusNode: widget.focusNode,
      decoration: const InputDecoration(
        border: OutlineInputBorder(borderSide: BorderSide.none),
        contentPadding: EdgeInsets.all(0),
      ),
      controller: widget.controller,
      enabled: true,
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
          return Center(
            child: Padding(
              padding: const EdgeInsets.only(top: 18.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  const CircularProgressIndicator(valueColor: AlwaysStoppedAnimation<Color>(Colors.white)),
                  const SizedBox(width: 16),
                  Text(
                    provider.conversation.discarded
                        ? context.l10n.summarizingConversation
                        : context.l10n.resummarizingConversation,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                  ),
                ],
              ),
            ),
          );
        }
        return ListView(
          shrinkWrap: true,
          children: [
            const SizedBox(height: 32),
            Text(
              context.l10n.nothingInterestingRetry,
              style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 20),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  decoration: BoxDecoration(
                    border: const GradientBoxBorder(
                      gradient: LinearGradient(
                        colors: [
                          Color.fromARGB(127, 208, 208, 208),
                          Color.fromARGB(127, 188, 99, 121),
                          Color.fromARGB(127, 86, 101, 182),
                          Color.fromARGB(127, 126, 190, 236),
                        ],
                      ),
                      width: 2,
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: MaterialButton(
                    onPressed: () async {
                      await provider.reprocessConversation();
                    },
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
                      child: Text(context.l10n.summarize, style: const TextStyle(color: Colors.white, fontSize: 16)),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 32),
          ],
        );
      },
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
    HapticFeedback.mediumImpact();
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

  @override
  Widget build(BuildContext context) {
    final selection = widget.summarySelection;
    final String content = selection.content.decodeString;

    if (widget.asSliver) {
      return _buildSliver(context, content, selection);
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 20),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: content.isEmpty
                ? Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Expanded(
                        child: GestureDetector(
                          onTap: () {
                            showModalBottomSheet(
                              context: context,
                              isScrollControlled: true,
                              backgroundColor: Colors.transparent,
                              builder: (context) => const SummarizedAppsBottomSheet(),
                            );
                          },
                          child: RichText(
                            text: TextSpan(
                              style: const TextStyle(color: Colors.grey),
                              text: context.l10n.noSummaryForApp,
                            ),
                          ),
                        ),
                      ),
                    ],
                  )
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

          // App info in a more subtle format below the content - only show if content is not empty
          if (content.isNotEmpty && !_isEditing)
            GestureDetector(
              onTap: () async {
                if (widget.app != null) {
                  PlatformManager.instance.analytics.pageOpened('App Detail');
                  await routeToPage(context, AppDetailPage(app: widget.app!));
                }
              },
              child: Padding(
                padding: const EdgeInsets.only(top: 12, left: 4),
                child: Row(
                  children: [
                    // App icon
                    widget.app != null
                        ? CachedNetworkImage(
                            imageUrl: widget.app!.getImageUrl(),
                            imageBuilder: (context, imageProvider) {
                              return CircleAvatar(
                                backgroundColor: Colors.white,
                                radius: 12,
                                backgroundImage: imageProvider,
                              );
                            },
                            errorWidget: (context, url, error) {
                              return const CircleAvatar(
                                backgroundColor: Colors.white,
                                radius: 12,
                                child: Icon(Icons.error_outline_rounded, size: 12),
                              );
                            },
                            progressIndicatorBuilder: (context, url, progress) => CircleAvatar(
                              backgroundColor: Colors.white,
                              radius: 12,
                              child: CircularProgressIndicator(
                                value: progress.progress,
                                valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
                                strokeWidth: 2,
                              ),
                            ),
                          )
                        : Container(
                            decoration: BoxDecoration(
                              image: DecorationImage(
                                image: AssetImage(Assets.images.background.path),
                                fit: BoxFit.cover,
                              ),
                              borderRadius: const BorderRadius.all(Radius.circular(12.0)),
                            ),
                            height: 24,
                            width: 24,
                            child: Stack(
                              alignment: Alignment.center,
                              children: [Image.asset(Assets.images.herologo.path, height: 16, width: 16)],
                            ),
                          ),

                    const SizedBox(width: 8),

                    // App name and description with arrow
                    Expanded(
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  _summarySourceLabel(context, selection),
                                  maxLines: 1,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w500,
                                    color: Colors.white,
                                    fontSize: 14,
                                  ),
                                ),
                                if (widget.app != null)
                                  Text(
                                    widget.app!.description.decodeString,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(color: Colors.grey, fontSize: 12),
                                  ),
                              ],
                            ),
                          ),
                          const SizedBox(
                            width: 42,
                            child: Icon(Icons.arrow_forward_ios, color: Colors.white, size: 20),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
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
          style: const TextStyle(color: Colors.white, fontSize: 16, height: 1.5),
          decoration: InputDecoration(
            filled: true,
            fillColor: Colors.grey.shade900,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
            contentPadding: const EdgeInsets.all(14),
            counterStyle: TextStyle(color: Colors.grey.shade500),
          ),
        ),
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            TextButton(
              onPressed: () => _exitEditing(cancelled: true),
              child: Text(
                context.l10n.cancel,
                style: TextStyle(color: Colors.grey.shade300, fontWeight: FontWeight.w500),
              ),
            ),
            const SizedBox(width: 8),
            ElevatedButton(
              onPressed: _save,
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: Colors.black,
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              ),
              child: Text(context.l10n.save, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
            ),
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
            const SliverToBoxAdapter(child: SizedBox(height: 8)),
          ],
        );
      },
      child: ListView(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        children: [
          const SizedBox(height: 32),
          Text(
            context.l10n.noSummaryForConversation,
            style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 20),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                decoration: BoxDecoration(
                  border: const GradientBoxBorder(
                    gradient: LinearGradient(
                      colors: [
                        Color.fromARGB(127, 208, 208, 208),
                        Color.fromARGB(127, 188, 99, 121),
                        Color.fromARGB(127, 86, 101, 182),
                        Color.fromARGB(127, 126, 190, 236),
                      ],
                    ),
                    width: 2,
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: MaterialButton(
                  onPressed: () {
                    showModalBottomSheet(
                      context: context,
                      isScrollControlled: true,
                      backgroundColor: Colors.transparent,
                      builder: (context) => const SummarizedAppsBottomSheet(),
                    );
                  },
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
                    child: Text(
                      context.l10n.generateSummary,
                      style: const TextStyle(color: Colors.white, fontSize: 16),
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 32),
        ],
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
                      borderRadius: BorderRadius.circular(16),
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
                              backgroundColor: const Color(0xFF2A2A2A),
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
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 15,
                                  fontWeight: FontWeight.w500,
                                  shadows: [Shadow(offset: Offset(0, 1), blurRadius: 2, color: Colors.black)],
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
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: content.isEmpty
                  ? Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Expanded(
                          child: GestureDetector(
                            onTap: () {
                              showModalBottomSheet(
                                context: context,
                                isScrollControlled: true,
                                backgroundColor: Colors.transparent,
                                builder: (context) => const SummarizedAppsBottomSheet(),
                              );
                            },
                            child: RichText(
                              text: TextSpan(
                                style: const TextStyle(color: Colors.grey),
                                text: context.l10n.noSummaryForApp,
                              ),
                            ),
                          ),
                        ),
                      ],
                    )
                  : _buildEditor(context),
            ),
          ),
          const SliverToBoxAdapter(child: SizedBox(height: 20)),
        ],
      );
    }

    return SliverMainAxisGroup(
      slivers: [
        if (content.isNotEmpty)
          SliverPadding(
            padding: const EdgeInsets.only(bottom: 20),
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
    return GestureDetector(
      onTap: () async {
        if (widget.app != null) {
          PlatformManager.instance.analytics.pageOpened('App Detail');
          await routeToPage(context, AppDetailPage(app: widget.app!));
        }
      },
      child: Padding(
        padding: const EdgeInsets.only(top: 12, left: 4),
        child: Row(
          children: [
            widget.app != null
                ? CachedNetworkImage(
                    imageUrl: widget.app!.getImageUrl(),
                    imageBuilder: (context, imageProvider) {
                      return CircleAvatar(backgroundColor: Colors.white, radius: 12, backgroundImage: imageProvider);
                    },
                    errorWidget: (context, url, error) {
                      return const CircleAvatar(
                        backgroundColor: Colors.white,
                        radius: 12,
                        child: Icon(Icons.error_outline_rounded, size: 12),
                      );
                    },
                    progressIndicatorBuilder: (context, url, progress) => CircleAvatar(
                      backgroundColor: Colors.white,
                      radius: 12,
                      child: CircularProgressIndicator(
                        value: progress.progress,
                        valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
                        strokeWidth: 2,
                      ),
                    ),
                  )
                : Container(
                    decoration: BoxDecoration(
                      image: DecorationImage(image: AssetImage(Assets.images.background.path), fit: BoxFit.cover),
                      borderRadius: const BorderRadius.all(Radius.circular(12.0)),
                    ),
                    height: 24,
                    width: 24,
                    child: Stack(
                      alignment: Alignment.center,
                      children: [Image.asset(Assets.images.herologo.path, height: 16, width: 16)],
                    ),
                  ),
            const SizedBox(width: 8),
            Expanded(
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _summarySourceLabel(context, selection),
                          maxLines: 1,
                          style: const TextStyle(fontWeight: FontWeight.w500, color: Colors.white, fontSize: 14),
                        ),
                        if (widget.app != null)
                          Text(
                            widget.app!.description.decodeString,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(color: Colors.grey, fontSize: 12),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 42, child: Icon(Icons.arrow_forward_ios, color: Colors.white, size: 20)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

///************************************************
///************ SETTINGS BOTTOM SHEET *************
///************************************************

///************************************************

class GetSheetTitle extends StatelessWidget {
  const GetSheetTitle({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        return Column(
          children: [
            ListTile(
              title: Text(
                provider.conversation.discarded
                    ? context.l10n.discardedConversation
                    : provider.conversation.structured.title,
                style: Theme.of(context).textTheme.labelLarge,
              ),
              leading: const Icon(Icons.description),
              trailing: IconButton(
                icon: const Icon(Icons.cancel_outlined),
                onPressed: () {
                  Navigator.of(context).pop(true);
                },
              ),
            ),
            const SizedBox(height: 8),
          ],
        );
      },
    );
  }
}

class GetDevToolsOptions extends StatefulWidget {
  final ServerConversation conversation;

  const GetDevToolsOptions({super.key, required this.conversation});

  @override
  State<GetDevToolsOptions> createState() => _GetDevToolsOptionsState();
}

class _GetDevToolsOptionsState extends State<GetDevToolsOptions> {
  bool loadingAppIntegrationTest = false;

  void changeLoadingAppIntegrationTest(bool value) {
    setState(() {
      loadingAppIntegrationTest = value;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Card(
          shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
          child: ListTile(
            title: Text(context.l10n.triggerConversationIntegration),
            leading: loadingAppIntegrationTest
                ? const SizedBox(
                    height: 24,
                    width: 24,
                    child: CircularProgressIndicator(valueColor: AlwaysStoppedAnimation<Color>(Colors.white)),
                  )
                : const Icon(Icons.send_to_mobile_outlined),
            onTap: () {
              changeLoadingAppIntegrationTest(true);
              if (SharedPreferencesUtil().webhookOnConversationCreated.isEmpty) {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () {
                      Navigator.pop(context);
                    },
                    () {
                      Navigator.pop(context);
                      routeToPage(context, const DeveloperSettingsPage());
                    },
                    context.l10n.webhookUrlNotSet,
                    context.l10n.setWebhookUrlInSettings,
                    okButtonText: context.l10n.settings,
                  ),
                );
                changeLoadingAppIntegrationTest(false);
                return;
              } else {
                webhookOnConversationCreatedCall(widget.conversation, returnRawBody: true).then((response) {
                  if (context.mounted) {
                    showDialog(
                      context: context,
                      builder: (c) => getDialog(
                        context,
                        () => Navigator.pop(context),
                        () => Navigator.pop(context),
                        context.l10n.result,
                        response,
                        okButtonText: context.l10n.ok,
                        singleButton: true,
                      ),
                    );
                  }
                  changeLoadingAppIntegrationTest(false);
                });
              }
            },
          ),
        ),
        Card(
          shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
          child: ListTile(
            title: Text(context.l10n.testConversationPrompt),
            leading: const Icon(Icons.chat),
            trailing: const Icon(Icons.arrow_forward_ios, size: 20),
            onTap: () {
              routeToPage(context, TestPromptsPage(conversation: widget.conversation));
            },
          ),
        ),
      ],
    );
  }
}

class CalendarEventDetailsSheet extends StatefulWidget {
  final CalendarEventLink calendarEvent;
  final Future<void> Function()? onUnlink;

  const CalendarEventDetailsSheet({super.key, required this.calendarEvent, this.onUnlink});

  @override
  State<CalendarEventDetailsSheet> createState() => _CalendarEventDetailsSheetState();
}

class _CalendarEventDetailsSheetState extends State<CalendarEventDetailsSheet> {
  bool _unlinking = false;

  String _fmt(DateTime dt) {
    final h = dt.hour % 12 == 0 ? 12 : dt.hour % 12;
    final m = dt.minute.toString().padLeft(2, '0');
    final period = dt.hour < 12 ? 'AM' : 'PM';
    return '$h:$m $period';
  }

  Future<void> _shareWithAttendees() async {
    final emails = widget.calendarEvent.attendeeEmails;
    if (emails.isEmpty) return;
    final subject = Uri.encodeComponent('Notes: ${widget.calendarEvent.title}');
    final uri = Uri.parse('mailto:${emails.join(',')}?subject=$subject');
    await launchUrl(uri);
  }

  @override
  Widget build(BuildContext context) {
    final start = widget.calendarEvent.startTime;
    final end = widget.calendarEvent.endTime;
    final timeStr = '${_fmt(start)} – ${_fmt(end)}';

    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1A1A1A),
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      padding: EdgeInsets.fromLTRB(20, 16, 20, MediaQuery.of(context).padding.bottom + 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(color: Colors.grey[700], borderRadius: BorderRadius.circular(2)),
            ),
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              const Icon(Icons.calendar_today, size: 18, color: Colors.white70),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  widget.calendarEvent.title,
                  style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Icon(Icons.access_time, size: 16, color: Colors.white54),
              const SizedBox(width: 8),
              Text(timeStr, style: const TextStyle(color: Colors.white70, fontSize: 14)),
            ],
          ),
          if (widget.calendarEvent.attendees.isNotEmpty) ...[
            const SizedBox(height: 12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.people_outline, size: 16, color: Colors.white54),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    widget.calendarEvent.attendees.join(', '),
                    style: const TextStyle(color: Colors.white70, fontSize: 14),
                  ),
                ),
              ],
            ),
          ],
          if (widget.calendarEvent.htmlLink != null) ...[
            const SizedBox(height: 16),
            GestureDetector(
              onTap: () => launchUrl(Uri.parse(widget.calendarEvent.htmlLink!), mode: LaunchMode.externalApplication),
              child: const Text(
                'Open in Google Calendar',
                style: TextStyle(color: Color(0xFF4285F4), fontSize: 14, decoration: TextDecoration.underline),
              ),
            ),
          ],
          const SizedBox(height: 24),
          const Divider(color: Color(0xFF2C2C2E)),
          const SizedBox(height: 8),
          // Share with attendees button
          if (widget.calendarEvent.attendeeEmails.isNotEmpty)
            _ActionRow(icon: Icons.share_outlined, label: 'Share with attendees', onTap: _shareWithAttendees),
          // Unlink button
          if (widget.onUnlink != null)
            _ActionRow(
              icon: Icons.link_off,
              label: 'Unlink calendar event',
              color: Colors.redAccent,
              loading: _unlinking,
              onTap: () async {
                setState(() => _unlinking = true);
                await widget.onUnlink!();
                if (!context.mounted) return;
                Navigator.pop(context);
              },
            ),
        ],
      ),
    );
  }
}

class _ActionRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback? onTap;
  final Color color;
  final bool loading;

  const _ActionRow({
    required this.icon,
    required this.label,
    this.onTap,
    this.color = Colors.white,
    this.loading = false,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: loading ? null : onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 4),
        child: Row(
          children: [
            loading
                ? SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: color))
                : Icon(icon, size: 20, color: color),
            const SizedBox(width: 12),
            Text(label, style: TextStyle(color: color, fontSize: 15)),
          ],
        ),
      ),
    );
  }
}
