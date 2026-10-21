import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/chat/page.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/services/dev_controls/journey_faults.dart';
import 'package:omi/services/dev_controls/semantic_controls.dart';

import 'support/fixture_backend.dart';
import 'support/hermetic_boot.dart';
import 'support/journey_evidence.dart';

/// Journey 2 — chat send / distinct assistant reply (SCA-488 / C2).
///
/// Positive: seed a signed-in fixture principal, open the real [ChatPage],
/// type a prompt into the real input field and tap the real send button
/// (the UI path — no direct provider calls for the interaction under test),
/// then require:
///   1. the send request actually reached the server (fixture journal),
///   2. a distinct assistant-role reply arrived through the real API path
///      (sender == ai, id minted by the server, text != prompt),
///   3. the reply is rendered in the transcript UI.
///
/// Negative variants arm one journey fault each and MUST fail with the
/// missing invariant named:
///   - suppress-send: the request never reaches the server; no reply.
///   - suppress-assistant-reply: the stream closes with no chunks.
///   - wrong-owner-session: the server rejects the swapped bearer (403).
///
/// Deterministic by construction: the fixture reply is locally generated;
/// no live-LLM wording is asserted.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final prompt = 'journey-two-prompt-${DateTime.now().millisecondsSinceEpoch}';

  testWidgets('positive: send through real UI, distinct assistant reply through real API path', (tester) async {
    final evidence = JourneyEvidence.begin(journeyId: 'j2_chat_send_assistant_reply', lane: journeyLane);
    final server = await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);

    evidence.stateBefore = SemanticControls.instance.state().toJson();
    evidence.note('fixture backend on ${server.baseUrl}');

    await JourneyHermeticBoot.pumpPage(tester, page: const ChatPage());

    // Real UI interaction: type into the real field, tap the real send button.
    final input = find.byKey(const ValueKey('omi.chat.input'));
    if (input.evaluate().isEmpty) {
      evidence.record('chat-input-present', ok: false, invariant: 'the chat input is reachable by its stable key');
      await evidence.write();
      fail('chat input with key omi.chat.input not found — add the ValueKey (see SCA-488 keys)');
    }
    await tester.enterText(input, prompt);
    await tester.pump();

    final send = find.byKey(const ValueKey('omi.chat.send'));
    evidence.record('chat-send-button-present',
        ok: send.evaluate().isNotEmpty, invariant: 'the send button is reachable by its stable key');
    expect(send, findsOneWidget);

    final sendsBefore = server.countOf('POST', '/v2/messages');
    await tester.tap(send);
    await tester.pumpAndSettle(const Duration(seconds: 5));

    final provider = tester.element(find.byType(ChatPage)).read<MessageProvider>();

    // 1. The send reached the server through the real HTTP path.
    evidence.record('send-reached-server',
        ok: server.countOf('POST', '/v2/messages') == sendsBefore + 1,
        invariant: 'a sent user message reaches the server and is echoed into the conversation',
        detail: 'POST /v2/messages count ${server.countOf('POST', '/v2/messages')}');
    expect(server.countOf('POST', '/v2/messages'), sendsBefore + 1,
        reason: 'send request must reach the fixture backend');

    // 2. User message rendered from the local-echo path.
    final userRendered = find.text(prompt).evaluate().isNotEmpty;
    evidence.record('user-message-rendered',
        ok: userRendered, invariant: 'the sent prompt is visible in the transcript');
    expect(userRendered, isTrue);

    // 3. Distinct assistant-role reply through the real API path.
    final aiMessages = provider.messages.where((m) => m.sender.name == 'ai').toList();
    final distinctReply = aiMessages.any((m) => m.id.startsWith('srv-reply-') && m.text != prompt);
    evidence.record(
      'distinct-assistant-reply',
      ok: distinctReply,
      invariant: 'a distinct assistant-role reply arrives through the real API path',
      detail: 'ai messages: ${aiMessages.map((m) => m.id).toList()}',
    );
    expect(distinctReply, isTrue, reason: 'assistant reply must be server-minted and distinct from the prompt');

    final replyText = aiMessages.firstWhere((m) => m.id.startsWith('srv-reply-')).text;
    final replyRendered = find.textContaining(server.assistantReplyText).evaluate().isNotEmpty;
    evidence.record('assistant-reply-rendered',
        ok: replyRendered, invariant: 'the assistant reply is visible in the transcript', detail: replyText);
    expect(replyRendered, isTrue);

    evidence.stateAfter = SemanticControls.instance.state().toJson();
    expect(evidence.failed, 0, reason: 'positive journey must pass every assertion');
    await evidence.write();
  });

  testWidgets('negative: suppress-send must fail naming the send invariant', (tester) async {
    final evidence = JourneyEvidence.begin(journeyId: 'j2_chat_send_assistant_reply.suppress-send', lane: journeyLane);
    final server = await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    JourneyFaultGate.instance.arm(JourneyFault.suppressSend);
    evidence.stateBefore = SemanticControls.instance.state().toJson();

    await JourneyHermeticBoot.pumpPage(tester, page: const ChatPage());
    await tester.enterText(find.byKey(const ValueKey('omi.chat.input')), prompt);
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    await tester.pumpAndSettle(const Duration(seconds: 5));

    final provider = tester.element(find.byType(ChatPage)).read<MessageProvider>();
    final sendsArrived = server.countOf('POST', '/v2/messages');
    final aiReply = provider.messages.any((m) => m.sender.name == 'ai' && m.id.startsWith('srv-reply-'));

    // The oracle: with the fault armed, the missing invariant MUST be absent.
    final invariantHeld = sendsArrived == 0 && !aiReply;
    evidence.record(
      'fault-exposes-missing-invariant',
      ok: invariantHeld,
      invariant: JourneyFault.suppressSend.invariant,
      detail: 'server saw $sendsArrived sends; ai reply present: $aiReply',
    );
    if (!invariantHeld) {
      await evidence.write();
      fail('oracle cannot detect suppress-send: request count=$sendsArrived reply=$aiReply');
    }
    // A nonzero failure with the invariant named: the positive path executed
    // as a negative run must be reported as failing.
    evidence.failed++; // the suppressed journey outcome itself
    evidence.assertions.add({
      'name': 'journey-under-fault',
      'ok': false,
      'invariant': JourneyFault.suppressSend.invariant,
      'detail': 'send suppressed: 0 requests, no assistant reply — expected failure',
    });
    evidence.stateAfter = SemanticControls.instance.state().toJson();
    await evidence.write();
  });

  testWidgets('negative: suppress-assistant-reply must fail naming the reply invariant', (tester) async {
    final evidence =
        JourneyEvidence.begin(journeyId: 'j2_chat_send_assistant_reply.suppress-assistant-reply', lane: journeyLane);
    final server = await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    server.arm(JourneyFault.suppressAssistantReply);
    evidence.stateBefore = SemanticControls.instance.state().toJson();

    await JourneyHermeticBoot.pumpPage(tester, page: const ChatPage());
    await tester.enterText(find.byKey(const ValueKey('omi.chat.input')), prompt);
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    await tester.pumpAndSettle(const Duration(seconds: 5));

    final provider = tester.element(find.byType(ChatPage)).read<MessageProvider>();
    final sendArrived = server.countOf('POST', '/v2/messages') > 0;
    final aiReply = provider.messages.any((m) => m.sender.name == 'ai' && m.id.startsWith('srv-reply-'));

    final invariantAbsent = sendArrived && !aiReply;
    evidence.record('fault-exposes-missing-invariant',
        ok: invariantAbsent,
        invariant: JourneyFault.suppressAssistantReply.invariant,
        detail: 'send arrived: $sendArrived; distinct reply present: $aiReply');
    if (!invariantAbsent) {
      await evidence.write();
      fail('oracle cannot detect a suppressed assistant reply');
    }
    evidence.failed++;
    evidence.assertions.add({
      'name': 'journey-under-fault',
      'ok': false,
      'invariant': JourneyFault.suppressAssistantReply.invariant,
      'detail': 'stream closed with no chunks — expected failure',
    });
    evidence.stateAfter = SemanticControls.instance.state().toJson();
    await evidence.write();
  });

  testWidgets('negative: wrong-owner-session must fail naming the ownership invariant', (tester) async {
    final evidence =
        JourneyEvidence.begin(journeyId: 'j2_chat_send_assistant_reply.wrong-owner-session', lane: journeyLane);
    final server = await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    JourneyFaultGate.instance.arm(JourneyFault.wrongOwnerSession);
    evidence.stateBefore = SemanticControls.instance.state().toJson();

    await JourneyHermeticBoot.pumpPage(tester, page: const ChatPage());
    await tester.enterText(find.byKey(const ValueKey('omi.chat.input')), prompt);
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    await tester.pumpAndSettle(const Duration(seconds: 5));

    final provider = tester.element(find.byType(ChatPage)).read<MessageProvider>();
    final ownershipRejected = server.requestLog.any((r) => r['path'] == '/v2/messages' && '$r'.contains('403')) ||
        !provider.messages.any((m) => m.sender.name == 'ai' && m.id.startsWith('srv-reply-'));

    // The server must refuse the wrong-owner bearer; the positive outcome
    // must be unattainable. Track rejections structurally: the fixture
    // records the swapped bearer in its journal.
    final sawWrongOwner = server.requestLog.any((r) => r['bearer'] == JourneyFixtureBackend.wrongOwnerBearer);
    evidence.record('wrong-owner-bearer-observed',
        ok: sawWrongOwner,
        invariant: JourneyFault.wrongOwnerSession.invariant,
        detail: server.requestLog.map((r) => '${r['path']} bearer=${r['bearer']}').toList());
    evidence.record('no-reply-under-wrong-owner',
        ok: ownershipRejected, invariant: JourneyFault.wrongOwnerSession.invariant);
    if (!sawWrongOwner || !ownershipRejected) {
      await evidence.write();
      fail('oracle cannot detect wrong-owner session (sawWrongOwner=$sawWrongOwner rejected=$ownershipRejected)');
    }
    evidence.failed++;
    evidence.assertions.add({
      'name': 'journey-under-fault',
      'ok': false,
      'invariant': JourneyFault.wrongOwnerSession.invariant,
      'detail': 'server rejected the swapped bearer — expected failure',
    });
    evidence.stateAfter = SemanticControls.instance.state().toJson();
    await evidence.write();
  });
}
