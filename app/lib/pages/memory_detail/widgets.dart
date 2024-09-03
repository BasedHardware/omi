import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/http/webhooks.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/pages/memory_detail/test_prompts.dart';
import 'package:friend_private/pages/plugins/page.dart';
import 'package:friend_private/pages/settings/calendar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/utils/features/calendar.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/expandable_text.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

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
                      memory.geolocation!.latitude!,
                      memory.geolocation!.longitude!,
                    ),
                  ),
                )
              : const SizedBox.shrink(),
          const SizedBox(height: 8),
        ];
}

///************************************************
///************ SETTINGS BOTTOM SHEET *************
///************************************************

_getSheetTitle(context, memory) {
  return <Widget>[
    ListTile(
      title: Text(
        memory.discarded ? 'Discarded Memory' : memory.structured.title,
        style: Theme.of(context).textTheme.labelLarge,
      ),
      leading: const Icon(Icons.description),
      trailing: IconButton(
        icon: const Icon(Icons.cancel_outlined),
        onPressed: () => Navigator.of(context).pop(),
      ),
    ),
    const SizedBox(height: 8),
  ];
}

_getDevToolsOptions(
  BuildContext context,
  ServerMemory memory,
  Function(bool) changeLoadingPluginIntegrationTest,
  bool loadingPluginIntegrationTest,
) {
  return <Widget>[
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
          routeToPage(context, TestPromptsPage(memory: memory));
        },
      ),
    ),
  ];
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

_getShareOptions(
  BuildContext context,
  ServerMemory memory,
  bool loadingShareMemoryViaURL,
  Function changeLoadingShareMemoryViaURL,
  bool loadingShareTranscript,
  Function changeLoadingShareTranscript,
  bool loadingShareSummary,
  Function changeLoadingShareSummary,
) {
  return <Widget>[
    Card(
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
      child: ListTile(
        title: const Text('Send web url'),
        leading: loadingShareMemoryViaURL ? _getLoadingIndicator() : const Icon(Icons.link),
        onTap: () async {
          if (loadingShareMemoryViaURL) return;
          changeLoadingShareMemoryViaURL(true);
          bool shared = await setMemoryVisibility(memory.id);
          if (!shared) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Memory URL could not be shared.')),
            );
            return;
          }
          String content = '''
              Here\'s my memory created with Omi. ${memory.structured.getEmoji()}
              
              https://h.omi.me/memories/${memory.id}
              
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
              
              ${memory.structured.title}
              
              ${memory.getTranscript(generate: true)}
              
              Get started using Omi today (https://www.omi.me).
              '''
                  .replaceAll('  ', '')
                  .trim();
              // TODO: Deeplink that let people download the app.
              await Share.share(content);
              changeLoadingShareTranscript(false);
            },
          ),
          memory.discarded
              ? const SizedBox()
              : ListTile(
                  title: const Text('Send Summary'),
                  leading: loadingShareSummary ? _getLoadingIndicator() : const Icon(Icons.summarize),
                  onTap: () async {
                    if (loadingShareSummary) return;
                    changeLoadingShareSummary(true);
                    String content = '''
              Here\'s my memory created with Omi.
              
              ${memory.structured.toString()}
              
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
            onTap: () => _copyContent(context, memory.getTranscript(generate: true)),
          ),
          memory.discarded
              ? const SizedBox()
              : ListTile(
                  title: const Text('Copy Summary'),
                  leading: const Icon(Icons.file_copy),
                  onTap: () => _copyContent(context, memory.structured.toString()))
        ],
      ),
    ),
  ];
}

_getSheetMainOptions(
  BuildContext context,
  ServerMemory memory,
  Function(bool) changeLoadingReprocessMemory,
  loadingReprocessMemory,
  Function(bool) changeDisplayDevTools,
  displayDevTools,
  Function(bool) changeDisplayShareOptions,
  displayShareOptions,
  Function reprocessMemory,
) {
  return [
    Card(
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
      child: Column(
        children: [
          ListTile(
            title: const Text('Share'),
            leading: const Icon(Icons.share),
            trailing: const Icon(Icons.arrow_forward_ios, size: 20),
            onTap: () {
              changeDisplayShareOptions(!displayShareOptions);
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
            SharedPreferencesUtil().devModeEnabled
                ? ListTile(
                    onTap: () {
                      changeDisplayDevTools(!displayDevTools);
                    },
                    title: const Text('Developer Tools'),
                    leading: const Icon(
                      Icons.developer_mode,
                      color: Colors.white,
                    ),
                    trailing: const Icon(Icons.arrow_forward_ios, size: 20),
                  )
                : const SizedBox.shrink()
          ],
        )),
    const SizedBox(height: 4),
    Card(
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(8)),
      ),
      child: Column(
        children: [
          ListTile(
            title: const Text('Re-summarize'),
            leading: loadingReprocessMemory
                ? const SizedBox(
                    width: 24,
                    height: 24,
                    child: CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                    ),
                  )
                : const Icon(Icons.refresh),
            onTap: loadingReprocessMemory
                ? null
                : () {
                    final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                    if (connectivityProvider.isConnected) {
                      reprocessMemory(context, memory, () {
                        changeLoadingReprocessMemory(!loadingReprocessMemory);
                      });
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
            onTap: loadingReprocessMemory
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
                            deleteMemoryServer(memory.id);
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
                        builder: (c) => getDialog(context, () => Navigator.pop(context), () => Navigator.pop(context),
                            'Unable to Delete Memory', 'Please check your internet connection and try again.',
                            singleButton: true, okButtonText: 'OK'),
                        context: context,
                      );
                    }
                  },
          ),
        ],
      ),
    ),
  ];
}

showOptionsBottomSheet(
  BuildContext context,
  StateSetter setState,
  ServerMemory memory,
  Function(BuildContext, ServerMemory, Function) reprocessMemory,
) async {
  bool displayDevTools = false;
  bool displayShareOptions = false;

  bool loadingReprocessMemory = false;
  bool loadingPluginIntegrationTest = false;
  bool loadingShareMemoryTranscript = false;
  bool loadingShareMemorySummary = false;
  bool loadingShareMemoryViaURL = false;

  var result = await showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(16),
          topRight: Radius.circular(16),
        ),
      ),
      builder: (context) => StatefulBuilder(builder: (context, setModalState) {
            changeDisplayDevOptions(bool value) => setModalState(() => displayDevTools = value);
            changeDisplayShareOptions(bool value) => setModalState(() => displayShareOptions = value);

            changeLoadingReprocessMemory(bool value) => setModalState(() => loadingReprocessMemory = value);
            changeLoadingPluginIntegrationTest(bool value) => setModalState(() => loadingPluginIntegrationTest = value);

            changeLoadingShareMemoryTranscript(bool value) => setModalState(() => loadingShareMemoryTranscript = value);
            changeLoadingShareMemorySummary(bool value) => setModalState(() => loadingShareMemorySummary = value);
            changeLoadingShareMemoryViaURL(bool value) => setModalState(() => loadingShareMemoryViaURL = value);

            return Container(
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surface,
                borderRadius: const BorderRadius.only(topLeft: Radius.circular(16), topRight: Radius.circular(16)),
              ),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  ..._getSheetTitle(context, memory),
                  ...(displayDevTools
                      ? _getDevToolsOptions(
                          context, memory, changeLoadingPluginIntegrationTest, loadingPluginIntegrationTest)
                      : displayShareOptions
                          ? _getShareOptions(
                              context,
                              memory,
                              loadingShareMemoryViaURL,
                              changeLoadingShareMemoryViaURL,
                              loadingShareMemoryTranscript,
                              changeLoadingShareMemoryTranscript,
                              loadingShareMemorySummary,
                              changeLoadingShareMemorySummary,
                            )
                          : _getSheetMainOptions(
                              context,
                              memory,
                              changeLoadingReprocessMemory,
                              loadingReprocessMemory,
                              changeDisplayDevOptions,
                              displayDevTools,
                              changeDisplayShareOptions,
                              displayShareOptions,
                              reprocessMemory,
                            )),
                  const SizedBox(height: 40),
                ],
              ),
            );
          }));
  if (result == true) setState(() {});
  debugPrint('showBottomSheet result: $result');
}
