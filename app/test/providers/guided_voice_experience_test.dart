import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import 'guided_voice_controller_test.dart' show FakeVoiceIO;

class ExperienceIO extends FakeVoiceIO implements GuidedVoiceExperienceIO {
  bool reachable = true;
  bool local = false;
  @override
  bool get livePreview => local;
  int checks = 0;
  Object? failure;
  bool chatFails = false;
  Completer<bool>? pendingCheck;
  Completer<String>? pendingChat;
  List<String>? chatFacts;
  @override
  Future<bool> preflight() async {
    checks++;
    return pendingCheck == null ? reachable : await pendingCheck!.future;
  }

  @override
  Future<void> prepare() async {
    if (failure != null) throw failure!;
    await super.prepare();
  }

  @override
  Future<String> transcribe(Uint8List pcm) async {
    if (failure != null) throw failure!;
    return super.transcribe(pcm);
  }

  @override
  Future<String> ask(String question, List<String> savedAnswers) async {
    chatFacts = savedAnswers;
    if (chatFails) throw StateError('Unavailable');
    return pendingChat == null ? 'Focus on finishing your bicycle project.' : await pendingChat!.future;
  }
}

Future<void> typedReview(GuidedVoiceController flow) async {
  await flow.typeInstead();
  await flow.submitTyped('I build bicycles.');
  await flow.skipPrompt();
  await flow.skipPrompt();
  await flow.skipPrompt();
}

void main() {
  test('failed preflight cannot open the mic and typing remains available; retry rechecks', () async {
    final io = ExperienceIO()..reachable = false;
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    expect(io.startCount, 0);
    expect(flow.error, 'transcription_unavailable');
    io.reachable = true;
    await flow.start();
    expect(io.checks, 2);
    expect(io.startCount, 1);
    await flow.pause();
    await flow.start();
    expect(io.checks, 2);
  });

  test('preflight timeout and navigation during check never start the mic', () async {
    final io = ExperienceIO()..pendingCheck = Completer<bool>();
    final flow = GuidedVoiceController(io, preflightTimeout: const Duration(milliseconds: 2));
    addTearDown(flow.dispose);
    await flow.start();
    expect(io.startCount, 0);
    expect(flow.error, 'transcription_unavailable');
    io.pendingCheck!.complete(true);
    final second = ExperienceIO()..pendingCheck = Completer<bool>();
    final other = GuidedVoiceController(second);
    addTearDown(other.dispose);
    final starting = other.start();
    await other.pause();
    second.pendingCheck!.complete(true);
    await starting;
    expect(second.startCount, 0);
  });

  for (final kind in ['permission_denied', 'permission_permanently_denied', 'engine_start_failed']) {
    test('prepare failure preserves $kind', () async {
      final io = ExperienceIO()..failure = GuidedVoiceFailure(kind);
      final flow = GuidedVoiceController(io);
      addTearDown(flow.dispose);
      await flow.start();
      expect(flow.error, kind);
      expect(io.startCount, 0);
      expect(flow.transcriptionPath, 'cloud');
    });
  }
  for (final kind in ['transcribe_timeout', 'transcribe_http_error', 'transcribe_empty']) {
    test('transcription failure $kind offers typed recovery on same prompt', () async {
      final io = ExperienceIO();
      final flow = GuidedVoiceController(io);
      addTearDown(flow.dispose);
      await flow.start();
      io.speak();
      io.failure = kind == 'transcribe_timeout' ? TimeoutException('test') : GuidedVoiceFailure(kind);
      await flow.next();
      expect(flow.error, kind);
      expect(flow.promptIndex, 0);
      await flow.typeInstead();
      await flow.submitTyped('I build bicycles.');
      expect(flow.answers.single.text, 'I build bicycles.');
      expect(flow.answers.single.audio, isEmpty);
      expect(flow.promptIndex, 1);
    });
  }
  test('empty transcript is distinct and spoken answers need explicit confirmation', () async {
    final io = ExperienceIO()..text = '';
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    io.speak();
    await flow.next();
    expect(flow.error, 'transcribe_empty');
    io.text = 'I build bicycles.';
    await flow.next();
    expect(flow.stage, IntroductionStage.confirmation);
    expect(flow.answers, isEmpty);
    await flow.confirmAnswer();
    expect(flow.answers.single.text, io.text);
  });
  test('typed-only Save and Finish saves memories without requiring voice enrollment', () async {
    final io = ExperienceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await typedReview(flow);
    await flow.saveAll();
    expect(flow.stage, IntroductionStage.done);
    expect(io.remembered, ['I build bicycles.']);
    expect(io.uploads, isEmpty);
  });
  test('typed answer uses submittedMemory lock through failure and retry', () async {
    final io = ExperienceIO()..memorySuccess = false;
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await typedReview(flow);
    await flow.saveAll();
    expect(flow.answers.single.locked, isTrue);
    flow.edit(0, 'Changed');
    flow.setKeep(0, false);
    expect(flow.answers.single.text, 'I build bicycles.');
    expect(flow.answers.single.keep, isTrue);
    io.memorySuccess = true;
    await flow.saveAll();
    expect(io.remembered, ['I build bicycles.']);
    await flow.saveAll();
    expect(io.remembered.length, 1);
  });
  test('typed goal uses the existing goal lock and idempotency key', () async {
    final io = ExperienceIO()..goalSuccess = false;
    final flow = GuidedVoiceController(io, accountUid: 'fixture');
    addTearDown(flow.dispose);
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.typeInstead();
    await flow.submitTyped('Ship my bicycle project');
    await flow.saveAll();
    flow.edit(0, 'Changed');
    io.goalSuccess = true;
    await flow.saveAll();
    expect(io.goalKeys, ['intro-goal-fixture', 'intro-goal-fixture']);
    expect(io.goals, ['Ship my bicycle project']);
  });
  test('payoff only sends successfully saved facts, gets chat or deterministic fallback', () async {
    final io = ExperienceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await typedReview(flow);
    await flow.saveAll();
    await flow.showPayoff('What should I focus on this week?', 'I build bicycles.');
    expect(flow.payoffSource, 'chat');
    expect(io.chatFacts, ['I build bicycles.']);
    expect(flow.payoffAnswer, contains('bicycle project'));
    await flow.saveAll();
    expect(flow.stage, IntroductionStage.payoff, reason: 'a stale second Save must not replace the payoff');
    expect(io.remembered, ['I build bicycles.']);
    final failed = ExperienceIO()..chatFails = true;
    final other = GuidedVoiceController(failed);
    addTearDown(other.dispose);
    await typedReview(other);
    await other.saveAll();
    await other.showPayoff('Question', 'I build bicycles.');
    expect(other.payoffSource, 'fallback');
    expect(other.payoffAnswer, 'I build bicycles.');
  });
  test('payoff timeout retains summary and early Continue ignores late chat', () async {
    final io = ExperienceIO()..pendingChat = Completer<String>();
    final flow = GuidedVoiceController(io, payoffTimeout: const Duration(milliseconds: 2));
    addTearDown(flow.dispose);
    await typedReview(flow);
    await flow.saveAll();
    await flow.showPayoff('Question', 'I build bicycles.');
    expect(flow.payoffLoading, isFalse);
    expect(flow.payoffSource, 'fallback');
    io.pendingChat!.complete('Late');
    await Future<void>.delayed(Duration.zero);
    expect(flow.payoffAnswer, 'I build bicycles.');
    final second = ExperienceIO()..pendingChat = Completer<String>();
    final other = GuidedVoiceController(second);
    addTearDown(other.dispose);
    await typedReview(other);
    await other.saveAll();
    final asking = other.showPayoff('Question', 'Saved summary');
    other.continuePayoff();
    second.pendingChat!.complete('Late');
    await asking;
    expect(other.payoffAnswer, 'Saved summary');
  });
  test('skip everything or save nothing has no payoff', () async {
    final flow = GuidedVoiceController(ExperienceIO());
    addTearDown(flow.dispose);
    await flow.showPayoff('Question', 'Summary');
    expect(flow.stage, IntroductionStage.ready);
    expect(flow.payoffLoading, isFalse);
  });
}
