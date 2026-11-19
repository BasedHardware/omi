// Owns the existing plans promo field and its optional current-plan action.
// Checkout keeps its controller/error; applying never selects a price or plan.
import 'package:flutter/material.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class PlanPromoCodeField extends StatefulWidget {
  const PlanPromoCodeField(
      {super.key,
      required this.controller,
      required this.error,
      required this.canApply,
      required this.busy,
      required this.applyEnabled,
      required this.applied,
      required this.onApply,
      required this.onChanged});

  final TextEditingController controller;
  final String? error;
  final bool canApply;
  final bool busy;
  final bool applyEnabled;
  final bool applied;
  final Future<void> Function() onApply;
  final VoidCallback onChanged;

  @override
  State<PlanPromoCodeField> createState() => _PlanPromoCodeFieldState();
}

class _PlanPromoCodeFieldState extends State<PlanPromoCodeField> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    OutlineInputBorder border(Color color) =>
        OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide(color: color));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Semantics(
          button: true,
          expanded: _expanded,
          child: InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            borderRadius: OmiRadius.smAll,
            child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 44),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  ExcludeSemantics(child: Icon(Icons.local_offer_outlined, color: OmiColors.textSecondary, size: 18)),
                  const SizedBox(width: OmiSpacing.xs),
                  Text(l10n.promoCode, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                  const SizedBox(width: OmiSpacing.xxs),
                  ExcludeSemantics(
                      child: Icon(_expanded ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                          color: OmiColors.textSecondary, size: 20)),
                ])),
          )),
      if (_expanded) ...[
        const SizedBox(height: OmiSpacing.xs),
        TextField(
          key: const ValueKey('plans_sheet_promo_code'),
          controller: widget.controller,
          enabled: !widget.busy,
          textInputAction: widget.canApply ? TextInputAction.done : null,
          onSubmitted: widget.canApply ? (_) => widget.onApply() : null,
          style: OmiType.callout,
          autocorrect: false,
          enableSuggestions: false,
          decoration: InputDecoration(
            hintText: l10n.enterPromoCode,
            hintStyle: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
            filled: true,
            fillColor: OmiColors.surface2,
            border: border(OmiColors.border),
            enabledBorder: border(OmiColors.border),
            focusedBorder: border(OmiColors.accent),
            errorBorder: border(OmiColors.danger),
            focusedErrorBorder: border(OmiColors.danger),
            errorText: widget.error,
            errorMaxLines: 4,
            contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
            suffixIcon: widget.controller.text.isNotEmpty
                ? OmiIconButton(
                    icon: const Icon(Icons.clear, size: 20),
                    label: l10n.clear,
                    color: OmiColors.textSecondary,
                    onPressed: widget.busy
                        ? null
                        : () {
                            widget.controller.clear();
                            widget.onChanged();
                          },
                  )
                : null,
          ),
          onChanged: (_) => widget.onChanged(),
        ),
        if (widget.canApply) ...[
          const SizedBox(height: OmiSpacing.sm),
          OmiButton.secondary(
            key: const ValueKey('plans_sheet_apply_code'),
            label: l10n.applyCodeToCurrentPlan,
            expand: true,
            isLoading: widget.busy,
            onPressed:
                !widget.applyEnabled || widget.busy || widget.controller.text.trim().isEmpty ? null : widget.onApply,
          ),
        ],
        if (widget.applied)
          Semantics(
              liveRegion: true,
              child: Text(
                l10n.subscriptionCodeResult('applied'),
                key: const ValueKey('plans_sheet_code_applied'),
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
              )),
      ],
    ]);
  }
}
