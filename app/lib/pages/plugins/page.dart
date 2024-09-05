import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/pages/plugins/plugin_detail.dart';
import 'package:friend_private/providers/plugin_provider.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

class PluginsPage extends StatefulWidget {
  final bool filterChatOnly;

  const PluginsPage({super.key, this.filterChatOnly = false});

  @override
  State<PluginsPage> createState() => _PluginsPageState();
}

class _PluginsPageState extends State<PluginsPage> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<PluginProvider>().initialize(widget.filterChatOnly);
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PluginProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.primary,
          automaticallyImplyLeading: true,
          title: const Text('Plugins'),
          centerTitle: true,
          elevation: 0,
          actions: [
            TextButton(
                onPressed: () {
                  launchUrl(Uri.parse('https://basedhardware.com/plugins'));
                },
                child: const Row(
                  children: [
                    Text(
                      'Create Yours',
                      style: TextStyle(color: Colors.white),
                    ),
                    SizedBox(
                      width: 8,
                    ),
                  ],
                ))
          ],
        ),
        body: GestureDetector(
          onTap: () => FocusScope.of(context).unfocus(),
          child: CustomScrollView(
            slivers: [
              const SliverToBoxAdapter(
                child: SizedBox(height: 32),
              ),
              SliverToBoxAdapter(
                child: Container(
                  padding: const EdgeInsets.fromLTRB(16, 8, 8, 0),
                  margin: const EdgeInsets.fromLTRB(18, 0, 18, 0),
                  decoration: const BoxDecoration(
                    color: Colors.black,
                    borderRadius: BorderRadius.all(Radius.circular(16)),
                    border: GradientBoxBorder(
                      gradient: LinearGradient(colors: [
                        Color.fromARGB(127, 208, 208, 208),
                        Color.fromARGB(127, 188, 99, 121),
                        Color.fromARGB(127, 86, 101, 182),
                        Color.fromARGB(127, 126, 190, 236)
                      ]),
                      width: 1,
                    ),
                    shape: BoxShape.rectangle,
                  ),
                  // TODO: reuse chat textfield
                  child: TextField(
                    onChanged: provider.updateSearchQuery,
                    obscureText: false,
                    decoration: InputDecoration(
                      hintText: 'Find your plugin...',
                      hintStyle: const TextStyle(fontSize: 14.0, color: Colors.grey),
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                      suffixIcon: provider.searchQuery.isEmpty
                          ? const SizedBox.shrink()
                          : IconButton(
                              icon: const Icon(
                                Icons.cancel,
                                color: Color(0xFFF7F4F4),
                                size: 28.0,
                              ),
                              onPressed: () => provider.updateSearchQuery(''),
                            ),
                    ),
                    style: const TextStyle(
                      // fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                      color: Colors.white,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ),
              const SliverToBoxAdapter(child: SizedBox(height: 16)),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: Row(
                    children: [
                      // const Text(
                      //   'Filter:',
                      //   style: TextStyle(color: Colors.white, fontSize: 16),
                      // ),
                      // const SizedBox(width: 16),
                      GestureDetector(
                        onTap: provider.toggleFilterMemories,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                          decoration: BoxDecoration(
                            color: provider.filterMemories ? Colors.deepPurple : Colors.transparent,
                            borderRadius: BorderRadius.circular(16),
                            border: provider.filterMemories
                                ? Border.all(color: Colors.deepPurple)
                                : Border.all(color: Colors.grey),
                          ),
                          child: const Text(
                            'Memories',
                            style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      GestureDetector(
                        onTap: provider.toggleFilterChat,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                          decoration: BoxDecoration(
                            color: provider.filterChat ? Colors.deepPurple : Colors.transparent,
                            borderRadius: BorderRadius.circular(16),
                            border: provider.filterChat
                                ? Border.all(color: Colors.deepPurple)
                                : Border.all(color: Colors.grey),
                          ),
                          child: const Text(
                            'Chat',
                            style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      GestureDetector(
                        onTap: provider.toggleFilterExternal,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                          decoration: BoxDecoration(
                            color: provider.filterExternal ? Colors.deepPurple : Colors.transparent,
                            borderRadius: BorderRadius.circular(16),
                            border: provider.filterExternal
                                ? Border.all(color: Colors.deepPurple)
                                : Border.all(color: Colors.grey),
                          ),
                          child: const Text(
                            'Integration',
                            style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              // const SliverToBoxAdapter(child: SizedBox(height: 8)),
              provider.filteredPlugins.isEmpty
                  ? SliverToBoxAdapter(
                      child: Padding(
                        padding: const EdgeInsets.only(top: 64, left: 14, right: 14),
                        child: Center(
                          child: Text(
                            context.read<ConnectivityProvider>().isConnected
                                ? 'No plugins found'
                                : 'Unable to fetch plugins :(\n\nPlease check your internet connection and try again.',
                            style: const TextStyle(color: Colors.white, fontSize: 16),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      ),
                    )
                  : const SliverToBoxAdapter(child: SizedBox(height: 8)),
              SliverList(
                  delegate: SliverChildBuilderDelegate(
                (context, index) {
                  final plugin = provider.filteredPlugins[index];
                  return Container(
                    padding: const EdgeInsets.fromLTRB(8, 8, 0, 8),
                    decoration: BoxDecoration(
                      shape: BoxShape.rectangle,
                      borderRadius: const BorderRadius.all(Radius.circular(16.0)),
                      color: Colors.grey.shade900,
                    ),
                    margin: EdgeInsets.only(bottom: 12, top: index == 0 ? 24 : 0, left: 16, right: 16),
                    child: ListTile(
                      onTap: () async {
                        await routeToPage(context, PluginDetailPage(plugin: plugin));
                        provider.setPlugins();
                      },
                      leading: CachedNetworkImage(
                        imageUrl: plugin.getImageUrl(),
                        imageBuilder: (context, imageProvider) => CircleAvatar(
                          backgroundColor: Colors.white,
                          maxRadius: 28,
                          backgroundImage: imageProvider,
                        ),
                        placeholder: (context, url) => const CircularProgressIndicator(),
                        errorWidget: (context, url, error) => const Icon(Icons.error),
                      ),
                      title: Text(
                        plugin.name,
                        maxLines: 1,
                        style: const TextStyle(fontWeight: FontWeight.w600, color: Colors.white, fontSize: 16),
                      ),
                      subtitle: Column(
                        mainAxisAlignment: MainAxisAlignment.start,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SizedBox(height: plugin.ratingAvg != null ? 4 : 0),
                          plugin.ratingAvg != null
                              ? Row(
                                  children: [
                                    Text(plugin.getRatingAvg()!),
                                    const SizedBox(width: 4),
                                    const Icon(Icons.star, color: Colors.deepPurple, size: 16),
                                    const SizedBox(width: 4),
                                    Text('(${plugin.ratingCount})'),
                                  ],
                                )
                              : Container(),
                          Padding(
                            padding: const EdgeInsets.only(top: 4.0),
                            child: Text(
                              plugin.description,
                              maxLines: 2,
                              style: const TextStyle(color: Colors.grey, fontSize: 14),
                            ),
                          ),
                          const SizedBox(height: 8),
                          Row(
                            children: [
                              plugin.worksWithMemories()
                                  ? Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: Colors.grey,
                                        borderRadius: BorderRadius.circular(16),
                                      ),
                                      child: const Text(
                                        'Memories',
                                        style: TextStyle(
                                            color: Colors.deepPurple, fontSize: 12, fontWeight: FontWeight.w500),
                                      ),
                                    )
                                  : const SizedBox.shrink(),
                              SizedBox(width: plugin.worksWithChat() ? 8 : 0),
                              plugin.worksWithChat()
                                  ? Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: Colors.grey,
                                        borderRadius: BorderRadius.circular(16),
                                      ),
                                      child: const Text(
                                        'Chat',
                                        style: TextStyle(
                                            color: Colors.deepPurple, fontSize: 12, fontWeight: FontWeight.w500),
                                      ),
                                    )
                                  : const SizedBox.shrink(),
                              SizedBox(width: plugin.worksExternally() ? 8 : 0),
                              plugin.worksExternally()
                                  ? Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: Colors.grey,
                                        borderRadius: BorderRadius.circular(16),
                                      ),
                                      child: const Text(
                                        'Integration',
                                        style: TextStyle(
                                            color: Colors.deepPurple, fontSize: 12, fontWeight: FontWeight.w500),
                                      ),
                                    )
                                  : const SizedBox.shrink(),
                            ],
                          )
                        ],
                      ),
                      trailing: provider.pluginLoading.isNotEmpty && provider.pluginLoading[index]
                          ? const SizedBox(
                              height: 24,
                              width: 24,
                              child: CircularProgressIndicator(
                                valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                              ),
                            )
                          : IconButton(
                              icon: Icon(
                                plugin.enabled ? Icons.check : Icons.arrow_downward_rounded,
                                color: plugin.enabled ? Colors.white : Colors.grey,
                              ),
                              onPressed: () {
                                if (plugin.worksExternally() && !plugin.enabled) {
                                  showDialog(
                                    context: context,
                                    builder: (c) => getDialog(
                                      context,
                                      () => Navigator.pop(context),
                                      () async {
                                        Navigator.pop(context);
                                        await routeToPage(context, PluginDetailPage(plugin: plugin));
                                        provider.setPlugins();
                                      },
                                      'Authorize External Plugin',
                                      'Do you allow this plugin to access your memories, transcripts, and recordings? Your data will be sent to the plugin\'s server for processing.',
                                      okButtonText: 'Confirm',
                                    ),
                                  );
                                } else {
                                  provider.togglePlugin(plugin.id.toString(), !plugin.enabled, index);
                                }
                              },
                            ),
                      // trailing: Switch(
                      //   value: plugin.isEnabled,
                      //   activeColor: Colors.deepPurple,
                      //   onChanged: (value) {
                      //     _togglePlugin(plugin.id.toString(), value);
                      //   },
                      // ),
                    ),
                  );
                },
                childCount: provider.filteredPlugins.length,
                // TODO: integration plugins should have a "auth" completed button or smth.
              )),
              // Expanded(
              //   child: ListView.builder(
              //     itemCount: filteredPlugins.length,
              //     itemBuilder: (context, index) {
              //       final plugin = filteredPlugins[index];
              //       return Container(
              //         padding: const EdgeInsets.fromLTRB(8, 8, 0, 8),
              //         decoration: BoxDecoration(
              //           shape: BoxShape.rectangle,
              //           borderRadius: const BorderRadius.all(Radius.circular(16.0)),
              //           color: Colors.grey.shade900,
              //         ),
              //         margin: EdgeInsets.only(bottom: 12, top: index == 0 ? 24 : 0, left: 16, right: 16),
              //         child: ListTile(
              //           onTap: () async {
              //             await routeToPage(context, PluginDetailPage(plugin: plugin));
              //             _fetchPlugins();
              //             // refresh plugins
              //           },
              //           leading: CircleAvatar(
              //             backgroundColor: Colors.white,
              //             maxRadius: 28,
              //             backgroundImage: NetworkImage(plugin.getImageUrl()),
              //           ),
              //           title: Text(
              //             plugin.name,
              //             maxLines: 1,
              //             style: const TextStyle(fontWeight: FontWeight.w600, color: Colors.white, fontSize: 16),
              //           ),
              //           subtitle: Column(
              //             mainAxisAlignment: MainAxisAlignment.start,
              //             crossAxisAlignment: CrossAxisAlignment.start,
              //             children: [
              //               SizedBox(height: plugin.ratingAvg != null ? 4 : 0),
              //               plugin.ratingAvg != null
              //                   ? Row(
              //                       children: [
              //                         Text(plugin.getRatingAvg()!),
              //                         const SizedBox(width: 4),
              //                         const Icon(Icons.star, color: Colors.deepPurple, size: 16),
              //                         const SizedBox(width: 4),
              //                         Text('(${plugin.ratingCount})'),
              //                       ],
              //                     )
              //                   : Container(),
              //               Padding(
              //                 padding: const EdgeInsets.only(top: 4.0),
              //                 child: Text(
              //                   plugin.description,
              //                   maxLines: 2,
              //                   style: const TextStyle(color: Colors.grey, fontSize: 14),
              //                 ),
              //               ),
              //               const SizedBox(height: 8),
              //               Row(
              //                 children: [
              //                   plugin.memories
              //                       ? Container(
              //                           padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              //                           decoration: BoxDecoration(
              //                             color: Colors.grey,
              //                             borderRadius: BorderRadius.circular(16),
              //                           ),
              //                           child: const Text(
              //                             'Memories',
              //                             style: TextStyle(
              //                                 color: Colors.deepPurple, fontSize: 12, fontWeight: FontWeight.w500),
              //                           ),
              //                         )
              //                       : const SizedBox.shrink(),
              //                   const SizedBox(width: 8),
              //                   plugin.chat
              //                       ? Container(
              //                           padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              //                           decoration: BoxDecoration(
              //                             color: Colors.grey,
              //                             borderRadius: BorderRadius.circular(16),
              //                           ),
              //                           child: const Text(
              //                             'Chat',
              //                             style: TextStyle(
              //                                 color: Colors.deepPurple, fontSize: 12, fontWeight: FontWeight.w500),
              //                           ),
              //                         )
              //                       : const SizedBox.shrink(),
              //                 ],
              //               )
              //             ],
              //           ),
              //           trailing: IconButton(
              //             icon: Icon(
              //               plugin.isEnabled ? Icons.check : Icons.arrow_downward_rounded,
              //               color: plugin.isEnabled ? Colors.white : Colors.grey,
              //             ),
              //             onPressed: () {
              //               _togglePlugin(plugin.id.toString(), !plugin.isEnabled);
              //             },
              //           ),
              //           // trailing: Switch(
              //           //   value: plugin.isEnabled,
              //           //   activeColor: Colors.deepPurple,
              //           //   onChanged: (value) {
              //           //     _togglePlugin(plugin.id.toString(), value);
              //           //   },
              //           // ),
              //         ),
              //       );
              //     },
              //   ),
              // ),
            ],
          ),
        ),
      );
    });
  }
}
