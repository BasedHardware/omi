import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart' as ble;
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:omi/backend/auth.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/dev_env.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/prod_env.dart';
import 'package:omi/firebase_options_dev.dart' as dev;
import 'package:omi/firebase_options_prod.dart' as prod;
import 'package:omi/flavors.dart';
import 'package:omi/main.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/growthbook.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/features/calendar.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:omi/utils/execution_gaurd.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;
import 'package:posthog_flutter/posthog_flutter.dart';

Future<void> appInit() async {
  if (F.env == Environment.prod) {
    Env.init(ProdEnv());
    await Firebase.initializeApp(options: prod.DefaultFirebaseOptions.currentPlatform);
  } else {
    Env.init(DevEnv());
    await Firebase.initializeApp(options: dev.DefaultFirebaseOptions.currentPlatform);
  }

  if (!ExecutionGuard.isWeb) {
    FlutterForegroundTask.initCommunicationPort();
    await IntercomManager().initIntercom();
    ble.FlutterBluePlus.setLogLevel(ble.LogLevel.info, color: true);
  }

  if (Env.posthogApiKey != null) {
    final config = PostHogConfig(Env.posthogApiKey!);
    config.debug = true;
    config.captureApplicationLifecycleEvents = true;
    config.host = 'https://us.i.posthog.com';
    await Posthog().setup(config);
  }

  ServiceManager.init();

  await NotificationService.instance.initialize();
  await SharedPreferencesUtil.init();
  await MixpanelManager.init();

  // TODO: thinh, move to app start
  await ServiceManager.instance().start();

  bool isAuth = (await getIdToken()) != null;
  if (isAuth) MixpanelManager().identify();
  initOpus(await opus_flutter.load());

  await GrowthbookUtil.init();
  CalendarUtil.init();

  if (Env.instabugApiKey != null) {
    await Instabug.setWelcomeMessageMode(WelcomeMessageMode.disabled);
    runZonedGuarded(
      () async {
        Instabug.init(
          token: Env.instabugApiKey!,
          invocationEvents: [InvocationEvent.none],
        );
        if (isAuth) {
          Instabug.identifyUser(
            FirebaseAuth.instance.currentUser?.email ?? '',
            SharedPreferencesUtil().fullName,
            SharedPreferencesUtil().uid,
          );
        }
        FlutterError.onError = (FlutterErrorDetails details) {
          Zone.current.handleUncaughtError(details.exception, details.stack ?? StackTrace.empty);
        };
        Instabug.setColorTheme(ColorTheme.dark);
        runApp(const MyApp());
      },
      CrashReporting.reportCrash,
    );
  } else {
    runApp(const MyApp());
  }
}
