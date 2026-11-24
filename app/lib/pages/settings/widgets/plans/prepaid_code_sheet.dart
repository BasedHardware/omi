// "Have a code?": redeem a fully prepaid Omi Pro code with no card and no checkout.
// Shown only while the server switch is on (UsageProvider.canRedeemPrepaidCode). No price or payment here.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/payment.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

typedef PrepaidCodeRedeem = Future<ApiResult<PrepaidCodeRedemption>> Function(String code);

/// The redeem call the entry uses; tests replace it.
@visibleForTesting
PrepaidCodeRedeem prepaidCodeRedeemer = redeemPrepaidCode;

/// The entry row. [style] lets a page with its own type (the trial paywall) keep its look.
/// [onRedeemed] runs after the sheet closes on a redeemed code; [onDiscountCode] takes a valid code that is a
/// discount rather than prepaid, for the caller's existing promo-code field.
class PrepaidCodeEntry extends StatelessWidget {
  const PrepaidCodeEntry({
    super.key,
    this.style,
    this.center = false,
    this.onRedeemed,
    this.onDiscountCode,
  });

  final TextStyle? style;
  final bool center;
  final VoidCallback? onRedeemed;
  final ValueChanged<String>? onDiscountCode;

  @override
  Widget build(BuildContext context) {
    final textStyle = style ?? OmiType.subhead.copyWith(color: OmiColors.textSecondary);
    return Semantics(
      button: true,
      child: InkWell(
        key: const ValueKey('prepaid_code_entry'),
        onTap: () async {
          final redeemed = await showPrepaidCodeSheet(context, onDiscountCode: onDiscountCode);
          if (redeemed) onRedeemed?.call();
        },
        borderRadius: OmiRadius.smAll,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: center ? MainAxisAlignment.center : MainAxisAlignment.start,
            children: [
              ExcludeSemantics(child: Icon(Icons.redeem_outlined, color: textStyle.color, size: 18)),
              const SizedBox(width: OmiSpacing.xs),
              Flexible(child: Text(context.l10n.prepaidCodeEntry, style: textStyle)),
            ],
          ),
        ),
      ),
    );
  }
}

/// True when a code was redeemed before the sheet closed.
Future<bool> showPrepaidCodeSheet(
  BuildContext context, {
  ValueChanged<String>? onDiscountCode,
  PrepaidCodeRedeem? redeem,
}) async {
  final usage = context.read<UsageProvider>();
  var redeemed = false;
  String? discountCode;
  await showOmiSheet<void>(
    context: context,
    title: context.l10n.prepaidCodeTitle,
    builder: (sheetContext) => PrepaidCodeSheet(
      redeem: redeem ?? prepaidCodeRedeemer,
      onRedeemed: () {
        redeemed = true;
        // The Stripe webhook grants Pro a moment after the subscription exists: read now and once more.
        unawaited(usage.fetchSubscription());
        Future.delayed(const Duration(seconds: 4), () => unawaited(usage.fetchSubscription()));
      },
      onDiscountCode: onDiscountCode == null
          ? null
          : (code) {
              discountCode = code;
              Navigator.of(sheetContext).pop();
            },
    ),
  );
  final handOff = discountCode;
  if (handOff != null) onDiscountCode?.call(handOff);
  return redeemed;
}

class PrepaidCodeSheet extends StatefulWidget {
  const PrepaidCodeSheet({
    super.key,
    required this.redeem,
    this.onRedeemed,
    this.onDiscountCode,
  });

  final PrepaidCodeRedeem redeem;
  final VoidCallback? onRedeemed;

  /// Set where a discount code has somewhere to go (the plans sheet's promo field) instead of a dead end.
  final ValueChanged<String>? onDiscountCode;

  @override
  State<PrepaidCodeSheet> createState() => _PrepaidCodeSheetState();
}

class _PrepaidCodeSheetState extends State<PrepaidCodeSheet> {
  final _controller = TextEditingController();
  bool _busy = false;
  String? _errorReason;
  PrepaidCodeRedemption? _redeemed;
  String _text = '';

  @override
  void initState() {
    super.initState();
    // Paste, autofill and programmatic input skip onChanged; the button and error follow the text itself.
    _controller.addListener(() {
      if (_controller.text == _text) return;
      setState(() {
        _text = _controller.text;
        _errorReason = null;
      });
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  static String _reason(ApiProblem problem) {
    if (problem.statusCode == 429) return 'rateLimited';
    return switch (problem.detail) {
      'invalid_code' => 'invalid',
      'code_used' => 'used',
      'code_expired' => 'expired',
      'has_plan' => 'hasPlan',
      'not_prepaid' => 'notPrepaid',
      'not_eligible' => 'notEligible',
      _ => 'other',
    };
  }

  Future<void> _submit() async {
    final code = _controller.text.trim();
    if (_busy || code.isEmpty) return;
    setState(() {
      _busy = true;
      _errorReason = null;
    });
    ApiResult<PrepaidCodeRedemption> result;
    try {
      result = await widget.redeem(code);
    } catch (_) {
      result = const ApiFailure(ApiProblem(ApiProblemKind.transport));
    }
    if (!mounted) return;
    switch (result) {
      case ApiSuccess<PrepaidCodeRedemption>(:final data):
        OmiHaptics.success();
        setState(() {
          _busy = false;
          _redeemed = data;
        });
        widget.onRedeemed?.call();
      case ApiFailure<PrepaidCodeRedemption>(:final problem):
        final reason = _reason(problem);
        final handOff = widget.onDiscountCode;
        if (reason == 'notPrepaid' && handOff != null) {
          handOff(code);
          return;
        }
        setState(() {
          _busy = false;
          _errorReason = reason;
        });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final redeemed = _redeemed;
    if (redeemed != null) {
      final date = OmiDateFormat.of(context).date(redeemed.endsAt);
      return Padding(
        key: const ValueKey('prepaid_code_success'),
        padding: const EdgeInsets.only(bottom: OmiSpacing.lg),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const SizedBox(height: OmiSpacing.sm),
          ExcludeSemantics(child: Icon(Icons.check_circle_outline, color: OmiColors.success, size: 40)),
          const SizedBox(height: OmiSpacing.sm),
          Semantics(
            liveRegion: true,
            child: Text(l10n.prepaidCodeRedeemed, style: OmiType.headline, textAlign: TextAlign.center),
          ),
          const SizedBox(height: OmiSpacing.xs),
          Text(
            l10n.yourPlanEndsOn(redeemed.plan, date),
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: OmiSpacing.lg),
          OmiButton(
            key: const ValueKey('prepaid_code_done'),
            label: l10n.done,
            expand: true,
            onPressed: () => Navigator.of(context).maybePop(),
          ),
        ]),
      );
    }
    OutlineInputBorder border(Color color) =>
        OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide(color: color));
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.lg),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        TextField(
          key: const ValueKey('prepaid_code_field'),
          controller: _controller,
          autofocus: true,
          enabled: !_busy,
          autocorrect: false,
          enableSuggestions: false,
          textCapitalization: TextCapitalization.characters,
          textInputAction: TextInputAction.done,
          onSubmitted: (_) => _submit(),
          style: OmiType.callout,
          decoration: InputDecoration(
            hintText: l10n.prepaidCodeFieldHint,
            hintStyle: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
            filled: true,
            fillColor: OmiColors.surface2,
            border: border(OmiColors.border),
            enabledBorder: border(OmiColors.border),
            focusedBorder: border(OmiColors.accent),
            errorBorder: border(OmiColors.danger),
            focusedErrorBorder: border(OmiColors.danger),
            errorText: _errorReason == null ? null : l10n.prepaidCodeResult(_errorReason!),
            errorMaxLines: 4,
            contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
          ),
        ),
        const SizedBox(height: OmiSpacing.md),
        OmiButton(
          key: const ValueKey('prepaid_code_redeem'),
          label: l10n.prepaidCodeRedeem,
          expand: true,
          isLoading: _busy,
          onPressed: _busy || _controller.text.trim().isEmpty ? null : _submit,
        ),
      ]),
    );
  }
}
