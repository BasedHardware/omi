import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/phone_calls/phone_setup_intro_page.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// The user's verified caller-ID numbers, with delete.
///
/// Safe to open from anywhere (Settings, the Phone page): it reloads the numbers on open, shows a
/// spinner until they arrive, and with no verified number offers the setup flow.
class PhoneCallSettingsPage extends StatefulWidget {
  const PhoneCallSettingsPage({super.key});

  @override
  State<PhoneCallSettingsPage> createState() => _PhoneCallSettingsPageState();
}

class _PhoneCallSettingsPageState extends State<PhoneCallSettingsPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<PhoneCallProvider>().loadVerifiedNumbers();
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.phoneCallSettingsTitle)),
      body: Consumer<PhoneCallProvider>(
        builder: (context, provider, _) {
          if (!provider.numbersLoaded) return const OmiLoadingState();
          if (provider.verifiedNumbers.isEmpty) {
            return OmiEmptyState(
              icon: Icons.phone_outlined,
              title: l10n.phoneNoVerifiedNumbersTitle,
              message: l10n.phoneNoVerifiedNumbersMessage,
              action: OmiButton(
                label: l10n.phoneGetStarted,
                size: OmiButtonSize.compact,
                onPressed: () => routeToPage(context, const PhoneSetupIntroPage()),
              ),
            );
          }
          return ListView(
            padding: const EdgeInsets.all(OmiSpacing.md),
            children: [
              OmiSettingsGroup(
                header: l10n.yourVerifiedNumbers,
                headerSubtitle: l10n.verifiedNumbersDescription,
                children: [
                  for (final number in provider.verifiedNumbers)
                    OmiSettingsRow(
                      leading: const Icon(Icons.phone),
                      title: number.phoneNumber,
                      subtitle: _formatVerifiedAt(context, number.verifiedAt),
                      trailing: OmiIconButton(
                        icon: const Icon(Icons.delete_outline),
                        label: l10n.phoneDeleteButton,
                        isDestructive: true,
                        onPressed: () => _confirmDelete(context, provider, number.id, number.phoneNumber),
                      ),
                    ),
                ],
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _confirmDelete(BuildContext context, PhoneCallProvider provider, String id, String phoneNumber) async {
    final l10n = context.l10n;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.deletePhoneNumberConfirm(phoneNumber),
      message: l10n.deletePhoneNumberWarning,
      confirmLabel: l10n.phoneDeleteButton,
      destructive: true,
    );
    if (!confirmed) return;
    final success = await provider.deleteNumber(id);
    if (!success && context.mounted) {
      OmiFeedback.error(
        context,
        l10n.phoneDeleteNumberFailed,
        actionLabel: l10n.tryAgain,
        onAction: () => _retryDelete(provider, id),
      );
    }
  }

  Future<void> _retryDelete(PhoneCallProvider provider, String id) async {
    final success = await provider.deleteNumber(id);
    if (!success && mounted) OmiFeedback.error(context, context.l10n.phoneDeleteNumberFailed);
  }

  String _formatVerifiedAt(BuildContext context, String verifiedAt) {
    final l10n = context.l10n;
    final dt = DateTime.tryParse(verifiedAt)?.toLocal();
    if (dt == null) return l10n.verifiedFallback;
    final diff = DateTime.now().difference(dt);
    if (diff.inMinutes < 60) return l10n.verifiedMinutesAgo(diff.inMinutes < 0 ? 0 : diff.inMinutes);
    if (diff.inHours < 24) return l10n.verifiedHoursAgo(diff.inHours);
    if (diff.inDays < 7) return l10n.verifiedDaysAgo(diff.inDays);
    return l10n.verifiedOnDate(OmiDateFormat.of(context).date(dt));
  }
}
