import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/webhooks.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/test_prompts.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_markdown_widget.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:tuple/tuple.dart';

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

    spans.add(TextSpan(
      text: text.substring(index, index + searchQuery.length),
      style: TextStyle(
        backgroundColor:
            isCurrentResult ? Colors.orange.withValues(alpha: 0.9) : Colors.deepPurple.withValues(alpha: 0.6),
        color: Colors.white,
        fontWeight: FontWeight.bold,
      ),
    ));

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

class GetSummaryWidgets extends StatelessWidget {
  final String searchQuery;
  const GetSummaryWidgets({super.key, this.searchQuery = ''});

  String setTime(DateTime? startedAt, DateTime createdAt, DateTime? finishedAt) {
    return startedAt == null ? dateTimeFormat('h:mm a', createdAt) : dateTimeFormat('h:mm a', startedAt);
  }

  String setTimeSDCard(DateTime? startedAt, DateTime createdAt) {
    return startedAt == null ? dateTimeFormat('h:mm a', createdAt) : dateTimeFormat('h:mm a', startedAt);
  }

  String _getDuration(ServerConversation conversation) {
    if (conversation.transcriptSegments.isEmpty) return '';

    int durationSeconds = conversation.getDurationInSeconds();
    if (durationSeconds <= 0) return '';

    return secondsToHumanReadable(durationSeconds);
  }

  String _getDateFormat(DateTime date) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final yesterday = today.subtract(const Duration(days: 1));
    final dateOnly = DateTime(date.year, date.month, date.day);

    if (dateOnly == today) {
      return 'Today';
    } else if (dateOnly == yesterday) {
      return 'Yesterday';
    } else if (date.year == now.year) {
      return dateTimeFormat('MMM d', date);
    } else {
      return dateTimeFormat('MMM d, yyyy', date);
    }
  }

  Widget _buildInfoChips(ServerConversation conversation) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        // Date chip
        _buildChip(
          label: _getDateFormat(conversation.createdAt),
          icon: Icons.calendar_today,
        ),
        // Time chip
        _buildChip(
          label: conversation.source == ConversationSource.sdcard
              ? setTimeSDCard(conversation.startedAt, conversation.createdAt)
              : setTime(conversation.startedAt, conversation.createdAt, conversation.finishedAt),
          icon: Icons.access_time,
        ),
        // Duration chip (only if segments exist)
        if (conversation.transcriptSegments.isNotEmpty && _getDuration(conversation).isNotEmpty)
          _buildChip(
            label: _getDuration(conversation),
            icon: Icons.timelapse,
          ),
      ],
    );
  }

  Widget _buildChip({required String label, required IconData icon}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.grey.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: 14,
            color: Colors.grey.shade300,
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              color: Colors.grey.shade300,
              fontSize: 13,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
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
            const SizedBox(height: 8),
            conversation.discarded
                ? Text(
                    'Discarded Conversation',
                    style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 32),
                  )
                : GetEditTextField(
                    conversationId: conversation.id,
                    focusNode: data.item3,
                    controller: data.item2,
                    content: conversation.structured.title.decodeString,
                    style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 32, color: Colors.white),
                  ),
            const SizedBox(height: 16),
            _buildInfoChips(conversation),
            const SizedBox(height: 16),
            conversation.discarded ? const SizedBox.shrink() : const SizedBox(height: 8),
          ],
        );
      },
    );
  }
}

class ActionItemsListWidget extends StatelessWidget {
  const ActionItemsListWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(builder: (context, provider, child) {
      return Column(
        children: [
          provider.conversation.structured.actionItems.isNotEmpty
              ? Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Action Items',
                      style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
                    ),
                    IconButton(
                      onPressed: () {
                        Clipboard.setData(ClipboardData(
                          text:
                              '- ${provider.conversation.structured.actionItems.map((e) => e.description.decodeString).join('\n- ')}',
                        ));
                        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                          content: Text('Action items copied to clipboard'),
                          duration: Duration(seconds: 2),
                        ));
                        MixpanelManager().copiedConversationDetails(provider.conversation, source: 'Action Items');
                      },
                      icon: const Icon(Icons.copy_rounded, color: Colors.white, size: 20),
                    )
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
                  MixpanelManager().deletedActionItem(provider.conversation);
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
                  //     MixpanelManager().deletedActionItem(provider.conversation);
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
                                  MixpanelManager().checkedActionItem(provider.conversation, idx);
                                } else {
                                  MixpanelManager().uncheckedActionItem(provider.conversation, idx);
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
    });
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
    return Consumer<ConversationDetailProvider>(builder: (context, provider, child) {
      if (provider.loadingReprocessConversation && provider.reprocessConversationId == provider.conversation.id) {
        return Center(
          child: Padding(
            padding: const EdgeInsets.only(top: 18.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                const CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                ),
                const SizedBox(width: 16),
                Text(
                  '${provider.conversation.discarded ? 'Summarizing' : 'Re-summarizing'} conversation...\nThis may take a few seconds',
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
            'Nothing interesting found,\nwant to retry?',
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
                    gradient: LinearGradient(colors: [
                      Color.fromARGB(127, 208, 208, 208),
                      Color.fromARGB(127, 188, 99, 121),
                      Color.fromARGB(127, 86, 101, 182),
                      Color.fromARGB(127, 126, 190, 236)
                    ]),
                    width: 2,
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: MaterialButton(
                  onPressed: () async {
                    await provider.reprocessConversation();
                  },
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  child: const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 16, vertical: 0),
                      child: Text('Summarize', style: TextStyle(color: Colors.white, fontSize: 16))),
                ),
              ),
            ],
          ),
          const SizedBox(height: 32),
        ],
      );
    });
  }
}

class AppResultDetailWidget extends StatelessWidget {
  final AppResponse appResponse;
  final App? app;
  final ServerConversation conversation;
  final String searchQuery;
  final int currentResultIndex;

  const AppResultDetailWidget({
    super.key,
    required this.appResponse,
    required this.app,
    required this.conversation,
    this.searchQuery = '',
    this.currentResultIndex = -1,
  });

  @override
  Widget build(BuildContext context) {
    final String content = appResponse.content.trim().decodeString;

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
                            text: const TextSpan(
                                style: TextStyle(color: Colors.grey),
                                text: "No summary available for this app. Try another app for better results."),
                          ),
                        ),
                      ),
                    ],
                  )
                : ConversationMarkdownWidget(
                    content: content,
                    searchQuery: searchQuery,
                    currentResultIndex: currentResultIndex,
                  ),
          ),

          // App info in a more subtle format below the content - only show if content is not empty
          if (content.isNotEmpty)
            GestureDetector(
              onTap: () async {
                if (app != null) {
                  MixpanelManager().pageOpened('App Detail');
                  await routeToPage(context, AppDetailPage(app: app!));
                }
              },
              child: Padding(
                padding: const EdgeInsets.only(top: 12, left: 4),
                child: Row(
                  children: [
                    // App icon
                    app != null
                        ? CachedNetworkImage(
                            imageUrl: app!.getImageUrl(),
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
                              children: [
                                Image.asset(
                                  Assets.images.herologo.path,
                                  height: 16,
                                  width: 16,
                                ),
                              ],
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
                                  app != null ? app!.name.decodeString : 'Unknown App',
                                  maxLines: 1,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w500,
                                    color: Colors.white,
                                    fontSize: 14,
                                  ),
                                ),
                                if (app != null)
                                  Text(
                                    app!.description.decodeString,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(color: Colors.grey, fontSize: 12),
                                  ),
                              ],
                            ),
                          ),
                          const SizedBox(
                            child: Icon(Icons.arrow_forward_ios, color: Colors.white, size: 20),
                            width: 42,
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
}

class GetAppsWidgets extends StatelessWidget {
  final String searchQuery;
  final int currentResultIndex;
  const GetAppsWidgets({super.key, this.searchQuery = '', this.currentResultIndex = -1});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        final summarizedApp = provider.getSummarizedApp();
        return Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.start,
          crossAxisAlignment: summarizedApp == null ? CrossAxisAlignment.center : CrossAxisAlignment.start,
          children: summarizedApp == null
              ? [child!]
              : [
                  // Show the summarized app
                  if (!provider.conversation.discarded) ...[
                    AppResultDetailWidget(
                      appResponse: summarizedApp,
                      app: provider.findAppById(summarizedApp.appId),
                      conversation: provider.conversation,
                      searchQuery: searchQuery,
                      currentResultIndex: currentResultIndex,
                    ),
                  ],
                  const SizedBox(height: 8)
                ],
        );
      },
      child: ListView(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        children: [
          const SizedBox(height: 32),
          Text(
            'No summary available\nfor this conversation.',
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
                    gradient: LinearGradient(colors: [
                      Color.fromARGB(127, 208, 208, 208),
                      Color.fromARGB(127, 188, 99, 121),
                      Color.fromARGB(127, 86, 101, 182),
                      Color.fromARGB(127, 126, 190, 236)
                    ]),
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
                  child: const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 16, vertical: 0),
                      child: Text('Generate Summary', style: TextStyle(color: Colors.white, fontSize: 16))),
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

  @override
  Widget build(BuildContext context) {
    return Selector<ConversationDetailProvider, Geolocation?>(selector: (context, provider) {
      if (provider.conversation.discarded) return null;
      return provider.conversation.geolocation;
    }, builder: (context, geolocation, child) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: geolocation == null
            ? []
            : [
                Text(
                  'Taken at',
                  style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 20),
                ),
                const SizedBox(height: 8),
                Text(
                  '${geolocation.address?.decodeString}',
                  style: TextStyle(color: Colors.grey.shade300),
                ),
                const SizedBox(height: 8),
                GestureDetector(
                  onTap: () async {
                    MapsUtil.launchMap(geolocation.latitude!, geolocation.longitude!);
                  },
                  child: CachedNetworkImage(
                    imageBuilder: (context, imageProvider) {
                      return Container(
                        margin: const EdgeInsets.only(top: 10, bottom: 8),
                        height: 200,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(16),
                          image: DecorationImage(
                            image: imageProvider,
                            fit: BoxFit.cover,
                          ),
                        ),
                      );
                    },
                    errorWidget: (context, url, error) {
                      return Container(
                        margin: const EdgeInsets.only(top: 10, bottom: 8),
                        height: 200,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(16),
                          color: Color(0xFF35343B),
                        ),
                        child: const Center(
                          child: Text(
                            'Could not load Maps. Please check your internet connection.',
                            textAlign: TextAlign.center,
                          ),
                        ),
                      );
                    },
                    imageUrl: MapsUtil.getMapImageUrl(
                      geolocation.latitude!,
                      geolocation.longitude!,
                    ),
                  ),
                ),
                const SizedBox(height: 8),
              ],
      );
    });
  }
}

///************************************************
///************ SETTINGS BOTTOM SHEET *************
///************************************************

class GetSheetTitle extends StatelessWidget {
  const GetSheetTitle({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(builder: (context, provider, child) {
      return Column(
        children: [
          ListTile(
            title: Text(
              provider.conversation.discarded ? 'Discarded Conversation' : provider.conversation.structured.title,
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
    });
  }
}

class GetDevToolsOptions extends StatefulWidget {
  final ServerConversation conversation;

  const GetDevToolsOptions({
    super.key,
    required this.conversation,
  });

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
    return Column(children: [
      Card(
        shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
        child: ListTile(
          title: const Text('Trigger Conversation Created Integration'),
          leading: loadingAppIntegrationTest
              ? const SizedBox(
                  height: 24,
                  width: 24,
                  child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
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
                  'Webhook URL not set',
                  'Please set the webhook URL in developer settings to use this feature.',
                  okButtonText: 'Settings',
                ),
              );
              changeLoadingAppIntegrationTest(false);
              return;
            } else {
              webhookOnConversationCreatedCall(widget.conversation, returnRawBody: true).then((response) {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () => Navigator.pop(context),
                    () => Navigator.pop(context),
                    'Result:',
                    response,
                    okButtonText: 'Ok',
                    singleButton: true,
                  ),
                );
                changeLoadingAppIntegrationTest(false);
              });
            }
          },
        ),
      ),
      Card(
        shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
        child: ListTile(
          title: const Text('Test a Conversation Prompt'),
          leading: const Icon(Icons.chat),
          trailing: const Icon(Icons.arrow_forward_ios, size: 20),
          onTap: () {
            routeToPage(context, TestPromptsPage(conversation: widget.conversation));
          },
        ),
      ),
      // widget.memory.postprocessing?.status == MemoryPostProcessingStatus.completed
      // widget.memory.postprocessing?.status != MemoryPostProcessingStatus.not_started
      //     ? Card(
      //         shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
      //         child: ListTile(
      //           title: const Text('Compare Transcripts Models'),
      //           leading: const Icon(Icons.chat),
      //           trailing: const Icon(Icons.arrow_forward_ios, size: 20),
      //           onTap: () {
      //             routeToPage(context, CompareTranscriptsPage(memory: widget.memory));
      //           },
      //         ),
      //       )
      //     : const SizedBox.shrink(),
    ]);
  }
}

_copyContent(BuildContext context, String content) {
  Clipboard.setData(ClipboardData(text: content));
  ScaffoldMessenger.of(context).showSnackBar(
    const SnackBar(content: Text('Transcript copied to clipboard')),
  );
  HapticFeedback.lightImpact();
  Navigator.pop(context);
}

_getLoadingIndicator() {
  return const SizedBox(
      width: 24,
      height: 24,
      child: CircularProgressIndicator(
        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
      ));
}

class GetShareOptions extends StatefulWidget {
  final ServerConversation conversation;

  const GetShareOptions({
    super.key,
    required this.conversation,
  });

  @override
  State<GetShareOptions> createState() => _GetShareOptionsState();
}

class _GetShareOptionsState extends State<GetShareOptions> {
  bool loadingShareConversationViaURL = false;
  bool loadingShareTranscript = false;
  bool loadingShareSummary = false;

  final GlobalKey _shareUrlKey = GlobalKey();
  final GlobalKey _shareTranscriptKey = GlobalKey();
  final GlobalKey _shareSummaryKey = GlobalKey();

  void changeLoadingShareConversationViaURL(bool value) {
    setState(() {
      loadingShareConversationViaURL = value;
    });
  }

  void changeLoadingShareTranscript(bool value) {
    setState(() {
      loadingShareTranscript = value;
    });
  }

  void changeLoadingShareSummary(bool value) {
    setState(() {
      loadingShareSummary = value;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Card(
          shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
          child: ListTile(
            key: _shareUrlKey,
            title: const Text('Send web url'),
            leading: loadingShareConversationViaURL ? _getLoadingIndicator() : const Icon(Icons.link),
            onTap: () async {
              if (loadingShareConversationViaURL) return;
              changeLoadingShareConversationViaURL(true);
              bool shared = await setConversationVisibility(widget.conversation.id);
              if (!shared) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Conversation URL could not be shared.')),
                );
                return;
              }
              String content =
                  '''https://h.omi.me/conversations/${widget.conversation.id}'''.replaceAll('  ', '').trim();
              print(content);
              final RenderBox? box = _shareUrlKey.currentContext?.findRenderObject() as RenderBox?;
              if (box != null) {
                final Offset position = box.localToGlobal(Offset.zero);
                final Size size = box.size;
                await Share.share(
                  content,
                  sharePositionOrigin: Rect.fromLTWH(position.dx, position.dy, size.width, size.height),
                );
              } else {
                await Share.share(content);
              }
              changeLoadingShareConversationViaURL(false);
            },
          ),
        ),
        const SizedBox(height: 4),
        Card(
          shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
          child: Column(
            children: [
              ListTile(
                key: _shareTranscriptKey,
                title: const Text('Send Transcript'),
                leading: loadingShareTranscript ? _getLoadingIndicator() : const Icon(Icons.description),
                onTap: () async {
                  if (loadingShareTranscript) return;
                  changeLoadingShareTranscript(true);
                  String content = '''
              ${widget.conversation.structured.title}

              ${widget.conversation.getTranscript(generate: true)}
              '''
                      .replaceAll('  ', '')
                      .trim();
                  // TODO: Deeplink that let people download the app.
                  final RenderBox? box = _shareTranscriptKey.currentContext?.findRenderObject() as RenderBox?;
                  if (box != null) {
                    final Offset position = box.localToGlobal(Offset.zero);
                    final Size size = box.size;
                    await Share.share(
                      content,
                      sharePositionOrigin: Rect.fromLTWH(position.dx, position.dy, size.width, size.height),
                    );
                  } else {
                    await Share.share(content);
                  }
                  changeLoadingShareTranscript(false);
                },
              ),
              widget.conversation.discarded
                  ? const SizedBox()
                  : ListTile(
                      key: _shareSummaryKey,
                      title: const Text('Send Summary'),
                      leading: loadingShareSummary ? _getLoadingIndicator() : const Icon(Icons.summarize),
                      onTap: () async {
                        if (loadingShareSummary) return;
                        changeLoadingShareSummary(true);
                        String content = widget.conversation.structured.toString().replaceAll('  ', '').trim();
                        final RenderBox? box = _shareSummaryKey.currentContext?.findRenderObject() as RenderBox?;
                        if (box != null) {
                          final Offset position = box.localToGlobal(Offset.zero);
                          final Size size = box.size;
                          await Share.share(
                            content,
                            sharePositionOrigin: Rect.fromLTWH(position.dx, position.dy, size.width, size.height),
                          );
                        } else {
                          await Share.share(content);
                        }
                        changeLoadingShareSummary(false);
                      },
                    )
            ],
          ),
        ),
        const SizedBox(height: 4),
        Card(
          shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
          child: Column(
            children: [
              ListTile(
                title: const Text('Copy Transcript'),
                leading: const Icon(Icons.copy),
                onTap: () => _copyContent(context, widget.conversation.getTranscript(generate: true)),
              ),
              widget.conversation.discarded
                  ? const SizedBox()
                  : ListTile(
                      title: const Text('Copy Summary'),
                      leading: const Icon(Icons.file_copy),
                      onTap: () => _copyContent(
                        context,
                        widget.conversation.structured.toString(),
                      ),
                    )
            ],
          ),
        ),
      ],
    );
  }
}
