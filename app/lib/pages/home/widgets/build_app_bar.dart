import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/pages/home/widgets/chat_apps_dropdown_widget.dart';
import 'package:omi/pages/home/widgets/speech_language_sheet.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:provider/provider.dart';


 PreferredSizeWidget buildAppBar (BuildContext context, PageController? controller) {
return   AppBar(
      automaticallyImplyLeading: false,
      backgroundColor: Theme.of(context).colorScheme.surface,
      title: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const BatteryInfoWidget(),
          Consumer<HomeProvider>(builder: (context, provider, child) {
            if (provider.selectedIndex == 0) {
              return Consumer<ConversationProvider>(
                  builder: (context, convoProvider, child) {
                if (convoProvider.missingWalsInSeconds >= 120) {
                  return GestureDetector(
                    onTap: () {
                      routeToPage(context, const SyncPage());
                    },
                    child: Container(
                      padding: const EdgeInsets.only(left: 12),
                      child: const Icon(Icons.download,
                          color: Colors.white, size: 24),
                    ),
                  );
                } else {
                  return const SizedBox.shrink();
                }
              });
            } else {
              return const SizedBox.shrink();
            }
          }),
          Consumer<HomeProvider>(
            builder: (context, provider, child) {
              if (provider.selectedIndex == 1) {
                return ChatAppsDropdownWidget(
                  controller: controller!,
                );
              } else if (provider.selectedIndex == 2) {
                return Padding(
                  padding: EdgeInsets.only(
                      right: MediaQuery.sizeOf(context).width * 0.16),
                  child: const Text('Explore',
                      style: TextStyle(color: Colors.white, fontSize: 18)),
                );
              } else {
                return Expanded(
                  child: Row(
                    children: [
                      const Spacer(),
                      SpeechLanguageSheet(
                        recordingLanguage: provider.recordingLanguage,
                        setRecordingLanguage: (language) {
                          provider.setRecordingLanguage(language);
                          // Notify capture provider
                          if (context.mounted) {
                            context
                                .read<CaptureProvider>()
                                .onRecordProfileSettingChanged();
                          }
                        },
                        availableLanguages: provider.availableLanguages,
                      ),
                    ],
                  ),
                );
              }
            },
          ),
          Row(
            children: [
              IconButton(
                  padding: const EdgeInsets.all(8.0),
                  icon: SvgPicture.asset(
                    Assets.images.icPersonaProfile.path,
                    width: 28,
                    height: 28,
                  ),
                  onPressed: () {
                    MixpanelManager().pageOpened('Persona Profile');

                    // Set routing in provider
                    var personaProvider =
                        Provider.of<PersonaProvider>(context, listen: false);
                    personaProvider.setRouting(PersonaProfileRouting.home);

                    // Navigate
                    var homeProvider =
                        Provider.of<HomeProvider>(context, listen: false);
                    homeProvider.setIndex(3);
                    if (homeProvider.onSelectedIndexChanged != null) {
                      homeProvider.onSelectedIndexChanged!(3);
                    }
                  }),
            ],
          ),
        ],
      ),
      elevation: 0,
      centerTitle: true,
    );
}