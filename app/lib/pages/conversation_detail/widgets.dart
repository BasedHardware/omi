import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/webhooks.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/test_prompts.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/expandable_text.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:tuple/tuple.dart';

import 'maps_util.dart';

class GetSummaryWidgets extends StatelessWidget {
  const GetSummaryWidgets({super.key});

  String setTime(DateTime? startedAt, DateTime createdAt, DateTime? finishedAt) {
    return startedAt == null
        ? dateTimeFormat('h:mm a', createdAt)
        : '${dateTimeFormat('h:mm a', startedAt)} to ${dateTimeFormat('h:mm a', finishedAt)}';
  }

  String setTimeSDCard(DateTime? startedAt, DateTime createdAt) {
    return startedAt == null ? dateTimeFormat('h:mm a', createdAt) : dateTimeFormat('h:mm a', startedAt);
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
            const SizedBox(height: 24),
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
            Text(
              conversation.source == ConversationSource.sdcard
                  ? 'Imported at ${dateTimeFormat('MMM d,  yyyy', conversation.createdAt)}, ${setTimeSDCard(conversation.startedAt, conversation.createdAt)}'
                  : '${dateTimeFormat('MMM d,  yyyy', conversation.createdAt)} ${conversation.startedAt == null ? 'at' : 'from'} ${setTime(conversation.startedAt, conversation.createdAt, conversation.finishedAt)}',
              style: const TextStyle(color: Colors.grey, fontSize: 16),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                GestureDetector(
                  onTap: conversation.onTagPressed(context),
                  child: Container(
                    decoration:
                        BoxDecoration(color: conversation.getTagColor(), borderRadius: BorderRadius.circular(16)),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    child: Text(
                      conversation.getTag(),
                      style: Theme.of(context).textTheme.titleLarge!.copyWith(color: conversation.getTagTextColor()),
                      maxLines: 1,
                    ),
                  ),
                )
              ],
            ),
            const SizedBox(height: 40),
            conversation.discarded
                ? const SizedBox.shrink()
                : Text('Overview', style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26)),
            conversation.discarded
                ? const SizedBox.shrink()
                : ((conversation.geolocation != null) ? const SizedBox(height: 8) : const SizedBox.shrink()),
            conversation.discarded ? const SizedBox.shrink() : const SizedBox(height: 8),
            conversation.discarded
                ? const SizedBox.shrink()
                : SelectionArea(
                    child: Text(
                      conversation.structured.overview.decodeString,
                      style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
                    ),
                  ),
            conversation.discarded ? const SizedBox.shrink() : const SizedBox(height: 40),
            const ActionItemsListWidget(),
            conversation.structured.actionItems.isNotEmpty ? const SizedBox(height: 40) : const SizedBox.shrink(),
            const EventsListWidget(),
            conversation.structured.events.isNotEmpty ? const SizedBox(height: 40) : const SizedBox.shrink(),
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
                  ScaffoldMessenger.of(context)
                      .showSnackBar(
                        SnackBar(
                          content: const Text('Action Item deleted successfully 🗑️'),
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                          action: SnackBarAction(
                            label: 'Undo',
                            textColor: Colors.white,
                            onPressed: () {
                              provider.undoDeleteActionItem(idx);
                            },
                          ),
                        ),
                      )
                      .closed
                      .then((reason) {
                    if (reason != SnackBarClosedReason.action) {
                      provider.deleteActionItemPermanently(tempItem, tempIdx);
                      MixpanelManager().deletedActionItem(provider.conversation);
                    }
                  });
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

class EventsListWidget extends StatelessWidget {
  const EventsListWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            provider.conversation.structured.events.isNotEmpty &&
                    !(provider.conversation.structured.events
                        .where((e) =>
                            e.startsAt.isBefore(provider.conversation.startedAt!.add(const Duration(hours: 6))) &&
                            e.startsAt.add(Duration(minutes: e.duration)).isBefore(provider.conversation.startedAt!))
                        .isNotEmpty)
                ? Row(
                    children: [
                      Icon(Icons.event, color: Colors.grey.shade300),
                      const SizedBox(width: 8),
                      Text(
                        'Events',
                        style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
                      )
                    ],
                  )
                : const SizedBox.shrink(),
            ListView.builder(
              itemCount: provider.conversation.structured.events.length,
              shrinkWrap: true,
              itemBuilder: (context, idx) {
                var event = provider.conversation.structured.events[idx];
                if (event.startsAt.isBefore(provider.conversation.startedAt!.add(const Duration(hours: 6))) &&
                    event.startsAt.add(Duration(minutes: event.duration)).isBefore(provider.conversation.startedAt!)) {
                  return const SizedBox.shrink();
                }
                return ListTile(
                  onTap: () {
                    AppSnackbar.showSnackbar(
                      'This integration is being deprecated. Please use the new Google Calendar app.',
                    );
                  },
                  contentPadding: EdgeInsets.zero,
                  title: Text(
                    event.title.decodeString,
                    style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                  ),
                  subtitle: Padding(
                    padding: const EdgeInsets.only(top: 4.0),
                    child: Text(
                      '${dateTimeFormat('MMM d, yyyy', event.startsAt)} at ${dateTimeFormat('h:mm a', event.startsAt)} ~ ${minutesConversion(event.duration)}',
                      style: const TextStyle(color: Colors.grey, fontSize: 15),
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

String minutesConversion(int minutes) {
  if (minutes < 60) {
    return '$minutes minutes';
  } else if (minutes < 1440) {
    var hrs = minutes / 60;
    if (hrs % 1 == 0) {
      return '${hrs.toInt()} hours';
    }
    return '${minutes / 60} hour${hrs > 1 ? 's' : ''}';
  } else {
    var days = minutes / 1440;
    if (days % 1 == 0) {
      return '${days.toInt()} days';
    }
    return '${minutes / 1440} day${days > 1 ? 's' : ''}';
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

class GetAppsWidgets extends StatelessWidget {
  const GetAppsWidgets({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.start,
          crossAxisAlignment:
              provider.conversation.appResults.isEmpty ? CrossAxisAlignment.center : CrossAxisAlignment.start,
          children: provider.conversation.appResults.isEmpty
              ? [child!]
              : [
                  // TODO: include a way to trigger specific apps
                  if (provider.conversation.appResults.isNotEmpty &&
                      !provider.conversation.discarded &&
                      provider.appResponseExpanded.isNotEmpty) ...[
                    provider.conversation.structured.actionItems.isEmpty
                        ? const SizedBox(height: 40)
                        : const SizedBox.shrink(),
                    Text(
                      'Apps 🧑‍💻',
                      style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
                      textAlign: TextAlign.start,
                    ),
                    const SizedBox(height: 24),
                    if (provider.conversation.appResults.isNotEmpty)
                      ...provider.conversation.appResults.mapIndexed(
                        (i, appResponse) {
                          if (appResponse.content.length < 5) return const SizedBox.shrink();
                          App? app = provider.appsList.firstWhereOrNull((element) => element.id == appResponse.appId);
                          return Container(
                            margin: const EdgeInsets.only(bottom: 40),
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.start,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                app != null
                                    ? ListTile(
                                        contentPadding: EdgeInsets.zero,
                                        leading: CachedNetworkImage(
                                          imageUrl: app.getImageUrl(),
                                          imageBuilder: (context, imageProvider) {
                                            return CircleAvatar(
                                              backgroundColor: Colors.white,
                                              radius: 16,
                                              backgroundImage: imageProvider,
                                            );
                                          },
                                          errorWidget: (context, url, error) {
                                            return const CircleAvatar(
                                              backgroundColor: Colors.white,
                                              radius: 16,
                                              child: Icon(Icons.error_outline_rounded),
                                            );
                                          },
                                          progressIndicatorBuilder: (context, url, progress) => CircleAvatar(
                                            backgroundColor: Colors.white,
                                            radius: 16,
                                            child: CircularProgressIndicator(
                                              value: progress.progress,
                                              valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
                                            ),
                                          ),
                                        ),
                                        title: Text(
                                          app.name.decodeString,
                                          maxLines: 1,
                                          style: const TextStyle(
                                            fontWeight: FontWeight.w500,
                                            color: Colors.white,
                                            fontSize: 16,
                                          ),
                                        ),
                                        subtitle: Padding(
                                          padding: const EdgeInsets.only(top: 4.0),
                                          child: Text(
                                            app.description.decodeString,
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            style: const TextStyle(color: Colors.grey, fontSize: 14),
                                          ),
                                        ),
                                        trailing: IconButton(
                                          icon: const Icon(Icons.copy_rounded, color: Colors.white, size: 20),
                                          onPressed: () {
                                            Clipboard.setData(ClipboardData(text: appResponse.content.trim()));
                                            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                                              content: Text('App response copied to clipboard'),
                                            ));
                                            MixpanelManager().copiedConversationDetails(provider.conversation,
                                                source: 'App Response');
                                          },
                                        ),
                                      )
                                    : ListTile(
                                        contentPadding: EdgeInsets.zero,
                                        leading: Container(
                                          decoration: BoxDecoration(
                                            image: DecorationImage(
                                              image: AssetImage(Assets.images.background.path),
                                              fit: BoxFit.cover,
                                            ),
                                            borderRadius: const BorderRadius.all(Radius.circular(16.0)),
                                          ),
                                          height: 30,
                                          width: 30,
                                          child: Stack(
                                            alignment: Alignment.center,
                                            children: [
                                              Image.asset(
                                                Assets.images.herologo.path,
                                                height: 24,
                                                width: 24,
                                              ),
                                            ],
                                          ),
                                        ),
                                        title: const Text(
                                          'Unknown App',
                                          maxLines: 1,
                                          style: TextStyle(
                                            fontWeight: FontWeight.w500,
                                            color: Colors.white,
                                            fontSize: 16,
                                          ),
                                        ),
                                        subtitle: const Padding(
                                          padding: EdgeInsets.only(top: 4.0),
                                          child: Text(
                                            'This app is private/deleted, or is not available at the moment',
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            style: TextStyle(color: Colors.grey, fontSize: 14),
                                          ),
                                        ),
                                        trailing: IconButton(
                                          icon: const Icon(Icons.copy_rounded, color: Colors.white, size: 20),
                                          onPressed: () {
                                            Clipboard.setData(ClipboardData(text: appResponse.content.trim()));
                                            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                                              content: Text('App response copied to clipboard'),
                                            ));
                                            MixpanelManager().copiedConversationDetails(provider.conversation,
                                                source: 'App Response');
                                          },
                                        ),
                                      ),
                                ExpandableTextWidget(
                                  text: appResponse.content.decodeString.trim(),
                                  isExpanded: provider.appResponseExpanded[i],
                                  toggleExpand: () {
                                    debugPrint('appResponseExpanded: ${provider.appResponseExpanded}');
                                    if (!provider.appResponseExpanded[i]) {
                                      MixpanelManager()
                                          .appResultExpanded(provider.conversation, appResponse.appId ?? '');
                                    }
                                    provider.updateAppResponseExpanded(i);
                                  },
                                  style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
                                  maxLines: 6,
                                  // Change this to 6 if you want the initial max lines to be 6
                                  linkColor: Colors.white,
                                ),
                              ],
                            ),
                          );
                        },
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
            'No apps were triggered\nfor this conversation.',
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
                    routeToPage(context, const AppsPage(showAppBar: true));
                    MixpanelManager().pageOpened('Memory Detail Apps');
                  },
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  child: const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 16, vertical: 0),
                      child: Text('Enable Apps', style: TextStyle(color: Colors.white, fontSize: 16))),
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
                  '${geolocation.address}',
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
                          color: Colors.grey.shade800,
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
              String content = '''https://h.omi.me/memories/${widget.conversation.id}'''.replaceAll('  ', '').trim();
              print(content);
              await Share.share(content);
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
                  await Share.share(content);
                  changeLoadingShareTranscript(false);
                },
              ),
              widget.conversation.discarded
                  ? const SizedBox()
                  : ListTile(
                      title: const Text('Send Summary'),
                      leading: loadingShareSummary ? _getLoadingIndicator() : const Icon(Icons.summarize),
                      onTap: () async {
                        if (loadingShareSummary) return;
                        changeLoadingShareSummary(true);
                        String content = widget.conversation.structured.toString().replaceAll('  ', '').trim();
                        await Share.share(content);
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

class GetSheetMainOptions extends StatelessWidget {
  const GetSheetMainOptions({
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(builder: (context, provider, child) {
      return Column(
        children: [
          Card(
            shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
            child: Column(
              children: [
                ListTile(
                  title: const Text('Share'),
                  leading: const Icon(Icons.share),
                  trailing: const Icon(Icons.arrow_forward_ios, size: 20),
                  onTap: () {
                    provider.toggleShareOptionsInSheet(!provider.displayShareOptionsInSheet);
                  },
                )
              ],
            ),
          ),
          const SizedBox(height: 4),
          const SizedBox(height: 4),
          Card(
            shape: const RoundedRectangleBorder(
              borderRadius: BorderRadius.all(Radius.circular(8)),
            ),
            child: Column(
              children: [
                ListTile(
                  title: Text(provider.conversation.discarded ? 'Summarize' : 'Re-summarize'),
                  leading: provider.loadingReprocessConversation
                      ? const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                        )
                      : const Icon(Icons.refresh),
                  onTap: provider.loadingReprocessConversation
                      ? null
                      : () async {
                          final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                          if (connectivityProvider.isConnected) {
                            await provider.reprocessConversation();
                            if (context.mounted) {
                              Navigator.pop(context);
                            }
                          } else {
                            showDialog(
                              builder: (c) => getDialog(
                                context,
                                () => Navigator.pop(context),
                                () => Navigator.pop(context),
                                'Unable to Re-summarize Conversation',
                                'Please check your internet connection and try again.',
                                singleButton: true,
                                okButtonText: 'OK',
                              ),
                              context: context,
                            );
                          }
                        },
                ),
                ListTile(
                  title: const Text('Delete'),
                  leading: const Icon(
                    Icons.delete,
                  ),
                  onTap: provider.loadingReprocessConversation
                      ? null
                      : () {
                          final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                          if (connectivityProvider.isConnected) {
                            showDialog(
                              context: context,
                              builder: (c) => getDialog(
                                context,
                                () => Navigator.pop(context),
                                () {
                                  context
                                      .read<ConversationProvider>()
                                      .deleteConversation(provider.conversation, provider.conversationIdx);
                                  Navigator.pop(context, true);
                                  Navigator.pop(context, true);
                                  Navigator.pop(context, {'deleted': true});
                                },
                                'Delete Conversation?',
                                'Are you sure you want to delete this conversation? This action cannot be undone.',
                                okButtonText: 'Confirm',
                              ),
                            );
                          } else {
                            showDialog(
                              builder: (c) => getDialog(
                                  context,
                                  () => Navigator.pop(context),
                                  () => Navigator.pop(context),
                                  'Unable to Delete Conversation',
                                  'Please check your internet connection and try again.',
                                  singleButton: true,
                                  okButtonText: 'OK'),
                              context: context,
                            );
                          }
                        },
                ),
              ],
            ),
          ),
          const SizedBox(height: 4),
          Card(
            shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
            child: Column(
              children: [
                ListTile(
                  onTap: () {
                    provider.toggleDevToolsInSheet(!provider.displayDevToolsInSheet);
                  },
                  title: const Text('Developer Tools'),
                  leading: const Icon(
                    Icons.developer_mode,
                    color: Colors.white,
                  ),
                  trailing: const Icon(Icons.arrow_forward_ios, size: 20),
                )
              ],
            ),
          )
        ],
      );
    });
  }
}

class ShowOptionsBottomSheet extends StatelessWidget {
  const ShowOptionsBottomSheet({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: const BorderRadius.only(topLeft: Radius.circular(16), topRight: Radius.circular(16)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      child: Consumer<ConversationDetailProvider>(builder: (context, provider, child) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const GetSheetTitle(),
            (provider.displayDevToolsInSheet
                ? GetDevToolsOptions(
                    conversation: provider.conversation,
                  )
                : provider.displayShareOptionsInSheet
                    ? GetShareOptions(
                        conversation: provider.conversation,
                      )
                    : const GetSheetMainOptions()),
            const SizedBox(height: 40),
          ],
        );
      }),
    );
  }
}
