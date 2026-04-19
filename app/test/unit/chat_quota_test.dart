import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/chat_quota.dart';

void main() {
  group('ChatUsageQuota.fromJson', () {
    test('parses full payload correctly', () {
      final json = {
        'plan': 'Neo',
        'plan_type': 'unlimited',
        'unit': 'questions',
        'used': 150,
        'limit': 2000,
        'percent': 7.5,
        'allowed': true,
        'reset_at': 1714521600,
      };
      final quota = ChatUsageQuota.fromJson(json);
      expect(quota.plan, 'Neo');
      expect(quota.planType, 'unlimited');
      expect(quota.unit, ChatQuotaUnit.questions);
      expect(quota.used, 150.0);
      expect(quota.limit, 2000.0);
      expect(quota.percent, 7.5);
      expect(quota.allowed, true);
      expect(quota.resetAt, 1714521600);
    });

    test('handles missing optional fields', () {
      final json = {
        'plan': 'Free',
        'plan_type': 'basic',
        'unit': 'questions',
        'used': 30,
        'percent': 100.0,
        'allowed': false,
      };
      final quota = ChatUsageQuota.fromJson(json);
      expect(quota.limit, isNull);
      expect(quota.resetAt, isNull);
      expect(quota.allowed, false);
    });

    test('coerces int to double for used and limit', () {
      final json = {
        'plan': 'Operator',
        'plan_type': 'operator',
        'unit': 'questions',
        'used': 499,
        'limit': 500,
        'percent': 99.8,
        'allowed': true,
        'reset_at': null,
      };
      final quota = ChatUsageQuota.fromJson(json);
      expect(quota.used, isA<double>());
      expect(quota.limit, isA<double>());
      expect(quota.used, 499.0);
      expect(quota.limit, 500.0);
    });

    test('parses cost_usd unit for Architect plan', () {
      final json = {
        'plan': 'Architect',
        'plan_type': 'architect',
        'unit': 'cost_usd',
        'used': 123.45,
        'limit': 400.0,
        'percent': 30.86,
        'allowed': true,
        'reset_at': 1714521600,
      };
      final quota = ChatUsageQuota.fromJson(json);
      expect(quota.unit, ChatQuotaUnit.costUsd);
      expect(quota.used, 123.45);
      expect(quota.limit, 400.0);
    });

    test('defaults for completely empty json', () {
      final quota = ChatUsageQuota.fromJson({});
      expect(quota.plan, 'Free');
      expect(quota.planType, 'basic');
      expect(quota.unit, ChatQuotaUnit.questions);
      expect(quota.used, 0.0);
      expect(quota.limit, isNull);
      expect(quota.allowed, true);
    });
  });

  group('ChatUsageQuota display getters', () {
    test('limitDisplay for questions unit', () {
      final quota = ChatUsageQuota(
        plan: 'Neo',
        planType: 'unlimited',
        unit: ChatQuotaUnit.questions,
        used: 100,
        limit: 2000,
        percent: 5.0,
        allowed: true,
      );
      expect(quota.limitDisplay, '2000 messages/month');
    });

    test('limitDisplay for cost_usd unit', () {
      final quota = ChatUsageQuota(
        plan: 'Architect',
        planType: 'architect',
        unit: ChatQuotaUnit.costUsd,
        used: 50.0,
        limit: 400.0,
        percent: 12.5,
        allowed: true,
      );
      expect(quota.limitDisplay, r'$400/mo compute budget');
    });

    test('limitDisplay for null limit', () {
      final quota = ChatUsageQuota(
        plan: 'Free',
        planType: 'basic',
        unit: ChatQuotaUnit.questions,
        used: 30,
        limit: null,
        percent: 100.0,
        allowed: false,
      );
      expect(quota.limitDisplay, 'Unlimited');
    });

    test('remainingDisplay for questions', () {
      final quota = ChatUsageQuota(
        plan: 'Neo',
        planType: 'unlimited',
        unit: ChatQuotaUnit.questions,
        used: 1800,
        limit: 2000,
        percent: 90.0,
        allowed: true,
      );
      expect(quota.remainingDisplay, '200 messages remaining');
    });

    test('remainingDisplay for cost_usd', () {
      final quota = ChatUsageQuota(
        plan: 'Architect',
        planType: 'architect',
        unit: ChatQuotaUnit.costUsd,
        used: 350.50,
        limit: 400.0,
        percent: 87.63,
        allowed: true,
      );
      expect(quota.remainingDisplay, r'$49.50 remaining');
    });

    test('remainingDisplay for null limit', () {
      final quota = ChatUsageQuota(
        plan: 'Free',
        planType: 'basic',
        unit: ChatQuotaUnit.questions,
        used: 30,
        limit: null,
        percent: 100.0,
        allowed: false,
      );
      expect(quota.remainingDisplay, 'Unlimited');
    });

    test('remainingDisplay clamps to zero when used exceeds limit', () {
      final quota = ChatUsageQuota(
        plan: 'Neo',
        planType: 'unlimited',
        unit: ChatQuotaUnit.questions,
        used: 2100,
        limit: 2000,
        percent: 105.0,
        allowed: false,
      );
      expect(quota.remainingDisplay, '0 messages remaining');
    });
  });

  group('ChatUsageQuota boundary', () {
    test('exactly at limit is not allowed (backend uses strict <)', () {
      final quota = ChatUsageQuota(
        plan: 'Operator',
        planType: 'operator',
        unit: ChatQuotaUnit.questions,
        used: 500,
        limit: 500,
        percent: 100.0,
        allowed: false,
      );
      expect(quota.allowed, false);
    });

    test('one below limit is allowed', () {
      final quota = ChatUsageQuota(
        plan: 'Operator',
        planType: 'operator',
        unit: ChatQuotaUnit.questions,
        used: 499,
        limit: 500,
        percent: 99.8,
        allowed: true,
      );
      expect(quota.allowed, true);
    });
  });
}
