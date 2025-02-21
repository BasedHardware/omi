import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/chat/page.dart';
import 'package:friend_private/pages/home/widgets/chat_apps_dropdown_widget.dart';
import 'package:friend_private/pages/persona/persona_profile.dart';
import 'package:friend_private/pages/persona/persona_provider.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';

class CloneChatPage extends StatefulWidget {
  const CloneChatPage({
    super.key,
  });

  @override
  State<CloneChatPage> createState() => CloneChatPageState();
}

class CloneChatPageState extends State<CloneChatPage> {
  @override
  void initState() {
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      final provider = Provider.of<PersonaProvider>(context, listen: false);
      await provider.getVerifiedUserPersona();
      if (provider.userPersona != null) {
        App selectedApp = provider.userPersona!;

        var appProvider = Provider.of<AppProvider>(context, listen: false);
        SharedPreferencesUtil().appsList = [selectedApp];
        appProvider.setApps();
        appProvider.setSelectedChatAppId(selectedApp.id);
        if (!selectedApp.enabled) {
          await appProvider.toggleApp(selectedApp.id, true, null);
        }

        var messageProvider = Provider.of<MessageProvider>(context, listen: false);
        await messageProvider.refreshMessages();
        if (messageProvider.messages.isEmpty) {
          messageProvider.sendInitialAppMessage(selectedApp);
        }
      }
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer3<MessageProvider, ConnectivityProvider, PersonaProvider>(
      builder: (context, provider, connectivityProvider, personaProvider, child) {
        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            automaticallyImplyLeading: false,
            backgroundColor: Theme.of(context).colorScheme.surface,
            title: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                GestureDetector(
                    child: SizedBox(
                      width: 44,
                      height: 44,
                      child: Padding(
                        padding: const EdgeInsets.all(0.0),
                        child: SvgPicture.asset('assets/images/ic_clone_plus.svg'),
                      ),
                    ),
                    onTap: () {
                      routeToPage(context, const PersonaProfilePage(), replace: true);
                    }),
                personaProvider.isLoading || personaProvider.userPersona == null
                    ? const SizedBox(width: 44)
                    : ChatAppsDropdownWidget(mode: ChatMode.chat_clone),
                const SizedBox(
                  width: 44,
                ),
              ],
            ),
          ),
          body: personaProvider.isLoading || personaProvider.userPersona == null
              ? const Center(
                  child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation(Colors.white),
                  ),
                )
              : GestureDetector(
                  onTap: () {
                    // Hide keyboard when tapping outside
                    FocusScope.of(context).unfocus();
                  },
                  child: const ChatPage(isPivotBottom: true),
                ),
        );
      },
    );
  }
}
