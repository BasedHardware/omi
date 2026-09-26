import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';

class FakeVoiceIO implements GuidedVoiceIO {
  void Function(Uint8List)? audio;
  final remembered = <String>[];
  final goals = <String>[];
  final goalKeys = <String>[];
  bool goalSuccess = true;
  bool unavailable = false;
  int startCount = 0;
  Completer<String>? pendingTranscription;
  final uploads = <Uint8List>[];
  String text = 'My name is Robin and I build bicycles.';
  bool uploadSuccess = true;
  bool memorySuccess = true;
  bool transcriptionFails = false;
  int stopCount = 0;
  Completer<void>? preparing;
  Completer<bool>? pendingUpload;
  // Holds the memory save open so a test can observe the review screen while the
  // voice profile is already saved and the answers are still uploading.
  Completer<void>? pendingMemory;
  @override
  bool get livePreview => false;
  @override
  Future<void> prepare() async {
    await preparing?.future;
  }

  @override
  Future<void> start(void Function(Uint8List) callback, VoidCallback interrupted) async {
    startCount++;
    audio = callback;
  }

  @override
  Future<void> stop() async {
    stopCount++;
  }

  @override
  Future<String> transcribe(Uint8List pcm) async {
    if (transcriptionFails) throw StateError('offline');
    return pendingTranscription == null ? text : await pendingTranscription!.future;
  }

  @override
  Future<bool> enroll(Uint8List pcm) async {
    if (unavailable) throw VoiceEnrollmentUnavailable();
    uploads.add(pcm);
    if (pendingUpload != null) return await pendingUpload!.future;
    return uploadSuccess;
  }

  @override
  Future<bool> remember(String text) async {
    await pendingMemory?.future;
    if (!memorySuccess) return false;
    remembered.add(text);
    return true;
  }

  @override
  Future<bool> saveGoal(String text, String idempotencyKey) async {
    goalKeys.add(idempotencyKey);
    if (!goalSuccess) return false;
    goals.add(text);
    return true;
  }

  @override
  Future<void> close() => stop();
  void speak([int seconds = 6]) => audio!(Uint8List(32000 * seconds));
}

void main() {
  Future<void> completeAnswers(FakeVoiceIO io, GuidedVoiceController flow) async {
    await flow.start();
    for (var i = 0; i < 4; i++) {
      io.text = i == 3 ? 'Right now my number one goal is to ship Omi.' : 'Personal detail $i';
      io.speak();
      await flow.next();
    }
  }

  test('one save finishes voice, selected memories and cleaned goal; double taps do nothing', () async {
    final io = FakeVoiceIO()..pendingUpload = Completer<bool>();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await completeAnswers(io, flow);
    flow.setKeep(1, false);
    final saving = flow.saveAll();
    expect(flow.busy, isTrue);
    await flow.saveAll();
    expect(io.uploads, hasLength(1));
    io.pendingUpload!.complete(true);
    await saving;
    expect(flow.stage, IntroductionStage.done);
    expect(flow.busy, isFalse);
    expect(io.remembered, ['Personal detail 0', 'Personal detail 2']);
    expect(io.goals, ['Ship Omi']);
  });

  test('voice failure does not block answers; retry only repeats the failed voice save', () async {
    final io = FakeVoiceIO()..uploadSuccess = false;
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await completeAnswers(io, flow);
    await flow.saveAll();
    expect(flow.stage, IntroductionStage.review);
    expect(flow.voiceError, 'upload');
    expect(flow.allMemoriesSaved, isTrue);
    io.uploadSuccess = true;
    await flow.saveAll();
    expect(flow.stage, IntroductionStage.done);
    expect(io.uploads, hasLength(2));
    expect(io.remembered, hasLength(3));
    expect(io.goals, ['Ship Omi']);
  });

  test('goal failure retries only the goal without reuploading a saved voice profile', () async {
    final io = FakeVoiceIO()..goalSuccess = false;
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await completeAnswers(io, flow);
    await flow.saveAll();
    expect(flow.error, 'goal');
    expect(flow.voiceSaved, isTrue);
    io.goalSuccess = true;
    await flow.saveAll();
    expect(flow.stage, IntroductionStage.done);
    expect(io.uploads, hasLength(1));
    expect(io.remembered, hasLength(3));
    expect(io.goalKeys[0], io.goalKeys[1]);
  });

  test('failed memories do not block the independent goal save', () async {
    final io = FakeVoiceIO()..memorySuccess = false;
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await completeAnswers(io, flow);
    await flow.saveAll();
    expect(flow.goalSaved, isTrue);
    expect(flow.voiceSaved, isTrue);
    expect(flow.stage, IntroductionStage.review);
    io.memorySuccess = true;
    await flow.saveAll();
    expect(flow.stage, IntroductionStage.done);
    expect(io.goals, hasLength(1));
    expect(io.uploads, hasLength(1));
  });

  test('disposed combined save does not start subsequent memory or goal requests', () async {
    final io = FakeVoiceIO()..pendingUpload = Completer<bool>();
    final flow = GuidedVoiceController(io);
    await completeAnswers(io, flow);
    final saving = flow.saveAll();
    flow.dispose();
    io.pendingUpload!.complete(true);
    await saving;
    expect(io.remembered, isEmpty);
    expect(io.goals, isEmpty);
  });

  test('backgrounding during transcription prevents automatic microphone restart', () async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    io.speak();
    io.pendingTranscription = Completer<String>();
    final next = flow.next();
    await Future<void>.delayed(Duration.zero);
    await flow.pause();
    io.pendingTranscription!.complete('My first answer');
    await next;
    expect(flow.promptIndex, 1);
    expect(flow.stage, IntroductionStage.ready);
    expect(io.startCount, 1);
  });

  test('fourth answer is a goal only; partial retry preserves its identity and content', () async {
    final io = FakeVoiceIO()..goalSuccess = false;
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    for (var i = 0; i < 4; i++) {
      io.text = i == 3 ? 'Ship my project' : 'Personal detail $i';
      io.speak();
      await flow.next();
    }
    expect(io.startCount, 4);
    expect(flow.stage, IntroductionStage.review);
    expect(flow.answers.last.isGoal, isTrue);
    flow.edit(3, 'Ship Omi');
    await flow.saveMemories();
    expect(flow.error, 'goal');
    expect(io.remembered, ['Personal detail 0', 'Personal detail 1', 'Personal detail 2']);
    expect(io.goals, isEmpty);
    flow.edit(3, 'Must not change a pending request');
    io.goalSuccess = true;
    await flow.saveMemories();
    expect(io.goals, ['Ship Omi']);
    expect(io.goalKeys[0], io.goalKeys[1]);
    expect(io.remembered, hasLength(3));
    expect(flow.goalSaved, isTrue);
    expect(flow.stage, IntroductionStage.done);
  });

  test('unchecking the goal never writes it as either a goal or a memory', () async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    for (var i = 0; i < 3; i++) {
      await flow.skipPrompt();
    }
    expect(io.startCount, 0);
    expect(flow.isGoalPrompt, isTrue);
    await flow.start();
    io.speak();
    await flow.next();
    flow.setKeep(0, false);
    await flow.saveMemories();
    expect(io.goals, isEmpty);
    expect(io.remembered, isEmpty);
  });

  test('embedding service failure is distinct from an invalid recording', () async {
    final io = FakeVoiceIO()..unavailable = true;
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    io.speak();
    await flow.next();
    for (var i = 0; i < 3; i++) {
      await flow.skipPrompt();
    }
    await flow.saveVoice();
    expect(flow.error, 'voiceUnavailable');
    expect(flow.voiceSaved, isFalse);
    expect(flow.answers, hasLength(1));
  });

  test('five seconds never auto-finishes; each Next advances exactly one prompt', () async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    io.speak(8);
    expect(flow.active, isTrue);
    expect(flow.progress, 0);
    expect(io.uploads, isEmpty);
    await flow.next();
    expect(flow.progress, closeTo(1 / 4, .001));
    expect(flow.answers.single.text, io.text);
    expect(flow.active, isTrue);
    expect(io.startCount, 2);
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.skipPrompt();
    expect(flow.stage, IntroductionStage.review);
    expect(flow.progress, 1);
    expect(io.remembered, isEmpty);
    await flow.saveVoice();
    expect(flow.voiceSaved, isTrue);
    expect(io.remembered, isEmpty);
  });

  test('skipping a recorded prompt discards it and never invents a memory from its starter', () async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    io.speak();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.skipPrompt();
    expect(flow.answers, isEmpty);
    await flow.saveMemories();
    expect(io.remembered, isEmpty);
  });

  test('transcription failure preserves audio for retry and does not advance', () async {
    final io = FakeVoiceIO()..transcriptionFails = true;
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    io.speak();
    await flow.next();
    expect(flow.stage, IntroductionStage.paused);
    expect(flow.promptIndex, 0);
    expect(flow.canFinish, isTrue);
    io.transcriptionFails = false;
    await flow.next();
    expect(flow.promptIndex, 1);
  });

  test('upload failure cannot claim success and retry uses identical audio', () async {
    final io = FakeVoiceIO()..uploadSuccess = false;
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    io.speak();
    await flow.next();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.saveVoice();
    expect(flow.voiceSaved, isFalse);
    expect(flow.stage, IntroductionStage.voiceError);
    io.uploadSuccess = true;
    await flow.saveVoice();
    expect(io.uploads[0], orderedEquals(io.uploads[1]));
    expect(flow.voiceSaved, isTrue);
  });

  test('short sample requests more speech without dropping earlier answers', () async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    io.speak(1);
    await flow.next();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.saveVoice();
    expect(flow.error, 'short');
    expect(io.uploads, isEmpty);
    flow.addSample();
    await flow.start();
    io.speak(6);
    await flow.next();
    await flow.saveVoice();
    expect(flow.answers, hasLength(2));
    expect(flow.voiceSaved, isTrue);
  });

  test('edited and selected statements only; successful writes are not retried', () async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    for (var i = 0; i < 4; i++) {
      await flow.start();
      io.speak();
      io.text = 'Answer $i';
      await flow.next();
    }
    flow.edit(0, 'Corrected first answer');
    flow.setKeep(1, false);
    flow.answers[2].saved = true;
    io.memorySuccess = false;
    await flow.saveMemories();
    expect(flow.stage, IntroductionStage.review);
    expect(flow.error, 'memories');
    io.memorySuccess = true;
    await flow.saveMemories();
    expect(io.remembered, ['Corrected first answer']);
    expect(io.goals, ['Answer 3']);
    expect(flow.stage, IntroductionStage.done);
  });

  test('pause preserves audio and resume appends to the same answer', () async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    io.speak(2);
    await flow.pause();
    expect(flow.stage, IntroductionStage.paused);
    expect(flow.seconds, 2);
    await flow.start();
    io.speak(3);
    await flow.next();
    expect(flow.answers.single.audio.length, 5 * 32000);
  });

  test('navigation during microphone preparation never starts recording', () async {
    final io = FakeVoiceIO()..preparing = Completer<void>();
    final flow = GuidedVoiceController(io);
    final starting = flow.start();
    flow.dispose();
    io.preparing!.complete();
    await starting;
    expect(io.audio, isNull);
  });

  test('late upload response cannot mutate a disposed session', () async {
    final io = FakeVoiceIO()..pendingUpload = Completer<bool>();
    final flow = GuidedVoiceController(io);
    await flow.start();
    io.speak();
    await flow.next();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.skipPrompt();
    final saving = flow.saveVoice();
    flow.dispose();
    io.pendingUpload!.complete(true);
    await saving;
    expect(flow.voiceSaved, isFalse);
  });
}
