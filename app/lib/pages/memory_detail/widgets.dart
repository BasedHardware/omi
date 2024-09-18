import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/http/webhooks.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/geolocation.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/pages/memory_detail/compare_transcripts.dart';
import 'package:friend_private/pages/memory_detail/memory_detail_provider.dart';
import 'package:friend_private/pages/memory_detail/test_prompts.dart';
import 'package:friend_private/pages/plugins/page.dart';
import 'package:friend_private/pages/settings/calendar.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/features/calendar.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/expandable_text.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'maps_util.dart';

class GetSummaryWidgets extends StatelessWidget {
  const GetSummaryWidgets({super.key});

  String setTime(DateTime? startedAt, DateTime createdAt, DateTime? finishedAt) {
    return startedAt == null
        ? dateTimeFormat('h:mm a', createdAt)
        : '${dateTimeFormat('h:mm a', startedAt)} to ${dateTimeFormat('h:mm a', finishedAt)}';
  }

  @override
  Widget build(BuildContext context) {
    return Selector<MemoryDetailProvider, ServerMemory>(
      selector: (context, provider) => provider.memory,
      builder: (context, memory, child) {
        return Column(
          mainAxisAlignment: MainAxisAlignment.start,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 24),
            Text(
              memory.discarded ? 'Discarded Memory' : memory.structured.title,
              style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 32),
            ),
            const SizedBox(height: 16),
            Text(
              '${dateTimeFormat('MMM d,  yyyy', memory.createdAt)} ${memory.startedAt == null ? 'at' : 'from'} ${setTime(memory.startedAt, memory.createdAt, memory.finishedAt)}',
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
                : GetEditTextField(
                    enabled: context.read<MemoryDetailProvider>().editingTitle,
                    overview: memory.structured.overview,
                  ),
            memory.discarded ? const SizedBox.shrink() : const SizedBox(height: 40),
            memory.structured.actionItems.isNotEmpty
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
                              text: '- ${memory.structured.actionItems.map((e) => e.description).join('\n- ')}'));
                          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                            content: Text('Action items copied to clipboard'),
                            duration: Duration(seconds: 2),
                          ));
                          // MixpanelManager().copiedMemoryDetails(memory, source: 'Action Items');
                        },
                        icon: const Icon(Icons.copy_rounded, color: Colors.white, size: 20),
                      )
                    ],
                  )
                : const SizedBox.shrink(),
            ...memory.structured.actionItems.map<Widget>((item) {
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
            memory.structured.actionItems.isNotEmpty ? const SizedBox(height: 40) : const SizedBox.shrink(),
            // memory.structured.events.isNotEmpty && memory.structured.events.where((e) => e.startsAt.isBefore(memory.startedAt!)).isNotEmpty
            //     ? Row(
            //         children: [
            //           Icon(Icons.event, color: Colors.grey.shade300),
            //           const SizedBox(width: 8),
            //           Text(
            //             'Events',
            //             style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
            //           )
            //         ],
            //       )
            //     : const SizedBox.shrink(),
            const EventsListWidget(),
            memory.structured.events.isNotEmpty ? const SizedBox(height: 40) : const SizedBox.shrink(),
          ],
        );
      },
    );
  }
}

class EventsListWidget extends StatelessWidget {
  const EventsListWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<MemoryDetailProvider>(
      builder: (context, provider, child) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            provider.memory.structured.events.isNotEmpty &&
                    !(provider.memory.structured.events
                        .where((e) =>
                            e.startsAt.isBefore(provider.memory.startedAt!.add(const Duration(hours: 6))) &&
                            e.startsAt.add(Duration(minutes: e.duration)).isBefore(provider.memory.startedAt!))
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
              itemCount: provider.memory.structured.events.length,
              shrinkWrap: true,
              itemBuilder: (context, idx) {
                var event = provider.memory.structured.events[idx];
                if (event.startsAt.isBefore(provider.memory.startedAt!.add(const Duration(hours: 6))) &&
                    event.startsAt.add(Duration(minutes: event.duration)).isBefore(provider.memory.startedAt!)) {
                  return const SizedBox.shrink();
                }
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(
                    event.title,
                    style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  subtitle: Padding(
                    padding: const EdgeInsets.only(top: 4.0),
                    child: Text(
                      '${dateTimeFormat('MMM d, yyyy', event.startsAt)} at ${dateTimeFormat('h:mm a', event.startsAt)} ~ ${minutesConversion(event.duration)}.',
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
                            context.read<MemoryDetailProvider>().updateEventState(true, idx);
                            setMemoryEventsState(provider.memory.id, [idx], [true]);
                            CalendarUtil().createEvent(
                              event.title,
                              event.startsAt,
                              event.duration,
                              description: event.description,
                            );
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('Event added to calendar'),
                              ),
                            );
                          },
                    icon: Icon(event.created ? Icons.check : Icons.add, color: Colors.white),
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
    return '${minutes / 60} hours';
  } else {
    return '${minutes / 1440} days';
  }
}

class GetEditTextField extends StatefulWidget {
  final bool enabled;
  final String overview;

  const GetEditTextField({super.key, required this.enabled, required this.overview});

  @override
  State<GetEditTextField> createState() => _GetEditTextFieldState();
}

class _GetEditTextFieldState extends State<GetEditTextField> {
  late TextEditingController controller;

  @override
  void initState() {
    controller = TextEditingController(text: widget.overview);
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return widget.enabled
        ? TextField(
            keyboardType: TextInputType.multiline,
            maxLines: null,
            decoration: const InputDecoration(
              border: OutlineInputBorder(borderSide: BorderSide.none),
              contentPadding: EdgeInsets.all(0),
            ),
            enabled: widget.enabled,
            style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
          )
        : SelectionArea(
            child: Text(
              controller.text,
              style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
            ),
          );
  }
}

class ReprocessDiscardedWidget extends StatelessWidget {
  const ReprocessDiscardedWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<MemoryDetailProvider>(builder: (context, provider, child) {
      if (provider.loadingReprocessMemory) {
        return const Center(
          child: Padding(
            padding: EdgeInsets.only(top: 18.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                ),
                SizedBox(width: 16),
                Text(
                  'Re-summarizing memory...\nThis may take a few seconds',
                  style: TextStyle(color: Colors.white, fontSize: 16),
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
                    await provider.reprocessMemory();
                  },
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  child: const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 16, vertical: 0),
                      child: Text('Re-summarise', style: TextStyle(color: Colors.white, fontSize: 16))),
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

class GetPluginsWidgets extends StatelessWidget {
  const GetPluginsWidgets({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<MemoryDetailProvider>(
      builder: (context, provider, child) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.start,
          crossAxisAlignment:
              provider.memory.pluginsResults.isEmpty ? CrossAxisAlignment.center : CrossAxisAlignment.start,
          children: provider.memory.pluginsResults.isEmpty
              ? [child!]
              : [
                  // TODO: include a way to trigger specific plugins
                  if (provider.memory.pluginsResults.isNotEmpty && !provider.memory.discarded) ...[
                    provider.memory.structured.actionItems.isEmpty
                        ? const SizedBox(height: 40)
                        : const SizedBox.shrink(),
                    Text(
                      'Plugins 🧑‍💻',
                      style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
                      textAlign: TextAlign.start,
                    ),
                    const SizedBox(height: 24),
                    ...provider.memory.pluginsResults.mapIndexed(
                      (i, pluginResponse) {
                        if (pluginResponse.content.length < 5) return const SizedBox.shrink();
                        Plugin? plugin =
                            provider.pluginsList.firstWhereOrNull((element) => element.id == pluginResponse.pluginId);
                        return Container(
                          margin: const EdgeInsets.only(bottom: 40),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.start,
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              plugin != null
                                  ? ListTile(
                                      contentPadding: EdgeInsets.zero,
                                      leading: CachedNetworkImage(
                                        imageUrl: plugin.getImageUrl(),
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
                                          MixpanelManager()
                                              .copiedMemoryDetails(provider.memory, source: 'Plugin Response');
                                        },
                                      ),
                                    )
                                  : const SizedBox.shrink(),
                              ExpandableTextWidget(
                                text: pluginResponse.content.trim(),
                                isExpanded: provider.pluginResponseExpanded[i],
                                toggleExpand: () {
                                  print('pluginResponseExpanded: ${provider.pluginResponseExpanded}');
                                  if (!provider.pluginResponseExpanded[i]) {
                                    MixpanelManager()
                                        .pluginResultExpanded(provider.memory, pluginResponse.pluginId ?? '');
                                  }
                                  provider.updatePluginResponseExpanded(i);
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
                    routeToPage(context, const PluginsPage());
                    MixpanelManager().pageOpened('Memory Detail Plugins');
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
        ],
      ),
    );
  }
}

class GetGeolocationWidgets extends StatelessWidget {
  const GetGeolocationWidgets({super.key});

  @override
  Widget build(BuildContext context) {
    return Selector<MemoryDetailProvider, Geolocation?>(selector: (context, provider) {
      if (provider.memory.discarded) return null;
      return provider.memory.geolocation;
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
                geolocation != null
                    ? GestureDetector(
                        onTap: () async {
                          // TODO: open google maps URL if available
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
                      )
                    : const SizedBox.shrink(),
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
    return Consumer<MemoryDetailProvider>(builder: (context, provider, child) {
      return Column(
        children: [
          ListTile(
            title: Text(
              provider.memory.discarded ? 'Discarded Memory' : provider.memory.structured.title,
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
  final ServerMemory memory;

  const GetDevToolsOptions({
    super.key,
    required this.memory,
  });

  @override
  State<GetDevToolsOptions> createState() => _GetDevToolsOptionsState();
}

class _GetDevToolsOptionsState extends State<GetDevToolsOptions> {
  bool loadingPluginIntegrationTest = false;

  void changeLoadingPluginIntegrationTest(bool value) {
    setState(() {
      loadingPluginIntegrationTest = value;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Card(
        shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
        child: ListTile(
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
            changeLoadingPluginIntegrationTest(true);
            // TODO: if not set, show dialog to set URL or take them to settings.

            webhookOnMemoryCreatedCall(widget.memory, returnRawBody: true).then((response) {
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
              changeLoadingPluginIntegrationTest(false);
            });
          },
        ),
      ),
      Card(
        shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
        child: ListTile(
          title: const Text('Test a Memory Prompt'),
          leading: const Icon(Icons.chat),
          trailing: const Icon(Icons.arrow_forward_ios, size: 20),
          onTap: () {
            routeToPage(context, TestPromptsPage(memory: widget.memory));
          },
        ),
      ),
      // widget.memory.postprocessing?.status == MemoryPostProcessingStatus.completed
      widget.memory.postprocessing?.status != MemoryPostProcessingStatus.not_started
          ? Card(
              shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
              child: ListTile(
                title: const Text('Compare Transcripts Models'),
                leading: const Icon(Icons.chat),
                trailing: const Icon(Icons.arrow_forward_ios, size: 20),
                onTap: () {
                  routeToPage(context, CompareTranscriptsPage(memory: widget.memory));
                },
              ),
            )
          : const SizedBox.shrink(),
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
  final ServerMemory memory;

  const GetShareOptions({
    super.key,
    required this.memory,
  });

  @override
  State<GetShareOptions> createState() => _GetShareOptionsState();
}

class _GetShareOptionsState extends State<GetShareOptions> {
  bool loadingShareMemoryViaURL = false;
  bool loadingShareTranscript = false;
  bool loadingShareSummary = false;

  void changeLoadingShareMemoryViaURL(bool value) {
    setState(() {
      loadingShareMemoryViaURL = value;
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
            leading: loadingShareMemoryViaURL ? _getLoadingIndicator() : const Icon(Icons.link),
            onTap: () async {
              if (loadingShareMemoryViaURL) return;
              changeLoadingShareMemoryViaURL(true);
              bool shared = await setMemoryVisibility(widget.memory.id);
              if (!shared) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Memory URL could not be shared.')),
                );
                return;
              }
              String content = '''
              Here\'s my memory created with Omi. ${widget.memory.structured.getEmoji()}
              
              https://h.omi.me/memories/${widget.memory.id}
              
              Get started using Omi today.
              '''
                  .replaceAll('  ', '')
                  .trim();
              print(content);
              await Share.share(content);
              changeLoadingShareMemoryViaURL(false);
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
                  // TODO: check web url open graph.
                  String content = '''
              Here\'s my memory created with Omi.
              
              ${widget.memory.structured.title}
              
              ${widget.memory.getTranscript(generate: true)}
              
              Get started using Omi today (https://www.omi.me).
              '''
                      .replaceAll('  ', '')
                      .trim();
                  // TODO: Deeplink that let people download the app.
                  await Share.share(content);
                  changeLoadingShareTranscript(false);
                },
              ),
              widget.memory.discarded
                  ? const SizedBox()
                  : ListTile(
                      title: const Text('Send Summary'),
                      leading: loadingShareSummary ? _getLoadingIndicator() : const Icon(Icons.summarize),
                      onTap: () async {
                        if (loadingShareSummary) return;
                        changeLoadingShareSummary(true);
                        String content = '''
              Here\'s my memory created with Omi.
              
              ${widget.memory.structured.toString()}
              
              Get started using Omi today (https://www.omi.me).
              '''
                            .replaceAll('  ', '')
                            .trim();
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
                onTap: () => _copyContent(context, widget.memory.getTranscript(generate: true)),
              ),
              widget.memory.discarded
                  ? const SizedBox()
                  : ListTile(
                      title: const Text('Copy Summary'),
                      leading: const Icon(Icons.file_copy),
                      onTap: () => _copyContent(
                        context,
                        widget.memory.structured.toString(),
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
    return Consumer<MemoryDetailProvider>(builder: (context, provider, child) {
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
                  title: const Text('Re-summarize'),
                  leading: provider.loadingReprocessMemory
                      ? const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                        )
                      : const Icon(Icons.refresh),
                  onTap: provider.loadingReprocessMemory
                      ? null
                      : () async {
                          final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                          if (connectivityProvider.isConnected) {
                            await provider.reprocessMemory();
                          } else {
                            showDialog(
                              builder: (c) => getDialog(
                                context,
                                () => Navigator.pop(context),
                                () => Navigator.pop(context),
                                'Unable to Re-summarize Memory',
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
                  onTap: provider.loadingReprocessMemory
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
                                  context.read<MemoryProvider>().deleteMemory(provider.memory, provider.memoryIdx);
                                  Navigator.pop(context, true);
                                  Navigator.pop(context, true);
                                  Navigator.pop(context, {'deleted': true});
                                },
                                'Delete Memory?',
                                'Are you sure you want to delete this memory? This action cannot be undone.',
                                okButtonText: 'Confirm',
                              ),
                            );
                          } else {
                            showDialog(
                              builder: (c) => getDialog(
                                  context,
                                  () => Navigator.pop(context),
                                  () => Navigator.pop(context),
                                  'Unable to Delete Memory',
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
      child: Consumer<MemoryDetailProvider>(builder: (context, provider, child) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const GetSheetTitle(),
            (provider.displayDevToolsInSheet
                ? GetDevToolsOptions(
                    memory: provider.memory,
                  )
                : provider.displayShareOptionsInSheet
                    ? GetShareOptions(
                        memory: provider.memory,
                      )
                    : const GetSheetMainOptions()),
            const SizedBox(height: 40),
          ],
        );
      }),
    );
  }
}
