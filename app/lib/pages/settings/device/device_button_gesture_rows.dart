import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/omi_button_action.dart';
import 'package:omi/pages/settings/device/device_control_sheets.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// One row per remappable tap gesture plus the fixed long press, for the Device page's
/// customization group.
///
/// The Device page rebuilds on every DeviceProvider tick, and each [OmiSettingsRow] relays
/// out (and so repaints) when rebuilt. These rows own their state and sit behind their own
/// [RepaintBoundary], so the page caches one instance: a tick neither rebuilds nor repaints
/// them. Bump [revision] to re-read the saved actions after something else changed them.
class DeviceButtonGestureRows extends StatefulWidget {
  const DeviceButtonGestureRows({super.key, this.revision = 0});

  final int revision;

  @override
  State<DeviceButtonGestureRows> createState() => _DeviceButtonGestureRowsState();
}

class _DeviceButtonGestureRowsState extends State<DeviceButtonGestureRows> {
  String _gestureTitle(OmiButtonGesture gesture) {
    return switch (gesture) {
      OmiButtonGesture.singleTap => context.l10n.singleTap,
      OmiButtonGesture.doubleTap => context.l10n.doubleTap,
      OmiButtonGesture.tripleTap => context.l10n.tripleTap,
    };
  }

  String _buttonActionLabel(OmiButtonAction action) {
    return switch (action) {
      OmiButtonAction.endConversation => context.l10n.endConversation,
      OmiButtonAction.muteUnmute => context.l10n.deviceOnboardingMuteUnmute,
      OmiButtonAction.starConversation => context.l10n.starConversation,
      OmiButtonAction.askQuestion => context.l10n.deviceOnboardingAskQuestionTitle,
      OmiButtonAction.none => context.l10n.doNothing,
    };
  }

  Future<void> _pickButtonAction(OmiButtonGesture gesture) async {
    final action = await showButtonActionSheet(
      context,
      gesture: gesture,
      current: SharedPreferencesUtil().buttonActionFor(gesture),
    );
    if (action == null || !mounted) return;
    // Persist first: setButtonActionFor returns a Future, which setState must not see.
    await SharedPreferencesUtil().setButtonActionFor(gesture, action);
    if (!mounted) return;
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final rows = <Widget>[
      for (final gesture in OmiButtonGesture.values)
        OmiSettingsRow(
          key: Key('button_gesture_${gesture.name}'),
          leading: const FaIcon(FontAwesomeIcons.handPointer),
          title: _gestureTitle(gesture),
          value: _buttonActionLabel(SharedPreferencesUtil().buttonActionFor(gesture)),
          onTap: () => _pickButtonAction(gesture),
          showChevron: true,
        ),
      OmiSettingsRow(
        key: const Key('button_gesture_longPress'),
        leading: const FaIcon(FontAwesomeIcons.powerOff),
        title: context.l10n.longPress,
        subtitle: context.l10n.longPressFixedSubtitle,
        value: context.l10n.powerOnOff,
        showChevron: false,
      ),
    ];
    // OmiSettingsGroup only divides its direct children, so divide these rows with the same 1pt
    // line, drawn as one coloured box rather than a Divider's five render objects.
    final divider = SizedBox(height: 1, width: double.infinity, child: ColoredBox(color: OmiColors.border));
    return RepaintBoundary(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < rows.length; i++) ...[
            if (i > 0) divider,
            rows[i],
          ],
        ],
      ),
    );
  }
}
