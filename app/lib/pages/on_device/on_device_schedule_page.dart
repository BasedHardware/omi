import 'package:flutter/material.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/on_device/on_device_components.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The schedule's name, for a settings value.
String onDeviceScheduleLabel(AppLocalizations l10n, OnDeviceSchedule schedule) {
  switch (schedule) {
    case OnDeviceSchedule.whileCharging:
      return l10n.onDeviceScheduleCharging;
    case OnDeviceSchedule.everyFewHours:
      return l10n.onDeviceScheduleHours;
    case OnDeviceSchedule.asYouTalk:
      return l10n.onDeviceScheduleLive;
  }
}

/// When recordings waiting on the phone get transcribed. Step 2 of 2 in setup ([step] set), or a
/// plain settings page. A choice applies as soon as it is made; Done turns the feature on and
/// returns true.
class OnDeviceSchedulePage extends StatelessWidget {
  const OnDeviceSchedulePage({super.key, this.controller, this.step});

  final OnDeviceTranscriptionController? controller;
  final int? step;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final controller = this.controller ?? OnDeviceTranscriptionController.instance;
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.onDeviceScheduleTitle)),
      body: SafeArea(
        top: false,
        child: ListenableBuilder(
          listenable: controller,
          builder: (context, _) {
            final settings = controller.settings;
            Widget option(OnDeviceSchedule schedule, String body, String? meta) => Padding(
                  padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
                  child: OnDeviceChoiceCard(
                    key: Key('on_device_schedule_${schedule.storageId}'),
                    title: onDeviceScheduleLabel(l10n, schedule),
                    badge: schedule == OnDeviceSchedule.whileCharging ? l10n.paywallRecommended : null,
                    body: body,
                    meta: meta,
                    selected: settings.schedule == schedule,
                    onSelected: () => controller.updateSettings(settings.copyWith(schedule: schedule)),
                  ),
                );
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.xs, OmiSpacing.lg, OmiSpacing.lg),
                    children: [
                      if (step != null) ...[
                        OnDeviceStepLabel(step: step!, total: 2),
                        const SizedBox(height: OmiSpacing.xs),
                      ],
                      Semantics(header: true, child: Text(l10n.onDeviceScheduleHeadline, style: OmiType.title1)),
                      const SizedBox(height: OmiSpacing.xs),
                      Text(l10n.onDeviceScheduleBody,
                          style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.4)),
                      const SizedBox(height: OmiSpacing.xl),
                      option(OnDeviceSchedule.whileCharging, l10n.onDeviceScheduleChargingBody, null),
                      option(OnDeviceSchedule.everyFewHours, l10n.onDeviceScheduleHoursBody, l10n.onDeviceUsesBattery),
                      option(OnDeviceSchedule.asYouTalk, l10n.onDeviceScheduleLiveBody, l10n.onDeviceUsesBattery),
                    ],
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.xs, OmiSpacing.lg, OmiSpacing.md),
                  child: OmiButton(
                    key: const Key('on_device_schedule_done'),
                    label: l10n.done,
                    expand: true,
                    onPressed: () async {
                      await controller.updateSettings(controller.settings.copyWith(enabled: true));
                      if (context.mounted) Navigator.of(context).pop(true);
                    },
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
