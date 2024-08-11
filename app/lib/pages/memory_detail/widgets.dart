import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/http/webhooks.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/pages/memories/widgets/confirm_deletion_widget.dart';
import 'package:friend_private/pages/memory_detail/test_prompts.dart';
import 'package:friend_private/pages/plugins/page.dart';
import 'package:friend_private/pages/settings/calendar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/features/calendar.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/expandable_text.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

import 'maps_util.dart';

List<Widget> getSummaryWidgets(
  BuildContext context,
  ServerMemory memory,
  TextEditingController overviewController,
  bool editingOverview,
  FocusNode focusOverviewField,
  StateSetter setState,
) {
  var structured = memory.structured;
  String time = memory.startedAt == null
      ? dateTimeFormat('h:mm a', memory.createdAt)
      : '${dateTimeFormat('h:mm a', memory.startedAt)} to ${dateTimeFormat('h:mm a', memory.finishedAt)}';
  return [
    const SizedBox(height: 24),
    Text(
      memory.discarded ? 'Discarded Memory' : structured.title,
      style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 32),
    ),
    const SizedBox(height: 16),
    Text(
      '${dateTimeFormat('MMM d,  yyyy', memory.createdAt)} ${memory.startedAt == null ? 'at' : 'from'} $time',
      style: const TextStyle(color: Colors.grey, fontSize: 16),
    ),
    const SizedBox(height: 16),
    Row(
      children: [
        GestureDetector(
          onTap: memory.onTagPressed(context),
          child: Container(
            decoration: BoxDecoration(color: memory.getTagColor(), borderRadius: BorderRadius.circular(16)),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Text(
              memory.getTag(),
              style: Theme.of(context).textTheme.titleLarge!.copyWith(color: memory.getTagTextColor()),
              maxLines: 1,
            ),
          ),
        )
      ],
    ),
    const SizedBox(height: 40),
    memory.discarded
        ? const SizedBox.shrink()
        : Text('Overview', style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26)),
    memory.discarded
        ? const SizedBox.shrink()
        : ((memory.geolocation != null) ? const SizedBox(height: 8) : const SizedBox.shrink()),
    memory.discarded ? const SizedBox.shrink() : const SizedBox(height: 8),
    memory.discarded
        ? const SizedBox.shrink()
        : _getEditTextField(memory, overviewController, editingOverview, focusOverviewField),
    memory.discarded ? const SizedBox.shrink() : const SizedBox(height: 40),
    structured.actionItems.isNotEmpty
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
                    Clipboard.setData(
                        ClipboardData(text: '- ${structured.actionItems.map((e) => e.description).join('\n- ')}'));
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('Action items copied to clipboard'),
                      duration: Duration(seconds: 2),
                    ));
                    // MixpanelManager().copiedMemoryDetails(memory, source: 'Action Items');
                  },
                  icon: const Icon(Icons.copy_rounded, color: Colors.white, size: 20))
            ],
          )
        : const SizedBox.shrink(),
    ...structured.actionItems.map<Widget>((item) {
      return Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
                padding: const EdgeInsets.only(top: 4.0),
                child: Icon(Icons.task_alt, color: Colors.grey.shade300, size: 20)),
            const SizedBox(width: 12),
            Expanded(
              child: SelectionArea(
                child: Text(
                  item.description,
                  style: TextStyle(color: Colors.grey.shade300, fontSize: 16, height: 1.3),
                ),
              ),
            ),
          ],
        ),
      );
    }),
    structured.actionItems.isNotEmpty ? const SizedBox(height: 40) : const SizedBox.shrink(),
    structured.events.isNotEmpty
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
    ...structured.events.map<Widget>((event) {
      return ListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(
          event.title,
          style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 4.0),
          child: Text(
            '${dateTimeFormat('MMM d, yyyy', event.startsAt)} at ${dateTimeFormat('h:mm a', event.startsAt)} ~ ${event.duration} minutes.',
            style: const TextStyle(color: Colors.grey, fontSize: 15),
          ),
        ),
        trailing: IconButton(
          onPressed: event.created
              ? null
              : () {
                  var calEnabled = SharedPreferencesUtil().calendarEnabled;
                  var calSelected = SharedPreferencesUtil().calendarId.isNotEmpty;
                  if (!calEnabled || !calSelected) {
                    routeToPage(context, const CalendarPage());
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(!calEnabled
                          ? 'Enable calendar integration to add events'
                          : 'Select a calendar to add events to'),
                    ));
                    return;
                  }
                  // TODO: calendar events in memory detail.
                  // MemoryProvider().setEventCreated(event);
                  setState(() => event.created = true);
                  CalendarUtil().createEvent(
                    event.title,
                    event.startsAt,
                    event.duration,
                    description: event.description,
                  );
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                    content: Text('Event added to calendar'),
                  ));
                },
          icon: Icon(event.created ? Icons.check : Icons.add, color: Colors.white),
        ),
      );
    }),
    structured.events.isNotEmpty ? const SizedBox(height: 40) : const SizedBox.shrink(),
  ];
}

_getEditTextField(ServerMemory memory, TextEditingController controller, bool enabled, FocusNode focusNode) {
  if (memory.discarded) return const SizedBox.shrink();
  return enabled
      ? TextField(
          controller: controller,
          keyboardType: TextInputType.multiline,
          focusNode: focusNode,
          maxLines: null,
          decoration: const InputDecoration(
            border: OutlineInputBorder(borderSide: BorderSide.none),
            contentPadding: EdgeInsets.all(0),
          ),
          enabled: enabled,
          style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
        )
      : SelectionArea(
          child: Text(
            controller.text,
            style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
          ),
        );
}

List<Widget> getPluginsWidgets(
  BuildContext context,
  ServerMemory memory,
  List<Plugin> pluginsList,
  List<bool> pluginResponseExpanded,
  Function(int) onItemToggled,
) {
  if (memory.pluginsResults.isEmpty) {
    return [
      const SizedBox(height: 32),
      Text(
        'No plugins were triggered\nfor this memory.',
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
                Navigator.of(context).push(MaterialPageRoute(builder: (c) => const PluginsPage()));
              },
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 16, vertical: 0),
                  child: Text('Enable Plugins', style: TextStyle(color: Colors.white, fontSize: 16))),
            ),
          ),
        ],
      ),
      const SizedBox(height: 32),
    ];
  }
  return [
    // TODO: include a way to trigger specific plugins
    if (memory.pluginsResults.isNotEmpty && !memory.discarded) ...[
      memory.structured.actionItems.isEmpty ? const SizedBox(height: 40) : const SizedBox.shrink(),
      Text(
        'Plugins 🧑‍💻',
        style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
      ),
      const SizedBox(height: 24),
      ...memory.pluginsResults.mapIndexed((i, pluginResponse) {
        if (pluginResponse.content.length < 5) return const SizedBox.shrink();
        Plugin? plugin = pluginsList.firstWhereOrNull((element) => element.id == pluginResponse.pluginId);
        return Container(
          margin: const EdgeInsets.only(bottom: 40),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.start,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              plugin != null
                  ? ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: CircleAvatar(
                        backgroundColor: Colors.white,
                        maxRadius: 16,
                        backgroundImage: NetworkImage(plugin.getImageUrl()),
                      ),
                      title: Text(
                        plugin.name,
                        maxLines: 1,
                        style: const TextStyle(
                          fontWeight: FontWeight.w600,
                          color: Colors.white,
                          fontSize: 16,
                        ),
                      ),
                      subtitle: Padding(
                        padding: const EdgeInsets.only(top: 4.0),
                        child: Text(
                          plugin.description,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(color: Colors.grey, fontSize: 14),
                        ),
                      ),
                      trailing: IconButton(
                        icon: const Icon(Icons.copy_rounded, color: Colors.white, size: 20),
                        onPressed: () {
                          Clipboard.setData(ClipboardData(text: pluginResponse.content.trim()));
                          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                            content: Text('Plugin response copied to clipboard'),
                          ));
                          MixpanelManager().copiedMemoryDetails(memory, source: 'Plugin Response');
                        },
                      ),
                    )
                  : const SizedBox.shrink(),
              ExpandableTextWidget(
                text: pluginResponse.content.trim(),
                isExpanded: pluginResponseExpanded[i],
                toggleExpand: () {
                  if (!pluginResponseExpanded[i]) {
                    MixpanelManager().pluginResultExpanded(memory, pluginResponse.pluginId ?? '');
                  }
                  onItemToggled(i);
                },
                style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
                maxLines: 6,
                // Change this to 6 if you want the initial max lines to be 6
                linkColor: Colors.white,
              ),
            ],
          ),
        );
      }),
    ],
    const SizedBox(height: 8)
  ];
}

List<Widget> getGeolocationWidgets(ServerMemory memory, BuildContext context) {
  return memory.geolocation == null || memory.discarded
      ? []
      : [
          Text(
            'Taken at',
            style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 20),
          ),
          const SizedBox(height: 8),
          Text(
            '${memory.geolocation!.address}',
            style: TextStyle(color: Colors.grey.shade300),
          ),
          const SizedBox(height: 8),
          memory.geolocation != null
              ? GestureDetector(
                  onTap: () async {
                    // TODO: open google maps URL if available
                    MapsUtil.launchMap(memory.geolocation!.latitude!, memory.geolocation!.longitude!);
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
                    imageUrl: MapsUtil.getMapImageUrl(
                      memory.geolocation!.latitude!,
                      memory.geolocation!.longitude!,
                    ),
                  ),
                )
              : const SizedBox.shrink(),
          const SizedBox(height: 8),
        ];
}

showOptionsBottomSheet(
  BuildContext context,
  StateSetter setState,
  ServerMemory memory,
  Function(BuildContext, StateSetter, ServerMemory, Function) reprocessMemory,
) async {
  bool loadingReprocessMemory = false;
  bool displayDevTools = false;
  bool loadingPluginIntegrationTest = false;

  var result = await showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(16),
          topRight: Radius.circular(16),
        ),
      ),
      builder: (context) => StatefulBuilder(builder: (context, setModalState) {
            return Container(
              height: SharedPreferencesUtil().devModeEnabled ? 280 : 216,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surface,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(16),
                  topRight: Radius.circular(16),
                ),
              ),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
              child: Column(
                children: displayDevTools
                    ? [
                        ListTile(
                          title: const Text('Trigger Memory Created Integration'),
                          leading: loadingPluginIntegrationTest
                              ? const SizedBox(
                                  height: 24,
                                  width: 24,
                                  child: CircularProgressIndicator(
                                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                  ),
                                )
                              : const Icon(Icons.send_to_mobile_outlined),
                          onTap: () {
                            setModalState(() => loadingPluginIntegrationTest = true);
                            // TODO: if not set, show dialog to set URL or take them to settings.

                            webhookOnMemoryCreatedCall(memory, returnRawBody: true).then((response) {
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
                              setModalState(() => loadingPluginIntegrationTest = false);
                            });
                          },
                        ),
                        ListTile(
                          title: const Text('Test a Memory Prompt'),
                          leading: const Icon(Icons.chat),
                          trailing: const Icon(Icons.arrow_forward_ios, size: 20),
                          onTap: () {
                            routeToPage(context, TestPromptsPage(memory: memory));
                          },
                        ),
                      ]
                    : [
                        ListTile(
                          title: const Text('Re-summarize'),
                          leading: loadingReprocessMemory
                              ? const SizedBox(
                                  width: 24,
                                  height: 24,
                                  child: CircularProgressIndicator(
                                    valueColor: AlwaysStoppedAnimation<Color>(Colors.deepPurple),
                                  ))
                              : const Icon(Icons.refresh, color: Colors.deepPurple),
                          onTap: loadingReprocessMemory
                              ? null
                              : () => reprocessMemory(context, setModalState, memory, () {
                                    setModalState(() {
                                      loadingReprocessMemory = !loadingReprocessMemory;
                                    });
                                  }),
                        ),
                        ListTile(
                          title: const Text('Delete'),
                          leading: const Icon(
                            Icons.delete,
                            color: Colors.red,
                          ),
                          onTap: loadingReprocessMemory
                              ? null
                              : () {
                                  showDialog(
                                    context: context,
                                    builder: (dialogContext) {
                                      return Dialog(
                                        elevation: 0,
                                        insetPadding: EdgeInsets.zero,
                                        backgroundColor: Colors.transparent,
                                        alignment:
                                            const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
                                        child: ConfirmDeletionWidget(
                                            memory: memory,
                                            onDelete: () {
                                              Navigator.pop(context, true);
                                              Navigator.pop(context, {'deleted': true});
                                            }),
                                      );
                                    },
                                  );
                                },
                        ),
                        SharedPreferencesUtil().devModeEnabled
                            ? ListTile(
                                onTap: () {
                                  setModalState(() {
                                    displayDevTools = !displayDevTools;
                                  });
                                },
                                title: const Text('Developer Tools'),
                                leading: const Icon(
                                  Icons.developer_mode,
                                  color: Colors.white,
                                ),
                                trailing: const Icon(Icons.arrow_forward_ios, size: 20),
                              )
                            : const SizedBox.shrink(),
                      ],
              ),
            );
          }));
  if (result == true) setState(() {});
  debugPrint('showBottomSheet result: $result');
}
