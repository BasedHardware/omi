import 'package:flutter/material.dart';

import 'package:webview_flutter/webview_flutter.dart';

import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

const _trainingUrl = 'https://omi.me/training';

/// The "Get free unlimited access" card in the plans sheet, for the training-data program.
///
/// Approved or pending members open the program page; everyone else starts the opt-in with
/// [onOptIn].
class TrainingDataOptionCard extends StatelessWidget {
  const TrainingDataOptionCard({
    super.key,
    required this.optedIn,
    required this.status,
    required this.isLoading,
    required this.onOptIn,
  });

  final bool optedIn;
  final String? status;
  final bool isLoading;
  final VoidCallback onOptIn;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final approved = optedIn && status == 'approved';
    final pending = optedIn && status == 'pending_review';
    final subtitle = approved
        ? l10n.trainingDataProgram
        : pending
            ? l10n.yourRequestUnderReview
            : l10n.shareDataForTraining;
    final VoidCallback? onTap = approved || pending
        ? () => routeToPage(context, TrainingProgramPage(title: l10n.omiTraining))
        : (isLoading ? null : onOptIn);

    return Semantics(
      button: true,
      child: Material(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.lg),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(l10n.getFreeUnlimitedAccess, style: OmiType.headline),
                      const SizedBox(height: OmiSpacing.xxs),
                      Text(subtitle, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                    ],
                  ),
                ),
                const SizedBox(width: OmiSpacing.xs),
                if (approved) ...[PlanBadge(label: l10n.active, inverted: true), const SizedBox(width: OmiSpacing.xs)],
                if (!approved && !pending && isLoading)
                  const OmiSpinner(size: OmiSpinnerSize.small)
                else
                  const ExcludeSemantics(child: Icon(Icons.chevron_right, color: OmiColors.textSecondary)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The training-data program page (omi.me/training) in a web view, with a load-failure state.
class TrainingProgramPage extends StatefulWidget {
  const TrainingProgramPage({super.key, required this.title});

  final String title;

  @override
  State<TrainingProgramPage> createState() => _TrainingProgramPageState();
}

class _TrainingProgramPageState extends State<TrainingProgramPage> {
  late final WebViewController _controller;
  bool _loading = true;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (_) {
            if (mounted) setState(() => _loading = true);
          },
          onPageFinished: (_) {
            if (mounted) setState(() => _loading = false);
          },
          onWebResourceError: (error) {
            // Only a failure of the page itself; a broken image or script still leaves a page.
            if (error.isForMainFrame != false && mounted) {
              setState(() {
                _failed = true;
                _loading = false;
              });
            }
          },
        ),
      );
    _load();
  }

  void _load() {
    setState(() {
      _failed = false;
      _loading = true;
    });
    _controller.loadRequest(Uri.parse(_trainingUrl));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(widget.title)),
      body: _failed
          ? OmiErrorState(message: context.l10n.couldNotLoadPage, onRetry: _load)
          : Stack(
              children: [
                WebViewWidget(controller: _controller),
                if (_loading) const OmiLoadingState(),
              ],
            ),
    );
  }
}

/// Explains the training-data program and asks for an explicit agreement. Resolves `true` only
/// when the reader ticked the agreement and chose Submit Request.
Future<bool> showTrainingDataOptInDialog(BuildContext context) async {
  final agreed = await showDialog<bool>(context: context, builder: (_) => const _TrainingDataOptInDialog());
  return agreed ?? false;
}

class _TrainingDataOptInDialog extends StatefulWidget {
  const _TrainingDataOptInDialog();

  @override
  State<_TrainingDataOptInDialog> createState() => _TrainingDataOptInDialogState();
}

class _TrainingDataOptInDialogState extends State<_TrainingDataOptInDialog> {
  bool _checked = false;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return OmiAlertDialog(
      title: l10n.omiTraining,
      content: Material(
        type: MaterialType.transparency,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l10n.getOmiUnlimitedFree, textAlign: TextAlign.start, style: OmiType.subhead.copyWith(height: 1.5)),
              const SizedBox(height: OmiSpacing.sm),
              Text(
                l10n.trainingDataBullets,
                textAlign: TextAlign.start,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.5),
              ),
              const SizedBox(height: OmiSpacing.xs),
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: OmiButton.tertiary(
                  label: l10n.learnMoreAtOmiTraining,
                  size: OmiButtonSize.compact,
                  onPressed: () => routeToPage(context, TrainingProgramPage(title: l10n.trainingDataProgram)),
                ),
              ),
              OmiCheckboxRow(
                label: l10n.agreeToContributeData,
                value: _checked,
                onChanged: (value) => setState(() => _checked = value),
              ),
            ],
          ),
        ),
      ),
      actions: [
        OmiDialogAction(label: l10n.cancel, onPressed: () => Navigator.of(context).pop(false)),
        OmiDialogAction(
          label: l10n.submitRequest,
          isDefault: true,
          onPressed: _checked ? () => Navigator.of(context).pop(true) : null,
        ),
      ],
    );
  }
}
