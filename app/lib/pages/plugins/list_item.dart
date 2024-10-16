import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/pages/plugins/plugin_detail.dart';
import 'package:friend_private/providers/plugin_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';

class PluginListItem extends StatelessWidget {
  final Plugin plugin;
  final int index;
  final PluginProvider provider;

  const PluginListItem({super.key, required this.plugin, required this.index, required this.provider});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () async {
        MixpanelManager().pageOpened('Plugin Detail');
        await routeToPage(context, PluginDetailPage(plugin: plugin));
        provider.setPlugins();
      },
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
        margin: EdgeInsets.only(bottom: 12, top: index == 0 ? 24 : 0),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            CachedNetworkImage(
              imageUrl: plugin.getImageUrl(),
              imageBuilder: (context, imageProvider) => Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  shape: BoxShape.rectangle,
                  borderRadius: BorderRadius.circular(8),
                  image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
                ),
              ),
              placeholder: (context, url) => const SizedBox(
                width: 48,
                height: 48,
                child: CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                ),
              ),
              errorWidget: (context, url, error) => const Icon(Icons.error),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.start,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    plugin.name,
                    maxLines: 1,
                    style: const TextStyle(fontWeight: FontWeight.w600, color: Colors.white, fontSize: 16),
                  ),
                  SizedBox(height: plugin.ratingAvg != null ? 4 : 0),
                  Padding(
                    padding: const EdgeInsets.only(top: 4.0),
                    child: Text(
                      plugin.description,
                      maxLines: 2,
                      style: const TextStyle(color: Colors.grey, fontSize: 14),
                    ),
                  ),
                  plugin.ratingAvg != null || plugin.installs > 0
                      ? Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.center,
                            mainAxisAlignment: MainAxisAlignment.start,
                            children: [
                              plugin.ratingAvg != null
                                  ? Row(
                                      crossAxisAlignment: CrossAxisAlignment.center,
                                      children: [
                                        Text(plugin.getRatingAvg()!),
                                        const SizedBox(width: 4),
                                        const Icon(Icons.star, color: Colors.deepPurple, size: 16),
                                        const SizedBox(width: 4),
                                        Text('(${plugin.ratingCount})'),
                                        const SizedBox(width: 16),
                                      ],
                                    )
                                  : const SizedBox(),
                              plugin.installs > 0
                                  ? Row(
                                      crossAxisAlignment: CrossAxisAlignment.center,
                                      children: [
                                        Icon(Icons.download_rounded, size: 16, color: Colors.grey.shade300),
                                        const SizedBox(width: 4),
                                        Text('${plugin.installs}'),
                                      ],
                                    )
                                  : Container(),
                            ],
                          ),
                        )
                      : Container(),
                ],
              ),
            ),
            const SizedBox(width: 16),
            provider.pluginLoading.isNotEmpty && provider.pluginLoading[index]
                ? const Padding(
                    padding: EdgeInsets.all(10),
                    child: SizedBox(
                      height: 24,
                      width: 24,
                      child: CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
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
          ],
        ),
      ),
    );
  }
}
