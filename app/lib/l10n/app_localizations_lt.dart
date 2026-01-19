// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Lithuanian (`lt`).
class AppLocalizationsLt extends AppLocalizations {
  AppLocalizationsLt([String locale = 'lt']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Pokalbis';

  @override
  String get transcriptTab => 'Transkripcija';

  @override
  String get actionItemsTab => 'Užduotys';

  @override
  String get deleteConversationTitle => 'Ištrinti pokalbį?';

  @override
  String get deleteConversationMessage => 'Ar tikrai norite ištrinti šį pokalbį? Šio veiksmo negalima atšaukti.';

  @override
  String get confirm => 'Patvirtinti';

  @override
  String get cancel => 'Atšaukti';

  @override
  String get ok => 'Gerai';

  @override
  String get delete => 'Ištrinti';

  @override
  String get add => 'Pridėti';

  @override
  String get update => 'Atnaujinti';

  @override
  String get save => 'Išsaugoti';

  @override
  String get edit => 'Redaguoti';

  @override
  String get close => 'Uždaryti';

  @override
  String get clear => 'Išvalyti';

  @override
  String get copyTranscript => 'Kopijuoti transkripciją';

  @override
  String get copySummary => 'Kopijuoti santrauką';

  @override
  String get testPrompt => 'Testuoti užklausą';

  @override
  String get reprocessConversation => 'Perdoroti pokalbį';

  @override
  String get deleteConversation => 'Ištrinti pokalbį';

  @override
  String get contentCopied => 'Turinys nukopijuotas į iškarpinę';

  @override
  String get failedToUpdateStarred => 'Nepavyko atnaujinti žvaigždutės būsenos.';

  @override
  String get conversationUrlNotShared => 'Pokalbio nuorodos nepavyko bendrinti.';

  @override
  String get errorProcessingConversation => 'Klaida dorojant pokalbį. Bandykite dar kartą vėliau.';

  @override
  String get noInternetConnection => 'Patikrinkite interneto ryšį ir bandykite dar kartą.';

  @override
  String get unableToDeleteConversation => 'Nepavyko ištrinti pokalbio';

  @override
  String get somethingWentWrong => 'Kažkas nepavyko! Bandykite dar kartą vėliau.';

  @override
  String get copyErrorMessage => 'Kopijuoti klaidos pranešimą';

  @override
  String get errorCopied => 'Klaidos pranešimas nukopijuotas į iškarpinę';

  @override
  String get remaining => 'Likę';

  @override
  String get loading => 'Kraunama...';

  @override
  String get loadingDuration => 'Kraunama trukmė...';

  @override
  String secondsCount(int count) {
    return '$count sek.';
  }

  @override
  String get people => 'Žmonės';

  @override
  String get addNewPerson => 'Pridėti naują asmenį';

  @override
  String get editPerson => 'Redaguoti asmenį';

  @override
  String get createPersonHint => 'Sukurkite naują asmenį ir apmokykite Omi atpažinti jų kalbą!';

  @override
  String get speechProfile => 'Kalbos profilis';

  @override
  String sampleNumber(int number) {
    return 'Pavyzdys $number';
  }

  @override
  String get settings => 'Nustatymai';

  @override
  String get language => 'Kalba';

  @override
  String get selectLanguage => 'Pasirinkti kalbą';

  @override
  String get deleting => 'Trinama...';

  @override
  String get pleaseCompleteAuthentication => 'Užbaikite autentifikaciją naršyklėje. Baigę grįžkite į programą.';

  @override
  String get failedToStartAuthentication => 'Nepavyko pradėti autentifikacijos';

  @override
  String get importStarted => 'Importavimas pradėtas! Gausite pranešimą, kai bus baigta.';

  @override
  String get failedToStartImport => 'Nepavyko pradėti importavimo. Bandykite dar kartą.';

  @override
  String get couldNotAccessFile => 'Nepavyko pasiekti pasirinkto failo';

  @override
  String get askOmi => 'Klauskite Omi';

  @override
  String get done => 'Atlikta';

  @override
  String get disconnected => 'Atjungta';

  @override
  String get searching => 'Ieškoma';

  @override
  String get connectDevice => 'Prijungti įrenginį';

  @override
  String get monthlyLimitReached => 'Pasiekėte mėnesio limitą.';

  @override
  String get checkUsage => 'Tikrinti naudojimą';

  @override
  String get syncingRecordings => 'Sinchronizuojami įrašai';

  @override
  String get recordingsToSync => 'Įrašai sinchronizavimui';

  @override
  String get allCaughtUp => 'Viskas atnaujinta';

  @override
  String get sync => 'Sinchronizuoti';

  @override
  String get pendantUpToDate => 'Pakabukas atnaujintas';

  @override
  String get allRecordingsSynced => 'Visi įrašai sinchronizuoti';

  @override
  String get syncingInProgress => 'Vyksta sinchronizavimas';

  @override
  String get readyToSync => 'Paruošta sinchronizuoti';

  @override
  String get tapSyncToStart => 'Paspauskite Sinchronizuoti, kad pradėtumėte';

  @override
  String get pendantNotConnected => 'Pakabukas neprijungtas. Prijunkite, kad sinchronizuotumėte.';

  @override
  String get everythingSynced => 'Viskas jau sinchronizuota.';

  @override
  String get recordingsNotSynced => 'Turite nesinchronizuotų įrašų.';

  @override
  String get syncingBackground => 'Tęsime įrašų sinchronizavimą fone.';

  @override
  String get noConversationsYet => 'Kol kas nėra pokalbių.';

  @override
  String get noStarredConversations => 'Kol kas nėra pažymėtų pokalbių.';

  @override
  String get starConversationHint =>
      'Norėdami pažymėti pokalbį, atidarykite jį ir paspauskite žvaigždutės piktogramą antraštėje.';

  @override
  String get searchConversations => 'Ieškoti pokalbių';

  @override
  String selectedCount(int count, Object s) {
    return 'Pasirinkta: $count';
  }

  @override
  String get merge => 'Sujungti';

  @override
  String get mergeConversations => 'Sujungti pokalbius';

  @override
  String mergeConversationsMessage(int count) {
    return 'Bus sujungti $count pokalbiai į vieną. Visas turinys bus sujungtas ir iš naujo sugeneruotas.';
  }

  @override
  String get mergingInBackground => 'Sujungiama fone. Tai gali užtrukti.';

  @override
  String get failedToStartMerge => 'Nepavyko pradėti sujungimo';

  @override
  String get askAnything => 'Klauskite bet ko';

  @override
  String get noMessagesYet => 'Kol kas nėra žinučių!\nKodėl gi nepradėtumėte pokalbio?';

  @override
  String get deletingMessages => 'Ištrinamos jūsų žinutės iš Omi atminties...';

  @override
  String get messageCopied => 'Žinutė nukopijuota į iškarpinę.';

  @override
  String get cannotReportOwnMessage => 'Negalite pranešti apie savo žinutes.';

  @override
  String get reportMessage => 'Pranešti apie žinutę';

  @override
  String get reportMessageConfirm => 'Ar tikrai norite pranešti apie šią žinutę?';

  @override
  String get messageReported => 'Apie žinutę pranešta sėkmingai.';

  @override
  String get thankYouFeedback => 'Ačiū už jūsų atsiliepimą!';

  @override
  String get clearChat => 'Išvalyti pokalbį?';

  @override
  String get clearChatConfirm => 'Ar tikrai norite išvalyti pokalbį? Šio veiksmo negalima atšaukti.';

  @override
  String get maxFilesLimit => 'Galite įkelti tik 4 failus vienu metu';

  @override
  String get chatWithOmi => 'Pokalbis su Omi';

  @override
  String get apps => 'Programėlės';

  @override
  String get noAppsFound => 'Programėlių nerasta';

  @override
  String get tryAdjustingSearch => 'Pabandykite pakeisti paiešką arba filtrus';

  @override
  String get createYourOwnApp => 'Sukurkite savo programėlę';

  @override
  String get buildAndShareApp => 'Sukurkite ir bendrinkite savo programėlę';

  @override
  String get searchApps => 'Ieškoti 1500+ programėlių';

  @override
  String get myApps => 'Mano programėlės';

  @override
  String get installedApps => 'Įdiegtos programėlės';

  @override
  String get unableToFetchApps =>
      'Nepavyko gauti programėlių :(\n\nPatikrinkite interneto ryšį ir bandykite dar kartą.';

  @override
  String get aboutOmi => 'Apie Omi';

  @override
  String get privacyPolicy => 'Privatumo politika';

  @override
  String get visitWebsite => 'Aplankyti svetainę';

  @override
  String get helpOrInquiries => 'Pagalba ar klausimai?';

  @override
  String get joinCommunity => 'Prisijunkite prie bendruomenės!';

  @override
  String get membersAndCounting => '8000+ narių ir vis daugėja.';

  @override
  String get deleteAccountTitle => 'Ištrinti paskyrą';

  @override
  String get deleteAccountConfirm => 'Ar tikrai norite ištrinti savo paskyrą?';

  @override
  String get cannotBeUndone => 'Šio veiksmo negalima atšaukti.';

  @override
  String get allDataErased => 'Visi jūsų prisiminimai ir pokalbiai bus negrįžtamai ištrinti.';

  @override
  String get appsDisconnected => 'Jūsų programėlės ir integracijos bus nedelsiant atjungtos.';

  @override
  String get exportBeforeDelete =>
      'Prieš ištrindami paskyrą galite eksportuoti duomenis, tačiau ištrynus jų atkurti neįmanoma.';

  @override
  String get deleteAccountCheckbox =>
      'Suprantu, kad mano paskyros ištrynimas yra galutinis ir visi duomenys, įskaitant prisiminimus ir pokalbius, bus prarasti ir jų atkurti nebus įmanoma.';

  @override
  String get areYouSure => 'Ar tikrai?';

  @override
  String get deleteAccountFinal =>
      'Šis veiksmas yra negrįžtamas ir galutinai ištrins jūsų paskyrą ir visus susijusius duomenis. Ar tikrai norite tęsti?';

  @override
  String get deleteNow => 'Ištrinti dabar';

  @override
  String get goBack => 'Grįžti atgal';

  @override
  String get checkBoxToConfirm =>
      'Pažymėkite langelį, kad patvirtintumėte, jog suprantate, kad paskyros ištrynimas yra galutinis ir negrįžtamas.';

  @override
  String get profile => 'Profilis';

  @override
  String get name => 'Vardas';

  @override
  String get email => 'El. paštas';

  @override
  String get customVocabulary => 'Pasirinktinis žodynas';

  @override
  String get identifyingOthers => 'Kitų atpažinimas';

  @override
  String get paymentMethods => 'Mokėjimo būdai';

  @override
  String get conversationDisplay => 'Pokalbių rodymas';

  @override
  String get dataPrivacy => 'Duomenys ir privatumas';

  @override
  String get userId => 'Naudotojo ID';

  @override
  String get notSet => 'Nenustatyta';

  @override
  String get userIdCopied => 'Naudotojo ID nukopijuotas į iškarpinę';

  @override
  String get systemDefault => 'Sistemos numatytasis';

  @override
  String get planAndUsage => 'Planas ir naudojimas';

  @override
  String get offlineSync => 'Autonominė sinchronizacija';

  @override
  String get deviceSettings => 'Įrenginio nustatymai';

  @override
  String get chatTools => 'Pokalbių įrankiai';

  @override
  String get feedbackBug => 'Atsiliepimai / Klaida';

  @override
  String get helpCenter => 'Pagalbos centras';

  @override
  String get developerSettings => 'Kūrėjo nustatymai';

  @override
  String get getOmiForMac => 'Gauti Omi Mac';

  @override
  String get referralProgram => 'Rekomendacijų programa';

  @override
  String get signOut => 'Atsijungti';

  @override
  String get appAndDeviceCopied => 'Programėlės ir įrenginio informacija nukopijuota';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => 'Jūsų privatumas, jūsų kontrolė';

  @override
  String get privacyIntro =>
      'Omi įsipareigoja saugoti jūsų privatumą. Šis puslapis leidžia kontroliuoti, kaip jūsų duomenys saugomi ir naudojami.';

  @override
  String get learnMore => 'Sužinoti daugiau...';

  @override
  String get dataProtectionLevel => 'Duomenų apsaugos lygis';

  @override
  String get dataProtectionDesc =>
      'Jūsų duomenys pagal numatytuosius nustatymus apsaugoti stipriu šifravimu. Peržiūrėkite savo nustatymus ir būsimas privatumo parinktis žemiau.';

  @override
  String get appAccess => 'Programėlių prieiga';

  @override
  String get appAccessDesc =>
      'Šios programėlės gali pasiekti jūsų duomenis. Paspauskite programėlę, kad valdytumėte jos leidimus.';

  @override
  String get noAppsExternalAccess => 'Jokios įdiegtos programėlės neturi išorinės prieigos prie jūsų duomenų.';

  @override
  String get deviceName => 'Įrenginio pavadinimas';

  @override
  String get deviceId => 'Įrenginio ID';

  @override
  String get firmware => 'Programinė įranga';

  @override
  String get sdCardSync => 'SD kortelės sinchronizacija';

  @override
  String get hardwareRevision => 'Aparatinės įrangos versija';

  @override
  String get modelNumber => 'Modelio numeris';

  @override
  String get manufacturer => 'Gamintojas';

  @override
  String get doubleTap => 'Dvigubas bakstelėjimas';

  @override
  String get ledBrightness => 'LED ryškumas';

  @override
  String get micGain => 'Mikrofono stiprinimas';

  @override
  String get disconnect => 'Atjungti';

  @override
  String get forgetDevice => 'Pamiršti įrenginį';

  @override
  String get chargingIssues => 'Krovimo problemos';

  @override
  String get disconnectDevice => 'Atjungti įrenginį';

  @override
  String get unpairDevice => 'Atjungti įrenginį';

  @override
  String get unpairAndForget => 'Atjungti ir pamiršti įrenginį';

  @override
  String get deviceDisconnectedMessage => 'Jūsų Omi buvo atjungtas 😔';

  @override
  String get deviceUnpairedMessage =>
      'Įrenginys atjungtas. Eikite į Nustatymus > „Bluetooth\" ir pamiršti įrenginį, kad užbaigtumėte atjungimą.';

  @override
  String get unpairDialogTitle => 'Atjungti įrenginį';

  @override
  String get unpairDialogMessage =>
      'Taip atjungsite įrenginį, kad jį būtų galima prijungti prie kito telefono. Norėdami užbaigti procesą, turėsite eiti į Nustatymus > „Bluetooth\" ir pamiršti įrenginį.';

  @override
  String get deviceNotConnected => 'Įrenginys neprijungtas';

  @override
  String get connectDeviceMessage => 'Prijunkite Omi įrenginį, kad pasiektumėte\nįrenginio nustatymus ir pritaikymą';

  @override
  String get deviceInfoSection => 'Įrenginio informacija';

  @override
  String get customizationSection => 'Pritaikymas';

  @override
  String get hardwareSection => 'Aparatinė įranga';

  @override
  String get v2Undetected => 'V2 neaptiktas';

  @override
  String get v2UndetectedMessage =>
      'Matome, kad turite V1 įrenginį arba jūsų įrenginys neprijungtas. SD kortelės funkcija prieinama tik V2 įrenginiams.';

  @override
  String get endConversation => 'Baigti pokalbį';

  @override
  String get pauseResume => 'Pristabdyti / tęsti';

  @override
  String get starConversation => 'Pažymėti pokalbį';

  @override
  String get doubleTapAction => 'Dvigubo bakstelėjimo veiksmas';

  @override
  String get endAndProcess => 'Baigti ir apdoroti pokalbį';

  @override
  String get pauseResumeRecording => 'Pristabdyti / tęsti įrašymą';

  @override
  String get starOngoing => 'Pažymėti vykstantį pokalbį';

  @override
  String get off => 'Išjungta';

  @override
  String get max => 'Maksimalus';

  @override
  String get mute => 'Nutildyti';

  @override
  String get quiet => 'Tylus';

  @override
  String get normal => 'Normalus';

  @override
  String get high => 'Aukštas';

  @override
  String get micGainDescMuted => 'Mikrofonas nutildytas';

  @override
  String get micGainDescLow => 'Labai tylus – triukšmingai aplinkai';

  @override
  String get micGainDescModerate => 'Tylus – vidutiniam triukšmui';

  @override
  String get micGainDescNeutral => 'Neutralus – subalansuotas įrašymas';

  @override
  String get micGainDescSlightlyBoosted => 'Šiek tiek sustiprintas – įprastam naudojimui';

  @override
  String get micGainDescBoosted => 'Sustiprintas – tyliai aplinkai';

  @override
  String get micGainDescHigh => 'Aukštas – tolimam ar tyliam balsui';

  @override
  String get micGainDescVeryHigh => 'Labai aukštas – labai tyliems šaltiniams';

  @override
  String get micGainDescMax => 'Maksimalus – naudokite atsargiai';

  @override
  String get developerSettingsTitle => 'Kūrėjo nustatymai';

  @override
  String get saving => 'Išsaugoma...';

  @override
  String get personaConfig => 'Konfigūruokite savo DI asmens charakteristikų';

  @override
  String get beta => 'BETA';

  @override
  String get transcription => 'Transkripcija';

  @override
  String get transcriptionConfig => 'Konfigūruoti STT teikėją';

  @override
  String get conversationTimeout => 'Pokalbio skirtasis laikas';

  @override
  String get conversationTimeoutConfig => 'Nustatykite, kada automatiškai baigiami pokalbiai';

  @override
  String get importData => 'Importuoti duomenis';

  @override
  String get importDataConfig => 'Importuoti duomenis iš kitų šaltinių';

  @override
  String get debugDiagnostics => 'Derinimas ir diagnostika';

  @override
  String get endpointUrl => 'Galinio taško URL';

  @override
  String get noApiKeys => 'Kol kas nėra API raktų';

  @override
  String get createKeyToStart => 'Sukurkite raktą, kad pradėtumėte';

  @override
  String get createKey => 'Sukurti raktą';

  @override
  String get docs => 'Dokumentai';

  @override
  String get yourOmiInsights => 'Jūsų Omi įžvalgos';

  @override
  String get today => 'Šiandien';

  @override
  String get thisMonth => 'Šį mėnesį';

  @override
  String get thisYear => 'Šiais metais';

  @override
  String get allTime => 'Visą laiką';

  @override
  String get noActivityYet => 'Kol kas nėra veiklos';

  @override
  String get startConversationToSeeInsights => 'Pradėkite pokalbį su Omi,\nkad čia matytumėte naudojimo įžvalgas.';

  @override
  String get listening => 'Klausymasis';

  @override
  String get listeningSubtitle => 'Bendras laikas, kurį Omi aktyviai klausėsi.';

  @override
  String get understanding => 'Supratimas';

  @override
  String get understandingSubtitle => 'Žodžiai, suprasti iš jūsų pokalbių.';

  @override
  String get providing => 'Teikimas';

  @override
  String get providingSubtitle => 'Automatiškai užfiksuotos užduotys ir pastabos.';

  @override
  String get remembering => 'Prisiminimas';

  @override
  String get rememberingSubtitle => 'Faktai ir detalės, prisiminti jums.';

  @override
  String get unlimitedPlan => 'Neribojamas planas';

  @override
  String get managePlan => 'Valdyti planą';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Jūsų planas bus atšauktas $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Jūsų planas bus atnaujintas $date.';
  }

  @override
  String get basicPlan => 'Nemokamas planas';

  @override
  String usageLimitMessage(String used, int limit) {
    return 'Panaudota $used iš $limit min.';
  }

  @override
  String get upgrade => 'Atnaujinti';

  @override
  String get upgradeToUnlimited => 'Atnaujinti į neribotą';

  @override
  String basicPlanDesc(int limit) {
    return 'Jūsų planas apima $limit nemokamų minučių per mėnesį. Atnaujinkite, kad gautumėte neribotą.';
  }

  @override
  String get shareStatsMessage => 'Dalinu savo Omi statistika! (omi.me – jūsų visada veikiantis DI asistentas)';

  @override
  String get sharePeriodToday => 'Šiandien omi:';

  @override
  String get sharePeriodMonth => 'Šį mėnesį omi:';

  @override
  String get sharePeriodYear => 'Šiais metais omi:';

  @override
  String get sharePeriodAllTime => 'Iki šiol omi:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Klausėsi $minutes minučių';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Suprato $words žodžių';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Suteikė $count įžvalgų';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Prisiminė $count prisiminimų';
  }

  @override
  String get debugLogs => 'Derinimo žurnalai';

  @override
  String get debugLogsAutoDelete => 'Automatiškai ištrinami po 3 dienų.';

  @override
  String get debugLogsDesc => 'Padeda diagnozuoti problemas';

  @override
  String get noLogFilesFound => 'Žurnalų failų nerasta.';

  @override
  String get omiDebugLog => 'Omi derinimo žurnalas';

  @override
  String get logShared => 'Žurnalas bendrintas';

  @override
  String get selectLogFile => 'Pasirinkti žurnalo failą';

  @override
  String get shareLogs => 'Bendrinti žurnalus';

  @override
  String get debugLogCleared => 'Derinimo žurnalas išvalytas';

  @override
  String get exportStarted => 'Eksportavimas pradėtas. Tai gali užtrukti keletą sekundžių...';

  @override
  String get exportAllData => 'Eksportuoti visus duomenis';

  @override
  String get exportDataDesc => 'Eksportuoti pokalbius į JSON failą';

  @override
  String get exportedConversations => 'Eksportuoti pokalbiai iš Omi';

  @override
  String get exportShared => 'Eksportas bendrintas';

  @override
  String get deleteKnowledgeGraphTitle => 'Ištrinti žinių grafiką?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Taip bus ištrinti visi išvesti žinių grafiko duomenys (mazgai ir ryšiai). Jūsų originalūs prisiminimai liks saugūs. Grafikas bus atstatytas laikui bėgant arba pagal kitą užklausą.';

  @override
  String get knowledgeGraphDeleted => 'Žinių grafikas sėkmingai ištrintas';

  @override
  String deleteGraphFailed(String error) {
    return 'Nepavyko ištrinti grafiko: $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Ištrinti žinių grafiką';

  @override
  String get deleteKnowledgeGraphDesc => 'Išvalyti visus mazgus ir ryšius';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP serveris';

  @override
  String get mcpServerDesc => 'Prijunkite DI asistentus prie savo duomenų';

  @override
  String get serverUrl => 'Serverio URL';

  @override
  String get urlCopied => 'URL nukopijuotas';

  @override
  String get apiKeyAuth => 'API rakto autentifikacija';

  @override
  String get header => 'Antraštė';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'Kliento ID';

  @override
  String get clientSecret => 'Kliento paslaptis';

  @override
  String get useMcpApiKey => 'Naudokite savo MCP API raktą';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Pokalbių įvykiai';

  @override
  String get newConversationCreated => 'Sukurtas naujas pokalbis';

  @override
  String get realtimeTranscript => 'Realaus laiko transkripcija';

  @override
  String get transcriptReceived => 'Transkripcija gauta';

  @override
  String get audioBytes => 'Garso baitai';

  @override
  String get audioDataReceived => 'Garso duomenys gauti';

  @override
  String get intervalSeconds => 'Intervalas (sekundės)';

  @override
  String get daySummary => 'Dienos santrauka';

  @override
  String get summaryGenerated => 'Santrauka sugeneruota';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Pridėti į claude_desktop_config.json';

  @override
  String get copyConfig => 'Kopijuoti konfigūraciją';

  @override
  String get configCopied => 'Konfigūracija nukopijuota į iškarpinę';

  @override
  String get listeningMins => 'Klausymasis (min.)';

  @override
  String get understandingWords => 'Supratimas (žodžiai)';

  @override
  String get insights => 'Įžvalgos';

  @override
  String get memories => 'Prisiminimai';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return 'Šį mėnesį panaudota $used iš $limit min.';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return 'Šį mėnesį panaudota $used iš $limit žodžių';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return 'Šį mėnesį gauta $used iš $limit įžvalgų';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return 'Šį mėnesį sukurta $used iš $limit prisiminimų';
  }

  @override
  String get visibility => 'Matomumas';

  @override
  String get visibilitySubtitle => 'Kontroliuokite, kurie pokalbiai rodomi jūsų sąraše';

  @override
  String get showShortConversations => 'Rodyti trumpus pokalbius';

  @override
  String get showShortConversationsDesc => 'Rodyti pokalbius, trumpesnius už ribą';

  @override
  String get showDiscardedConversations => 'Rodyti atmestus pokalbius';

  @override
  String get showDiscardedConversationsDesc => 'Įtraukti pokalbius, pažymėtus kaip atmesti';

  @override
  String get shortConversationThreshold => 'Trumpo pokalbio riba';

  @override
  String get shortConversationThresholdSubtitle =>
      'Pokalbiai, trumpesni už šią ribą, bus paslėpti, nebent įjungta aukščiau';

  @override
  String get durationThreshold => 'Trukmės riba';

  @override
  String get durationThresholdDesc => 'Slėpti pokalbius, trumpesnius už šią ribą';

  @override
  String minLabel(int count) {
    return '$count min.';
  }

  @override
  String get customVocabularyTitle => 'Pasirinktinis žodynas';

  @override
  String get addWords => 'Pridėti žodžių';

  @override
  String get addWordsDesc => 'Vardai, terminai ar neįprasti žodžiai';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Prisijungti';

  @override
  String get comingSoon => 'Greitai';

  @override
  String get chatToolsFooter => 'Prijunkite savo programėles, kad matytumėte duomenis ir metrikas pokalbyje.';

  @override
  String get completeAuthInBrowser => 'Užbaikite autentifikaciją naršyklėje. Baigę grįžkite į programą.';

  @override
  String failedToStartAuth(String appName) {
    return 'Nepavyko pradėti $appName autentifikacijos';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Atjungti $appName?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Ar tikrai norite atsijungti nuo $appName? Galite bet kada vėl prisijungti.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Atjungta nuo $appName';
  }

  @override
  String get failedToDisconnect => 'Nepavyko atjungti';

  @override
  String connectTo(String appName) {
    return 'Prisijungti prie $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Jums reikės autorizuoti Omi prieigą prie jūsų $appName duomenų. Bus atidaryta naršyklė autentifikacijai.';
  }

  @override
  String get continueAction => 'Tęsti';

  @override
  String get languageTitle => 'Kalba';

  @override
  String get primaryLanguage => 'Pagrindinė kalba';

  @override
  String get automaticTranslation => 'Automatinis vertimas';

  @override
  String get detectLanguages => 'Aptikti 10+ kalbų';

  @override
  String get authorizeSavingRecordings => 'Leisti išsaugoti įrašus';

  @override
  String get thanksForAuthorizing => 'Ačiū, kad leidote!';

  @override
  String get needYourPermission => 'Mums reikia jūsų leidimo';

  @override
  String get alreadyGavePermission => 'Jau davėte mums leidimą išsaugoti jūsų įrašus. Primename, kodėl mums to reikia:';

  @override
  String get wouldLikePermission => 'Norėtume jūsų leidimo išsaugoti jūsų balso įrašus. Štai kodėl:';

  @override
  String get improveSpeechProfile => 'Pagerinti jūsų kalbos profilį';

  @override
  String get improveSpeechProfileDesc =>
      'Naudojame įrašus tolesniam jūsų asmeninio kalbos profilio mokymui ir tobulinimui.';

  @override
  String get trainFamilyProfiles => 'Mokyti draugų ir šeimos profilius';

  @override
  String get trainFamilyProfilesDesc => 'Jūsų įrašai padeda atpažinti ir kurti profilius jūsų draugams ir šeimai.';

  @override
  String get enhanceTranscriptAccuracy => 'Pagerinti transkripcijos tikslumą';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'Mūsų modeliui tobulėjant, galime pateikti geresnius transkripcijos rezultatus jūsų įrašams.';

  @override
  String get legalNotice =>
      'Teisinis pranešimas: balso duomenų įrašymo ir saugojimo teisėtumas gali skirtis priklausomai nuo jūsų buvimo vietos ir kaip naudojate šią funkciją. Tai jūsų atsakomybė užtikrinti atitiktį vietiniams įstatymams ir taisyklėms.';

  @override
  String get alreadyAuthorized => 'Jau autorizuota';

  @override
  String get authorize => 'Leisti';

  @override
  String get revokeAuthorization => 'Atšaukti leidimą';

  @override
  String get authorizationSuccessful => 'Leidimas sėkmingas!';

  @override
  String get failedToAuthorize => 'Nepavyko autorizuoti. Bandykite dar kartą.';

  @override
  String get authorizationRevoked => 'Leidimas atšauktas.';

  @override
  String get recordingsDeleted => 'Įrašai ištrinti.';

  @override
  String get failedToRevoke => 'Nepavyko atšaukti leidimo. Bandykite dar kartą.';

  @override
  String get permissionRevokedTitle => 'Leidimas atšauktas';

  @override
  String get permissionRevokedMessage => 'Ar norite, kad ištrintume visus jūsų esamus įrašus?';

  @override
  String get yes => 'Taip';

  @override
  String get editName => 'Redaguoti vardą';

  @override
  String get howShouldOmiCallYou => 'Kaip Omi turėtų jus vadinti?';

  @override
  String get enterYourName => 'Įveskite savo vardą';

  @override
  String get nameCannotBeEmpty => 'Vardas negali būti tuščias';

  @override
  String get nameUpdatedSuccessfully => 'Vardas sėkmingai atnaujintas!';

  @override
  String get calendarSettings => 'Kalendoriaus nustatymai';

  @override
  String get calendarProviders => 'Kalendoriaus teikėjai';

  @override
  String get macOsCalendar => 'macOS kalendorius';

  @override
  String get connectMacOsCalendar => 'Prijunkite savo vietinį macOS kalendorių';

  @override
  String get googleCalendar => 'Google kalendorius';

  @override
  String get syncGoogleAccount => 'Sinchronizuoti su savo Google paskyra';

  @override
  String get showMeetingsMenuBar => 'Rodyti būsimus susitikimus meniu juostoje';

  @override
  String get showMeetingsMenuBarDesc => 'Rodyti kitą susitikimą ir laiką iki jo pradžios macOS meniu juostoje';

  @override
  String get showEventsNoParticipants => 'Rodyti renginius be dalyvių';

  @override
  String get showEventsNoParticipantsDesc => 'Kai įjungta, „Coming Up\" rodo renginius be dalyvių ar vaizdo nuorodos.';

  @override
  String get yourMeetings => 'Jūsų susitikimai';

  @override
  String get refresh => 'Atnaujinti';

  @override
  String get noUpcomingMeetings => 'Nerasta būsimų susitikimų';

  @override
  String get checkingNextDays => 'Tikrinama ateinančių 30 dienų';

  @override
  String get tomorrow => 'Rytoj';

  @override
  String get googleCalendarComingSoon => 'Google kalendoriaus integracija greitai!';

  @override
  String connectedAsUser(String userId) {
    return 'Prisijungta kaip vartotojas: $userId';
  }

  @override
  String get defaultWorkspace => 'Numatytoji darbo sritis';

  @override
  String get tasksCreatedInWorkspace => 'Užduotys bus sukurtos šioje darbo srityje';

  @override
  String get defaultProjectOptional => 'Numatytasis projektas (nebūtinas)';

  @override
  String get leaveUnselectedTasks => 'Palikite nepasirinkus, kad sukurtumėte užduotis be projekto';

  @override
  String get noProjectsInWorkspace => 'Šioje darbo srityje nerasta projektų';

  @override
  String get conversationTimeoutDesc => 'Pasirinkite, kiek laiko laukti tylos prieš automatiškai baigiant pokalbį:';

  @override
  String get timeout2Minutes => '2 minutės';

  @override
  String get timeout2MinutesDesc => 'Baigti pokalbį po 2 minučių tylos';

  @override
  String get timeout5Minutes => '5 minutės';

  @override
  String get timeout5MinutesDesc => 'Baigti pokalbį po 5 minučių tylos';

  @override
  String get timeout10Minutes => '10 minučių';

  @override
  String get timeout10MinutesDesc => 'Baigti pokalbį po 10 minučių tylos';

  @override
  String get timeout30Minutes => '30 minučių';

  @override
  String get timeout30MinutesDesc => 'Baigti pokalbį po 30 minučių tylos';

  @override
  String get timeout4Hours => '4 valandos';

  @override
  String get timeout4HoursDesc => 'Baigti pokalbį po 4 valandų tylos';

  @override
  String get conversationEndAfterHours => 'Pokalbiai dabar bus baigiami po 4 valandų tylos';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Pokalbiai dabar bus baigiami po $minutes minutės(-ių) tylos';
  }

  @override
  String get tellUsPrimaryLanguage => 'Pasakykite mums savo pagrindinę kalbą';

  @override
  String get languageForTranscription =>
      'Nustatykite savo kalbą tikslesnėms transkripcijoms ir individualizuotai patirčiai.';

  @override
  String get singleLanguageModeInfo =>
      'Įjungtas vienos kalbos režimas. Vertimas išjungtas, kad būtų didesnis tikslumas.';

  @override
  String get searchLanguageHint => 'Ieškoti kalbos pagal pavadinimą ar kodą';

  @override
  String get noLanguagesFound => 'Kalbų nerasta';

  @override
  String get skip => 'Praleisti';

  @override
  String languageSetTo(String language) {
    return 'Kalba nustatyta į $language';
  }

  @override
  String get failedToSetLanguage => 'Nepavyko nustatyti kalbos';

  @override
  String appSettings(String appName) {
    return '$appName nustatymai';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Atjungti nuo $appName?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Bus pašalinta jūsų $appName autentifikacija. Jums reikės vėl prisijungti, kad ją naudotumėte.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Prisijungta prie $appName';
  }

  @override
  String get account => 'Paskyra';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Jūsų užduotys bus sinchronizuotos su jūsų $appName paskyra';
  }

  @override
  String get defaultSpace => 'Numatytoji erdvė';

  @override
  String get selectSpaceInWorkspace => 'Pasirinkite erdvę savo darbo srityje';

  @override
  String get noSpacesInWorkspace => 'Šioje darbo srityje nerasta erdvių';

  @override
  String get defaultList => 'Numatytasis sąrašas';

  @override
  String get tasksAddedToList => 'Užduotys bus pridėtos į šį sąrašą';

  @override
  String get noListsInSpace => 'Šioje erdvėje nerasta sąrašų';

  @override
  String failedToLoadRepos(String error) {
    return 'Nepavyko įkelti saugyklų: $error';
  }

  @override
  String get defaultRepoSaved => 'Numatytoji saugykla išsaugota';

  @override
  String get failedToSaveDefaultRepo => 'Nepavyko išsaugoti numatytosios saugyklos';

  @override
  String get defaultRepository => 'Numatytoji saugykla';

  @override
  String get selectDefaultRepoDesc =>
      'Pasirinkite numatytąją saugyklą problemų kūrimui. Kurdami problemas galite nurodyti kitą saugyklą.';

  @override
  String get noReposFound => 'Saugyklų nerasta';

  @override
  String get private => 'Privati';

  @override
  String updatedDate(String date) {
    return 'Atnaujinta $date';
  }

  @override
  String get yesterday => 'vakar';

  @override
  String daysAgo(int count) {
    return 'prieš $count d.';
  }

  @override
  String get oneWeekAgo => 'prieš 1 savaitę';

  @override
  String weeksAgo(int count) {
    return 'prieš $count sav.';
  }

  @override
  String get oneMonthAgo => 'prieš 1 mėnesį';

  @override
  String monthsAgo(int count) {
    return 'prieš $count mėn.';
  }

  @override
  String get issuesCreatedInRepo => 'Problemos bus sukurtos jūsų numatytojoje saugykloje';

  @override
  String get taskIntegrations => 'Užduočių integracijos';

  @override
  String get configureSettings => 'Konfigūruoti nustatymus';

  @override
  String get completeAuthBrowser => 'Užbaikite autentifikaciją naršyklėje. Baigę grįžkite į programą.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Nepavyko pradėti $appName autentifikacijos';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Prisijungti prie $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Jums reikės autorizuoti Omi kurti užduotis jūsų $appName paskyroje. Bus atidaryta naršyklė autentifikacijai.';
  }

  @override
  String get continueButton => 'Tęsti';

  @override
  String appIntegration(String appName) {
    return '$appName integracija';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'Integracija su $appName greitai! Sunkiai dirbame, kad suteiktume daugiau užduočių valdymo parinkčių.';
  }

  @override
  String get gotIt => 'Supratau';

  @override
  String get tasksExportedOneApp => 'Užduotys gali būti eksportuojamos į vieną programėlę vienu metu.';

  @override
  String get completeYourUpgrade => 'Užbaikite savo atnaujinimą';

  @override
  String get importConfiguration => 'Importuoti konfigūraciją';

  @override
  String get exportConfiguration => 'Eksportuoti konfigūraciją';

  @override
  String get bringYourOwn => 'Naudokite savo';

  @override
  String get payYourSttProvider => 'Laisvai naudokite omi. Mokate tik savo STT teikėjui tiesiogiai.';

  @override
  String get freeMinutesMonth => '1 200 nemokamų minučių per mėnesį įtraukta. Neribota su ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => 'Reikalingas pagrindinis kompiuteris';

  @override
  String get validPortRequired => 'Reikalingas tinkamas prievadas';

  @override
  String get validWebsocketUrlRequired => 'Reikalingas tinkamas WebSocket URL (wss://)';

  @override
  String get apiUrlRequired => 'Reikalingas API URL';

  @override
  String get apiKeyRequired => 'Reikalingas API raktas';

  @override
  String get invalidJsonConfig => 'Netinkama JSON konfigūracija';

  @override
  String errorSaving(String error) {
    return 'Klaida išsaugant: $error';
  }

  @override
  String get configCopiedToClipboard => 'Konfigūracija nukopijuota į iškarpinę';

  @override
  String get pasteJsonConfig => 'Įklijuokite savo JSON konfigūraciją žemiau:';

  @override
  String get addApiKeyAfterImport => 'Importavę turėsite pridėti savo API raktą';

  @override
  String get paste => 'Įklijuoti';

  @override
  String get import => 'Importuoti';

  @override
  String get invalidProviderInConfig => 'Netinkamas teikėjas konfigūracijoje';

  @override
  String importedConfig(String providerName) {
    return 'Importuota $providerName konfigūracija';
  }

  @override
  String invalidJson(String error) {
    return 'Netinkamas JSON: $error';
  }

  @override
  String get provider => 'Teikėjas';

  @override
  String get live => 'Tiesioginis';

  @override
  String get onDevice => 'Įrenginyje';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'Įveskite savo STT HTTP galinį tašką';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => 'Įveskite savo tiesioginį STT WebSocket galinį tašką';

  @override
  String get apiKey => 'API raktas';

  @override
  String get enterApiKey => 'Įveskite savo API raktą';

  @override
  String get storedLocallyNeverShared => 'Saugoma vietoje, niekada nebendrinam';

  @override
  String get host => 'Pagrindinis kompiuteris';

  @override
  String get port => 'Prievadas';

  @override
  String get advanced => 'Išplėstiniai';

  @override
  String get configuration => 'Konfigūracija';

  @override
  String get requestConfiguration => 'Užklausos konfigūracija';

  @override
  String get responseSchema => 'Atsakymo schema';

  @override
  String get modified => 'Pakeista';

  @override
  String get resetRequestConfig => 'Atkurti užklausos konfigūraciją į numatytąją';

  @override
  String get logs => 'Žurnalai';

  @override
  String get logsCopied => 'Žurnalai nukopijuoti';

  @override
  String get noLogsYet => 'Kol kas nėra žurnalų. Pradėkite įrašinėti, kad matytumėte pasirinktinio STT veiklą.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName naudoja $codecReason. Bus naudojamas Omi.';
  }

  @override
  String get omiTranscription => 'Omi transkripcija';

  @override
  String get bestInClassTranscription => 'Geriausia klasės transkripcija be jokio nustatymo';

  @override
  String get instantSpeakerLabels => 'Akimirksniu kalbėtojų etiketės';

  @override
  String get languageTranslation => '100+ kalbų vertimas';

  @override
  String get optimizedForConversation => 'Optimizuota pokalbiams';

  @override
  String get autoLanguageDetection => 'Automatinis kalbos aptikimas';

  @override
  String get highAccuracy => 'Aukštas tikslumas';

  @override
  String get privacyFirst => 'Pirmiausiai privatumas';

  @override
  String get saveChanges => 'Išsaugoti pakeitimus';

  @override
  String get resetToDefault => 'Atkurti į numatytuosius';

  @override
  String get viewTemplate => 'Peržiūrėti šabloną';

  @override
  String get trySomethingLike => 'Pabandykite kažką panašaus...';

  @override
  String get tryIt => 'Išbandykite';

  @override
  String get creatingPlan => 'Kuriamas planas';

  @override
  String get developingLogic => 'Kuriama logika';

  @override
  String get designingApp => 'Projektuojama programėlė';

  @override
  String get generatingIconStep => 'Generuojama piktograma';

  @override
  String get finalTouches => 'Paskutiniai patobulinimai';

  @override
  String get processing => 'Apdorojama...';

  @override
  String get features => 'Funkcijos';

  @override
  String get creatingYourApp => 'Kuriama jūsų programėlė...';

  @override
  String get generatingIcon => 'Generuojama piktograma...';

  @override
  String get whatShouldWeMake => 'Ką turėtume sukurti?';

  @override
  String get appName => 'Programėlės pavadinimas';

  @override
  String get description => 'Aprašymas';

  @override
  String get publicLabel => 'Vieša';

  @override
  String get privateLabel => 'Privati';

  @override
  String get free => 'Nemokai';

  @override
  String get perMonth => '/ Mėnesį';

  @override
  String get tailoredConversationSummaries => 'Pritaikytos pokalbių santraukos';

  @override
  String get customChatbotPersonality => 'Pasirinktinė pokalbių roboto asmenybė';

  @override
  String get makePublic => 'Padaryti viešą';

  @override
  String get anyoneCanDiscover => 'Bet kas gali rasti jūsų programėlę';

  @override
  String get onlyYouCanUse => 'Tik jūs galite naudoti šią programėlę';

  @override
  String get paidApp => 'Mokama programėlė';

  @override
  String get usersPayToUse => 'Vartotojai moka, kad naudotų jūsų programėlę';

  @override
  String get freeForEveryone => 'Nemokamai visiems';

  @override
  String get perMonthLabel => '/ mėnesį';

  @override
  String get creating => 'Kuriama...';

  @override
  String get createApp => 'Sukurti programėlę';

  @override
  String get searchingForDevices => 'Ieškoma įrenginių...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'ĮRENGINIAI',
      one: 'ĮRENGINYS',
    );
    return 'RASTA $count $_temp0 NETOLIESE';
  }

  @override
  String get pairingSuccessful => 'SUSIEJIMAS SĖKMINGAS';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Klaida jungiantis prie Apple Watch: $error';
  }

  @override
  String get dontShowAgain => 'Daugiau nerodyti';

  @override
  String get iUnderstand => 'Suprantu';

  @override
  String get enableBluetooth => 'Įjungti Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi reikia Bluetooth, kad prisijungtų prie jūsų nešiojamo įrenginio. Įjunkite Bluetooth ir bandykite dar kartą.';

  @override
  String get contactSupport => 'Susisiekti su palaikymu?';

  @override
  String get connectLater => 'Prijungti vėliau';

  @override
  String get grantPermissions => 'Suteikti leidimus';

  @override
  String get backgroundActivity => 'Foninė veikla';

  @override
  String get backgroundActivityDesc => 'Leiskite Omi veikti fone geresniam stabilumui';

  @override
  String get locationAccess => 'Vietos prieiga';

  @override
  String get locationAccessDesc => 'Įjunkite foninę vietos nustatymą visapusiškesnei patirčiai';

  @override
  String get notifications => 'Pranešimai';

  @override
  String get notificationsDesc => 'Įjunkite pranešimus, kad būtumėte informuoti';

  @override
  String get locationServiceDisabled => 'Vietos tarnyba išjungta';

  @override
  String get locationServiceDisabledDesc =>
      'Vietos tarnyba išjungta. Eikite į Nustatymus > Privatumas ir sauga > Vietos tarnybos ir įjunkite ją';

  @override
  String get backgroundLocationDenied => 'Foninės vietos prieiga atmesta';

  @override
  String get backgroundLocationDeniedDesc =>
      'Eikite į įrenginio nustatymus ir nustatykite vietos leidimą į „Visada leisti\"';

  @override
  String get lovingOmi => 'Patinka Omi?';

  @override
  String get leaveReviewIos =>
      'Padėkite mums pasiekti daugiau žmonių palikdami atsiliepimą App Store. Jūsų atsiliepimas mums reiškia labai daug!';

  @override
  String get leaveReviewAndroid =>
      'Padėkite mums pasiekti daugiau žmonių palikdami atsiliepimą „Google Play\" parduotuvėje. Jūsų atsiliepimas mums reiškia labai daug!';

  @override
  String get rateOnAppStore => 'Įvertinti App Store';

  @override
  String get rateOnGooglePlay => 'Įvertinti „Google Play\"';

  @override
  String get maybeLater => 'Galbūt vėliau';

  @override
  String get speechProfileIntro => 'Omi turi išmokti jūsų tikslų ir jūsų balso. Vėliau galėsite jį keisti.';

  @override
  String get getStarted => 'Pradėti';

  @override
  String get allDone => 'Viskas atlikta!';

  @override
  String get keepGoing => 'Tęskite, jums puikiai sekasi';

  @override
  String get skipThisQuestion => 'Praleisti šį klausimą';

  @override
  String get skipForNow => 'Kol kas praleisti';

  @override
  String get connectionError => 'Ryšio klaida';

  @override
  String get connectionErrorDesc =>
      'Nepavyko prisijungti prie serverio. Patikrinkite interneto ryšį ir bandykite dar kartą.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Aptiktas netinkamas įrašas';

  @override
  String get multipleSpeakersDesc =>
      'Atrodo, kad įraše yra keli kalbėtojai. Įsitikinkite, kad esate tylioje vietoje, ir bandykite dar kartą.';

  @override
  String get tooShortDesc => 'Neaptikta pakankamai kalbos. Kalbėkite daugiau ir bandykite dar kartą.';

  @override
  String get invalidRecordingDesc => 'Įsitikinkite, kad kalbate bent 5 sekundes ir ne ilgiau nei 90.';

  @override
  String get areYouThere => 'Ar jūs čia?';

  @override
  String get noSpeechDesc =>
      'Nepavyko aptikti jokios kalbos. Įsitikinkite, kad kalbate bent 10 sekundžių ir ne ilgiau nei 3 minutes.';

  @override
  String get connectionLost => 'Ryšys prarastas';

  @override
  String get connectionLostDesc => 'Ryšys buvo nutrauktas. Patikrinkite interneto ryšį ir bandykite dar kartą.';

  @override
  String get tryAgain => 'Bandyti dar kartą';

  @override
  String get connectOmiOmiGlass => 'Prijungti Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Tęsti be įrenginio';

  @override
  String get permissionsRequired => 'Reikalingi leidimai';

  @override
  String get permissionsRequiredDesc =>
      'Šiai programai reikia Bluetooth ir vietos leidimų, kad tinkamai veiktų. Įjunkite juos nustatymuose.';

  @override
  String get openSettings => 'Atidaryti nustatymus';

  @override
  String get wantDifferentName => 'Norite, kad jus vadintų kitaip?';

  @override
  String get whatsYourName => 'Koks jūsų vardas?';

  @override
  String get speakTranscribeSummarize => 'Kalbėti. Transkribuoti. Apibendrinti.';

  @override
  String get signInWithApple => 'Prisijungti su Apple';

  @override
  String get signInWithGoogle => 'Prisijungti su Google';

  @override
  String get byContinuingAgree => 'Tęsdami sutinkate su mūsų ';

  @override
  String get termsOfUse => 'Naudojimo sąlygomis';

  @override
  String get omiYourAiCompanion => 'Omi – jūsų DI palydovas';

  @override
  String get captureEveryMoment =>
      'Užfiksuokite kiekvieną akimirką. Gaukite DI pagrindu\nsukurtas santraukas. Daugiau nebedarykite užrašų.';

  @override
  String get appleWatchSetup => 'Apple Watch sąranka';

  @override
  String get permissionRequestedExclaim => 'Leidimas paprašytas!';

  @override
  String get microphonePermission => 'Mikrofono leidimas';

  @override
  String get permissionGrantedNow =>
      'Leidimas suteiktas! Dabar:\n\nAtidarykite Omi programą savo laikrodyje ir paspauskite „Tęsti\" žemiau';

  @override
  String get needMicrophonePermission =>
      'Mums reikia mikrofono leidimo.\n\n1. Paspauskite „Suteikti leidimą\"\n2. Leiskite savo iPhone\n3. Laikrodžio programėlė užsidarys\n4. Atidarykite iš naujo ir paspauskite „Tęsti\"';

  @override
  String get grantPermissionButton => 'Suteikti leidimą';

  @override
  String get needHelp => 'Reikia pagalbos?';

  @override
  String get troubleshootingSteps =>
      'Trikčių šalinimas:\n\n1. Įsitikinkite, kad Omi įdiegtas jūsų laikrodyje\n2. Atidarykite Omi programą savo laikrodyje\n3. Ieškokite leidimo iššokančio lango\n4. Paspauskite „Leisti\", kai bus paprašyta\n5. Programėlė jūsų laikrodyje užsidarys – atidarykite ją iš naujo\n6. Grįžkite ir paspauskite „Tęsti\" savo iPhone';

  @override
  String get recordingStartedSuccessfully => 'Įrašymas pradėtas sėkmingai!';

  @override
  String get permissionNotGrantedYet =>
      'Leidimas dar nesuteiktas. Įsitikinkite, kad leidote prieigą prie mikrofono ir iš naujo atidarėte programą savo laikrodyje.';

  @override
  String errorRequestingPermission(String error) {
    return 'Klaida prašant leidimo: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Klaida pradedant įrašymą: $error';
  }

  @override
  String get selectPrimaryLanguage => 'Pasirinkite savo pagrindinę kalbą';

  @override
  String get languageBenefits => 'Nustatykite savo kalbą tikslesnėms transkripcijoms ir individualizuotai patirčiai';

  @override
  String get whatsYourPrimaryLanguage => 'Kokia jūsų pagrindinė kalba?';

  @override
  String get selectYourLanguage => 'Pasirinkite savo kalbą';

  @override
  String get personalGrowthJourney => 'Jūsų asmeninio augimo kelionė su DI, kuris klauso kiekvieno jūsų žodžio.';

  @override
  String get actionItemsTitle => 'Užduotys';

  @override
  String get actionItemsDescription =>
      'Bakstelėkite, kad redaguotumėte • Ilgai spauskite, kad pasirinktumėte • Braukite veiksmams';

  @override
  String get tabToDo => 'Atlikti';

  @override
  String get tabDone => 'Baigta';

  @override
  String get tabOld => 'Senos';

  @override
  String get emptyTodoMessage => '🎉 Viskas atnaujinta!\nNėra laukiančių užduočių';

  @override
  String get emptyDoneMessage => 'Kol kas nėra baigtų elementų';

  @override
  String get emptyOldMessage => '✅ Nėra senų užduočių';

  @override
  String get noItems => 'Nėra elementų';

  @override
  String get actionItemMarkedIncomplete => 'Užduotis pažymėta kaip nebaigta';

  @override
  String get actionItemCompleted => 'Užduotis baigta';

  @override
  String get deleteActionItemTitle => 'Ištrinti užduotį';

  @override
  String get deleteActionItemMessage => 'Ar tikrai norite ištrinti šią užduotį?';

  @override
  String get deleteSelectedItemsTitle => 'Ištrinti pasirinktus elementus';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Ar tikrai norite ištrinti $count pasirinktą(-s) užduotį(-is)?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Užduotis „$description\" ištrinta';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return 'Ištrinta $count užduotis(-ių)';
  }

  @override
  String get failedToDeleteItem => 'Nepavyko ištrinti užduoties';

  @override
  String get failedToDeleteItems => 'Nepavyko ištrinti elementų';

  @override
  String get failedToDeleteSomeItems => 'Nepavyko ištrinti kai kurių elementų';

  @override
  String get welcomeActionItemsTitle => 'Pasiruošę užduotims';

  @override
  String get welcomeActionItemsDescription =>
      'Jūsų DI automatiškai išgaus užduotis iš jūsų pokalbių. Jos atsiras čia, kai bus sukurtos.';

  @override
  String get autoExtractionFeature => 'Automatiškai išgauta iš pokalbių';

  @override
  String get editSwipeFeature => 'Bakstelėkite, kad redaguotumėte, braukite, kad baigtumėte ar ištrintumėte';

  @override
  String itemsSelected(int count) {
    return 'Pasirinkta: $count';
  }

  @override
  String get selectAll => 'Pasirinkti viską';

  @override
  String get deleteSelected => 'Ištrinti pasirinktus';

  @override
  String searchMemories(int count) {
    return 'Ieškoti $count prisiminimų';
  }

  @override
  String get memoryDeleted => 'Prisiminimas ištrintas.';

  @override
  String get undo => 'Atšaukti';

  @override
  String get noMemoriesYet => 'Kol kas nėra prisiminimų';

  @override
  String get noAutoMemories => 'Kol kas nėra automatiškai išgautų prisiminimų';

  @override
  String get noManualMemories => 'Kol kas nėra rankinio prisiminimų';

  @override
  String get noMemoriesInCategories => 'Šiose kategorijose nėra prisiminimų';

  @override
  String get noMemoriesFound => 'Prisiminimų nerasta';

  @override
  String get addFirstMemory => 'Pridėti pirmąjį prisiminimą';

  @override
  String get clearMemoryTitle => 'Išvalyti Omi atmintį';

  @override
  String get clearMemoryMessage => 'Ar tikrai norite išvalyti Omi atmintį? Šio veiksmo negalima atšaukti.';

  @override
  String get clearMemoryButton => 'Išvalyti atmintį';

  @override
  String get memoryClearedSuccess => 'Omi atmintis apie jus išvalyta';

  @override
  String get noMemoriesToDelete => 'Nėra prisiminimų trinimui';

  @override
  String get createMemoryTooltip => 'Sukurti naują prisiminimą';

  @override
  String get createActionItemTooltip => 'Sukurti naują užduotį';

  @override
  String get memoryManagement => 'Prisiminimų valdymas';

  @override
  String get filterMemories => 'Filtruoti prisiminimus';

  @override
  String totalMemoriesCount(int count) {
    return 'Turite $count prisiminimų iš viso';
  }

  @override
  String get publicMemories => 'Vieši prisiminimai';

  @override
  String get privateMemories => 'Privatūs prisiminimai';

  @override
  String get makeAllPrivate => 'Padaryti visus prisiminimus privačius';

  @override
  String get makeAllPublic => 'Padaryti visus prisiminimus viešus';

  @override
  String get deleteAllMemories => 'Ištrinti visus prisiminimus';

  @override
  String get allMemoriesPrivateResult => 'Visi prisiminimai dabar privatūs';

  @override
  String get allMemoriesPublicResult => 'Visi prisiminimai dabar vieši';

  @override
  String get newMemory => 'Naujas prisiminimas';

  @override
  String get editMemory => 'Redaguoti prisiminimą';

  @override
  String get memoryContentHint => 'Mėgstu valgyti ledus...';

  @override
  String get failedToSaveMemory => 'Nepavyko išsaugoti. Patikrinkite ryšį.';

  @override
  String get saveMemory => 'Išsaugoti prisiminimą';

  @override
  String get retry => 'Bandyti dar kartą';

  @override
  String get createActionItem => 'Sukurti užduotį';

  @override
  String get editActionItem => 'Redaguoti užduotį';

  @override
  String get actionItemDescriptionHint => 'Ką reikia padaryti?';

  @override
  String get actionItemDescriptionEmpty => 'Užduoties aprašymas negali būti tuščias.';

  @override
  String get actionItemUpdated => 'Užduotis atnaujinta';

  @override
  String get failedToUpdateActionItem => 'Nepavyko atnaujinti užduoties';

  @override
  String get actionItemCreated => 'Užduotis sukurta';

  @override
  String get failedToCreateActionItem => 'Nepavyko sukurti užduoties';

  @override
  String get dueDate => 'Terminas';

  @override
  String get time => 'Laikas';

  @override
  String get addDueDate => 'Pridėti terminą';

  @override
  String get pressDoneToSave => 'Paspauskite atlikta, kad išsaugotumėte';

  @override
  String get pressDoneToCreate => 'Paspauskite atlikta, kad sukurtumėte';

  @override
  String get filterAll => 'Viskas';

  @override
  String get filterSystem => 'Apie jus';

  @override
  String get filterInteresting => 'Įžvalgos';

  @override
  String get filterManual => 'Rankinis';

  @override
  String get completed => 'Baigta';

  @override
  String get markComplete => 'Pažymėti kaip baigtą';

  @override
  String get actionItemDeleted => 'Užduotis ištrinta';

  @override
  String get failedToDeleteActionItem => 'Nepavyko ištrinti užduoties';

  @override
  String get deleteActionItemConfirmTitle => 'Ištrinti užduotį';

  @override
  String get deleteActionItemConfirmMessage => 'Ar tikrai norite ištrinti šią užduotį?';

  @override
  String get appLanguage => 'Programėlės kalba';

  @override
  String get appInterfaceSectionTitle => 'PROGRAMOS SĄSAJA';

  @override
  String get speechTranscriptionSectionTitle => 'KALBA IR TRANSKRIBAVIMAS';

  @override
  String get languageSettingsHelperText =>
      'Programos kalba keičia meniu ir mygtukus. Kalbos kalba įtakoja, kaip transkribuojami jūsų įrašai.';
}
