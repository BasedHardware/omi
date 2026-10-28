import 'package:omi/backend/schema/gen/subscription_usage_wire.g.dart' as wire;
import 'package:omi/models/transcription_allowance.dart';

enum SubscriptionStatus { active, inactive }

/// A subscription plan identity received from the backend.
///
/// This is intentionally a class rather than an enum. The backend can deploy
/// a new plan before this app is updated, and decoding that value must not
/// silently turn a paying subscriber into [PlanType.basic]. Known plan values
/// retain the enum-shaped API used by the app (`PlanType.values`, `.name`, and
/// the static plan constants), while unknown values retain their raw wire ID.
class PlanType {
  static const PlanType basic = PlanType._('basic', 'basic', 'basic');
  static const PlanType unlimited = PlanType._('unlimited', 'unlimited', 'unlimited');
  static const PlanType architect = PlanType._('architect', 'architect', 'architect');
  static const PlanType operator = PlanType._('operator', 'operator', 'operator');
  static const PlanType plus = PlanType._('plus', 'plus', 'plus');
  static const PlanType unlimitedV2 = PlanType._('unlimitedV2', 'unlimited_v2', 'unlimited_v2');

  /// The canonical catalog identities known by this client.
  ///
  /// Legacy aliases and future identities are deliberately not included.
  static const List<PlanType> values = <PlanType>[basic, unlimited, architect, operator, plus, unlimitedV2];

  /// Dart-style identifier used by existing analytics and UI call sites.
  final String name;

  /// The exact plan ID to use at the backend wire boundary.
  ///
  /// For an unknown plan this is the raw value received from the backend.
  final String wireName;

  /// Canonical catalog identity, or null for an unrecognized future value.
  final String? _canonicalWireName;

  const PlanType._(this.name, this.wireName, this._canonicalWireName);

  /// Creates a lossless representation for a plan ID unknown to this client.
  factory PlanType.unknown(String rawWireName) {
    return PlanType._(rawWireName, rawWireName, null);
  }

  /// Decodes a backend plan ID without collapsing unknown values to Basic.
  ///
  /// `pro` is the catalog's legacy alias for Architect and is canonicalized to
  /// Architect's identity at the domain boundary.
  factory PlanType.fromWire(String? value) {
    switch (value) {
      case 'basic':
        return PlanType.basic;
      case 'unlimited':
        return PlanType.unlimited;
      case 'architect':
        return PlanType.architect;
      case 'operator':
        return PlanType.operator;
      case 'plus':
        return PlanType.plus;
      case 'unlimited_v2':
        return PlanType.unlimitedV2;
      case 'pro':
        return PlanType.architect;
      case null:
        // GeneratedSubscription supplies the legacy default for an omitted
        // plan field. Keep this defensive path aligned with that contract.
        return PlanType.basic;
      default:
        return PlanType.unknown(value);
    }
  }

  bool get isUnknown => _canonicalWireName == null;

  /// Unknown plans never infer paid access from an unfamiliar ID.
  bool get isPaid => !isUnknown && _canonicalWireName != PlanType.basic.wireName;

  /// Plans with no monthly transcription cap. Plus is paid but metered
  /// (1500 min/month), so it is deliberately excluded. Unknown plans are
  /// conservative and do not infer unlimited access.
  bool get hasUnlimitedTranscription =>
      _canonicalWireName == PlanType.unlimited.wireName ||
      _canonicalWireName == PlanType.operator.wireName ||
      _canonicalWireName == PlanType.architect.wireName ||
      _canonicalWireName == PlanType.unlimitedV2.wireName;

  /// Mirrors backend DESKTOP_ENTITLED_PLAN_TYPES.
  bool get grantsDesktop =>
      _canonicalWireName == PlanType.operator.wireName ||
      _canonicalWireName == PlanType.architect.wireName ||
      _canonicalWireName == PlanType.unlimitedV2.wireName;

  @override
  bool operator ==(Object other) {
    if (other is! PlanType) return false;
    if (isUnknown || other.isUnknown) {
      return isUnknown && other.isUnknown && wireName == other.wireName;
    }
    return _canonicalWireName == other._canonicalWireName;
  }

  @override
  int get hashCode => isUnknown ? wireName.hashCode : _canonicalWireName.hashCode;

  @override
  String toString() => isUnknown ? 'PlanType.unknown($wireName)' : 'PlanType.$name';
}

PlanType _planTypeFromWire(String? value) => PlanType.fromWire(value);

SubscriptionStatus _subscriptionStatusFromWire(String? value) {
  return SubscriptionStatus.values.asNameMap()[value] ?? SubscriptionStatus.inactive;
}

class PlanLimits {
  final int? transcriptionSeconds;
  final int? wordsTranscribed;
  final int? insightsGained;
  final int? chatQuestionsPerMonth;
  final double? chatCostUsdPerMonth;

  PlanLimits({
    this.transcriptionSeconds,
    this.wordsTranscribed,
    this.insightsGained,
    this.chatQuestionsPerMonth,
    this.chatCostUsdPerMonth,
  });

  factory PlanLimits.fromJson(Map<String, dynamic> json) {
    return PlanLimits.fromGenerated(wire.GeneratedPlanLimits.fromJson(json));
  }

  factory PlanLimits.fromGenerated(wire.GeneratedPlanLimits generated) {
    return PlanLimits(
      transcriptionSeconds: generated.transcriptionSeconds,
      wordsTranscribed: generated.wordsTranscribed,
      insightsGained: generated.insightsGained,
      chatQuestionsPerMonth: generated.chatQuestionsPerMonth,
      chatCostUsdPerMonth: generated.chatCostUsdPerMonth,
    );
  }

  wire.GeneratedPlanLimits toGenerated() {
    return wire.GeneratedPlanLimits(
      transcriptionSeconds: transcriptionSeconds,
      wordsTranscribed: wordsTranscribed,
      insightsGained: insightsGained,
      chatQuestionsPerMonth: chatQuestionsPerMonth,
      chatCostUsdPerMonth: chatCostUsdPerMonth,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class Subscription {
  final PlanType plan;
  final SubscriptionStatus status;
  final int? currentPeriodEnd;
  final String? stripeSubscriptionId;
  final String? currentPriceId;
  final List<String> features;
  final bool cancelAtPeriodEnd;
  final bool deprecated;
  final String? deprecationMessage;
  final PlanLimits limits;

  Subscription({
    required this.plan,
    required this.status,
    this.currentPeriodEnd,
    this.stripeSubscriptionId,
    this.currentPriceId,
    this.features = const [],
    this.cancelAtPeriodEnd = false,
    this.deprecated = false,
    this.deprecationMessage,
    PlanLimits? limits,
  }) : limits = limits ?? PlanLimits();

  factory Subscription.fromJson(Map<String, dynamic> json) {
    return Subscription.fromGenerated(wire.GeneratedSubscription.fromJson(json));
  }

  factory Subscription.fromGenerated(wire.GeneratedSubscription generated) {
    return Subscription(
      plan: _planTypeFromWire(generated.plan),
      status: _subscriptionStatusFromWire(generated.status),
      currentPeriodEnd: generated.currentPeriodEnd,
      stripeSubscriptionId: generated.stripeSubscriptionId,
      currentPriceId: generated.currentPriceId,
      features: generated.features,
      cancelAtPeriodEnd: generated.cancelAtPeriodEnd,
      deprecated: generated.deprecated,
      deprecationMessage: generated.deprecationMessage,
      limits: PlanLimits.fromGenerated(generated.limits),
    );
  }

  wire.GeneratedSubscription toGenerated() {
    return wire.GeneratedSubscription(
      plan: plan.wireName,
      status: status.name,
      currentPeriodEnd: currentPeriodEnd,
      stripeSubscriptionId: stripeSubscriptionId,
      currentPriceId: currentPriceId,
      features: features,
      cancelAtPeriodEnd: cancelAtPeriodEnd,
      deprecated: deprecated,
      deprecationMessage: deprecationMessage,
      limits: limits.toGenerated(),
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class PricingOption {
  final String id;
  final String title;
  final String? description;
  final String priceString;

  PricingOption({required this.id, required this.title, this.description, required this.priceString});

  factory PricingOption.fromJson(Map<String, dynamic> json) {
    return PricingOption.fromGenerated(wire.GeneratedPricingOption.fromJson(json));
  }

  factory PricingOption.fromGenerated(wire.GeneratedPricingOption generated) {
    return PricingOption(
      id: generated.id,
      title: generated.title,
      description: generated.description,
      priceString: generated.priceString,
    );
  }

  wire.GeneratedPricingOption toGenerated() {
    return wire.GeneratedPricingOption(id: id, title: title, description: description, priceString: priceString);
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class SubscriptionPlan {
  final String id;
  final String title;
  final List<String> features;
  final List<PricingOption> prices;

  SubscriptionPlan({required this.id, required this.title, this.features = const [], this.prices = const []});

  factory SubscriptionPlan.fromJson(Map<String, dynamic> json) {
    return SubscriptionPlan.fromGenerated(wire.GeneratedSubscriptionPlan.fromJson(json));
  }

  factory SubscriptionPlan.fromGenerated(wire.GeneratedSubscriptionPlan generated) {
    return SubscriptionPlan(
      id: generated.id,
      title: generated.title,
      features: generated.features,
      prices: generated.prices.map(PricingOption.fromGenerated).toList(),
    );
  }

  wire.GeneratedSubscriptionPlan toGenerated() {
    return wire.GeneratedSubscriptionPlan(
      id: id,
      title: title,
      features: features,
      prices: prices.map((price) => price.toGenerated()).toList(),
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class PhoneCallQuota {
  final bool hasAccess;
  final bool isPaid;
  final int? monthlyLimit;
  final int monthlyUsed;
  final int? remaining;
  final int? maxDurationSeconds;
  final List<String> allowedCountries;
  final int? resetAt;

  PhoneCallQuota({
    required this.hasAccess,
    required this.isPaid,
    this.monthlyLimit,
    this.monthlyUsed = 0,
    this.remaining,
    this.maxDurationSeconds,
    this.allowedCountries = const [],
    this.resetAt,
  });

  factory PhoneCallQuota.fromJson(Map<String, dynamic> json) {
    return PhoneCallQuota.fromGenerated(wire.GeneratedPhoneCallQuota.fromJson(json));
  }

  factory PhoneCallQuota.fromGenerated(wire.GeneratedPhoneCallQuota generated) {
    return PhoneCallQuota(
      hasAccess: generated.hasAccess,
      isPaid: generated.isPaid,
      monthlyLimit: generated.monthlyLimit,
      monthlyUsed: generated.monthlyUsed,
      remaining: generated.remaining,
      maxDurationSeconds: generated.maxDurationSeconds,
      allowedCountries: generated.allowedCountries,
      resetAt: generated.resetAt,
    );
  }

  wire.GeneratedPhoneCallQuota toGenerated() {
    return wire.GeneratedPhoneCallQuota(
      hasAccess: hasAccess,
      isPaid: isPaid,
      monthlyLimit: monthlyLimit,
      monthlyUsed: monthlyUsed,
      remaining: remaining,
      maxDurationSeconds: maxDurationSeconds,
      allowedCountries: allowedCountries,
      resetAt: resetAt,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class HeldAudioRecording {
  final String id;
  final int startedAt;
  final int seconds;

  const HeldAudioRecording({required this.id, required this.startedAt, required this.seconds});

  factory HeldAudioRecording.fromGenerated(wire.GeneratedHeldAudioRecording generated) {
    return HeldAudioRecording(id: generated.id, startedAt: generated.startedAt, seconds: generated.seconds);
  }
}

class HeldAudioSummary {
  final String state;
  bool get isRecovering => state == 'recovering';
  final int seconds;
  final int resetAt;
  final bool retainLive;
  final int count;
  final List<HeldAudioRecording> recordings;

  const HeldAudioSummary({
    this.state = 'paused',
    required this.seconds,
    required this.resetAt,
    required this.retainLive,
    this.count = 0,
    this.recordings = const [],
  });

  factory HeldAudioSummary.fromGenerated(wire.GeneratedHeldAudioSummary generated) {
    return HeldAudioSummary(
      state: generated.state,
      seconds: generated.seconds,
      resetAt: generated.resetAt,
      retainLive: generated.retainLive,
      count: generated.count,
      recordings: generated.recordings.map(HeldAudioRecording.fromGenerated).toList(),
    );
  }
}

/// Server-owned processing estimate and choice. Never infer a reset/upgrade
/// decision from the legacy held_audio recovery state or a client clock.
class ProcessingBacklog {
  final String state;
  final bool budgetExhausted;
  final int heldAudioCount;
  final int heldAudioSeconds;
  final int deferredConversations;
  final int deferredSeconds;
  final double estimatedUnits;
  final double estimatedHours;
  final double estimatedPercent;
  final double? remainingUnits;
  final bool exceedsRemaining;

  const ProcessingBacklog({
    required this.state,
    this.budgetExhausted = true,
    this.heldAudioCount = 0,
    this.heldAudioSeconds = 0,
    this.deferredConversations = 0,
    this.deferredSeconds = 0,
    this.estimatedUnits = 0,
    this.estimatedHours = 0,
    this.estimatedPercent = 0,
    this.remainingUnits,
    this.exceedsRemaining = false,
  });

  int get waitingSeconds => heldAudioSeconds + deferredSeconds;

  bool get isCapped => state == 'capped';
  bool get isWaitingChoice => state == 'waiting_choice';
  bool get isProcessing => state == 'processing';
  bool get isVisible => isCapped || isWaitingChoice || isProcessing;

  factory ProcessingBacklog.fromJson(Map<String, dynamic> json) =>
      ProcessingBacklog.fromGenerated(wire.GeneratedProcessingBacklog.fromJson(json));

  factory ProcessingBacklog.fromGenerated(wire.GeneratedProcessingBacklog generated) => ProcessingBacklog(
        state: generated.state,
        budgetExhausted: generated.budgetExhausted,
        heldAudioCount: generated.heldAudioCount,
        heldAudioSeconds: generated.heldAudioSeconds,
        deferredConversations: generated.deferredConversations,
        deferredSeconds: generated.deferredSeconds,
        estimatedUnits: generated.estimatedUnits,
        estimatedHours: generated.estimatedHours,
        estimatedPercent: generated.estimatedPercent,
        remainingUnits: generated.remainingUnits,
        exceedsRemaining: generated.exceedsRemaining,
      );

  wire.GeneratedProcessingBacklog toGenerated() => wire.GeneratedProcessingBacklog(
        state: state,
        budgetExhausted: budgetExhausted,
        heldAudioCount: heldAudioCount,
        heldAudioSeconds: heldAudioSeconds,
        deferredConversations: deferredConversations,
        deferredSeconds: deferredSeconds,
        estimatedUnits: estimatedUnits,
        estimatedHours: estimatedHours,
        estimatedPercent: estimatedPercent,
        remainingUnits: remainingUnits,
        exceedsRemaining: exceedsRemaining,
      );

  Map<String, dynamic> toJson() => {
        'state': state,
        'budget_exhausted': budgetExhausted,
        'held_audio_count': heldAudioCount,
        'held_audio_seconds': heldAudioSeconds,
        'deferred_conversations': deferredConversations,
        'deferred_seconds': deferredSeconds,
        'estimated_units': estimatedUnits,
        'estimated_hours': estimatedHours,
        'estimated_percent': estimatedPercent,
        'remaining_units': remainingUnits,
        'exceeds_remaining': exceedsRemaining,
      };
}

class UserSubscriptionResponse {
  final Subscription subscription;
  final int transcriptionSecondsUsed;
  final int transcriptionSecondsLimit;
  final int wordsTranscribedUsed;
  final int wordsTranscribedLimit;
  final int insightsGainedUsed;
  final int insightsGainedLimit;
  final List<SubscriptionPlan> availablePlans;
  final bool showSubscriptionUi;

  /// Backend-confirmed: this reader can still get an introductory free trial on checkout.
  final bool trialEligible;
  // Chat quota fields — populated from subscription endpoint
  final double chatQuotaUsed;
  final String? chatQuotaUnit;
  final double chatQuotaPercent;
  final bool chatQuotaAllowed;
  final int? chatQuotaResetAt;
  final PhoneCallQuota? phoneCallQuota;
  final TranscriptionAllowanceSnapshot? transcriptionAllowance;
  final HeldAudioSummary? heldAudio;
  final ProcessingBacklog? processingBacklog;

  UserSubscriptionResponse({
    required this.subscription,
    required this.transcriptionSecondsUsed,
    required this.transcriptionSecondsLimit,
    required this.wordsTranscribedUsed,
    required this.wordsTranscribedLimit,
    required this.insightsGainedUsed,
    required this.insightsGainedLimit,
    this.availablePlans = const [],
    this.showSubscriptionUi = true,
    this.trialEligible = false,
    this.chatQuotaUsed = 0.0,
    this.chatQuotaUnit,
    this.chatQuotaPercent = 0.0,
    this.chatQuotaAllowed = true,
    this.chatQuotaResetAt,
    this.phoneCallQuota,
    this.transcriptionAllowance,
    this.heldAudio,
    this.processingBacklog,
  });

  factory UserSubscriptionResponse.fromJson(Map<String, dynamic> json) =>
      UserSubscriptionResponse.fromGenerated(wire.GeneratedUserSubscriptionResponse.fromJson(json));

  factory UserSubscriptionResponse.fromGenerated(wire.GeneratedUserSubscriptionResponse generated) {
    return UserSubscriptionResponse(
      subscription: Subscription.fromGenerated(generated.subscription),
      processingBacklog:
          generated.processingBacklog == null ? null : ProcessingBacklog.fromGenerated(generated.processingBacklog!),
      transcriptionSecondsUsed: generated.transcriptionSecondsUsed,
      transcriptionSecondsLimit: generated.transcriptionSecondsLimit,
      wordsTranscribedUsed: generated.wordsTranscribedUsed,
      wordsTranscribedLimit: generated.wordsTranscribedLimit,
      insightsGainedUsed: generated.insightsGainedUsed,
      insightsGainedLimit: generated.insightsGainedLimit,
      availablePlans: generated.availablePlans.map(SubscriptionPlan.fromGenerated).toList(),
      showSubscriptionUi: generated.showSubscriptionUi,
      trialEligible: generated.trialEligible,
      chatQuotaUsed: generated.chatQuotaUsed,
      chatQuotaUnit: generated.chatQuotaUnit,
      chatQuotaPercent: generated.chatQuotaPercent,
      chatQuotaAllowed: generated.chatQuotaAllowed,
      chatQuotaResetAt: generated.chatQuotaResetAt,
      phoneCallQuota: generated.phoneCallQuota == null ? null : PhoneCallQuota.fromGenerated(generated.phoneCallQuota!),
      transcriptionAllowance: generated.transcriptionAllowance == null
          ? null
          : TranscriptionAllowanceSnapshot.fromGenerated(generated.transcriptionAllowance!),
      heldAudio: generated.heldAudio == null ? null : HeldAudioSummary.fromGenerated(generated.heldAudio!),
    );
  }

  wire.GeneratedUserSubscriptionResponse toGenerated() {
    return wire.GeneratedUserSubscriptionResponse(
      subscription: subscription.toGenerated(),
      processingBacklog: processingBacklog?.toGenerated(),
      transcriptionSecondsUsed: transcriptionSecondsUsed,
      transcriptionSecondsLimit: transcriptionSecondsLimit,
      wordsTranscribedUsed: wordsTranscribedUsed,
      wordsTranscribedLimit: wordsTranscribedLimit,
      insightsGainedUsed: insightsGainedUsed,
      insightsGainedLimit: insightsGainedLimit,
      availablePlans: availablePlans.map((plan) => plan.toGenerated()).toList(),
      showSubscriptionUi: showSubscriptionUi,
      chatQuotaUsed: chatQuotaUsed,
      chatQuotaUnit: chatQuotaUnit,
      chatQuotaPercent: chatQuotaPercent,
      chatQuotaAllowed: chatQuotaAllowed,
      chatQuotaResetAt: chatQuotaResetAt,
      phoneCallQuota: phoneCallQuota?.toGenerated(),
      transcriptionAllowance: transcriptionAllowance?.toGenerated(),
      heldAudio: heldAudio == null
          ? null
          : wire.GeneratedHeldAudioSummary(
              state: heldAudio!.state,
              recordings: heldAudio!.recordings
                  .map(
                    (row) =>
                        wire.GeneratedHeldAudioRecording(id: row.id, seconds: row.seconds, startedAt: row.startedAt),
                  )
                  .toList(),
              resetAt: heldAudio!.resetAt,
              retainLive: heldAudio!.retainLive,
              seconds: heldAudio!.seconds,
              count: heldAudio!.count,
            ),
    );
  }

  Map<String, dynamic> toJson() => {
        ...toGenerated().toJson(),
        if (processingBacklog != null) 'processing_backlog': processingBacklog!.toJson(),
      };
}
