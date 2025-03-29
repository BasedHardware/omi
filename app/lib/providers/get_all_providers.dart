import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/persona/persona_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/calendar_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/facts_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:provider/provider.dart';

import 'package:flutter/widgets.dart';

dynamic getAllProviders() {
  return [
    ListenableProvider(create: (context) => ConnectivityProvider()),
    ChangeNotifierProvider(create: (context) => AuthenticationProvider()),
    ChangeNotifierProvider(create: (context) => ConversationProvider()),
    ListenableProvider(create: (context) => AppProvider()),
    ChangeNotifierProxyProvider<AppProvider, MessageProvider>(
      create: (context) => MessageProvider(),
      update: (BuildContext context, value, MessageProvider? previous) =>
          (previous?..updateAppProvider(value)) ?? MessageProvider(),
    ),
    ChangeNotifierProxyProvider2<ConversationProvider, MessageProvider, CaptureProvider>(
      create: (context) => CaptureProvider(),
      update: (BuildContext context, conversation, message, CaptureProvider? previous) =>
          (previous?..updateProviderInstances(conversation, message)) ?? CaptureProvider(),
    ),
    ChangeNotifierProxyProvider<CaptureProvider, DeviceProvider>(
      create: (context) => DeviceProvider(),
      update: (BuildContext context, captureProvider, DeviceProvider? previous) =>
          (previous?..setProviders(captureProvider)) ?? DeviceProvider(),
    ),
    ChangeNotifierProxyProvider<DeviceProvider, OnboardingProvider>(
      create: (context) => OnboardingProvider(),
      update: (BuildContext context, value, OnboardingProvider? previous) =>
          (previous?..setDeviceProvider(value)) ?? OnboardingProvider(),
    ),
    ListenableProvider(create: (context) => HomeProvider()),
    ChangeNotifierProxyProvider<DeviceProvider, SpeechProfileProvider>(
      create: (context) => SpeechProfileProvider(),
      update: (BuildContext context, device, SpeechProfileProvider? previous) =>
          (previous?..setProviders(device)) ?? SpeechProfileProvider(),
    ),
    ChangeNotifierProxyProvider2<AppProvider, ConversationProvider, ConversationDetailProvider>(
      create: (context) => ConversationDetailProvider(),
      update: (BuildContext context, app, conversation, ConversationDetailProvider? previous) =>
          (previous?..setProviders(app, conversation)) ?? ConversationDetailProvider(),
    ),
    ChangeNotifierProvider(create: (context) => CalenderProvider()),
    ChangeNotifierProvider(create: (context) => DeveloperModeProvider()),
    ChangeNotifierProxyProvider<AppProvider, AddAppProvider>(
      create: (context) => AddAppProvider(),
      update: (BuildContext context, value, AddAppProvider? previous) =>
          (previous?..setAppProvider(value)) ?? AddAppProvider(),
    ),
    ChangeNotifierProvider(create: (context) => PaymentMethodProvider()),
    ChangeNotifierProvider(create: (context) => PersonaProvider()),
    ChangeNotifierProvider(create: (context) => FactsProvider()),
  ];
}
