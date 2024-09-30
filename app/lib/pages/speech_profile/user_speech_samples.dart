import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/speech_profile.dart';
import 'package:friend_private/providers/user_speech_samples_provider.dart';
import 'package:friend_private/widgets/extensions/functions.dart';
import 'package:just_audio/just_audio.dart';
import 'package:provider/provider.dart';

class UserSpeechSamples extends StatelessWidget {
  const UserSpeechSamples({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (context) => UserSpeechSamplesProvider(),
      child: const UserSpeechSamplesView(),
    );
  }
}

class UserSpeechSamplesView extends StatefulWidget {
  const UserSpeechSamplesView({super.key});

  @override
  State<UserSpeechSamplesView> createState() => _UserSpeechSamplesState();
}

class _UserSpeechSamplesState extends State<UserSpeechSamplesView> {
  @override
  void initState() {
    () {
      context.read<UserSpeechSamplesProvider>().init();
      context.read<UserSpeechSamplesProvider>().setupAudioPlayerListeners();
    }.withPostFrameCallback();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<UserSpeechSamplesProvider>(
      builder: (context, provider, child) {
        return Scaffold(
          appBar: AppBar(
            title: const Text('Speech Samples'),
            backgroundColor: Theme.of(context).colorScheme.primary,
            // actions: [
            //   IconButton(
            //       onPressed: () {
            //         showDialog(
            //           context: context,
            //           builder: (c) => getDialog(
            //             context,
            //             () => Navigator.pop(context),
            //             () => Navigator.pop(context),
            //             'How to take more samples?',
            //             '1. Authorize Omi to store your memories audio recordings.\n2. Once you create a new memory with this settings, you can edit your transcript, and select segments to expand your speech profile.',
            //             singleButton: true,
            //           ),
            //         );
            //       },
            //       icon: const Icon(
            //         Icons.question_mark,
            //         size: 20,
            //       ))
            // ],
          ),
          backgroundColor: Theme.of(context).colorScheme.primary,
          body: provider.loading
              ? const Center(
                  child: CircularProgressIndicator(
                  color: Colors.white,
                ))
              : ListView.builder(
                  itemCount: provider.samplesUrl.length,
                  itemBuilder: (context, index) {
                    // if (index == provider.samplesUrl.length) {
                    //   return const Padding(
                    //     padding: EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                    //     child: Column(
                    //       mainAxisAlignment: MainAxisAlignment.start,
                    //       crossAxisAlignment: CrossAxisAlignment.start,
                    //       children: [
                    //         Text(
                    //           'How to take more samples?',
                    //           style: TextStyle(fontSize: 16),
                    //         ),
                    //         SizedBox(height: 16),
                    //         Text('1. Authorize Omi to store your memories audio recordings.'),
                    //         SizedBox(height: 8),
                    //         Text(
                    //             '2. Once you create a new memory with this settings, you will be able to edit your transcript, and select which segments include.'),
                    //       ],
                    //     ),
                    //   );
                    // }
                    return Column(
                      children: [
                        ListTile(
                          leading: IconButton(
                            icon: Icon(
                              provider.currentPlayingIndex == index && provider.isPlaying
                                  ? Icons.pause
                                  : Icons.play_arrow,
                            ),
                            onPressed: () => provider.playPause(index),
                          ),
                          title: Text(index == 0 ? 'Speech Profile' : 'Additional Sample $index'),
                          // _getFileNameFromUrl(samplesUrl[index])
                          subtitle: FutureBuilder<Duration?>(
                            future: AudioPlayer().setUrl(provider.samplesUrl[index]),
                            builder: (context, snapshot) {
                              if (snapshot.hasData) {
                                return Text('Duration: ${snapshot.data!.inSeconds} seconds');
                              } else {
                                return const Text('Loading duration...');
                              }
                            },
                          ),
                          // TODO: view memory source and segment on tap
                          trailing: index == 0
                              ? const SizedBox()
                              : IconButton(
                                  onPressed: () {
                                    String name = provider.getFileNameFromUrl(provider.samplesUrl[index]);
                                    var parts = name.split('_segment_');
                                    deleteProfileSample(parts[0], int.tryParse(parts[1])!);
                                    provider.samplesUrl.removeAt(index);
                                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                                        content: Text(
                                      'Additional Speech Sample Removed',
                                    )));
                                    setState(() {});
                                  },
                                  icon: const Icon(Icons.delete, size: 20),
                                ),
                        ),
                        index == 0 ? const SizedBox(height: 8) : const SizedBox(),
                        index == 0
                            ? Divider(
                                color: Colors.grey.shade600,
                              )
                            : const SizedBox(),
                        index == 0 ? const SizedBox(height: 8) : const SizedBox(),
                      ],
                    );
                  },
                ),
        );
      },
    );
  }
}
