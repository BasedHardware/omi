import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:just_audio/just_audio.dart';

class UserSpeechSamplesProvider extends BaseProvider {
  List<String> samplesUrl = [];
  final AudioPlayer _audioPlayer = AudioPlayer();
  int? currentPlayingIndex;
  bool isPlaying = false;

  @override
  void dispose() {
    _audioPlayer.dispose();
    super.dispose();
  }

  init() async {
    loading = true;
    notifyListeners();
    String? url = await getUserSpeechProfile();
    if (url == null) {
      // showDialog(
      //   context: context,
      //   builder: (c) => getDialog(
      //     context,
      //     () {
      //       Navigator.of(context).pop();
      //       Navigator.of(context).pop();
      //     },
      //     () {},
      //     'Unexpected error',
      //     'Failed to get profile samples. Please try again later.',
      //     okButtonText: 'Ok',
      //     singleButton: true,
      //   ),
      // );
      loading = false;
      return;
    }
    samplesUrl.add(url);
    List<String> expandedSamples = await getExpandedProfileSamples();
    samplesUrl.addAll(expandedSamples);
    loading = false;
    notifyListeners();
  }

  String getFileNameFromUrl(String url) {
    Uri uri = Uri.parse(url);
    String fileName = uri.pathSegments.last;
    return fileName.split('.').first;
  }

  void setupAudioPlayerListeners() {
    _audioPlayer.playerStateStream.listen((playerState) {
      if (playerState.processingState == ProcessingState.completed) {
        currentPlayingIndex = null;
        isPlaying = false;
        notifyListeners();
      }
    });
  }

  Future<void> playPause(int index) async {
    if (currentPlayingIndex == index) {
      if (isPlaying) {
        _audioPlayer.pause();
        isPlaying = false;
      } else {
        _audioPlayer.play();
        isPlaying = true;
      }
    } else {
      _audioPlayer.stop();
      await _audioPlayer.setUrl(samplesUrl[index]);
      currentPlayingIndex = index;
      isPlaying = true;
      notifyListeners();
      await _audioPlayer.play();
    }
    notifyListeners();
  }
}
