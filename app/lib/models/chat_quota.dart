class ChatQuotaUnit {
  static const String questions = 'questions';
  static const String costUsd = 'cost_usd';
}

class ChatUsageQuota {
  final String plan;
  final String planType;
  final String unit;
  final double used;
  final double? limit;
  final double percent;
  final bool allowed;
  final int? resetAt;

  ChatUsageQuota({
    required this.plan,
    required this.planType,
    required this.unit,
    required this.used,
    this.limit,
    this.percent = 0.0,
    this.allowed = true,
    this.resetAt,
  });

  factory ChatUsageQuota.fromJson(Map<String, dynamic> json) {
    return ChatUsageQuota(
      plan: json['plan'] as String? ?? 'Free',
      planType: json['plan_type'] as String? ?? 'basic',
      unit: json['unit'] as String? ?? ChatQuotaUnit.questions,
      used: (json['used'] as num?)?.toDouble() ?? 0.0,
      limit: (json['limit'] as num?)?.toDouble(),
      percent: (json['percent'] as num?)?.toDouble() ?? 0.0,
      allowed: json['allowed'] as bool? ?? true,
      resetAt: json['reset_at'] as int?,
    );
  }

  String get remainingDisplay {
    if (limit == null) return 'Unlimited';
    final remaining = (limit! - used).clamp(0, limit!);
    if (unit == ChatQuotaUnit.costUsd) {
      return '\$${remaining.toStringAsFixed(2)} remaining';
    }
    return '${remaining.toInt()} messages remaining';
  }

  String get limitDisplay {
    if (limit == null) return 'Unlimited';
    if (unit == ChatQuotaUnit.costUsd) {
      return '\$${limit!.toStringAsFixed(0)}/mo compute budget';
    }
    return '${limit!.toInt()} messages/month';
  }
}
