// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for French (`fr`).
class AppLocalizationsFr extends AppLocalizations {
  AppLocalizationsFr([String locale = 'fr']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => 'Conversation';

  @override
  String get transcriptTab => 'Transcription';

  @override
  String get actionItemsTab => 'Actions à faire';

  @override
  String get deleteConversationTitle => 'Supprimer la conversation ?';

  @override
  String get deleteConversationMessage =>
      'Êtes-vous sûr de vouloir supprimer cette conversation ? Cette action est irréversible.';

  @override
  String get confirm => 'Confirmer';

  @override
  String get cancel => 'Annuler';

  @override
  String get ok => 'OK';

  @override
  String get delete => 'Supprimer';

  @override
  String get add => 'Ajouter';

  @override
  String get update => 'Mettre à jour';

  @override
  String get save => 'Enregistrer';

  @override
  String get edit => 'Modifier';

  @override
  String get close => 'Fermer';

  @override
  String get clear => 'Effacer';

  @override
  String get copyTranscript => 'Copier la transcription';

  @override
  String get copySummary => 'Copier le résumé';

  @override
  String get testPrompt => 'Tester le prompt';

  @override
  String get reprocessConversation => 'Retraiter la conversation';

  @override
  String get deleteConversation => 'Supprimer la conversation';

  @override
  String get contentCopied => 'Contenu copié dans le presse-papiers';

  @override
  String get failedToUpdateStarred => 'Échec de la mise à jour du statut favori.';

  @override
  String get conversationUrlNotShared => 'L\'URL de la conversation n\'a pas pu être partagée.';

  @override
  String get errorProcessingConversation =>
      'Erreur lors du traitement de la conversation. Veuillez réessayer plus tard.';

  @override
  String get noInternetConnection => 'Veuillez vérifier votre connexion internet et réessayer.';

  @override
  String get unableToDeleteConversation => 'Impossible de supprimer la conversation';

  @override
  String get somethingWentWrong => 'Une erreur s\'est produite ! Veuillez réessayer plus tard.';

  @override
  String get copyErrorMessage => 'Copier le message d\'erreur';

  @override
  String get errorCopied => 'Message d\'erreur copié dans le presse-papiers';

  @override
  String get remaining => 'Restant';

  @override
  String get loading => 'Chargement...';

  @override
  String get loadingDuration => 'Chargement de la durée...';

  @override
  String secondsCount(int count) {
    return '$count secondes';
  }

  @override
  String get people => 'Personnes';

  @override
  String get addNewPerson => 'Ajouter une nouvelle personne';

  @override
  String get editPerson => 'Modifier la personne';

  @override
  String get createPersonHint => 'Créez une nouvelle personne et entraînez Omi à reconnaître sa voix aussi !';

  @override
  String get speechProfile => 'Profil vocal';

  @override
  String sampleNumber(int number) {
    return 'Échantillon $number';
  }

  @override
  String get settings => 'Paramètres';

  @override
  String get language => 'Langue';

  @override
  String get selectLanguage => 'Sélectionner la langue';

  @override
  String get deleting => 'Suppression...';

  @override
  String get pleaseCompleteAuthentication =>
      'Veuillez compléter l\'authentification dans votre navigateur. Une fois terminé, revenez à l\'application.';

  @override
  String get failedToStartAuthentication => 'Échec du démarrage de l\'authentification';

  @override
  String get importStarted => 'Importation démarrée ! Vous serez notifié une fois terminée.';

  @override
  String get failedToStartImport => 'Échec du démarrage de l\'importation. Veuillez réessayer.';

  @override
  String get couldNotAccessFile => 'Impossible d\'accéder au fichier sélectionné';

  @override
  String get askOmi => 'Demander à Omi';

  @override
  String get done => 'Terminé';

  @override
  String get disconnected => 'Déconnecté';

  @override
  String get searching => 'Recherche';

  @override
  String get connectDevice => 'Connecter l\'appareil';

  @override
  String get monthlyLimitReached => 'Vous avez atteint votre limite mensuelle.';

  @override
  String get checkUsage => 'Vérifier l\'utilisation';

  @override
  String get syncingRecordings => 'Synchronisation des enregistrements';

  @override
  String get recordingsToSync => 'Enregistrements à synchroniser';

  @override
  String get allCaughtUp => 'Tout est à jour';

  @override
  String get sync => 'Synchroniser';

  @override
  String get pendantUpToDate => 'Le pendentif est à jour';

  @override
  String get allRecordingsSynced => 'Tous les enregistrements sont synchronisés';

  @override
  String get syncingInProgress => 'Synchronisation en cours';

  @override
  String get readyToSync => 'Prêt à synchroniser';

  @override
  String get tapSyncToStart => 'Appuyez sur Synchroniser pour commencer';

  @override
  String get pendantNotConnected => 'Pendentif non connecté. Connectez-vous pour synchroniser.';

  @override
  String get everythingSynced => 'Tout est déjà synchronisé.';

  @override
  String get recordingsNotSynced => 'Vous avez des enregistrements qui ne sont pas encore synchronisés.';

  @override
  String get syncingBackground => 'Nous continuerons à synchroniser vos enregistrements en arrière-plan.';

  @override
  String get noConversationsYet => 'Pas encore de conversations.';

  @override
  String get noStarredConversations => 'Pas encore de conversations favorites.';

  @override
  String get starConversationHint =>
      'Pour marquer une conversation comme favorite, ouvrez-la et appuyez sur l\'icône étoile dans l\'en-tête.';

  @override
  String get searchConversations => 'Rechercher des conversations';

  @override
  String selectedCount(int count, Object s) {
    return '$count sélectionné(s)';
  }

  @override
  String get merge => 'Fusionner';

  @override
  String get mergeConversations => 'Fusionner les conversations';

  @override
  String mergeConversationsMessage(int count) {
    return 'Cela combinera $count conversations en une seule. Tout le contenu sera fusionné et régénéré.';
  }

  @override
  String get mergingInBackground => 'Fusion en cours en arrière-plan. Cela peut prendre un moment.';

  @override
  String get failedToStartMerge => 'Échec du démarrage de la fusion';

  @override
  String get askAnything => 'Demandez n\'importe quoi';

  @override
  String get noMessagesYet => 'Pas encore de messages !\nPourquoi ne pas commencer une conversation ?';

  @override
  String get deletingMessages => 'Suppression de vos messages de la mémoire d\'Omi...';

  @override
  String get messageCopied => 'Message copié dans le presse-papiers.';

  @override
  String get cannotReportOwnMessage => 'Vous ne pouvez pas signaler vos propres messages.';

  @override
  String get reportMessage => 'Signaler le message';

  @override
  String get reportMessageConfirm => 'Êtes-vous sûr de vouloir signaler ce message ?';

  @override
  String get messageReported => 'Message signalé avec succès.';

  @override
  String get thankYouFeedback => 'Merci pour votre retour !';

  @override
  String get clearChat => 'Effacer la discussion ?';

  @override
  String get clearChatConfirm => 'Êtes-vous sûr de vouloir effacer la discussion ? Cette action est irréversible.';

  @override
  String get maxFilesLimit => 'Vous ne pouvez télécharger que 4 fichiers à la fois';

  @override
  String get chatWithOmi => 'Discuter avec Omi';

  @override
  String get apps => 'Applications';

  @override
  String get noAppsFound => 'Aucune application trouvée';

  @override
  String get tryAdjustingSearch => 'Essayez d\'ajuster votre recherche ou vos filtres';

  @override
  String get createYourOwnApp => 'Créez votre propre application';

  @override
  String get buildAndShareApp => 'Créez et partagez votre application personnalisée';

  @override
  String get searchApps => 'Rechercher plus de 1500 applications';

  @override
  String get myApps => 'Mes applications';

  @override
  String get installedApps => 'Applications installées';

  @override
  String get unableToFetchApps =>
      'Impossible de récupérer les applications :(\n\nVeuillez vérifier votre connexion internet et réessayer.';

  @override
  String get aboutOmi => 'À propos d\'Omi';

  @override
  String get privacyPolicy => 'Politique de confidentialité';

  @override
  String get visitWebsite => 'Visiter le site web';

  @override
  String get helpOrInquiries => 'Aide ou questions ?';

  @override
  String get joinCommunity => 'Rejoignez la communauté !';

  @override
  String get membersAndCounting => 'Plus de 8000 membres et ça continue.';

  @override
  String get deleteAccountTitle => 'Supprimer le compte';

  @override
  String get deleteAccountConfirm => 'Êtes-vous sûr de vouloir supprimer votre compte ?';

  @override
  String get cannotBeUndone => 'Cette action est irréversible.';

  @override
  String get allDataErased => 'Toutes vos mémoires et conversations seront définitivement effacées.';

  @override
  String get appsDisconnected => 'Vos applications et intégrations seront déconnectées immédiatement.';

  @override
  String get exportBeforeDelete =>
      'Vous pouvez exporter vos données avant de supprimer votre compte, mais une fois supprimé, il ne pourra pas être récupéré.';

  @override
  String get deleteAccountCheckbox =>
      'Je comprends que la suppression de mon compte est permanente et que toutes les données, y compris les mémoires et conversations, seront perdues et ne pourront pas être récupérées.';

  @override
  String get areYouSure => 'Êtes-vous sûr ?';

  @override
  String get deleteAccountFinal =>
      'Cette action est irréversible et supprimera définitivement votre compte et toutes les données associées. Êtes-vous sûr de vouloir continuer ?';

  @override
  String get deleteNow => 'Supprimer maintenant';

  @override
  String get goBack => 'Retour';

  @override
  String get checkBoxToConfirm =>
      'Cochez la case pour confirmer que vous comprenez que la suppression de votre compte est permanente et irréversible.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Nom';

  @override
  String get email => 'E-mail';

  @override
  String get customVocabulary => 'Vocabulaire personnalisé';

  @override
  String get identifyingOthers => 'Identification des autres';

  @override
  String get paymentMethods => 'Moyens de paiement';

  @override
  String get conversationDisplay => 'Affichage des conversations';

  @override
  String get dataPrivacy => 'Données et confidentialité';

  @override
  String get userId => 'ID utilisateur';

  @override
  String get notSet => 'Non défini';

  @override
  String get userIdCopied => 'ID utilisateur copié dans le presse-papiers';

  @override
  String get systemDefault => 'Par défaut du système';

  @override
  String get planAndUsage => 'Forfait et utilisation';

  @override
  String get offlineSync => 'Synchronisation hors ligne';

  @override
  String get deviceSettings => 'Paramètres de l\'appareil';

  @override
  String get chatTools => 'Outils de chat';

  @override
  String get feedbackBug => 'Retour / Bug';

  @override
  String get helpCenter => 'Centre d\'aide';

  @override
  String get developerSettings => 'Paramètres développeur';

  @override
  String get getOmiForMac => 'Obtenir Omi pour Mac';

  @override
  String get referralProgram => 'Programme de parrainage';

  @override
  String get signOut => 'Déconnexion';

  @override
  String get appAndDeviceCopied => 'Détails de l\'application et de l\'appareil copiés';

  @override
  String get wrapped2025 => 'Rétrospective 2025';

  @override
  String get yourPrivacyYourControl => 'Votre vie privée, votre contrôle';

  @override
  String get privacyIntro =>
      'Chez Omi, nous nous engageons à protéger votre vie privée. Cette page vous permet de contrôler la façon dont vos données sont stockées et utilisées.';

  @override
  String get learnMore => 'En savoir plus...';

  @override
  String get dataProtectionLevel => 'Niveau de protection des données';

  @override
  String get dataProtectionDesc =>
      'Vos données sont sécurisées par défaut avec un cryptage fort. Vérifiez vos paramètres et les futures options de confidentialité ci-dessous.';

  @override
  String get appAccess => 'Accès des applications';

  @override
  String get appAccessDesc =>
      'Les applications suivantes peuvent accéder à vos données. Appuyez sur une application pour gérer ses autorisations.';

  @override
  String get noAppsExternalAccess => 'Aucune application installée n\'a d\'accès externe à vos données.';

  @override
  String get deviceName => 'Nom de l\'appareil';

  @override
  String get deviceId => 'ID de l\'appareil';

  @override
  String get firmware => 'Firmware';

  @override
  String get sdCardSync => 'Synchronisation carte SD';

  @override
  String get hardwareRevision => 'Révision matérielle';

  @override
  String get modelNumber => 'Numéro de modèle';

  @override
  String get manufacturer => 'Fabricant';

  @override
  String get doubleTap => 'Double appui';

  @override
  String get ledBrightness => 'Luminosité LED';

  @override
  String get micGain => 'Gain du micro';

  @override
  String get disconnect => 'Déconnecter';

  @override
  String get forgetDevice => 'Oublier l\'appareil';

  @override
  String get chargingIssues => 'Problèmes de charge';

  @override
  String get disconnectDevice => 'Déconnecter l\'appareil';

  @override
  String get unpairDevice => 'Dissocier l\'appareil';

  @override
  String get unpairAndForget => 'Dissocier et oublier l\'appareil';

  @override
  String get deviceDisconnectedMessage => 'Votre Omi a été déconnecté 😔';

  @override
  String get deviceUnpairedMessage =>
      'Appareil dissocié. Allez dans Réglages > Bluetooth et oubliez l\'appareil pour terminer la dissociation.';

  @override
  String get unpairDialogTitle => 'Dissocier l\'appareil';

  @override
  String get unpairDialogMessage =>
      'Cela dissociera l\'appareil afin qu\'il puisse être connecté à un autre téléphone. Vous devrez aller dans Réglages > Bluetooth et oublier l\'appareil pour terminer le processus.';

  @override
  String get deviceNotConnected => 'Appareil non connecté';

  @override
  String get connectDeviceMessage =>
      'Connectez votre appareil Omi pour accéder aux\nparamètres et à la personnalisation de l\'appareil';

  @override
  String get deviceInfoSection => 'Informations sur l\'appareil';

  @override
  String get customizationSection => 'Personnalisation';

  @override
  String get hardwareSection => 'Matériel';

  @override
  String get v2Undetected => 'V2 non détecté';

  @override
  String get v2UndetectedMessage =>
      'Nous voyons que vous avez soit un appareil V1, soit votre appareil n\'est pas connecté. La fonctionnalité carte SD n\'est disponible que pour les appareils V2.';

  @override
  String get endConversation => 'Terminer la conversation';

  @override
  String get pauseResume => 'Pause/Reprendre';

  @override
  String get starConversation => 'Marquer la conversation comme favorite';

  @override
  String get doubleTapAction => 'Action double appui';

  @override
  String get endAndProcess => 'Terminer et traiter la conversation';

  @override
  String get pauseResumeRecording => 'Pause/Reprendre l\'enregistrement';

  @override
  String get starOngoing => 'Marquer la conversation en cours comme favorite';

  @override
  String get off => 'Désactivé';

  @override
  String get max => 'Max';

  @override
  String get mute => 'Muet';

  @override
  String get quiet => 'Silencieux';

  @override
  String get normal => 'Normal';

  @override
  String get high => 'Élevé';

  @override
  String get micGainDescMuted => 'Le microphone est en sourdine';

  @override
  String get micGainDescLow => 'Très silencieux - pour les environnements bruyants';

  @override
  String get micGainDescModerate => 'Silencieux - pour un bruit modéré';

  @override
  String get micGainDescNeutral => 'Neutre - enregistrement équilibré';

  @override
  String get micGainDescSlightlyBoosted => 'Légèrement amplifié - utilisation normale';

  @override
  String get micGainDescBoosted => 'Amplifié - pour les environnements calmes';

  @override
  String get micGainDescHigh => 'Élevé - pour les voix distantes ou douces';

  @override
  String get micGainDescVeryHigh => 'Très élevé - pour les sources très silencieuses';

  @override
  String get micGainDescMax => 'Maximum - à utiliser avec précaution';

  @override
  String get developerSettingsTitle => 'Paramètres développeur';

  @override
  String get saving => 'Enregistrement...';

  @override
  String get personaConfig => 'Configurez votre persona IA';

  @override
  String get beta => 'BÊTA';

  @override
  String get transcription => 'Transcription';

  @override
  String get transcriptionConfig => 'Configurer le fournisseur STT';

  @override
  String get conversationTimeout => 'Délai de conversation';

  @override
  String get conversationTimeoutConfig => 'Définir quand les conversations se terminent automatiquement';

  @override
  String get importData => 'Importer des données';

  @override
  String get importDataConfig => 'Importer des données d\'autres sources';

  @override
  String get debugDiagnostics => 'Débogage et diagnostics';

  @override
  String get endpointUrl => 'URL du point de terminaison';

  @override
  String get noApiKeys => 'Pas encore de clés API';

  @override
  String get createKeyToStart => 'Créez une clé pour commencer';

  @override
  String get createKey => 'Créer une clé';

  @override
  String get docs => 'Documentation';

  @override
  String get yourOmiInsights => 'Vos statistiques Omi';

  @override
  String get today => 'Aujourd\'hui';

  @override
  String get thisMonth => 'Ce mois-ci';

  @override
  String get thisYear => 'Cette année';

  @override
  String get allTime => 'Depuis toujours';

  @override
  String get noActivityYet => 'Pas encore d\'activité';

  @override
  String get startConversationToSeeInsights =>
      'Commencez une conversation avec Omi\npour voir vos statistiques d\'utilisation ici.';

  @override
  String get listening => 'Écoute';

  @override
  String get listeningSubtitle => 'Temps total d\'écoute active d\'Omi.';

  @override
  String get understanding => 'Compréhension';

  @override
  String get understandingSubtitle => 'Mots compris de vos conversations.';

  @override
  String get providing => 'Fourniture';

  @override
  String get providingSubtitle => 'Actions à faire et notes capturées automatiquement.';

  @override
  String get remembering => 'Mémorisation';

  @override
  String get rememberingSubtitle => 'Faits et détails mémorisés pour vous.';

  @override
  String get unlimitedPlan => 'Forfait illimité';

  @override
  String get managePlan => 'Gérer le forfait';

  @override
  String cancelAtPeriodEnd(String date) {
    return 'Votre forfait sera annulé le $date.';
  }

  @override
  String renewsOn(String date) {
    return 'Votre forfait sera renouvelé le $date.';
  }

  @override
  String get basicPlan => 'Forfait gratuit';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$used sur $limit min utilisées';
  }

  @override
  String get upgrade => 'Mettre à niveau';

  @override
  String get upgradeToUnlimited => 'Passer à l\'illimité';

  @override
  String basicPlanDesc(int limit) {
    return 'Votre forfait comprend $limit minutes gratuites par mois. Passez à l\'illimité.';
  }

  @override
  String get shareStatsMessage => 'Je partage mes statistiques Omi ! (omi.me - votre assistant IA toujours actif)';

  @override
  String get sharePeriodToday => 'Aujourd\'hui, Omi a :';

  @override
  String get sharePeriodMonth => 'Ce mois-ci, Omi a :';

  @override
  String get sharePeriodYear => 'Cette année, Omi a :';

  @override
  String get sharePeriodAllTime => 'Jusqu\'à présent, Omi a :';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 Écouté pendant $minutes minutes';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 Compris $words mots';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ Fourni $count aperçus';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 Mémorisé $count souvenirs';
  }

  @override
  String get debugLogs => 'Journaux de débogage';

  @override
  String get debugLogsAutoDelete => 'Suppression automatique après 3 jours.';

  @override
  String get debugLogsDesc => 'Aide à diagnostiquer les problèmes';

  @override
  String get noLogFilesFound => 'Aucun fichier journal trouvé.';

  @override
  String get omiDebugLog => 'Journal de débogage Omi';

  @override
  String get logShared => 'Journal partagé';

  @override
  String get selectLogFile => 'Sélectionner un fichier journal';

  @override
  String get shareLogs => 'Partager les journaux';

  @override
  String get debugLogCleared => 'Journal de débogage effacé';

  @override
  String get exportStarted => 'Exportation démarrée. Cela peut prendre quelques secondes...';

  @override
  String get exportAllData => 'Exporter toutes les données';

  @override
  String get exportDataDesc => 'Exporter les conversations vers un fichier JSON';

  @override
  String get exportedConversations => 'Conversations exportées depuis Omi';

  @override
  String get exportShared => 'Exportation partagée';

  @override
  String get deleteKnowledgeGraphTitle => 'Supprimer le graphe de connaissances ?';

  @override
  String get deleteKnowledgeGraphMessage =>
      'Cela supprimera toutes les données du graphe de connaissances dérivées (nœuds et connexions). Vos mémoires originales resteront intactes. Le graphe sera reconstruit au fil du temps ou lors de la prochaine demande.';

  @override
  String get knowledgeGraphDeleted => 'Graphe de connaissances supprimé avec succès';

  @override
  String deleteGraphFailed(String error) {
    return 'Échec de la suppression du graphe : $error';
  }

  @override
  String get deleteKnowledgeGraph => 'Supprimer le graphe de connaissances';

  @override
  String get deleteKnowledgeGraphDesc => 'Effacer tous les nœuds et connexions';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'Serveur MCP';

  @override
  String get mcpServerDesc => 'Connecter les assistants IA à vos données';

  @override
  String get serverUrl => 'URL du serveur';

  @override
  String get urlCopied => 'URL copiée';

  @override
  String get apiKeyAuth => 'Authentification par clé API';

  @override
  String get header => 'En-tête';

  @override
  String get authorizationBearer => 'Authorization: Bearer <clé>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => 'ID client';

  @override
  String get clientSecret => 'Secret client';

  @override
  String get useMcpApiKey => 'Utilisez votre clé API MCP';

  @override
  String get webhooks => 'Webhooks';

  @override
  String get conversationEvents => 'Événements de conversation';

  @override
  String get newConversationCreated => 'Nouvelle conversation créée';

  @override
  String get realtimeTranscript => 'Transcription en temps réel';

  @override
  String get transcriptReceived => 'Transcription reçue';

  @override
  String get audioBytes => 'Octets audio';

  @override
  String get audioDataReceived => 'Données audio reçues';

  @override
  String get intervalSeconds => 'Intervalle (secondes)';

  @override
  String get daySummary => 'Résumé du jour';

  @override
  String get summaryGenerated => 'Résumé généré';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'Ajouter à claude_desktop_config.json';

  @override
  String get copyConfig => 'Copier la configuration';

  @override
  String get configCopied => 'Configuration copiée dans le presse-papiers';

  @override
  String get listeningMins => 'Écoute (min)';

  @override
  String get understandingWords => 'Compréhension (mots)';

  @override
  String get insights => 'Aperçus';

  @override
  String get memories => 'Mémoires';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '$used sur $limit min utilisées ce mois-ci';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '$used sur $limit mots utilisés ce mois-ci';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '$used sur $limit aperçus obtenus ce mois-ci';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '$used sur $limit mémoires créées ce mois-ci';
  }

  @override
  String get visibility => 'Visibilité';

  @override
  String get visibilitySubtitle => 'Contrôlez quelles conversations apparaissent dans votre liste';

  @override
  String get showShortConversations => 'Afficher les conversations courtes';

  @override
  String get showShortConversationsDesc => 'Afficher les conversations plus courtes que le seuil';

  @override
  String get showDiscardedConversations => 'Afficher les conversations ignorées';

  @override
  String get showDiscardedConversationsDesc => 'Inclure les conversations marquées comme ignorées';

  @override
  String get shortConversationThreshold => 'Seuil de conversation courte';

  @override
  String get shortConversationThresholdSubtitle =>
      'Les conversations plus courtes que cela seront masquées sauf si activé ci-dessus';

  @override
  String get durationThreshold => 'Seuil de durée';

  @override
  String get durationThresholdDesc => 'Masquer les conversations plus courtes que cela';

  @override
  String minLabel(int count) {
    return '$count min';
  }

  @override
  String get customVocabularyTitle => 'Vocabulaire personnalisé';

  @override
  String get addWords => 'Ajouter des mots';

  @override
  String get addWordsDesc => 'Noms, termes ou mots inhabituels';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => 'Connecter';

  @override
  String get comingSoon => 'Bientôt disponible';

  @override
  String get chatToolsFooter => 'Connectez vos applications pour afficher les données et les métriques dans le chat.';

  @override
  String get completeAuthInBrowser =>
      'Veuillez compléter l\'authentification dans votre navigateur. Une fois terminé, revenez à l\'application.';

  @override
  String failedToStartAuth(String appName) {
    return 'Échec du démarrage de l\'authentification $appName';
  }

  @override
  String disconnectAppTitle(String appName) {
    return 'Déconnecter $appName ?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return 'Êtes-vous sûr de vouloir vous déconnecter de $appName ? Vous pouvez vous reconnecter à tout moment.';
  }

  @override
  String disconnectedFrom(String appName) {
    return 'Déconnecté de $appName';
  }

  @override
  String get failedToDisconnect => 'Échec de la déconnexion';

  @override
  String connectTo(String appName) {
    return 'Se connecter à $appName';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Vous devrez autoriser Omi à accéder à vos données $appName. Cela ouvrira votre navigateur pour l\'authentification.';
  }

  @override
  String get continueAction => 'Continuer';

  @override
  String get languageTitle => 'Langue';

  @override
  String get primaryLanguage => 'Langue principale';

  @override
  String get automaticTranslation => 'Traduction automatique';

  @override
  String get detectLanguages => 'Détecter plus de 10 langues';

  @override
  String get authorizeSavingRecordings => 'Autoriser l\'enregistrement des enregistrements';

  @override
  String get thanksForAuthorizing => 'Merci pour l\'autorisation !';

  @override
  String get needYourPermission => 'Nous avons besoin de votre permission';

  @override
  String get alreadyGavePermission =>
      'Vous nous avez déjà donné la permission d\'enregistrer vos enregistrements. Voici un rappel de pourquoi nous en avons besoin :';

  @override
  String get wouldLikePermission =>
      'Nous aimerions avoir votre permission pour sauvegarder vos enregistrements vocaux. Voici pourquoi :';

  @override
  String get improveSpeechProfile => 'Améliorer votre profil vocal';

  @override
  String get improveSpeechProfileDesc =>
      'Nous utilisons les enregistrements pour entraîner et améliorer davantage votre profil vocal personnel.';

  @override
  String get trainFamilyProfiles => 'Entraîner des profils pour les amis et la famille';

  @override
  String get trainFamilyProfilesDesc =>
      'Vos enregistrements nous aident à reconnaître et créer des profils pour vos amis et votre famille.';

  @override
  String get enhanceTranscriptAccuracy => 'Améliorer la précision de la transcription';

  @override
  String get enhanceTranscriptAccuracyDesc =>
      'À mesure que notre modèle s\'améliore, nous pouvons fournir de meilleurs résultats de transcription pour vos enregistrements.';

  @override
  String get legalNotice =>
      'Avis juridique : La légalité de l\'enregistrement et du stockage des données vocales peut varier selon votre emplacement et la façon dont vous utilisez cette fonctionnalité. Il est de votre responsabilité de vous assurer de la conformité aux lois et réglementations locales.';

  @override
  String get alreadyAuthorized => 'Déjà autorisé';

  @override
  String get authorize => 'Autoriser';

  @override
  String get revokeAuthorization => 'Révoquer l\'autorisation';

  @override
  String get authorizationSuccessful => 'Autorisation réussie !';

  @override
  String get failedToAuthorize => 'Échec de l\'autorisation. Veuillez réessayer.';

  @override
  String get authorizationRevoked => 'Autorisation révoquée.';

  @override
  String get recordingsDeleted => 'Enregistrements supprimés.';

  @override
  String get failedToRevoke => 'Échec de la révocation de l\'autorisation. Veuillez réessayer.';

  @override
  String get permissionRevokedTitle => 'Permission révoquée';

  @override
  String get permissionRevokedMessage =>
      'Voulez-vous que nous supprimions également tous vos enregistrements existants ?';

  @override
  String get yes => 'Oui';

  @override
  String get editName => 'Modifier le nom';

  @override
  String get howShouldOmiCallYou => 'Comment Omi devrait-il vous appeler ?';

  @override
  String get enterYourName => 'Entrez votre nom';

  @override
  String get nameCannotBeEmpty => 'Le nom ne peut pas être vide';

  @override
  String get nameUpdatedSuccessfully => 'Nom mis à jour avec succès !';

  @override
  String get calendarSettings => 'Paramètres du calendrier';

  @override
  String get calendarProviders => 'Fournisseurs de calendrier';

  @override
  String get macOsCalendar => 'Calendrier macOS';

  @override
  String get connectMacOsCalendar => 'Connectez votre calendrier macOS local';

  @override
  String get googleCalendar => 'Google Agenda';

  @override
  String get syncGoogleAccount => 'Synchroniser avec votre compte Google';

  @override
  String get showMeetingsMenuBar => 'Afficher les réunions à venir dans la barre de menus';

  @override
  String get showMeetingsMenuBarDesc =>
      'Afficher votre prochaine réunion et le temps restant avant son début dans la barre de menus macOS';

  @override
  String get showEventsNoParticipants => 'Afficher les événements sans participants';

  @override
  String get showEventsNoParticipantsDesc =>
      'Lorsque activé, À venir affiche les événements sans participants ou lien vidéo.';

  @override
  String get yourMeetings => 'Vos réunions';

  @override
  String get refresh => 'Actualiser';

  @override
  String get noUpcomingMeetings => 'Aucune réunion à venir trouvée';

  @override
  String get checkingNextDays => 'Vérification des 30 prochains jours';

  @override
  String get tomorrow => 'Demain';

  @override
  String get googleCalendarComingSoon => 'L\'intégration Google Agenda arrive bientôt !';

  @override
  String connectedAsUser(String userId) {
    return 'Connecté en tant qu\'utilisateur : $userId';
  }

  @override
  String get defaultWorkspace => 'Espace de travail par défaut';

  @override
  String get tasksCreatedInWorkspace => 'Les tâches seront créées dans cet espace de travail';

  @override
  String get defaultProjectOptional => 'Projet par défaut (facultatif)';

  @override
  String get leaveUnselectedTasks => 'Laissez non sélectionné pour créer des tâches sans projet';

  @override
  String get noProjectsInWorkspace => 'Aucun projet trouvé dans cet espace de travail';

  @override
  String get conversationTimeoutDesc =>
      'Choisissez combien de temps attendre en silence avant de terminer automatiquement une conversation :';

  @override
  String get timeout2Minutes => '2 minutes';

  @override
  String get timeout2MinutesDesc => 'Terminer la conversation après 2 minutes de silence';

  @override
  String get timeout5Minutes => '5 minutes';

  @override
  String get timeout5MinutesDesc => 'Terminer la conversation après 5 minutes de silence';

  @override
  String get timeout10Minutes => '10 minutes';

  @override
  String get timeout10MinutesDesc => 'Terminer la conversation après 10 minutes de silence';

  @override
  String get timeout30Minutes => '30 minutes';

  @override
  String get timeout30MinutesDesc => 'Terminer la conversation après 30 minutes de silence';

  @override
  String get timeout4Hours => '4 heures';

  @override
  String get timeout4HoursDesc => 'Terminer la conversation après 4 heures de silence';

  @override
  String get conversationEndAfterHours => 'Les conversations se termineront maintenant après 4 heures de silence';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return 'Les conversations se termineront maintenant après $minutes minute(s) de silence';
  }

  @override
  String get tellUsPrimaryLanguage => 'Dites-nous votre langue principale';

  @override
  String get languageForTranscription =>
      'Définissez votre langue pour des transcriptions plus précises et une expérience personnalisée.';

  @override
  String get singleLanguageModeInfo =>
      'Le mode langue unique est activé. La traduction est désactivée pour une meilleure précision.';

  @override
  String get searchLanguageHint => 'Rechercher une langue par nom ou code';

  @override
  String get noLanguagesFound => 'Aucune langue trouvée';

  @override
  String get skip => 'Passer';

  @override
  String languageSetTo(String language) {
    return 'Langue définie sur $language';
  }

  @override
  String get failedToSetLanguage => 'Échec de la définition de la langue';

  @override
  String appSettings(String appName) {
    return 'Paramètres de $appName';
  }

  @override
  String disconnectFromApp(String appName) {
    return 'Déconnecter de $appName ?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return 'Cela supprimera votre authentification $appName. Vous devrez vous reconnecter pour l\'utiliser à nouveau.';
  }

  @override
  String connectedToApp(String appName) {
    return 'Connecté à $appName';
  }

  @override
  String get account => 'Compte';

  @override
  String actionItemsSyncedTo(String appName) {
    return 'Vos actions à faire seront synchronisées avec votre compte $appName';
  }

  @override
  String get defaultSpace => 'Espace par défaut';

  @override
  String get selectSpaceInWorkspace => 'Sélectionnez un espace dans votre espace de travail';

  @override
  String get noSpacesInWorkspace => 'Aucun espace trouvé dans cet espace de travail';

  @override
  String get defaultList => 'Liste par défaut';

  @override
  String get tasksAddedToList => 'Les tâches seront ajoutées à cette liste';

  @override
  String get noListsInSpace => 'Aucune liste trouvée dans cet espace';

  @override
  String failedToLoadRepos(String error) {
    return 'Échec du chargement des dépôts : $error';
  }

  @override
  String get defaultRepoSaved => 'Dépôt par défaut enregistré';

  @override
  String get failedToSaveDefaultRepo => 'Échec de l\'enregistrement du dépôt par défaut';

  @override
  String get defaultRepository => 'Dépôt par défaut';

  @override
  String get selectDefaultRepoDesc =>
      'Sélectionnez un dépôt par défaut pour créer des issues. Vous pouvez toujours spécifier un autre dépôt lors de la création d\'issues.';

  @override
  String get noReposFound => 'Aucun dépôt trouvé';

  @override
  String get private => 'Privé';

  @override
  String updatedDate(String date) {
    return 'Mis à jour $date';
  }

  @override
  String get yesterday => 'hier';

  @override
  String daysAgo(int count) {
    return 'il y a $count jours';
  }

  @override
  String get oneWeekAgo => 'il y a 1 semaine';

  @override
  String weeksAgo(int count) {
    return 'il y a $count semaines';
  }

  @override
  String get oneMonthAgo => 'il y a 1 mois';

  @override
  String monthsAgo(int count) {
    return 'il y a $count mois';
  }

  @override
  String get issuesCreatedInRepo => 'Les issues seront créées dans votre dépôt par défaut';

  @override
  String get taskIntegrations => 'Intégrations de tâches';

  @override
  String get configureSettings => 'Configurer les paramètres';

  @override
  String get completeAuthBrowser =>
      'Veuillez compléter l\'authentification dans votre navigateur. Une fois terminé, revenez à l\'application.';

  @override
  String failedToStartAppAuth(String appName) {
    return 'Échec du démarrage de l\'authentification $appName';
  }

  @override
  String connectToAppTitle(String appName) {
    return 'Se connecter à $appName';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return 'Vous devrez autoriser Omi à créer des tâches dans votre compte $appName. Cela ouvrira votre navigateur pour l\'authentification.';
  }

  @override
  String get continueButton => 'Continuer';

  @override
  String appIntegration(String appName) {
    return 'Intégration $appName';
  }

  @override
  String integrationComingSoon(String appName) {
    return 'L\'intégration avec $appName arrive bientôt ! Nous travaillons dur pour vous apporter plus d\'options de gestion des tâches.';
  }

  @override
  String get gotIt => 'Compris';

  @override
  String get tasksExportedOneApp => 'Les tâches peuvent être exportées vers une seule application à la fois.';

  @override
  String get completeYourUpgrade => 'Complétez votre mise à niveau';

  @override
  String get importConfiguration => 'Importer la configuration';

  @override
  String get exportConfiguration => 'Exporter la configuration';

  @override
  String get bringYourOwn => 'Apportez le vôtre';

  @override
  String get payYourSttProvider => 'Utilisez Omi librement. Vous ne payez que votre fournisseur STT directement.';

  @override
  String get freeMinutesMonth => '1 200 minutes gratuites/mois incluses. Illimité avec ';

  @override
  String get omiUnlimited => 'Omi Illimité';

  @override
  String get hostRequired => 'L\'hôte est requis';

  @override
  String get validPortRequired => 'Un port valide est requis';

  @override
  String get validWebsocketUrlRequired => 'Une URL WebSocket valide est requise (wss://)';

  @override
  String get apiUrlRequired => 'L\'URL de l\'API est requise';

  @override
  String get apiKeyRequired => 'La clé API est requise';

  @override
  String get invalidJsonConfig => 'Configuration JSON invalide';

  @override
  String errorSaving(String error) {
    return 'Erreur d\'enregistrement : $error';
  }

  @override
  String get configCopiedToClipboard => 'Configuration copiée dans le presse-papiers';

  @override
  String get pasteJsonConfig => 'Collez votre configuration JSON ci-dessous :';

  @override
  String get addApiKeyAfterImport => 'Vous devrez ajouter votre propre clé API après l\'importation';

  @override
  String get paste => 'Coller';

  @override
  String get import => 'Importer';

  @override
  String get invalidProviderInConfig => 'Fournisseur invalide dans la configuration';

  @override
  String importedConfig(String providerName) {
    return 'Configuration $providerName importée';
  }

  @override
  String invalidJson(String error) {
    return 'JSON invalide : $error';
  }

  @override
  String get provider => 'Fournisseur';

  @override
  String get live => 'En direct';

  @override
  String get onDevice => 'Sur l\'appareil';

  @override
  String get apiUrl => 'URL de l\'API';

  @override
  String get enterSttHttpEndpoint => 'Entrez votre point de terminaison HTTP STT';

  @override
  String get websocketUrl => 'URL WebSocket';

  @override
  String get enterLiveSttWebsocket => 'Entrez votre point de terminaison WebSocket STT en direct';

  @override
  String get apiKey => 'Clé API';

  @override
  String get enterApiKey => 'Entrez votre clé API';

  @override
  String get storedLocallyNeverShared => 'Stocké localement, jamais partagé';

  @override
  String get host => 'Hôte';

  @override
  String get port => 'Port';

  @override
  String get advanced => 'Avancé';

  @override
  String get configuration => 'Configuration';

  @override
  String get requestConfiguration => 'Configuration de la requête';

  @override
  String get responseSchema => 'Schéma de réponse';

  @override
  String get modified => 'Modifié';

  @override
  String get resetRequestConfig => 'Réinitialiser la config de requête par défaut';

  @override
  String get logs => 'Journaux';

  @override
  String get logsCopied => 'Journaux copiés';

  @override
  String get noLogsYet => 'Pas encore de journaux. Commencez à enregistrer pour voir l\'activité STT personnalisée.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName utilise $codecReason. Omi sera utilisé.';
  }

  @override
  String get omiTranscription => 'Transcription Omi';

  @override
  String get bestInClassTranscription => 'Transcription de premier ordre sans configuration';

  @override
  String get instantSpeakerLabels => 'Étiquettes de locuteur instantanées';

  @override
  String get languageTranslation => 'Traduction dans plus de 100 langues';

  @override
  String get optimizedForConversation => 'Optimisé pour la conversation';

  @override
  String get autoLanguageDetection => 'Détection automatique de la langue';

  @override
  String get highAccuracy => 'Haute précision';

  @override
  String get privacyFirst => 'Confidentialité d\'abord';

  @override
  String get saveChanges => 'Enregistrer les modifications';

  @override
  String get resetToDefault => 'Réinitialiser par défaut';

  @override
  String get viewTemplate => 'Voir le modèle';

  @override
  String get trySomethingLike => 'Essayez quelque chose comme...';

  @override
  String get tryIt => 'Essayer';

  @override
  String get creatingPlan => 'Création du plan';

  @override
  String get developingLogic => 'Développement de la logique';

  @override
  String get designingApp => 'Conception de l\'application';

  @override
  String get generatingIconStep => 'Génération de l\'icône';

  @override
  String get finalTouches => 'Touches finales';

  @override
  String get processing => 'Traitement...';

  @override
  String get features => 'Fonctionnalités';

  @override
  String get creatingYourApp => 'Création de votre application...';

  @override
  String get generatingIcon => 'Génération de l\'icône...';

  @override
  String get whatShouldWeMake => 'Que devrions-nous créer ?';

  @override
  String get appName => 'Nom de l\'application';

  @override
  String get description => 'Description';

  @override
  String get publicLabel => 'Public';

  @override
  String get privateLabel => 'Privé';

  @override
  String get free => 'Gratuit';

  @override
  String get perMonth => '/ Mois';

  @override
  String get tailoredConversationSummaries => 'Résumés de conversation personnalisés';

  @override
  String get customChatbotPersonality => 'Personnalité de chatbot personnalisée';

  @override
  String get makePublic => 'Rendre public';

  @override
  String get anyoneCanDiscover => 'N\'importe qui peut découvrir votre application';

  @override
  String get onlyYouCanUse => 'Vous seul pouvez utiliser cette application';

  @override
  String get paidApp => 'Application payante';

  @override
  String get usersPayToUse => 'Les utilisateurs paient pour utiliser votre application';

  @override
  String get freeForEveryone => 'Gratuit pour tous';

  @override
  String get perMonthLabel => '/ mois';

  @override
  String get creating => 'Création...';

  @override
  String get createApp => 'Créer l\'application';

  @override
  String get searchingForDevices => 'Recherche d\'appareils...';

  @override
  String devicesFoundNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'APPAREILS',
      one: 'APPAREIL',
    );
    return '$count $_temp0 TROUVÉ(S) À PROXIMITÉ';
  }

  @override
  String get pairingSuccessful => 'APPAIRAGE RÉUSSI';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Erreur de connexion à l\'Apple Watch : $error';
  }

  @override
  String get dontShowAgain => 'Ne plus afficher';

  @override
  String get iUnderstand => 'Je comprends';

  @override
  String get enableBluetooth => 'Activer le Bluetooth';

  @override
  String get bluetoothNeeded =>
      'Omi a besoin du Bluetooth pour se connecter à votre wearable. Veuillez activer le Bluetooth et réessayer.';

  @override
  String get contactSupport => 'Contacter le support ?';

  @override
  String get connectLater => 'Se connecter plus tard';

  @override
  String get grantPermissions => 'Accorder les autorisations';

  @override
  String get backgroundActivity => 'Activité en arrière-plan';

  @override
  String get backgroundActivityDesc => 'Laissez Omi fonctionner en arrière-plan pour une meilleure stabilité';

  @override
  String get locationAccess => 'Accès à la localisation';

  @override
  String get locationAccessDesc => 'Activez la localisation en arrière-plan pour l\'expérience complète';

  @override
  String get notifications => 'Notifications';

  @override
  String get notificationsDesc => 'Activez les notifications pour rester informé';

  @override
  String get locationServiceDisabled => 'Service de localisation désactivé';

  @override
  String get locationServiceDisabledDesc =>
      'Le service de localisation est désactivé. Veuillez aller dans Réglages > Confidentialité et sécurité > Services de localisation et l\'activer';

  @override
  String get backgroundLocationDenied => 'Accès à la localisation en arrière-plan refusé';

  @override
  String get backgroundLocationDeniedDesc =>
      'Veuillez aller dans les paramètres de l\'appareil et définir l\'autorisation de localisation sur « Toujours autoriser »';

  @override
  String get lovingOmi => 'Vous aimez Omi ?';

  @override
  String get leaveReviewIos =>
      'Aidez-nous à atteindre plus de personnes en laissant un avis sur l\'App Store. Votre retour compte énormément pour nous !';

  @override
  String get leaveReviewAndroid =>
      'Aidez-nous à atteindre plus de personnes en laissant un avis sur le Google Play Store. Votre retour compte énormément pour nous !';

  @override
  String get rateOnAppStore => 'Noter sur l\'App Store';

  @override
  String get rateOnGooglePlay => 'Noter sur Google Play';

  @override
  String get maybeLater => 'Peut-être plus tard';

  @override
  String get speechProfileIntro =>
      'Omi doit apprendre vos objectifs et votre voix. Vous pourrez les modifier plus tard.';

  @override
  String get getStarted => 'Commencer';

  @override
  String get allDone => 'Terminé !';

  @override
  String get keepGoing => 'Continuez, vous vous en sortez très bien';

  @override
  String get skipThisQuestion => 'Passer cette question';

  @override
  String get skipForNow => 'Passer pour l\'instant';

  @override
  String get connectionError => 'Erreur de connexion';

  @override
  String get connectionErrorDesc =>
      'Échec de la connexion au serveur. Veuillez vérifier votre connexion internet et réessayer.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Enregistrement invalide détecté';

  @override
  String get multipleSpeakersDesc =>
      'Il semble y avoir plusieurs locuteurs dans l\'enregistrement. Veuillez vous assurer d\'être dans un endroit calme et réessayer.';

  @override
  String get tooShortDesc => 'Pas assez de parole détectée. Veuillez parler davantage et réessayer.';

  @override
  String get invalidRecordingDesc => 'Veuillez vous assurer de parler pendant au moins 5 secondes et pas plus de 90.';

  @override
  String get areYouThere => 'Êtes-vous là ?';

  @override
  String get noSpeechDesc =>
      'Nous n\'avons pas pu détecter de parole. Veuillez vous assurer de parler pendant au moins 10 secondes et pas plus de 3 minutes.';

  @override
  String get connectionLost => 'Connexion perdue';

  @override
  String get connectionLostDesc =>
      'La connexion a été interrompue. Veuillez vérifier votre connexion internet et réessayer.';

  @override
  String get tryAgain => 'Réessayer';

  @override
  String get connectOmiOmiGlass => 'Connecter Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Continuer sans appareil';

  @override
  String get permissionsRequired => 'Autorisations requises';

  @override
  String get permissionsRequiredDesc =>
      'Cette application a besoin des autorisations Bluetooth et Localisation pour fonctionner correctement. Veuillez les activer dans les paramètres.';

  @override
  String get openSettings => 'Ouvrir les paramètres';

  @override
  String get wantDifferentName => 'Voulez-vous utiliser un autre nom ?';

  @override
  String get whatsYourName => 'Comment vous appelez-vous ?';

  @override
  String get speakTranscribeSummarize => 'Parlez. Transcrivez. Résumez.';

  @override
  String get signInWithApple => 'Se connecter avec Apple';

  @override
  String get signInWithGoogle => 'Se connecter avec Google';

  @override
  String get byContinuingAgree => 'En continuant, vous acceptez notre ';

  @override
  String get termsOfUse => 'Conditions d\'utilisation';

  @override
  String get omiYourAiCompanion => 'Omi – Votre compagnon IA';

  @override
  String get captureEveryMoment =>
      'Capturez chaque moment. Obtenez des résumés\nalimentés par l\'IA. Ne prenez plus jamais de notes.';

  @override
  String get appleWatchSetup => 'Configuration Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Permission demandée !';

  @override
  String get microphonePermission => 'Permission du microphone';

  @override
  String get permissionGrantedNow =>
      'Permission accordée ! Maintenant :\n\nOuvrez l\'application Omi sur votre montre et appuyez sur « Continuer » ci-dessous';

  @override
  String get needMicrophonePermission =>
      'Nous avons besoin de la permission du microphone.\n\n1. Appuyez sur « Accorder la permission »\n2. Autorisez sur votre iPhone\n3. L\'application de la montre se fermera\n4. Rouvrez et appuyez sur « Continuer »';

  @override
  String get grantPermissionButton => 'Accorder la permission';

  @override
  String get needHelp => 'Besoin d\'aide ?';

  @override
  String get troubleshootingSteps =>
      'Dépannage :\n\n1. Assurez-vous qu\'Omi est installé sur votre montre\n2. Ouvrez l\'application Omi sur votre montre\n3. Recherchez la fenêtre de permission\n4. Appuyez sur « Autoriser » lorsque demandé\n5. L\'application sur votre montre se fermera - rouvrez-la\n6. Revenez et appuyez sur « Continuer » sur votre iPhone';

  @override
  String get recordingStartedSuccessfully => 'Enregistrement démarré avec succès !';

  @override
  String get permissionNotGrantedYet =>
      'Permission non encore accordée. Veuillez vous assurer d\'avoir autorisé l\'accès au microphone et rouvert l\'application sur votre montre.';

  @override
  String errorRequestingPermission(String error) {
    return 'Erreur lors de la demande de permission : $error';
  }

  @override
  String errorStartingRecording(String error) {
    return 'Erreur lors du démarrage de l\'enregistrement : $error';
  }

  @override
  String get selectPrimaryLanguage => 'Sélectionnez votre langue principale';

  @override
  String get languageBenefits =>
      'Définissez votre langue pour des transcriptions plus précises et une expérience personnalisée';

  @override
  String get whatsYourPrimaryLanguage => 'Quelle est votre langue principale ?';

  @override
  String get selectYourLanguage => 'Sélectionnez votre langue';

  @override
  String get personalGrowthJourney =>
      'Votre parcours de croissance personnelle avec une IA qui écoute chacun de vos mots.';

  @override
  String get actionItemsTitle => 'À faire';

  @override
  String get actionItemsDescription =>
      'Appuyez pour modifier • Appui long pour sélectionner • Glissez pour les actions';

  @override
  String get tabToDo => 'À faire';

  @override
  String get tabDone => 'Terminé';

  @override
  String get tabOld => 'Ancien';

  @override
  String get emptyTodoMessage => '🎉 Tout est à jour !\nAucune action en attente';

  @override
  String get emptyDoneMessage => 'Aucun élément terminé pour le moment';

  @override
  String get emptyOldMessage => '✅ Aucune ancienne tâche';

  @override
  String get noItems => 'Aucun élément';

  @override
  String get actionItemMarkedIncomplete => 'Action marquée comme incomplète';

  @override
  String get actionItemCompleted => 'Action terminée';

  @override
  String get deleteActionItemTitle => 'Supprimer l\'action';

  @override
  String get deleteActionItemMessage => 'Êtes-vous sûr de vouloir supprimer cette action ?';

  @override
  String get deleteSelectedItemsTitle => 'Supprimer les éléments sélectionnés';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return 'Êtes-vous sûr de vouloir supprimer $count action(s) sélectionnée(s) ?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return 'Action « $description » supprimée';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count action(s) supprimée(s)';
  }

  @override
  String get failedToDeleteItem => 'Échec de la suppression de l\'action';

  @override
  String get failedToDeleteItems => 'Échec de la suppression des éléments';

  @override
  String get failedToDeleteSomeItems => 'Échec de la suppression de certains éléments';

  @override
  String get welcomeActionItemsTitle => 'Prêt pour les actions';

  @override
  String get welcomeActionItemsDescription =>
      'Votre IA extraira automatiquement les tâches et les choses à faire de vos conversations. Elles apparaîtront ici une fois créées.';

  @override
  String get autoExtractionFeature => 'Extraites automatiquement des conversations';

  @override
  String get editSwipeFeature => 'Appuyez pour modifier, glissez pour terminer ou supprimer';

  @override
  String itemsSelected(int count) {
    return '$count sélectionné(s)';
  }

  @override
  String get selectAll => 'Tout sélectionner';

  @override
  String get deleteSelected => 'Supprimer la sélection';

  @override
  String searchMemories(int count) {
    return 'Rechercher $count mémoires';
  }

  @override
  String get memoryDeleted => 'Mémoire supprimée.';

  @override
  String get undo => 'Annuler';

  @override
  String get noMemoriesYet => 'Pas encore de mémoires';

  @override
  String get noAutoMemories => 'Pas encore de mémoires extraites automatiquement';

  @override
  String get noManualMemories => 'Pas encore de mémoires manuelles';

  @override
  String get noMemoriesInCategories => 'Aucune mémoire dans ces catégories';

  @override
  String get noMemoriesFound => 'Aucune mémoire trouvée';

  @override
  String get addFirstMemory => 'Ajoutez votre première mémoire';

  @override
  String get clearMemoryTitle => 'Effacer la mémoire d\'Omi';

  @override
  String get clearMemoryMessage =>
      'Êtes-vous sûr de vouloir effacer la mémoire d\'Omi ? Cette action est irréversible.';

  @override
  String get clearMemoryButton => 'Effacer la mémoire';

  @override
  String get memoryClearedSuccess => 'La mémoire d\'Omi vous concernant a été effacée';

  @override
  String get noMemoriesToDelete => 'Aucune mémoire à supprimer';

  @override
  String get createMemoryTooltip => 'Créer une nouvelle mémoire';

  @override
  String get createActionItemTooltip => 'Créer une nouvelle action';

  @override
  String get memoryManagement => 'Gestion des mémoires';

  @override
  String get filterMemories => 'Filtrer les mémoires';

  @override
  String totalMemoriesCount(int count) {
    return 'Vous avez $count mémoires au total';
  }

  @override
  String get publicMemories => 'Mémoires publiques';

  @override
  String get privateMemories => 'Mémoires privées';

  @override
  String get makeAllPrivate => 'Rendre toutes les mémoires privées';

  @override
  String get makeAllPublic => 'Rendre toutes les mémoires publiques';

  @override
  String get deleteAllMemories => 'Supprimer toutes les mémoires';

  @override
  String get allMemoriesPrivateResult => 'Toutes les mémoires sont maintenant privées';

  @override
  String get allMemoriesPublicResult => 'Toutes les mémoires sont maintenant publiques';

  @override
  String get newMemory => 'Nouvelle mémoire';

  @override
  String get editMemory => 'Modifier la mémoire';

  @override
  String get memoryContentHint => 'J\'aime manger des glaces...';

  @override
  String get failedToSaveMemory => 'Échec de l\'enregistrement. Veuillez vérifier votre connexion.';

  @override
  String get saveMemory => 'Enregistrer la mémoire';

  @override
  String get retry => 'Réessayer';

  @override
  String get createActionItem => 'Créer une action';

  @override
  String get editActionItem => 'Modifier l\'action';

  @override
  String get actionItemDescriptionHint => 'Que faut-il faire ?';

  @override
  String get actionItemDescriptionEmpty => 'La description de l\'action ne peut pas être vide.';

  @override
  String get actionItemUpdated => 'Action mise à jour';

  @override
  String get failedToUpdateActionItem => 'Échec de la mise à jour de l\'action';

  @override
  String get actionItemCreated => 'Action créée';

  @override
  String get failedToCreateActionItem => 'Échec de la création de l\'action';

  @override
  String get dueDate => 'Date d\'échéance';

  @override
  String get time => 'Heure';

  @override
  String get addDueDate => 'Ajouter une date d\'échéance';

  @override
  String get pressDoneToSave => 'Appuyez sur Terminé pour enregistrer';

  @override
  String get pressDoneToCreate => 'Appuyez sur Terminé pour créer';

  @override
  String get filterAll => 'Tous';

  @override
  String get filterSystem => 'À propos de vous';

  @override
  String get filterInteresting => 'Aperçus';

  @override
  String get filterManual => 'Manuel';

  @override
  String get completed => 'Terminé';

  @override
  String get markComplete => 'Marquer comme terminé';

  @override
  String get actionItemDeleted => 'Action supprimée';

  @override
  String get failedToDeleteActionItem => 'Échec de la suppression de l\'action';

  @override
  String get deleteActionItemConfirmTitle => 'Supprimer l\'action';

  @override
  String get deleteActionItemConfirmMessage => 'Êtes-vous sûr de vouloir supprimer cette action ?';

  @override
  String get appLanguage => 'Langue de l\'application';

  @override
  String get appInterfaceSectionTitle => 'INTERFACE DE L\'APPLICATION';

  @override
  String get speechTranscriptionSectionTitle => 'VOIX ET TRANSCRIPTION';

  @override
  String get languageSettingsHelperText =>
      'La langue de l\'application modifie les menus et les boutons. La langue vocale affecte la transcription de vos enregistrements.';
}
