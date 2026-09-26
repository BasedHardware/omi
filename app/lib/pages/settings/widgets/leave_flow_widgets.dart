import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Shared pieces of the multi-step "leave" flows (delete account, cancel subscription).
///
/// Each step is its own pushed route, so the iOS edge swipe and Android system back step back
/// one step, exactly like the leading [OmiBackButton].

/// Remembers the flow's first route so a later step can leave the whole flow at once.
class LeaveFlowExit {
  Route<dynamic>? _firstRoute;

  /// True once the flow was left on purpose (kept, completed); a pop of the first step after that
  /// is not an abandon.
  bool finished = false;

  /// Call from the first step's `didChangeDependencies`.
  void attach(BuildContext firstStepContext) => _firstRoute ??= ModalRoute.of(firstStepContext);

  /// Pops every step of the flow, completing the first step's route with [result].
  void close<T extends Object?>(BuildContext context, [T? result]) {
    finished = true;
    final navigator = Navigator.of(context);
    final first = _firstRoute;
    if (first != null && first.isActive) {
      navigator.popUntil((route) => route == first);
    }
    navigator.pop(result);
  }
}

/// One step of a leave flow: back button, step indicator, a large title and subtitle, the step's
/// body and a bottom action area.
class LeaveFlowStepScaffold extends StatelessWidget {
  const LeaveFlowStepScaffold({
    super.key,
    required this.step,
    required this.stepCount,
    required this.title,
    this.subtitle,
    required this.body,
    required this.actions,
    this.canPop = true,
    this.onPopInvoked,
  });

  /// Zero-based index of this step.
  final int step;
  final int stepCount;
  final String title;
  final String? subtitle;
  final Widget body;
  final Widget actions;

  /// False only while an operation that cannot be cancelled runs.
  final bool canPop;
  final void Function(bool didPop)? onPopInvoked;

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: canPop,
      onPopInvokedWithResult: (didPop, _) => onPopInvoked?.call(didPop),
      child: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: Scaffold(
          backgroundColor: OmiColors.surface0,
          appBar: AppBar(
            leading: OmiBackButton(onPressed: canPop ? null : () {}),
            title: _StepIndicator(step: step, count: stepCount),
          ),
          body: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.md, OmiSpacing.xl, 0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Semantics(header: true, child: Text(title, style: OmiType.title2)),
                    if (subtitle != null) ...[
                      const SizedBox(height: OmiSpacing.xxs),
                      Text(subtitle!, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: OmiSpacing.lg),
              Expanded(child: body),
              SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.sm, OmiSpacing.xl, OmiSpacing.md),
                  child: actions,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StepIndicator extends StatelessWidget {
  const _StepIndicator({required this.step, required this.count});

  final int step;
  final int count;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: context.l10n.leaveFlowStepOf(step + 1, count),
      child: ExcludeSemantics(
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(count, (i) {
            return Container(
              width: i == step ? 24 : 8,
              height: 4,
              margin: const EdgeInsets.symmetric(horizontal: 3),
              decoration: BoxDecoration(
                color: i <= step ? OmiColors.textPrimary : OmiColors.surface3,
                borderRadius: OmiRadius.pillAll,
              ),
            );
          }),
        ),
      ),
    );
  }
}

/// A selectable reason row (radio semantics).
class LeaveFlowReasonTile extends StatelessWidget {
  const LeaveFlowReasonTile({
    super.key,
    required this.icon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final FaIconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      inMutuallyExclusiveGroup: true,
      child: Material(
        color: selected ? OmiColors.surface2 : OmiColors.surface1,
        shape: RoundedRectangleBorder(
          borderRadius: OmiRadius.mdAll,
          side: BorderSide(color: selected ? OmiColors.textTertiary : OmiColors.border),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 56),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.sm),
              child: Row(
                children: [
                  _IconBadge(icon: icon, color: selected ? OmiColors.textPrimary : OmiColors.textSecondary),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: Text(
                      label,
                      style: OmiType.subhead.copyWith(
                        color: selected ? OmiColors.textPrimary : OmiColors.textSecondary,
                      ),
                    ),
                  ),
                  ExcludeSemantics(
                    child: Icon(
                      selected ? Icons.check_circle_rounded : Icons.circle_outlined,
                      size: 22,
                      color: selected ? OmiColors.textPrimary : OmiColors.textTertiary,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A row that states one consequence of leaving.
class LeaveFlowConsequenceRow extends StatelessWidget {
  const LeaveFlowConsequenceRow({super.key, required this.icon, required this.text});

  final FaIconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
      child: Container(
        constraints: const BoxConstraints(minHeight: 56),
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.sm),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.mdAll,
          border: Border.all(color: OmiColors.border),
        ),
        child: Row(
          children: [
            _IconBadge(icon: icon, color: OmiColors.textSecondary),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              child: Text(text, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.3)),
            ),
          ],
        ),
      ),
    );
  }
}

/// A tinted notice box (warning or danger) above a step's list.
class LeaveFlowNotice extends StatelessWidget {
  const LeaveFlowNotice({super.key, required this.icon, required this.text, required this.color});

  final FaIconData icon;
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(OmiSpacing.sm),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: OmiRadius.mdAll,
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: ExcludeSemantics(child: FaIcon(icon, size: 14, color: color)),
            ),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(child: Text(text, style: OmiType.footnote.copyWith(color: color, height: 1.5))),
          ],
        ),
      ),
    );
  }
}

/// The multi-line feedback field of a leave flow.
class LeaveFlowTextField extends StatelessWidget {
  const LeaveFlowTextField({super.key, required this.controller, required this.maxLength, this.hint});

  final TextEditingController controller;
  final int maxLength;
  final String? hint;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
      child: TextField(
        controller: controller,
        maxLines: 5,
        maxLength: maxLength,
        style: OmiType.subhead.copyWith(height: 1.5),
        decoration: leaveFlowInputDecoration(hint: hint),
      ),
    );
  }
}

/// Input decoration shared by the leave flows' text fields.
InputDecoration leaveFlowInputDecoration({String? hint, Color focusColor = OmiColors.textTertiary}) {
  OutlineInputBorder border(Color color) =>
      OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide(color: color));
  return InputDecoration(
    hintText: hint,
    hintStyle: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
    filled: true,
    fillColor: OmiColors.surface1,
    border: border(OmiColors.border),
    enabledBorder: border(OmiColors.border),
    focusedBorder: border(focusColor),
    counterStyle: OmiType.caption.copyWith(color: OmiColors.textTertiary),
    contentPadding: const EdgeInsets.all(OmiSpacing.md),
  );
}

class _IconBadge extends StatelessWidget {
  const _IconBadge({required this.icon, required this.color});

  final FaIconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: Container(
        width: 36,
        height: 36,
        decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
        child: Center(child: FaIcon(icon, size: 14, color: color)),
      ),
    );
  }
}
