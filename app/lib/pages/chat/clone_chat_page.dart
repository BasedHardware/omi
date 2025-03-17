import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/home/widgets/chat_apps_dropdown_widget.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/other/temp.dart';
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
        // Set to null to chat with Omi by default
        appProvider.setSelectedChatAppId(null);
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
                const SizedBox(width: 44),
                personaProvider.isLoading || personaProvider.userPersona == null
                    ? const SizedBox(width: 44)
                    : ChatAppsDropdownWidget(mode: ChatMode.chat_clone),
                IconButton(
                  padding: const EdgeInsets.all(8.0),
                  icon: SvgPicture.asset(
                    Assets.images.icPersonaProfile.path,
                    width: 28,
                    height: 28,
                  ),
                  onPressed: () {
                    personaProvider.setRouting(PersonaProfileRouting.no_device);
                    routeToPage(context, const PersonaProfilePage(), replace: true);
                  },
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
