// import 'dart:async';
// import 'dart:io';
//
// import 'package:flutter/material.dart';
// import 'package:friend_private/backend/http/api/speech_profile.dart';
// import 'package:friend_private/backend/preferences.dart';
// import 'package:friend_private/backend/schema/bt_device.dart';
// import 'package:friend_private/backend/schema/sample.dart';
// import 'package:friend_private/utils/audio/wav_bytes.dart';
// import 'package:friend_private/utils/ble/communication.dart';
// import 'package:tuple/tuple.dart';
//
// class RecordSampleTab extends StatefulWidget {
//   final BTDeviceStruct? btDevice;
//   final SpeakerIdSample sample;
//   final int sampleIdx;
//   final int totalSamples;
//   final VoidCallback onRecordCompleted;
//   final VoidCallback goNext;
//
//   const RecordSampleTab({
//     super.key,
//     required this.sample,
//     required this.btDevice,
//     required this.sampleIdx,
//     required this.totalSamples,
//     required this.onRecordCompleted,
//     required this.goNext,
//   });
//
//   @override
//   State<RecordSampleTab> createState() => _RecordSampleTabState();
// }
//
// class _RecordSampleTabState extends State<RecordSampleTab> with TickerProviderStateMixin {
//   StreamSubscription? audioBytesStream;
//   WavBytesUtil? audioStorage;
//   bool recording = false;
//   bool speechRecorded = false;
//   late AnimationController _controller;
//   late Animation<double> _animation;
//
//   bool uploadingSample = false;
//
//   changeLoadingState() => setState(() => uploadingSample = !uploadingSample);
//
//   @override
//   void initState() {
//     _controller = AnimationController(
//       duration: const Duration(milliseconds: 1000),
//       vsync: this,
//     )..repeat(reverse: true);
//     _animation = Tween<double>(begin: 1.1, end: 1.5).animate(_controller);
//     super.initState();
//   }
//
//   Future<void> startRecording() async {
//     audioBytesStream?.cancel();
//     if (widget.btDevice == null) return;
//     audioStorage = WavBytesUtil(codec: await getAudioCodec(widget.btDevice!.id));
//
//     audioBytesStream = await getBleAudioBytesListener(widget.btDevice!.id, onAudioBytesReceived: (List<int> value) {
//       if (value.isEmpty) return;
//       audioStorage!.storeFramePacket(value);
//     });
//
//     setState(() {
//       recording = true;
//       speechRecorded = false;
//     });
//   }
//
//   Future<void> confirmRecording() async {
//     // TODO: how to upload nonsense uploads?
//     // - people who say it too fast
//     // - people who spend a lot of time
//     // - people who don't say anything
//     if (!(audioStorage?.hasFrames() ?? false)) return;
//     changeLoadingState();
//     setState(() {
//       recording = false;
//       speechRecorded = true;
//     });
//     widget.onRecordCompleted();
//
//     await Future.delayed(const Duration(seconds: 2)); // wait for bytes streaming to stream all
//     audioBytesStream?.cancel();
//     Tuple2<File, List<List<int>>> file = await audioStorage!.createWavFile(filename: '${widget.sample.id}.wav');
//     changeLoadingState();
//     await uploadSample(file.item1); // optimistic request
//     // TODO: handle failures + url: null, retry sample
//   }
//
//   Future<void> cancelRecording() async {
//     audioBytesStream?.cancel();
//     audioStorage?.clearAudioBytes();
//     setState(() {
//       recording = false;
//       speechRecorded = false;
//       // bucket = List.filled(40000, 0).toList(growable: true);
//     });
//   }
//
//   listenRecording() async {}
//
//   @override
//   void dispose() {
//     audioBytesStream?.cancel();
//     audioStorage?.clearAudioBytes();
//     _controller.dispose();
//     super.dispose();
//   }
//
//   @override
//   Widget build(BuildContext context) {
//     // int seconds = (audioStorage?.audioBytes.length ?? 0) ~/ 8000;
//     return Column(
//       mainAxisAlignment: MainAxisAlignment.spaceBetween,
//       children: [
//         const SizedBox(height: 32),
//         Center(
//           child: Text(
//             'Sample: ${widget.sampleIdx + 1}/${widget.totalSamples}',
//             style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
//           ),
//         ),
//         const SizedBox(height: 32),
//         Padding(
//           padding: const EdgeInsets.symmetric(horizontal: 32.0),
//           child: Center(
//             child: Text(
//               widget.sample.phrase,
//               style: const TextStyle(color: Colors.white, fontSize: 40, fontWeight: FontWeight.w500),
//               textAlign: TextAlign.center,
//             ),
//           ),
//         ),
//         SizedBox(
//           height: 200,
//           width: 200,
//           child: Center(
//             child: Stack(
//               alignment: Alignment.center,
//               children: [
//                 if (recording)
//                   AnimatedBuilder(
//                     animation: _animation,
//                     builder: (context, child) {
//                       return Container(
//                         height: 88 * _animation.value,
//                         width: 88 * _animation.value,
//                         decoration: BoxDecoration(
//                           shape: BoxShape.circle,
//                           gradient: RadialGradient(
//                             colors: [Colors.white, Colors.grey.shade900],
//                             stops: const [0.6, 1],
//                           ),
//                         ),
//                       );
//                     },
//                   ),
//                 Container(
//                   height: 88,
//                   width: 88,
//                   decoration: BoxDecoration(
//                     color: Colors.grey.shade900,
//                     shape: BoxShape.circle,
//                   ),
//                   child: !speechRecorded
//                       ? IconButton(
//                           onPressed: recording ? confirmRecording : startRecording,
//                           icon: const Icon(Icons.mic, color: Colors.white, size: 48),
//                         )
//                       : uploadingSample
//                           ? const Center(
//                               child: SizedBox(
//                                 height: 24,
//                                 width: 24,
//                                 child: CircularProgressIndicator(
//                                   color: Colors.white,
//                                 ),
//                               ),
//                             )
//                           : IconButton(
//                               onPressed: widget.goNext,
//                               icon: const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 48),
//                             ),
//                 ),
//               ],
//             ),
//           ),
//         ),
//         const SizedBox(height: 32),
//       ],
//     );
//   }
// }
