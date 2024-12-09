import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

class ChatAppsDropdownWidget extends StatelessWidget {
  final PageController? controller;

  ChatAppsDropdownWidget({super.key, this.controller});

  final FocusNode focusNode = FocusNode();

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
      child: Consumer<AppProvider>(builder: (context, provider, child) {
        return Padding(
          padding: const EdgeInsets.only(left: 0),
          child: provider.apps.where((p) => p.enabled).isEmpty
              ? GestureDetector(
                  onTap: () {
                    MixpanelManager().pageOpened('Chat Apps');
                    // routeToPage(context, const AppsPage(filterChatOnly: true));
                    context.read<HomeProvider>().setIndex(2);
                    controller?.animateToPage(2, duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
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
                    value: provider.getSelectedApp()?.id ?? "no_selected",
                    onChanged: (s) async {
                      if ((s == 'no_selected' && provider.apps.where((p) => p.enabled).isEmpty) || s == 'enable') {
                        // routeToPage(context, const AppsPage(filterChatOnly: true));
                        MixpanelManager().pageOpened('Chat Apps');
                        context.read<HomeProvider>().setIndex(2);
                        controller?.animateToPage(2,
                            duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
                        return;
                      }
                      if (s == null || s == provider.selectedChatAppId) return;
                      provider.setSelectedChatAppId(s);
                      await context.read<MessageProvider>().refreshMessages(dropdownSelected: true);
                      var app = provider.getSelectedApp();
                      if (context.read<MessageProvider>().messages.isEmpty) {
                        context.read<MessageProvider>().sendInitialAppMessage(app);
                      }
                    },
                    focusNode: focusNode,
                    // icon: Container(),
                    alignment: Alignment.center,
                    dropdownColor: Colors.black,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                    underline: Container(height: 0, color: Colors.transparent),
                    isExpanded: false,
                    itemHeight: 48,
                    padding: EdgeInsets.zero,
                    items: _getAppsDropdownItems(context, provider),
                  ),
                ),
        );
      }),
    );
  }

  _getAppsDropdownItems(BuildContext context, AppProvider provider) {
    var items = [
          DropdownMenuItem<String>(
            value: 'no_selected',
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Container(
                  decoration: const BoxDecoration(
                    image: DecorationImage(
                      image: AssetImage("assets/images/background.png"),
                      fit: BoxFit.cover,
                    ),
                    borderRadius: BorderRadius.all(Radius.circular(16.0)),
                  ),
                  height: 24,
                  width: 24,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      Image.asset(
                        "assets/images/herologo.png",
                        height: 16,
                        width: 16,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 10),
                Text(
                  provider.apps.where((p) => p.enabled).isEmpty ? 'Enable Apps' : 'Omi',
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                ),
                // const SizedBox(width: 40),
                // Icon(Icons.arrow_drop_down, color: Colors.white, size: 24)
              ],
            ),
          )
        ] +
        provider.apps.where((p) => p.enabled && p.worksWithChat()).map<DropdownMenuItem<String>>((App app) {
          return DropdownMenuItem<String>(
            value: app.id,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              mainAxisAlignment: MainAxisAlignment.start,
              children: [
                CachedNetworkImage(
                  imageUrl: app.getImageUrl(),
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
                  app.name.length > 18 ? '${app.name.substring(0, 18)}...' : app.name + ' ' * (18 - app.name.length),
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                )
              ],
            ),
          );
        }).toList();
    if (provider.apps.where((p) => p.enabled).isNotEmpty) {
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
