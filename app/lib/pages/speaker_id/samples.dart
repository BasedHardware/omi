import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/speech_profile.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:just_audio/just_audio.dart';

class ProfileSamples extends StatefulWidget {
  const ProfileSamples({super.key});

  @override
  State<ProfileSamples> createState() => _ProfileSamplesState();
}

class _ProfileSamplesState extends State<ProfileSamples> {
  List<String> samplesUrl = [];
  bool loading = true;
  final AudioPlayer _audioPlayer = AudioPlayer();
  int? _currentPlayingIndex;
  bool _isPlaying = false;

  @override
  void initState() {
    _init();
    _setupAudioPlayerListeners();
    super.initState();
  }

  @override
  void dispose() {
    _audioPlayer.dispose();
    super.dispose();
  }

  _init() async {
    String? url = await getUserSpeechProfile();
    if (url == null) {
      showDialog(
          context: context,
          builder: (c) => getDialog(
                context,
                () {
                  Navigator.of(context).pop();
                  Navigator.of(context).pop();
                },
                () {},
                'Unexpected error',
                'Failed to get profile samples. Please try again later.',
                okButtonText: 'Ok',
                singleButton: true,
              ));
      return;
    }
    samplesUrl.add(url);
    List<String> expandedSamples = await getExpandedProfileSamples();
    samplesUrl.addAll(expandedSamples);
    loading = false;
    setState(() {});
  }

  String _getFileNameFromUrl(String url) {
    Uri uri = Uri.parse(url);
    String fileName = uri.pathSegments.last;
    return fileName.split('.').first;
  }

  void _setupAudioPlayerListeners() {
    _audioPlayer.playerStateStream.listen((playerState) {
      if (playerState.processingState == ProcessingState.completed) {
        setState(() {
          _currentPlayingIndex = null;
          _isPlaying = false;
        });
      }
    });
  }

  Future<void> _playPause(int index) async {
    if (_currentPlayingIndex == index) {
      if (_isPlaying) {
        _audioPlayer.pause();
        _isPlaying = false;
      } else {
        _audioPlayer.play();
        _isPlaying = true;
      }
    } else {
      _audioPlayer.stop();
      await _audioPlayer.setUrl(samplesUrl[index]);
      setState(() {
        _currentPlayingIndex = index;
        _isPlaying = true;
      });
      await _audioPlayer.play();
    }
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Speech Samples'),
        backgroundColor: Theme.of(context).colorScheme.primary,
        actions: [
          IconButton(
              onPressed: () {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () => Navigator.pop(context),
                    () => Navigator.pop(context),
                    'How to take more samples?',
                    '1. Authorize Omi to store your memories audio recordings.\n2. Once you create a new memory with this settings, you can edit your transcript, and select segments to expand your speech profile.',
                    singleButton: true,
                  ),
                );
              },
              icon: const Icon(
                Icons.question_mark,
                size: 20,
              ))
        ],
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: loading
          ? const Center(
              child: CircularProgressIndicator(
              color: Colors.white,
            ))
          : ListView.builder(
              itemCount: samplesUrl.length + 1,
              itemBuilder: (context, index) {
                if (index == samplesUrl.length) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(horizontal:20, vertical: 16),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.start,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'How to take more samples?',
                          style: TextStyle(fontSize: 16),
                        ),
                        SizedBox(height: 16),
                        Text('1. Authorize Omi to store your memories audio recordings.'),
                        SizedBox(height: 8),
                        Text('2. Once you create a new memory with this settings, you will be able to edit your transcript, and select which segments include.'),
                      ],
                    ),
                  );
                }
                return Column(
                  children: [
                    ListTile(
                      leading: IconButton(
                        icon: Icon(
                          _currentPlayingIndex == index && _isPlaying ? Icons.pause : Icons.play_arrow,
                        ),
                        onPressed: () => _playPause(index),
                      ),
                      title: Text(index == 0 ? 'Speech Profile' : 'Additional Sample $index'),
                      // _getFileNameFromUrl(samplesUrl[index])
                      subtitle: FutureBuilder<Duration?>(
                        future: AudioPlayer().setUrl(samplesUrl[index]),
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
                                String name = _getFileNameFromUrl(samplesUrl[index]);
                                var parts = name.split('_segment_');
                                deleteProfileSample(parts[0], int.tryParse(parts[1])!);
                                samplesUrl.removeAt(index);
                                ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                                    content: Text(
                                  'Additional Speech Sample Removed',
                                )));
                                setState(() {});
                              },
                              icon: const Icon(Icons.delete, size: 20),
                            ),
                    ),
                    index == 0 ? SizedBox(height: 8) : const SizedBox(),
                    index == 0
                        ? Divider(
                            color: Colors.grey.shade600,
                          )
                        : const SizedBox(),
                    index == 0 ? SizedBox(height: 8) : const SizedBox(),
                  ],
                );
              },
            ),
    );
  }
}
