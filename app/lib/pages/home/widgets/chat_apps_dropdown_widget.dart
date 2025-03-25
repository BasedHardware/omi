import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:provider/provider.dart';

enum ChatMode { chat, chat_clone }

class ChatAppsDropdownWidget extends StatelessWidget {
  final PageController? controller;
  final ChatMode mode;

  ChatAppsDropdownWidget({super.key, this.controller, this.mode = ChatMode.chat});

  final FocusNode focusNode = FocusNode();

  @override
  Widget build(BuildContext context) {
    return Selector<HomeProvider, bool>(
      selector: (context, state) => state.selectedIndex == 1,
      builder: (context, isChatPage, child) {
        if (mode == ChatMode.chat && !isChatPage) {
          return const SizedBox(
            width: 16,
          );
        }
        return child!;
      },
      child: Consumer<AppProvider>(builder: (context, provider, child) {
        var selectedApp = provider.apps.firstWhereOrNull((app) => app.id == provider.selectedChatAppId);
        return Padding(
          padding: const EdgeInsets.only(left: 0),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: PopupMenuButton<String>(
              iconSize: 164,
              icon: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisAlignment: MainAxisAlignment.center,
                mainAxisSize: MainAxisSize.max,
                children: [
                  selectedApp != null ? _getAppAvatar(selectedApp) : _getOmiAvatar(),
                  const SizedBox(width: 8),
                  Container(
                    constraints: const BoxConstraints(
                      maxWidth: 100,
                    ),
                    child: Text(
                      selectedApp != null ? selectedApp.getName() : "Omi",
                      style: const TextStyle(color: Colors.white, fontSize: 16),
                      overflow: TextOverflow.fade,
                    ),
                  ),
                  const SizedBox(width: 8),
                  const SizedBox(
                    width: 24,
                    child: Icon(Icons.keyboard_arrow_down, color: Colors.white60, size: 16),
                  ),
                ],
              ),
              constraints: const BoxConstraints(
                minWidth: 250.0,
                maxWidth: 250.0,
                maxHeight: 350.0,
              ),
              offset:
                  Offset((MediaQuery.sizeOf(context).width - 250) / 2 / MediaQuery.devicePixelRatioOf(context), 114),
              shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(16))),
              onSelected: (String? val) async {
                if (val == null || val == provider.selectedChatAppId) {
                  return;
                }

                // clear chat
                if (val == 'clear_chat') {
                  showDialog(
                    context: context,
                    builder: (ctx) {
                      return getDialog(context, () {
                        Navigator.of(context).pop();
                      }, () {
                        context.read<MessageProvider>().clearChat();
                        Navigator.of(context).pop();
                      }, "Clear Chat?", "Are you sure you want to clear the chat? This action cannot be undone.");
                    },
                  );
                  return;
                }

                // enable apps
                if (val == 'enable') {
                  MixpanelManager().pageOpened('Chat Apps');
                  context.read<HomeProvider>().setIndex(2);
                  controller?.animateToPage(2, duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
                  return;
                }

                // select app by id
                provider.setSelectedChatAppId(val);
                await context.read<MessageProvider>().refreshMessages(dropdownSelected: true);
                var app = provider.getSelectedApp();
                if (context.read<MessageProvider>().messages.isEmpty) {
                  context.read<MessageProvider>().sendInitialAppMessage(app);
                }
              },
              itemBuilder: (BuildContext context) {
                return _getAppsDropdownItems(context, provider);
              },
              color: Colors.grey.shade900,
            ),
          ),
        );
      }),
    );
  }

  _getAppAvatar(App app) {
    return CachedNetworkImage(
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
    );
  }

  _getOmiAvatar() {
    return Container(
      decoration: BoxDecoration(
        image: DecorationImage(
          image: AssetImage(Assets.images.background.path),
          fit: BoxFit.cover,
        ),
        borderRadius: const BorderRadius.all(Radius.circular(16.0)),
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
    );
  }

  List<PopupMenuItem<String>> _getAppsDropdownItems(BuildContext context, AppProvider provider) {
    return mode == ChatMode.chat_clone ? _getCloneChatDropdownItems(provider) : _getChatDropdownItems(provider);
  }

  List<PopupMenuItem<String>> _getCloneChatDropdownItems(AppProvider provider) {
    var selectedApp = provider.apps.firstWhereOrNull((app) => app.id == provider.selectedChatAppId);
    return [
      const PopupMenuItem<String>(
        height: 40,
        value: 'clear_chat',
        child: Padding(
          padding: EdgeInsets.only(left: 32),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Clear Chat', style: TextStyle(color: Colors.redAccent, fontSize: 16)),
              SizedBox(
                width: 24,
                child: Icon(Icons.delete, color: Colors.redAccent, size: 16),
              ),
            ],
          ),
        ),
      ),
      const PopupMenuItem<String>(
        height: 1,
        child: Divider(height: 1),
      ),
      // Add Omi option to the dropdown
      PopupMenuItem<String>(
        height: 40,
        value: 'no_selected',
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            _getOmiAvatar(),
            const SizedBox(width: 10),
            Expanded(
              child: Container(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      "Omi",
                      style: TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                    ),
                    selectedApp == null
                        ? const SizedBox(
                            width: 24,
                            child: Icon(Icons.check, color: Colors.white60, size: 16),
                          )
                        : const SizedBox.shrink(),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
      ...provider.apps.where((p) => p.enabled && p.worksWithChat()).map<PopupMenuItem<String>>((App app) {
        return PopupMenuItem<String>(
          height: 40,
          value: app.id,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            mainAxisAlignment: MainAxisAlignment.start,
            children: [
              _getAppAvatar(app),
              const SizedBox(width: 8),
              Expanded(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        overflow: TextOverflow.fade,
                        app.getName(),
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                      ),
                    ),
                    selectedApp?.id == app.id
                        ? const SizedBox(
                            width: 24,
                            child: Icon(Icons.check, color: Colors.white60, size: 16),
                          )
                        : const SizedBox.shrink(),
                  ],
                ),
              ),
            ],
          ),
        );
      }).toList(),
    ];
  }

  List<PopupMenuItem<String>> _getChatDropdownItems(AppProvider provider) {
    var selectedApp = provider.apps.firstWhereOrNull((app) => app.id == provider.selectedChatAppId);
    return [
      const PopupMenuItem<String>(
        height: 40,
        value: 'clear_chat',
        child: Padding(
          padding: EdgeInsets.only(left: 32),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Clear Chat', style: TextStyle(color: Colors.redAccent, fontSize: 16)),
              SizedBox(
                width: 24,
                child: Icon(Icons.delete, color: Colors.redAccent, size: 16),
              ),
            ],
          ),
        ),
      ),
      const PopupMenuItem<String>(
        height: 1,
        child: Divider(height: 1),
      ),
      PopupMenuItem<String>(
        value: 'enable',
        height: 40,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          mainAxisAlignment: MainAxisAlignment.start,
          mainAxisSize: MainAxisSize.max,
          children: [
            const SizedBox(
              width: 24,
              child: Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Container(
                child: const Row(
                  mainAxisSize: MainAxisSize.max,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Enable Apps', style: TextStyle(color: Colors.white, fontSize: 16)),
                    SizedBox(
                      width: 24,
                      child: Icon(Icons.apps, color: Colors.white60, size: 16),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
      const PopupMenuItem<String>(
        height: 1,
        child: Divider(height: 1),
      ),
      PopupMenuItem<String>(
        height: 40,
        value: 'no_selected',
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            _getOmiAvatar(),
            const SizedBox(width: 10),
            Expanded(
              child: Container(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      "Omi",
                      style: TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                    ),
                    selectedApp == null
                        ? const SizedBox(
                            width: 24,
                            child: Icon(Icons.check, color: Colors.white60, size: 16),
                          )
                        : const SizedBox.shrink(),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
      ...provider.apps.where((p) => p.enabled && p.worksWithChat()).map<PopupMenuItem<String>>((App app) {
        return PopupMenuItem<String>(
          height: 40,
          value: app.id,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            mainAxisAlignment: MainAxisAlignment.start,
            children: [
              _getAppAvatar(app),
              const SizedBox(width: 8),
              Expanded(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        overflow: TextOverflow.fade,
                        app.getName(),
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                      ),
                    ),
                    selectedApp?.id == app.id
                        ? const SizedBox(
                            width: 24,
                            child: Icon(Icons.check, color: Colors.white60, size: 16),
                          )
                        : const SizedBox.shrink(),
                  ],
                ),
              ),
            ],
          ),
        );
      }).toList(),
    ];
  }
}
