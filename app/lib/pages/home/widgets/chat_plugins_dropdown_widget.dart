import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/pages/plugins/page.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/providers/plugin_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';

class ChatPluginsDropdownWidget extends StatelessWidget {
  const ChatPluginsDropdownWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Selector<HomeProvider, bool>(
      selector: (context, state) => state.selectedIndex == 1,
      builder: (context, isChatPage, child) {
        if (!isChatPage) {
          return const SizedBox(
            width: 16,
          );
        }
        return child!;
      },
      child: Consumer<PluginProvider>(builder: (context, provider, child) {
        return Padding(
          padding: const EdgeInsets.only(left: 0),
          child: provider.plugins.where((p) => p.enabled).isEmpty
              ? GestureDetector(
                  onTap: () {
                    MixpanelManager().pageOpened('Chat Plugins');

                    routeToPage(context, const PluginsPage(filterChatOnly: true));
                  },
                  child: const Row(
                    children: [
                      Icon(size: 20, Icons.chat, color: Colors.white),
                      SizedBox(width: 10),
                      Text(
                        'Enable Apps',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                      ),
                    ],
                  ),
                )
              : Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: DropdownButton<String>(
                    menuMaxHeight: 350,
                    value: provider.selectedChatPluginId,
                    onChanged: (s) async {
                      if ((s == 'no_selected' && provider.plugins.where((p) => p.enabled).isEmpty) || s == 'enable') {
                        routeToPage(context, const PluginsPage(filterChatOnly: true));
                        MixpanelManager().pageOpened('Chat Plugins');
                        return;
                      }
                      if (s == null || s == provider.selectedChatPluginId) return;
                      provider.setSelectedChatPluginId(s);
                      var plugin = provider.getSelectedPlugin();
                      context.read<MessageProvider>().sendInitialPluginMessage(plugin);
                    },
                    icon: Container(),
                    alignment: Alignment.center,
                    dropdownColor: Colors.black,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                    underline: Container(height: 0, color: Colors.transparent),
                    isExpanded: false,
                    itemHeight: 48,
                    padding: EdgeInsets.zero,
                    items: _getPluginsDropdownItems(context, provider),
                  ),
                ),
        );
      }),
    );
  }

  _getPluginsDropdownItems(BuildContext context, PluginProvider provider) {
    var items = [
          DropdownMenuItem<String>(
            value: 'no_selected',
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                const Icon(size: 20, Icons.chat, color: Colors.white),
                const SizedBox(width: 10),
                Text(
                  provider.plugins.where((p) => p.enabled).isEmpty ? 'Enable Apps   ' : 'Select an App',
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                )
              ],
            ),
          )
        ] +
        provider.plugins.where((p) => p.enabled && p.worksWithChat()).map<DropdownMenuItem<String>>((Plugin plugin) {
          return DropdownMenuItem<String>(
            value: plugin.id,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              mainAxisAlignment: MainAxisAlignment.start,
              children: [
                CachedNetworkImage(
                  imageUrl: plugin.getImageUrl(),
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
                      child: Icon(Icons.error_outline_rounded),
                    );
                  },
                  progressIndicatorBuilder: (context, url, progress) => CircleAvatar(
                    backgroundColor: Colors.white,
                    radius: 12,
                    child: CircularProgressIndicator(
                      value: progress.progress,
                      valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  plugin.name.length > 18
                      ? '${plugin.name.substring(0, 18)}...'
                      : plugin.name + ' ' * (18 - plugin.name.length),
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                )
              ],
            ),
          );
        }).toList();
    if (provider.plugins.where((p) => p.enabled).isNotEmpty) {
      items.add(const DropdownMenuItem<String>(
        value: 'enable',
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            CircleAvatar(
              backgroundColor: Colors.transparent,
              maxRadius: 12,
              child: Icon(Icons.star, color: Colors.purpleAccent),
            ),
            SizedBox(width: 8),
            Text('Enable Apps   ', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16))
          ],
        ),
      ));
    }
    return items;
  }
}
