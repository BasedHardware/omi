import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations_zh.dart';

void main() {
  final l10n = AppLocalizationsZh();

  test('Chinese onboarding copy uses natural product language', () {
    expect(l10n.omiYourAiCompanion, 'Omi – 您的 AI 助手');
    expect(l10n.captureEveryMoment, '记录每个瞬间，AI 为您生成摘要。');
    expect(l10n.speakTranscribeSummarize, '开口说，自动转写，智能总结。');
  });

  test('Chinese labels distinguish transcript and summary actions', () {
    expect(l10n.transcriptTab, '文字记录');
    expect(l10n.summarize, '生成摘要');
    expect(l10n.generateSummary, '生成摘要');
    expect(l10n.summary, '摘要');
    expect(l10n.allCaughtUp, '已全部完成');
  });

  test('Chinese baseline-memory labels do not fall back to English', () {
    expect(l10n.pinAsBaseline, '设为基准记忆');
    expect(l10n.unpinAsBaseline, '取消基准记忆');
    expect(l10n.baselineMemory, '基准记忆');
    expect(l10n.alwaysInContext, '始终包含在上下文中');
  });

  test('Chinese feedback copy is consistent and interpolates dates', () {
    expect(l10n.summaryGeneratedForDate('2026/8/2'), '已为 2026/8/2 生成摘要');
    expect(l10n.summaryGeneratedFor('2026/8/2'), '已为 2026/8/2 生成摘要');
    expect(l10n.failedToGenerateSummary, '生成摘要失败。请确保当天有对话记录。');
    expect(l10n.keepGoingGreat, '加油，继续保持！');
    expect(l10n.wrappedLetsHitRewind, '让我们回顾一下你的');
  });
}
