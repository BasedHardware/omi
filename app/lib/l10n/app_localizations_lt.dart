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
  String get noInternetConnection => 'Nėra interneto ryšio';

  @override
  String get unableToDeleteConversation => 'Nepavyko ištrinti pokalbio';

  @override
  String get somethingWentWrong => 'Kažkas nepavyko! Bandykite dar kartą vėliau.';

  @override
  String get copyErrorMessage => 'Kopijuoti klaidos pranešimą';

  @override
  String get errorCopied => 'Klaidos pranešimas nukopijuotas į iškarpinę';

  @override
  String get remaining => 'Liko';

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
  String get askOmi => 'Paklausti Omi';

  @override
  String get done => 'Atlikta';

  @override
  String get disconnected => 'Atjungta';

  @override
  String get searching => 'Ieškoma...';

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
  String get noConversationsYet => 'Dar nėra pokalbių';

  @override
  String get noStarredConversations => 'Kol kas nėra pažymėtų pokalbių.';

  @override
  String get starConversationHint =>
      'Norėdami pažymėti pokalbį, atidarykite jį ir paspauskite žvaigždutės piktogramą antraštėje.';

  @override
  String get searchConversations => 'Ieškoti pokalbių...';

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
  String get apps => 'Programos';

  @override
  String get noAppsFound => 'Programų nerasta';

  @override
  String get tryAdjustingSearch => 'Pabandykite pakeisti paiešką arba filtrus';

  @override
  String get createYourOwnApp => 'Sukurkite savo programėlę';

  @override
  String get buildAndShareApp => 'Sukurkite ir bendrinkite savo programėlę';

  @override
  String get searchApps => 'Ieškoti programų...';

  @override
  String get myApps => 'Mano programos';

  @override
  String get installedApps => 'Įdiegtos programos';

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
  String get sdCardSync => 'SD kortelės sinchronizavimas';

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
  String get chargingIssues => 'Įkrovimo problemos';

  @override
  String get disconnectDevice => 'Atjungti įrenginį';

  @override
  String get unpairDevice => 'Atjungti įrenginio susiejimą';

  @override
  String get unpairAndForget => 'Atjungti ir pamiršti įrenginį';

  @override
  String get deviceDisconnectedMessage => 'Jūsų Omi buvo atjungtas 😔';

  @override
  String get deviceUnpairedMessage =>
      'Įrenginys atjungtas. Eikite į Nustatymai > Bluetooth ir pamiršite įrenginį, kad užbaigtumėte atsiejimą.';

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
  String get yesterday => 'Vakar';

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
  String get resetToDefault => 'Atstatyti į numatytąją';

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
  String get createApp => 'Sukurti programą';

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
  String get maybeLater => 'Gal vėliau';

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
  String get deleteActionItemTitle => 'Ištrinti veiksmo elementą';

  @override
  String get deleteActionItemMessage => 'Ar tikrai norite ištrinti šį veiksmo elementą?';

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
  String get createActionItem => 'Sukurti veiksmo elementą';

  @override
  String get editActionItem => 'Redaguoti veiksmo elementą';

  @override
  String get actionItemDescriptionHint => 'Ką reikia padaryti?';

  @override
  String get actionItemDescriptionEmpty => 'Užduoties aprašymas negali būti tuščias.';

  @override
  String get actionItemUpdated => 'Užduotis atnaujinta';

  @override
  String get failedToUpdateActionItem => 'Nepavyko atnaujinti veiksmo elemento';

  @override
  String get actionItemCreated => 'Užduotis sukurta';

  @override
  String get failedToCreateActionItem => 'Nepavyko sukurti veiksmo elemento';

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
  String get completed => 'Užbaigta';

  @override
  String get markComplete => 'Pažymėti kaip užbaigtą';

  @override
  String get actionItemDeleted => 'Veiksmo elementas ištrintas';

  @override
  String get failedToDeleteActionItem => 'Nepavyko ištrinti veiksmo elemento';

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

  @override
  String get translationNotice => 'Vertimo pranešimas';

  @override
  String get translationNoticeMessage =>
      'Omi verčia pokalbius į jūsų pagrindinę kalbą. Atnaujinkite bet kada skiltyje Nustatymai → Profiliai.';

  @override
  String get pleaseCheckInternetConnection => 'Patikrinkite interneto ryšį ir bandykite dar kartą';

  @override
  String get pleaseSelectReason => 'Pasirinkite priežastį';

  @override
  String get tellUsMoreWhatWentWrong => 'Pasakykite mums daugiau apie tai, kas nutiko ne taip...';

  @override
  String get selectText => 'Pasirinkti tekstą';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maksimaliai $count tikslų leidžiama';
  }

  @override
  String get conversationCannotBeMerged => 'Šis pokalbis negali būti sujungtas (užrakintas arba jau sujungiamas)';

  @override
  String get pleaseEnterFolderName => 'Įveskite aplanko pavadinimą';

  @override
  String get failedToCreateFolder => 'Nepavyko sukurti aplanko';

  @override
  String get failedToUpdateFolder => 'Nepavyko atnaujinti aplanko';

  @override
  String get folderName => 'Aplanko pavadinimas';

  @override
  String get descriptionOptional => 'Aprašymas (neprivaloma)';

  @override
  String get failedToDeleteFolder => 'Nepavyko ištrinti aplanko';

  @override
  String get editFolder => 'Redaguoti aplanką';

  @override
  String get deleteFolder => 'Ištrinti aplanką';

  @override
  String get transcriptCopiedToClipboard => 'Transkriptai nukopijuoti į iškarpinę';

  @override
  String get summaryCopiedToClipboard => 'Santrauka nukopijuota į iškarpinę';

  @override
  String get conversationUrlCouldNotBeShared => 'Pokalbio URL negalima bendrinti.';

  @override
  String get urlCopiedToClipboard => 'URL nukopijuotas į iškarpinę';

  @override
  String get exportTranscript => 'Eksportuoti transkriptą';

  @override
  String get exportSummary => 'Eksportuoti santrauką';

  @override
  String get exportButton => 'Eksportuoti';

  @override
  String get actionItemsCopiedToClipboard => 'Veiksmų elementai nukopijuoti į iškarpinę';

  @override
  String get summarize => 'Apibendrinti';

  @override
  String get generateSummary => 'Generuoti santrauką';

  @override
  String get conversationNotFoundOrDeleted => 'Pokalbis nerastas arba buvo ištrintas';

  @override
  String get deleteMemory => 'Ištrinti atmintį?';

  @override
  String get thisActionCannotBeUndone => 'Šio veiksmo negalima atšaukti.';

  @override
  String memoriesCount(int count) {
    return '$count atminčių';
  }

  @override
  String get noMemoriesInCategory => 'Šioje kategorijoje dar nėra atsiminimų';

  @override
  String get addYourFirstMemory => 'Pridėkite savo pirmąjį atsiminimą';

  @override
  String get firmwareDisconnectUsb => 'Atjunkite USB';

  @override
  String get firmwareUsbWarning => 'USB ryšys atnaujinimo metu gali sugadinti jūsų įrenginį.';

  @override
  String get firmwareBatteryAbove15 => 'Baterija virš 15%';

  @override
  String get firmwareEnsureBattery => 'Įsitikinkite, kad jūsų įrenginyje yra 15% baterijos.';

  @override
  String get firmwareStableConnection => 'Stabilus ryšys';

  @override
  String get firmwareConnectWifi => 'Prisijunkite prie WiFi arba mobiliojo ryšio.';

  @override
  String failedToStartUpdate(String error) {
    return 'Nepavyko pradėti atnaujinimo: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Prieš atnaujinant įsitikinkite:';

  @override
  String get confirmed => 'Patvirtinta!';

  @override
  String get release => 'Paleisti';

  @override
  String get slideToUpdate => 'Slinkite norėdami atnaujinti';

  @override
  String copiedToClipboard(String title) {
    return '$title nukopijuota į iškarpinę';
  }

  @override
  String get batteryLevel => 'Baterijos lygis';

  @override
  String get productUpdate => 'Produkto atnaujinimas';

  @override
  String get offline => 'Neprisijungęs';

  @override
  String get available => 'Prieinamas';

  @override
  String get unpairDeviceDialogTitle => 'Atjungti įrenginio susiejimą';

  @override
  String get unpairDeviceDialogMessage =>
      'Tai atjungs įrenginio susiejimą, kad jį būtų galima prijungti prie kito telefono. Turėsite eiti į Nustatymai > Bluetooth ir pamiršti įrenginį, kad užbaigtumėte procesą.';

  @override
  String get unpair => 'Atjungti susiejimą';

  @override
  String get unpairAndForgetDevice => 'Atjungti susiejimą ir pamiršti įrenginį';

  @override
  String get unknownDevice => 'Nežinomas įrenginys';

  @override
  String get unknown => 'Nežinomas';

  @override
  String get productName => 'Produkto pavadinimas';

  @override
  String get serialNumber => 'Serijos numeris';

  @override
  String get connected => 'Prijungtas';

  @override
  String get privacyPolicyTitle => 'Privatumo politika';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'No API keys yet';

  @override
  String get createKeyToGetStarted => 'Create a key to get started';

  @override
  String get persona => 'Persona';

  @override
  String get configureYourAiPersona => 'Configure your AI persona';

  @override
  String get configureSttProvider => 'Configure STT provider';

  @override
  String get setWhenConversationsAutoEnd => 'Set when conversations auto-end';

  @override
  String get importDataFromOtherSources => 'Import data from other sources';

  @override
  String get debugAndDiagnostics => 'Debug & Diagnostics';

  @override
  String get autoDeletesAfter3Days => 'Auto-deletes after 3 days.';

  @override
  String get helpsDiagnoseIssues => 'Helps diagnose issues';

  @override
  String get exportStartedMessage => 'Export started. This may take a few seconds...';

  @override
  String get exportConversationsToJson => 'Export conversations to a JSON file';

  @override
  String get knowledgeGraphDeletedSuccess => 'Knowledge Graph deleted successfully';

  @override
  String failedToDeleteGraph(String error) {
    return 'Failed to delete graph: $error';
  }

  @override
  String get clearAllNodesAndConnections => 'Clear all nodes and connections';

  @override
  String get addToClaudeDesktopConfig => 'Add to claude_desktop_config.json';

  @override
  String get connectAiAssistantsToData => 'Connect AI assistants to your data';

  @override
  String get useYourMcpApiKey => 'Use your MCP API key';

  @override
  String get realTimeTranscript => 'Real-time Transcript';

  @override
  String get experimental => 'Experimental';

  @override
  String get transcriptionDiagnostics => 'Transcription Diagnostics';

  @override
  String get detailedDiagnosticMessages => 'Detailed diagnostic messages';

  @override
  String get autoCreateSpeakers => 'Auto-create Speakers';

  @override
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Follow-up Questions';

  @override
  String get suggestQuestionsAfterConversations => 'Suggest questions after conversations';

  @override
  String get goalTracker => 'Goal Tracker';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Daily Reflection';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'Veiksmo elemento aprašymas negali būti tuščias';

  @override
  String get saved => 'Išsaugota';

  @override
  String get overdue => 'Pavėluota';

  @override
  String get failedToUpdateDueDate => 'Nepavyko atnaujinti termino';

  @override
  String get markIncomplete => 'Pažymėti kaip neužbaigtą';

  @override
  String get editDueDate => 'Redaguoti terminą';

  @override
  String get setDueDate => 'Nustatyti terminą';

  @override
  String get clearDueDate => 'Išvalyti terminą';

  @override
  String get failedToClearDueDate => 'Nepavyko išvalyti termino';

  @override
  String get mondayAbbr => 'Pr';

  @override
  String get tuesdayAbbr => 'An';

  @override
  String get wednesdayAbbr => 'Tr';

  @override
  String get thursdayAbbr => 'Kt';

  @override
  String get fridayAbbr => 'Pn';

  @override
  String get saturdayAbbr => 'Št';

  @override
  String get sundayAbbr => 'Sk';

  @override
  String get howDoesItWork => 'Kaip tai veikia?';

  @override
  String get sdCardSyncDescription =>
      'SD kortelės sinchronizavimas importuos jūsų atsiminimus iš SD kortelės į programą';

  @override
  String get checksForAudioFiles => 'Patikrina garso failus SD kortelėje';

  @override
  String get omiSyncsAudioFiles => 'Omi tada sinchronizuoja garso failus su serveriu';

  @override
  String get serverProcessesAudio => 'Serveris apdoroja garso failus ir sukuria atsiminimus';

  @override
  String get youreAllSet => 'Viskas paruošta!';

  @override
  String get welcomeToOmiDescription =>
      'Sveiki atvykę į Omi! Jūsų AI palydovas pasirengęs padėti jums pokalbių, užduočių ir daugiau.';

  @override
  String get startUsingOmi => 'Pradėti naudoti Omi';

  @override
  String get back => 'Atgal';

  @override
  String get keyboardShortcuts => 'Klaviatūros spartieji klavišai';

  @override
  String get toggleControlBar => 'Perjungti valdymo juostą';

  @override
  String get pressKeys => 'Paspauskite klavišus...';

  @override
  String get cmdRequired => '⌘ būtinas';

  @override
  String get invalidKey => 'Netinkamas klavišas';

  @override
  String get space => 'Tarpas';

  @override
  String get search => 'Ieškoti';

  @override
  String get searchPlaceholder => 'Ieškoti...';

  @override
  String get untitledConversation => 'Nepavadinta pokalbis';

  @override
  String countRemaining(String count) {
    return '$count liko';
  }

  @override
  String get addGoal => 'Pridėti tikslą';

  @override
  String get editGoal => 'Redaguoti tikslą';

  @override
  String get icon => 'Piktograma';

  @override
  String get goalTitle => 'Tikslo pavadinimas';

  @override
  String get current => 'Dabartinis';

  @override
  String get target => 'Tikslas';

  @override
  String get saveGoal => 'Išsaugoti';

  @override
  String get goals => 'Tikslai';

  @override
  String get tapToAddGoal => 'Bakstelėkite, kad pridėtumėte tikslą';

  @override
  String get welcomeBack => 'Sveiki sugrįžę';

  @override
  String get yourConversations => 'Jūsų pokalbiai';

  @override
  String get reviewAndManageConversations => 'Peržiūrėkite ir tvarkykite įrašytus pokalbius';

  @override
  String get startCapturingConversations => 'Pradėkite fiksuoti pokalbius su Omi įrenginiu, kad juos matytumėte čia.';

  @override
  String get useMobileAppToCapture => 'Naudokite mobilią programą garso įrašymui';

  @override
  String get conversationsProcessedAutomatically => 'Pokalbiai apdorojami automatiškai';

  @override
  String get getInsightsInstantly => 'Gaukite įžvalgas ir santraukas akimirksniu';

  @override
  String get showAll => 'Rodyti viską →';

  @override
  String get noTasksForToday =>
      'Šiandien nėra užduočių.\\nPaprašykite Omi daugiau užduočių arba sukurkite rankiniu būdu.';

  @override
  String get dailyScore => 'DIENOS ĮVERTINIMAS';

  @override
  String get dailyScoreDescription => 'Įvertinimas, padedantis geriau sutelkti dėmesį į vykdymą.';

  @override
  String get searchResults => 'Paieškos rezultatai';

  @override
  String get actionItems => 'Veiksmų punktai';

  @override
  String get tasksToday => 'Šiandien';

  @override
  String get tasksTomorrow => 'Rytoj';

  @override
  String get tasksNoDeadline => 'Be termino';

  @override
  String get tasksLater => 'Vėliau';

  @override
  String get loadingTasks => 'Įkeliamos užduotys...';

  @override
  String get tasks => 'Užduotys';

  @override
  String get swipeTasksToIndent => 'Braukite užduotis, kad įtrauktumėte, vilkite tarp kategorijų';

  @override
  String get create => 'Kurti';

  @override
  String get noTasksYet => 'Dar nėra užduočių';

  @override
  String get tasksFromConversationsWillAppear =>
      'Užduotys iš jūsų pokalbių bus rodomos čia.\nSpustelėkite Kurti, kad pridėtumėte vieną rankiniu būdu.';

  @override
  String get monthJan => 'Saus';

  @override
  String get monthFeb => 'Vas';

  @override
  String get monthMar => 'Kov';

  @override
  String get monthApr => 'Bal';

  @override
  String get monthMay => 'Geg';

  @override
  String get monthJun => 'Birž';

  @override
  String get monthJul => 'Liep';

  @override
  String get monthAug => 'Rugp';

  @override
  String get monthSep => 'Rugs';

  @override
  String get monthOct => 'Spal';

  @override
  String get monthNov => 'Lapkr';

  @override
  String get monthDec => 'Gruod';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Veiksmo elementas sėkmingai atnaujintas';

  @override
  String get actionItemCreatedSuccessfully => 'Veiksmo elementas sėkmingai sukurtas';

  @override
  String get actionItemDeletedSuccessfully => 'Veiksmo elementas sėkmingai ištrintas';

  @override
  String get deleteActionItem => 'Ištrinti veiksmo elementą';

  @override
  String get deleteActionItemConfirmation =>
      'Ar tikrai norite ištrinti šį veiksmo elementą? Šio veiksmo negalima atšaukti.';

  @override
  String get enterActionItemDescription => 'Įveskite veiksmo elemento aprašymą...';

  @override
  String get markAsCompleted => 'Pažymėti kaip atliktą';

  @override
  String get setDueDateAndTime => 'Nustatyti terminą ir laiką';

  @override
  String get reloadingApps => 'Programų perkrovimas...';

  @override
  String get loadingApps => 'Programų įkėlimas...';

  @override
  String get browseInstallCreateApps => 'Naršykite, įdiekite ir kurkite programas';

  @override
  String get all => 'Visos';

  @override
  String get open => 'Atidaryti';

  @override
  String get install => 'Įdiegti';

  @override
  String get noAppsAvailable => 'Nėra prieinamų programų';

  @override
  String get unableToLoadApps => 'Nepavyko įkelti programų';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Pabandykite pakoreguoti paieškos terminus arba filtrus';

  @override
  String get checkBackLaterForNewApps => 'Užsukite vėliau dėl naujų programų';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Patikrinkite interneto ryšį ir bandykite dar kartą';

  @override
  String get createNewApp => 'Sukurti naują programėlę';

  @override
  String get buildSubmitCustomOmiApp => 'Sukurkite ir pateikite savo tinkintą Omi programėlę';

  @override
  String get submittingYourApp => 'Jūsų programėlė pateikiama...';

  @override
  String get preparingFormForYou => 'Ruošiama forma jums...';

  @override
  String get appDetails => 'Programėlės informacija';

  @override
  String get paymentDetails => 'Mokėjimo informacija';

  @override
  String get previewAndScreenshots => 'Peržiūra ir ekrano kopijos';

  @override
  String get appCapabilities => 'Programėlės galimybės';

  @override
  String get aiPrompts => 'DI nurodymai';

  @override
  String get chatPrompt => 'Pokalbio nurodymas';

  @override
  String get chatPromptPlaceholder =>
      'Jūs esate puiki programėlė, jūsų darbas – atsakyti į vartotojų užklausas ir padaryti, kad jie jaustųsi gerai...';

  @override
  String get conversationPrompt => 'Pokalbio raginimas';

  @override
  String get conversationPromptPlaceholder =>
      'Jūs esate puiki programėlė, gausite pokalbio transkripcą ir santrauką...';

  @override
  String get notificationScopes => 'Pranešimų sritys';

  @override
  String get appPrivacyAndTerms => 'Programėlės privatumas ir sąlygos';

  @override
  String get makeMyAppPublic => 'Padaryti mano programėlę viešą';

  @override
  String get submitAppTermsAgreement =>
      'Pateikdamas šią programėlę, sutinku su Omi AI paslaugų teikimo sąlygomis ir privatumo politika';

  @override
  String get submitApp => 'Pateikti programėlę';

  @override
  String get needHelpGettingStarted => 'Reikia pagalbos pradedant?';

  @override
  String get clickHereForAppBuildingGuides => 'Spustelėkite čia programėlių kūrimo vadovams ir dokumentacijai';

  @override
  String get submitAppQuestion => 'Pateikti programėlę?';

  @override
  String get submitAppPublicDescription =>
      'Jūsų programėlė bus peržiūrėta ir padaryta vieša. Galite pradėti ją naudoti iš karto, net peržiūros metu!';

  @override
  String get submitAppPrivateDescription =>
      'Jūsų programėlė bus peržiūrėta ir padaryta prieinama jums privačiai. Galite pradėti ją naudoti iš karto, net peržiūros metu!';

  @override
  String get startEarning => 'Pradėkite uždirbti! 💰';

  @override
  String get connectStripeOrPayPal => 'Prijunkite Stripe arba PayPal, kad gautumėte mokėjimus už savo programėlę.';

  @override
  String get connectNow => 'Prijungti dabar';

  @override
  String installsCount(String count) {
    return '$count+ diegimų';
  }

  @override
  String get uninstallApp => 'Pašalinti programą';

  @override
  String get subscribe => 'Prenumeruoti';

  @override
  String get dataAccessNotice => 'Duomenų prieigos pranešimas';

  @override
  String get dataAccessWarning =>
      'Ši programa turės prieigą prie jūsų duomenų. Omi AI neatsako už tai, kaip ši programa naudoja, modifikuoja ar ištrina jūsų duomenis';

  @override
  String get installApp => 'Įdiegti programą';

  @override
  String get betaTesterNotice => 'Esate šios programos beta testuotojas. Ji dar nėra vieša. Ji taps vieša patvirtinus.';

  @override
  String get appUnderReviewOwner => 'Jūsų programa peržiūrima ir matoma tik jums. Ji taps vieša patvirtinus.';

  @override
  String get appRejectedNotice =>
      'Jūsų programa buvo atmesta. Atnaujinkite programos informaciją ir pateikite ją iš naujo peržiūrai.';

  @override
  String get setupSteps => 'Sąrankos veiksmai';

  @override
  String get setupInstructions => 'Sąrankos instrukcijos';

  @override
  String get integrationInstructions => 'Integracijos instrukcijos';

  @override
  String get preview => 'Peržiūra';

  @override
  String get aboutTheApp => 'Apie programą';

  @override
  String get aboutThePersona => 'Apie asmenybę';

  @override
  String get chatPersonality => 'Pokalbio asmenybė';

  @override
  String get ratingsAndReviews => 'Įvertinimai ir atsiliepimai';

  @override
  String get noRatings => 'nėra įvertinimų';

  @override
  String ratingsCount(String count) {
    return '$count+ įvertinimų';
  }

  @override
  String get errorActivatingApp => 'Klaida aktyvinant programą';

  @override
  String get integrationSetupRequired => 'Jei tai integracijos programa, įsitikinkite, kad sąranka užbaigta.';

  @override
  String get installed => 'Įdiegta';
}
