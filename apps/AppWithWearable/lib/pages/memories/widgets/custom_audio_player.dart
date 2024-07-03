import 'dart:io';
import 'dart:math';

import 'package:audio_session/audio_session.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/svg.dart';
import 'package:just_audio/just_audio.dart';
import 'package:just_waveform/just_waveform.dart';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;
import 'package:rxdart/rxdart.dart';

enum PlayerLoadingState {
  loading,
  loaded,
  error,
}

class AudioPlayerTestPage extends StatefulWidget {
  const AudioPlayerTestPage({super.key});

  @override
  State<AudioPlayerTestPage> createState() => _AudioPlayerTestPageState();
}

class _AudioPlayerTestPageState extends State<AudioPlayerTestPage> {
  final files = ['BabyElephantWalk60.wav', 'ImperialMarch60.wav', 'PinkPanther30.wav', 'Player.mp3'];
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Audio Player Test'),
      ),
      body: ListView.separated(
        itemCount: files.length,
        padding: const EdgeInsets.all(16),
        separatorBuilder: (ctx, index) => const SizedBox(height: 16),
        itemBuilder: (ctx, index) {
          return ListTile(
            tileColor: Colors.white,
            title: Text(
              files[index],
              style: const TextStyle(color: Colors.black),
            ),
            onTap: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (ctx) => CustomAudioPlayer(
                    audioFilePath: 'assets/audios/${files[index]}',
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}

class CustomAudioPlayer extends StatefulWidget {
  const CustomAudioPlayer({super.key, required this.audioFilePath, this.isNetworkFile = false});
  final String audioFilePath;
  final bool isNetworkFile;

  @override
  State<CustomAudioPlayer> createState() => _CustomAudioPlayerState();
}

class _CustomAudioPlayerState extends State<CustomAudioPlayer> with WidgetsBindingObserver {
  final _player = AudioPlayer();
  final progressStream = BehaviorSubject<WaveformProgress>();
  var _playerLoadingState = PlayerLoadingState.loading;
  final navigatorKey = GlobalKey<NavigatorState>();
  String errorMessage = '';
  @override
  void initState() {
    super.initState();
    ambiguate(WidgetsBinding.instance)!.addObserver(this);
    SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
      statusBarColor: Colors.black,
    ));
    _init();
  }

  Future<void> _init() async {
    debugPrint('Audio File Path: ${widget.audioFilePath}');
    final session = await AudioSession.instance;
    await session.configure(const AudioSessionConfiguration.music());
    _player.playbackEventStream.listen((event) {}, onError: (Object e, StackTrace stackTrace) {
      debugPrint('A stream error occurred: $e');
    });
    try {
      await _player.setAudioSource(widget.isNetworkFile
          ? AudioSource.uri(Uri.parse(widget.audioFilePath))
          : AudioSource.asset(widget.audioFilePath));
    } on PlayerException catch (e) {
      debugPrint('PlayerException: ${e}');
      setState(() {
        _playerLoadingState = PlayerLoadingState.error;
      });
      errorMessage = "PlayerException: ${e}";
      ScaffoldMessenger.of(navigatorKey.currentContext ?? context).showSnackBar(SnackBar(content: Text(errorMessage)));
      Navigator.of(navigatorKey.currentContext ?? context).pop();
      return;
    } catch (e) {
      debugPrint('Error loading audio source: $e');
      setState(() {
        _playerLoadingState = PlayerLoadingState.error;
      });
      errorMessage = "Error loading audio source: $e";
      ScaffoldMessenger.of(navigatorKey.currentContext ?? context).showSnackBar(SnackBar(content: Text(errorMessage)));
      Navigator.of(navigatorKey.currentContext ?? context).pop();
      return;
    }

    ///read audio file from assets
    final audioFile = File(p.join((await getTemporaryDirectory()).path, widget.audioFilePath.split('/').last));
    try {
      Future<ByteData> tempFile = widget.isNetworkFile
          ? NetworkAssetBundle(Uri.parse(widget.audioFilePath)).load(widget.audioFilePath)
          : rootBundle.load(widget.audioFilePath);
      await audioFile.writeAsBytes((await tempFile).buffer.asUint8List());
      final waveFile = File(p.join((await getTemporaryDirectory()).path, 'waveform.wav'));
      JustWaveform.extract(audioInFile: audioFile, waveOutFile: waveFile)
          .listen(progressStream.add, onError: progressStream.addError);
    } catch (e) {
      setState(() {
        _playerLoadingState = PlayerLoadingState.error;
      });
      errorMessage = "Audio File Reading Error: $e";
      ScaffoldMessenger.of(navigatorKey.currentContext ?? context).showSnackBar(SnackBar(content: Text(errorMessage)));
      Navigator.of(navigatorKey.currentContext ?? context).pop();
      progressStream.addError(e);
      return;
    }
    setState(() {
      _playerLoadingState = PlayerLoadingState.loaded;
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) {
      _player.stop();
    }
  }

  @override
  void dispose() {
    ambiguate(WidgetsBinding.instance)!.removeObserver(this);
    _player.dispose();
    super.dispose();
  }

  Stream<PositionData> get _positionDataStream => Rx.combineLatest3<Duration, Duration, Duration?, PositionData>(
      _player.positionStream,
      _player.bufferedPositionStream,
      _player.durationStream,
      (position, bufferedPosition, duration) => PositionData(position, bufferedPosition, duration ?? Duration.zero));

  @override
  Widget build(BuildContext context) {
    return Material(
      key: navigatorKey,
      child: SafeArea(
        child: _showProperView(context),
      ),
    );
  }

  Widget _showProperView(BuildContext context) {
    if (PlayerLoadingState.loading == _playerLoadingState) {
      return const Center(child: CircularProgressIndicator(color: Colors.white));
    } else if (PlayerLoadingState.error == _playerLoadingState) {
      return Text(errorMessage);
    }
    return Column(
      children: [
        Container(
          alignment: Alignment.center,
          margin: const EdgeInsets.all(16.0),
          child: Container(
            height: 150.0,
            padding: const EdgeInsets.symmetric(horizontal: 2),
            decoration: const BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.all(Radius.circular(4.0)),
              boxShadow: [
                BoxShadow(
                  color: Colors.black26,
                  offset: Offset(0.0, 2.0),
                  blurRadius: 2.0,
                ),
              ],
            ),
            width: double.maxFinite,
            child: StreamBuilder<WaveformProgress>(
              stream: progressStream,
              builder: (context, snapshot) {
                if (snapshot.hasError) {
                  return Center(
                    child: Text(
                      'Error: ${snapshot.error}',
                      style: Theme.of(context).textTheme.titleLarge,
                      textAlign: TextAlign.center,
                    ),
                  );
                }
                final progress = snapshot.data?.progress ?? 0.0;
                final waveform = snapshot.data?.waveform;
                if (waveform == null) {
                  return Center(
                    child: Text(
                      '${(100 * progress).toInt()}%',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  );
                }
                return AudioWaveformWidget(
                  waveform: waveform,
                  start: Duration.zero,
                  duration: waveform.duration,
                  positionDataStream: _positionDataStream,
                  player: _player,
                );
              },
            ),
          ),
        ),
        StreamBuilder(
          stream: _positionDataStream,
          builder: (context, AsyncSnapshot snapshot) {
            if (snapshot.hasError) {
              return Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16.0),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      RegExp(r'((^0*[1-9]\d*:)?\d{2}:\d{2})\.\d+$')
                              .firstMatch("${const Duration(seconds: 0)}")
                              ?.group(1) ??
                          "${_player.position}",
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              );
            } else if (snapshot.connectionState == ConnectionState.waiting) {
              return Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16.0),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      RegExp(r'((^0*[1-9]\d*:)?\d{2}:\d{2})\.\d+$')
                              .firstMatch("${const Duration(seconds: 0)}")
                              ?.group(1) ??
                          "${_player.position}",
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              );
            }
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    RegExp(r'((^0*[1-9]\d*:)?\d{2}:\d{2})\.\d+$').firstMatch("${_player.position}")?.group(1) ??
                        "${Duration.zero}",
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  Text(
                    RegExp(r'((^0*[1-9]\d*:)?\d{2}:\d{2})\.\d+$')
                            .firstMatch("${_player.bufferedPosition - _player.position}")
                            ?.group(1) ??
                        "${(Duration.zero)}",
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            );
          },
        ),
        ControlButtons(_player),
      ],
    );
  }
}

/// Displays the play/pause button and volume/speed sliders.
class ControlButtons extends StatelessWidget {
  final AudioPlayer player;

  const ControlButtons(this.player, {super.key});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Opens volume slider dialog
        IconButton(
          icon: SvgPicture.asset(
            'assets/images/replay_15.svg',
            colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
          ),
          iconSize: 48.0,
          onPressed: () => player.seek(
            Duration(
              seconds: player.position.inSeconds <= 15 ? 0 : player.position.inSeconds - 15,
            ),
          ),
        ),

        StreamBuilder<PlayerState>(
          stream: player.playerStateStream,
          builder: (context, snapshot) {
            final playerState = snapshot.data;
            final processingState = playerState?.processingState;
            final playing = playerState?.playing;
            if (playing != true) {
              return IconButton(
                icon: const Icon(Icons.play_arrow),
                iconSize: 64.0,
                onPressed: player.play,
              );
            } else if (processingState != ProcessingState.completed) {
              return IconButton(
                icon: const Icon(Icons.pause),
                iconSize: 64.0,
                onPressed: player.pause,
              );
            } else {
              return IconButton(
                icon: const Icon(Icons.replay),
                iconSize: 64.0,
                onPressed: () => player.seek(Duration.zero),
              );
            }
          },
        ),
        IconButton(
          icon: SvgPicture.asset(
            'assets/images/forward_15.svg',
            colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
          ),
          iconSize: 48.0,
          onPressed: () => player.seek(
            Duration(
              seconds: player.position.inSeconds >= player.duration!.inSeconds - 15
                  ? player.bufferedPosition.inSeconds
                  : player.position.inSeconds + 15,
            ),
          ),
        ),
      ],
    );
  }
}

class PositionData {
  final Duration position;
  final Duration bufferedPosition;
  final Duration duration;

  PositionData(this.position, this.bufferedPosition, this.duration);
}

T? ambiguate<T>(T? value) => value;

class AudioWaveformWidget extends StatefulWidget {
  final Color waveColor;
  final double scale;
  final double strokeWidth;
  final double pixelsPerStep;
  final Waveform waveform;
  final Duration start;
  final Duration duration;
  final Stream<PositionData> positionDataStream;
  final AudioPlayer player;

  const AudioWaveformWidget({
    super.key,
    required this.waveform,
    required this.start,
    required this.duration,
    this.waveColor = Colors.black,
    this.scale = 4.0,
    this.strokeWidth = 1.0,
    this.pixelsPerStep = 3.0,
    required this.positionDataStream,
    required this.player,
  });

  @override
  _AudioWaveformState createState() => _AudioWaveformState();
}

class _AudioWaveformState extends State<AudioWaveformWidget> {
  @override
  Widget build(BuildContext context) {
    return StreamBuilder<PositionData>(
      stream: widget.positionDataStream,
      builder: (context, snapshot) {
        final positionData = snapshot.data;
        final position = positionData?.position ?? Duration.zero;
        final duration = positionData?.duration ?? Duration.zero;

        final startCalculate = (position.inMilliseconds < 5);
        final endCalculate = (position.inMilliseconds > duration.inMilliseconds - 5);
        return Stack(
          fit: StackFit.expand,
          children: [
            ClipRect(
              child: CustomPaint(
                painter: AudioWaveformPainter(
                  waveColor: widget.waveColor,
                  waveform: widget.waveform,
                  start: widget.start,
                  duration: widget.duration,
                  scale: widget.scale,
                  strokeWidth: widget.strokeWidth,
                  pixelsPerStep: widget.pixelsPerStep,
                  currentPoint: position,
                ),
              ),
            ),
            SliderTheme(
              data: SliderTheme.of(context).copyWith(
                thumbColor: Colors.red,
                thumbShape: VerticalSliderForAudio(
                    height: 150,
                    position: startCalculate
                        ? 0
                        : endCalculate
                            ? 1
                            : 2),
                activeTrackColor: Colors.transparent,
                inactiveTrackColor: Colors.transparent,
                overlayColor: Colors.red.shade200,
                overlayShape: SquareThumbShape(
                  width: startCalculate || endCalculate ? 0 : 8,
                  height: 150,
                ),
              ),
              child: Slider(
                min: 0.0,
                max: duration.inMilliseconds.toDouble(),
                value: min(position.inMilliseconds.toDouble(), duration.inMilliseconds.toDouble()),
                onChanged: (value) {
                  widget.player.seek(Duration(milliseconds: value.toInt()));
                  setState(() {});
                },
                onChangeEnd: (value) => widget.player.seek,
              ),
            ),
          ],
        );
      },
    );
  }
}

class SquareThumbShape extends SliderComponentShape {
  final double width;
  final double height;

  SquareThumbShape({this.width = 12.0, this.height = 8.0});

  @override
  Size getPreferredSize(bool isEnabled, bool isDiscrete) {
    return Size(width, height);
  }

  @override
  void paint(
    PaintingContext context,
    Offset center, {
    required Animation<double> activationAnimation,
    required Animation<double> enableAnimation,
    required bool isDiscrete,
    required TextPainter labelPainter,
    required RenderBox parentBox,
    required SliderThemeData sliderTheme,
    required TextDirection textDirection,
    required double value,
    required double textScaleFactor,
    required Size sizeWithOverflow,
  }) {
    final Canvas canvas = context.canvas;

    final Paint paint = Paint()
      ..color = Colors.red.shade100
      ..style = PaintingStyle.fill;

    final RRect thumbRect = RRect.fromRectAndRadius(
      Rect.fromCenter(center: center, width: width, height: height),
      const Radius.circular(8),
    );

    canvas.drawRRect(thumbRect, paint);
  }
}

class VerticalSliderForAudio extends SliderComponentShape {
  final double height;
  final int position;
  VerticalSliderForAudio({required this.height, this.position = 0});
  @override
  Size getPreferredSize(bool isEnabled, bool isDiscrete) => Size.zero;

  @override
  void paint(
    PaintingContext context,
    Offset center, {
    required Animation<double> activationAnimation,
    required Animation<double> enableAnimation,
    required bool isDiscrete,
    required TextPainter labelPainter,
    required RenderBox parentBox,
    required SliderThemeData sliderTheme,
    required TextDirection textDirection,
    required double value,
    required double textScaleFactor,
    required Size sizeWithOverflow,
  }) {
    final canvas = context.canvas;
    final paint = Paint()..color = Colors.red;
    canvas.drawRRect(
      RRect.fromRectAndCorners(
        Rect.fromCenter(center: center, width: 4, height: height),
        topLeft: Radius.circular(position == 0 ? 16 : 4),
        topRight: Radius.circular(position == 1 ? 16 : 4),
        bottomLeft: Radius.circular(position == 0 ? 16 : 4),
        bottomRight: Radius.circular(position == 1 ? 16 : 4),
      ),
      paint,
    );
  }
}

class AudioWaveformPainter extends CustomPainter {
  final double scale;
  final double strokeWidth;
  final double pixelsPerStep;
  final Paint wavePaint;
  final Waveform waveform;
  final Duration start;
  final Duration duration;
  final Duration currentPoint;

  AudioWaveformPainter({
    required this.waveform,
    required this.start,
    required this.duration,
    Color waveColor = Colors.black,
    required this.scale,
    required this.strokeWidth,
    required this.pixelsPerStep,
    required this.currentPoint,
  }) : wavePaint = Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = strokeWidth
          ..strokeCap = StrokeCap.round
          ..color = waveColor;

  @override
  void paint(Canvas canvas, Size size) {
    if (duration == Duration.zero) return;

    double width = size.width;
    double height = size.height;

    final waveformPixelsPerWindow = waveform.positionToPixel(duration).toInt();
    final waveformPixelsPerDevicePixel = waveformPixelsPerWindow / width;
    final waveformPixelsPerStep = waveformPixelsPerDevicePixel * pixelsPerStep;
    final sampleOffset = waveform.positionToPixel(start);
    final sampleStart = -sampleOffset % waveformPixelsPerStep;
    for (var i = sampleStart.toDouble(); i <= waveformPixelsPerWindow + 1.0; i += waveformPixelsPerStep) {
      wavePaint.color = i < currentPoint.inSeconds * 100 ? Colors.red : Colors.black;
      final sampleIdx = (sampleOffset + i).toInt();
      final x = i / waveformPixelsPerDevicePixel;
      final minY = normalise(waveform.getPixelMin(sampleIdx), height);
      final maxY = normalise(waveform.getPixelMax(sampleIdx), height);
      canvas.drawLine(
        Offset(x + strokeWidth / 2, max(strokeWidth * 0.75, minY)),
        Offset(x + strokeWidth / 2, min(height - strokeWidth * 0.75, maxY)),
        wavePaint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant AudioWaveformPainter oldDelegate) {
    return false;
  }

  double normalise(int s, double height) {
    if (waveform.flags == 0) {
      final y = 32768 + (scale * s).clamp(-32768.0, 32767.0).toDouble();
      return height - 1 - y * height / 65536;
    } else {
      final y = 128 + (scale * s).clamp(-128.0, 127.0).toDouble();
      return height - 1 - y * height / 256;
    }
  }
}
