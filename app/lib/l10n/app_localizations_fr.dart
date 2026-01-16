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
  String get deleteConversationMessage => 'Êtes-vous sûr de vouloir supprimer cette conversation ? Cette action est irréversible.';

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
  String get errorProcessingConversation => 'Erreur lors du traitement de la conversation. Veuillez réessayer plus tard.';

  @override
  String get noInternetConnection => 'Aucune connexion Internet';

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
  String get speechProfile => 'Profil Vocal';

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
  String get pleaseCompleteAuthentication => 'Veuillez compléter l\'authentification dans votre navigateur. Une fois terminé, revenez à l\'application.';

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
  String get searching => 'Recherche en cours...';

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
  String get noConversationsYet => 'Pas encore de conversations';

  @override
  String get noStarredConversations => 'Aucune conversation favorite';

  @override
  String get starConversationHint => 'Pour marquer une conversation comme favorite, ouvrez-la et appuyez sur l\'icône étoile dans l\'en-tête.';

  @override
  String get searchConversations => 'Rechercher des conversations...';

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
  String get messageCopied => '✨ Message copié dans le presse-papiers';

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
  String get searchApps => 'Rechercher des applications...';

  @override
  String get myApps => 'Mes applications';

  @override
  String get installedApps => 'Applications installées';

  @override
  String get unableToFetchApps => 'Impossible de récupérer les applications :(\n\nVeuillez vérifier votre connexion internet et réessayer.';

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
  String get membersAndCounting => '8000+ membres et ça continue.';

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
  String get exportBeforeDelete => 'Vous pouvez exporter vos données avant de supprimer votre compte, mais une fois supprimé, il ne pourra pas être récupéré.';

  @override
  String get deleteAccountCheckbox => 'Je comprends que la suppression de mon compte est permanente et que toutes les données, y compris les mémoires et conversations, seront perdues et ne pourront pas être récupérées.';

  @override
  String get areYouSure => 'Êtes-vous sûr ?';

  @override
  String get deleteAccountFinal => 'Cette action est irréversible et supprimera définitivement votre compte et toutes les données associées. Êtes-vous sûr de vouloir continuer ?';

  @override
  String get deleteNow => 'Supprimer maintenant';

  @override
  String get goBack => 'Retour';

  @override
  String get checkBoxToConfirm => 'Cochez la case pour confirmer que vous comprenez que la suppression de votre compte est permanente et irréversible.';

  @override
  String get profile => 'Profil';

  @override
  String get name => 'Nom';

  @override
  String get email => 'E-mail';

  @override
  String get customVocabulary => 'Vocabulaire Personnalisé';

  @override
  String get identifyingOthers => 'Identification des Autres';

  @override
  String get paymentMethods => 'Méthodes de Paiement';

  @override
  String get conversationDisplay => 'Affichage des Conversations';

  @override
  String get dataPrivacy => 'Confidentialité des Données';

  @override
  String get userId => 'ID Utilisateur';

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
  String get signOut => 'Se Déconnecter';

  @override
  String get appAndDeviceCopied => 'Détails de l\'application et de l\'appareil copiés';

  @override
  String get wrapped2025 => 'Rétrospective 2025';

  @override
  String get yourPrivacyYourControl => 'Votre vie privée, votre contrôle';

  @override
  String get privacyIntro => 'Chez Omi, nous nous engageons à protéger votre vie privée. Cette page vous permet de contrôler la façon dont vos données sont stockées et utilisées.';

  @override
  String get learnMore => 'En savoir plus...';

  @override
  String get dataProtectionLevel => 'Niveau de protection des données';

  @override
  String get dataProtectionDesc => 'Vos données sont sécurisées par défaut avec un cryptage fort. Vérifiez vos paramètres et les futures options de confidentialité ci-dessous.';

  @override
  String get appAccess => 'Accès des applications';

  @override
  String get appAccessDesc => 'Les applications suivantes peuvent accéder à vos données. Appuyez sur une application pour gérer ses autorisations.';

  @override
  String get noAppsExternalAccess => 'Aucune application installée n\'a d\'accès externe à vos données.';

  @override
  String get deviceName => 'Nom de l\'appareil';

  @override
  String get deviceId => 'ID de l\'appareil';

  @override
  String get firmware => 'Micrologiciel';

  @override
  String get sdCardSync => 'Synchronisation de la carte SD';

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
  String get deviceUnpairedMessage => 'Appareil dissocié. Allez dans Paramètres > Bluetooth et oubliez l\'appareil pour terminer la dissociation.';

  @override
  String get unpairDialogTitle => 'Dissocier l\'appareil';

  @override
  String get unpairDialogMessage => 'Cela dissociera l\'appareil afin qu\'il puisse être connecté à un autre téléphone. Vous devrez aller dans Réglages > Bluetooth et oublier l\'appareil pour terminer le processus.';

  @override
  String get deviceNotConnected => 'Appareil non connecté';

  @override
  String get connectDeviceMessage => 'Connectez votre appareil Omi pour accéder aux\nparamètres et à la personnalisation de l\'appareil';

  @override
  String get deviceInfoSection => 'Informations sur l\'appareil';

  @override
  String get customizationSection => 'Personnalisation';

  @override
  String get hardwareSection => 'Matériel';

  @override
  String get v2Undetected => 'V2 non détecté';

  @override
  String get v2UndetectedMessage => 'Nous voyons que vous avez soit un appareil V1, soit votre appareil n\'est pas connecté. La fonctionnalité carte SD n\'est disponible que pour les appareils V2.';

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
  String get createKey => 'Créer une Clé';

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
  String get startConversationToSeeInsights => 'Commencez une conversation avec Omi\npour voir vos statistiques d\'utilisation ici.';

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
  String get upgradeToUnlimited => 'Passer à illimité';

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
  String get deleteKnowledgeGraphMessage => 'Cela supprimera toutes les données du graphe de connaissances dérivées (nœuds et connexions). Vos mémoires originales resteront intactes. Le graphe sera reconstruit au fil du temps ou lors de la prochaine demande.';

  @override
  String get knowledgeGraphDeleted => 'Graphe de connaissances supprimé';

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
  String get insights => 'Informations';

  @override
  String get memories => 'Souvenirs';

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
  String get shortConversationThresholdSubtitle => 'Les conversations plus courtes que cela seront masquées sauf si activé ci-dessus';

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
  String get completeAuthInBrowser => 'Veuillez compléter l\'authentification dans votre navigateur. Une fois terminé, revenez à l\'application.';

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
  String get alreadyGavePermission => 'Vous nous avez déjà donné la permission d\'enregistrer vos enregistrements. Voici un rappel de pourquoi nous en avons besoin :';

  @override
  String get wouldLikePermission => 'Nous aimerions avoir votre permission pour sauvegarder vos enregistrements vocaux. Voici pourquoi :';

  @override
  String get improveSpeechProfile => 'Améliorer votre profil vocal';

  @override
  String get improveSpeechProfileDesc => 'Nous utilisons les enregistrements pour entraîner et améliorer davantage votre profil vocal personnel.';

  @override
  String get trainFamilyProfiles => 'Entraîner des profils pour les amis et la famille';

  @override
  String get trainFamilyProfilesDesc => 'Vos enregistrements nous aident à reconnaître et créer des profils pour vos amis et votre famille.';

  @override
  String get enhanceTranscriptAccuracy => 'Améliorer la précision de la transcription';

  @override
  String get enhanceTranscriptAccuracyDesc => 'À mesure que notre modèle s\'améliore, nous pouvons fournir de meilleurs résultats de transcription pour vos enregistrements.';

  @override
  String get legalNotice => 'Avis juridique : La légalité de l\'enregistrement et du stockage des données vocales peut varier selon votre emplacement et la façon dont vous utilisez cette fonctionnalité. Il est de votre responsabilité de vous assurer de la conformité aux lois et réglementations locales.';

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
  String get permissionRevokedMessage => 'Voulez-vous que nous supprimions également tous vos enregistrements existants ?';

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
  String get showMeetingsMenuBarDesc => 'Afficher votre prochaine réunion et le temps restant avant son début dans la barre de menus macOS';

  @override
  String get showEventsNoParticipants => 'Afficher les événements sans participants';

  @override
  String get showEventsNoParticipantsDesc => 'Lorsque activé, À venir affiche les événements sans participants ou lien vidéo.';

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
  String get conversationTimeoutDesc => 'Choisissez combien de temps attendre en silence avant de terminer automatiquement une conversation :';

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
  String get languageForTranscription => 'Définissez votre langue pour des transcriptions plus précises et une expérience personnalisée.';

  @override
  String get singleLanguageModeInfo => 'Le mode langue unique est activé. La traduction est désactivée pour une meilleure précision.';

  @override
  String get searchLanguageHint => 'Rechercher une langue par nom ou code';

  @override
  String get noLanguagesFound => 'Aucune langue trouvée';

  @override
  String get skip => 'Ignorer';

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
  String get selectDefaultRepoDesc => 'Sélectionnez un dépôt par défaut pour créer des issues. Vous pouvez toujours spécifier un autre dépôt lors de la création d\'issues.';

  @override
  String get noReposFound => 'Aucun dépôt trouvé';

  @override
  String get private => 'Privé';

  @override
  String updatedDate(String date) {
    return 'Mis à jour $date';
  }

  @override
  String get yesterday => 'Hier';

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
  String get completeAuthBrowser => 'Veuillez compléter l\'authentification dans votre navigateur. Une fois terminé, revenez à l\'application.';

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
  String get createApp => 'Créer une application';

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
  String get bluetoothNeeded => 'Omi a besoin du Bluetooth pour se connecter à votre wearable. Veuillez activer le Bluetooth et réessayer.';

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
  String get locationServiceDisabledDesc => 'Le service de localisation est désactivé. Veuillez aller dans Réglages > Confidentialité et sécurité > Services de localisation et l\'activer';

  @override
  String get backgroundLocationDenied => 'Accès à la localisation en arrière-plan refusé';

  @override
  String get backgroundLocationDeniedDesc => 'Veuillez aller dans les paramètres de l\'appareil et définir l\'autorisation de localisation sur « Toujours autoriser »';

  @override
  String get lovingOmi => 'Vous aimez Omi ?';

  @override
  String get leaveReviewIos => 'Aidez-nous à atteindre plus de personnes en laissant un avis sur l\'App Store. Votre retour compte énormément pour nous !';

  @override
  String get leaveReviewAndroid => 'Aidez-nous à atteindre plus de personnes en laissant un avis sur le Google Play Store. Votre retour compte énormément pour nous !';

  @override
  String get rateOnAppStore => 'Noter sur l\'App Store';

  @override
  String get rateOnGooglePlay => 'Noter sur Google Play';

  @override
  String get maybeLater => 'Peut-être plus tard';

  @override
  String get speechProfileIntro => 'Omi doit apprendre vos objectifs et votre voix. Vous pourrez les modifier plus tard.';

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
  String get connectionErrorDesc => 'Échec de la connexion au serveur. Veuillez vérifier votre connexion internet et réessayer.';

  @override
  String get invalidRecordingMultipleSpeakers => 'Enregistrement invalide détecté';

  @override
  String get multipleSpeakersDesc => 'Il semble y avoir plusieurs locuteurs dans l\'enregistrement. Veuillez vous assurer d\'être dans un endroit calme et réessayer.';

  @override
  String get tooShortDesc => 'Pas assez de parole détectée. Veuillez parler davantage et réessayer.';

  @override
  String get invalidRecordingDesc => 'Veuillez vous assurer de parler pendant au moins 5 secondes et pas plus de 90.';

  @override
  String get areYouThere => 'Êtes-vous là ?';

  @override
  String get noSpeechDesc => 'Nous n\'avons pas pu détecter de parole. Veuillez vous assurer de parler pendant au moins 10 secondes et pas plus de 3 minutes.';

  @override
  String get connectionLost => 'Connexion perdue';

  @override
  String get connectionLostDesc => 'La connexion a été interrompue. Veuillez vérifier votre connexion internet et réessayer.';

  @override
  String get tryAgain => 'Réessayer';

  @override
  String get connectOmiOmiGlass => 'Connecter Omi / OmiGlass';

  @override
  String get continueWithoutDevice => 'Continuer sans appareil';

  @override
  String get permissionsRequired => 'Autorisations requises';

  @override
  String get permissionsRequiredDesc => 'Cette application a besoin des autorisations Bluetooth et Localisation pour fonctionner correctement. Veuillez les activer dans les paramètres.';

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
  String get captureEveryMoment => 'Capturez chaque moment. Obtenez des résumés\nalimentés par l\'IA. Ne prenez plus jamais de notes.';

  @override
  String get appleWatchSetup => 'Configuration Apple Watch';

  @override
  String get permissionRequestedExclaim => 'Permission demandée !';

  @override
  String get microphonePermission => 'Permission du microphone';

  @override
  String get permissionGrantedNow => 'Permission accordée ! Maintenant :\n\nOuvrez l\'application Omi sur votre montre et appuyez sur « Continuer » ci-dessous';

  @override
  String get needMicrophonePermission => 'Nous avons besoin de la permission du microphone.\n\n1. Appuyez sur « Accorder la permission »\n2. Autorisez sur votre iPhone\n3. L\'application de la montre se fermera\n4. Rouvrez et appuyez sur « Continuer »';

  @override
  String get grantPermissionButton => 'Accorder la permission';

  @override
  String get needHelp => 'Besoin d\'aide ?';

  @override
  String get troubleshootingSteps => 'Dépannage :\n\n1. Assurez-vous qu\'Omi est installé sur votre montre\n2. Ouvrez l\'application Omi sur votre montre\n3. Recherchez la fenêtre de permission\n4. Appuyez sur « Autoriser » lorsque demandé\n5. L\'application sur votre montre se fermera - rouvrez-la\n6. Revenez et appuyez sur « Continuer » sur votre iPhone';

  @override
  String get recordingStartedSuccessfully => 'Enregistrement démarré avec succès !';

  @override
  String get permissionNotGrantedYet => 'Permission non encore accordée. Veuillez vous assurer d\'avoir autorisé l\'accès au microphone et rouvert l\'application sur votre montre.';

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
  String get languageBenefits => 'Définissez votre langue pour des transcriptions plus précises et une expérience personnalisée';

  @override
  String get whatsYourPrimaryLanguage => 'Quelle est votre langue principale ?';

  @override
  String get selectYourLanguage => 'Sélectionnez votre langue';

  @override
  String get personalGrowthJourney => 'Votre parcours de croissance personnelle avec une IA qui écoute chacun de vos mots.';

  @override
  String get actionItemsTitle => 'À faire';

  @override
  String get actionItemsDescription => 'Appuyez pour modifier • Appui long pour sélectionner • Glissez pour les actions';

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
  String get deleteActionItemTitle => 'Supprimer l\'élément d\'action';

  @override
  String get deleteActionItemMessage => 'Êtes-vous sûr de vouloir supprimer cet élément d\'action?';

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
  String get welcomeActionItemsDescription => 'Votre IA extraira automatiquement les tâches et les choses à faire de vos conversations. Elles apparaîtront ici une fois créées.';

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
  String get searchMemories => 'Rechercher des souvenirs...';

  @override
  String get memoryDeleted => 'Mémoire supprimée.';

  @override
  String get undo => 'Annuler';

  @override
  String get noMemoriesYet => '🧠 Pas encore de souvenirs';

  @override
  String get noAutoMemories => 'Pas encore de mémoires extraites automatiquement';

  @override
  String get noManualMemories => 'Pas encore de mémoires manuelles';

  @override
  String get noMemoriesInCategories => 'Aucune mémoire dans ces catégories';

  @override
  String get noMemoriesFound => '🔍 Aucun souvenir trouvé';

  @override
  String get addFirstMemory => 'Ajoutez votre première mémoire';

  @override
  String get clearMemoryTitle => 'Effacer la mémoire d\'Omi';

  @override
  String get clearMemoryMessage => 'Êtes-vous sûr de vouloir effacer la mémoire d\'Omi ? Cette action est irréversible.';

  @override
  String get clearMemoryButton => 'Effacer la mémoire';

  @override
  String get memoryClearedSuccess => 'La mémoire d\'Omi vous concernant a été effacée';

  @override
  String get noMemoriesToDelete => 'Aucun souvenir à supprimer';

  @override
  String get createMemoryTooltip => 'Créer une nouvelle mémoire';

  @override
  String get createActionItemTooltip => 'Créer une nouvelle action';

  @override
  String get memoryManagement => 'Gestion de la mémoire';

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
  String get deleteAllMemories => 'Supprimer tous les souvenirs';

  @override
  String get allMemoriesPrivateResult => 'Toutes les mémoires sont maintenant privées';

  @override
  String get allMemoriesPublicResult => 'Toutes les mémoires sont maintenant publiques';

  @override
  String get newMemory => '✨ Nouveau souvenir';

  @override
  String get editMemory => '✏️ Modifier le souvenir';

  @override
  String get memoryContentHint => 'J\'aime manger des glaces...';

  @override
  String get failedToSaveMemory => 'Échec de l\'enregistrement. Veuillez vérifier votre connexion.';

  @override
  String get saveMemory => 'Enregistrer la mémoire';

  @override
  String get retry => 'Réessayer';

  @override
  String get createActionItem => 'Créer une tâche';

  @override
  String get editActionItem => 'Modifier la tâche';

  @override
  String get actionItemDescriptionHint => 'Que faut-il faire ?';

  @override
  String get actionItemDescriptionEmpty => 'La description de l\'action ne peut pas être vide.';

  @override
  String get actionItemUpdated => 'Action mise à jour';

  @override
  String get failedToUpdateActionItem => 'Échec de la mise à jour de la tâche';

  @override
  String get actionItemCreated => 'Action créée';

  @override
  String get failedToCreateActionItem => 'Échec de la création de la tâche';

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
  String get actionItemDeleted => 'Élément d\'action supprimé';

  @override
  String get failedToDeleteActionItem => 'Échec de la suppression de la tâche';

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
  String get languageSettingsHelperText => 'La langue de l\'application modifie les menus et les boutons. La langue vocale affecte la transcription de vos enregistrements.';

  @override
  String get translationNotice => 'Avis de traduction';

  @override
  String get translationNoticeMessage => 'Omi traduit les conversations dans votre langue principale. Mettez-la à jour à tout moment dans Paramètres → Profils.';

  @override
  String get pleaseCheckInternetConnection => 'Veuillez vérifier votre connexion Internet et réessayer';

  @override
  String get pleaseSelectReason => 'Veuillez sélectionner une raison';

  @override
  String get tellUsMoreWhatWentWrong => 'Dites-nous en plus sur ce qui s\'est mal passé...';

  @override
  String get selectText => 'Sélectionner le texte';

  @override
  String maximumGoalsAllowed(int count) {
    return 'Maximum $count objectifs autorisés';
  }

  @override
  String get conversationCannotBeMerged => 'Cette conversation ne peut pas être fusionnée (verrouillée ou déjà en cours de fusion)';

  @override
  String get pleaseEnterFolderName => 'Veuillez saisir un nom de dossier';

  @override
  String get failedToCreateFolder => 'Échec de la création du dossier';

  @override
  String get failedToUpdateFolder => 'Échec de la mise à jour du dossier';

  @override
  String get folderName => 'Nom du dossier';

  @override
  String get descriptionOptional => 'Description (facultatif)';

  @override
  String get failedToDeleteFolder => 'Échec de la suppression du dossier';

  @override
  String get editFolder => 'Modifier le dossier';

  @override
  String get deleteFolder => 'Supprimer le dossier';

  @override
  String get transcriptCopiedToClipboard => 'Transcription copiée dans le presse-papiers';

  @override
  String get summaryCopiedToClipboard => 'Résumé copié dans le presse-papiers';

  @override
  String get conversationUrlCouldNotBeShared => 'L\'URL de la conversation n\'a pas pu être partagée.';

  @override
  String get urlCopiedToClipboard => 'URL copiée dans le presse-papiers';

  @override
  String get exportTranscript => 'Exporter la transcription';

  @override
  String get exportSummary => 'Exporter le résumé';

  @override
  String get exportButton => 'Exporter';

  @override
  String get actionItemsCopiedToClipboard => 'Éléments d\'action copiés dans le presse-papiers';

  @override
  String get summarize => 'Résumer';

  @override
  String get generateSummary => 'Générer un résumé';

  @override
  String get conversationNotFoundOrDeleted => 'Conversation introuvable ou supprimée';

  @override
  String get deleteMemory => 'Supprimer le souvenir';

  @override
  String get thisActionCannotBeUndone => 'Cette action ne peut pas être annulée.';

  @override
  String memoriesCount(int count) {
    return '$count souvenirs';
  }

  @override
  String get noMemoriesInCategory => 'Aucun souvenir dans cette catégorie pour le moment';

  @override
  String get addYourFirstMemory => 'Ajoutez votre premier souvenir';

  @override
  String get firmwareDisconnectUsb => 'Déconnecter USB';

  @override
  String get firmwareUsbWarning => 'La connexion USB pendant les mises à jour peut endommager votre appareil.';

  @override
  String get firmwareBatteryAbove15 => 'Batterie supérieure à 15%';

  @override
  String get firmwareEnsureBattery => 'Assurez-vous que votre appareil a 15% de batterie.';

  @override
  String get firmwareStableConnection => 'Connexion stable';

  @override
  String get firmwareConnectWifi => 'Connectez-vous au WiFi ou aux données cellulaires.';

  @override
  String failedToStartUpdate(String error) {
    return 'Échec du démarrage de la mise à jour: $error';
  }

  @override
  String get beforeUpdateMakeSure => 'Avant la mise à jour, assurez-vous:';

  @override
  String get confirmed => 'Confirmé!';

  @override
  String get release => 'Relâcher';

  @override
  String get slideToUpdate => 'Glisser pour mettre à jour';

  @override
  String copiedToClipboard(String title) {
    return '$title copié dans le presse-papiers';
  }

  @override
  String get batteryLevel => 'Niveau de batterie';

  @override
  String get productUpdate => 'Mise à jour du produit';

  @override
  String get offline => 'Hors ligne';

  @override
  String get available => 'Disponible';

  @override
  String get unpairDeviceDialogTitle => 'Dissocier l\'appareil';

  @override
  String get unpairDeviceDialogMessage => 'Cela dissociera l\'appareil pour qu\'il puisse être connecté à un autre téléphone. Vous devrez aller dans Paramètres > Bluetooth et oublier l\'appareil pour terminer le processus.';

  @override
  String get unpair => 'Dissocier';

  @override
  String get unpairAndForgetDevice => 'Dissocier et oublier l\'appareil';

  @override
  String get unknownDevice => 'Périphérique inconnu';

  @override
  String get unknown => 'Inconnu';

  @override
  String get productName => 'Nom du produit';

  @override
  String get serialNumber => 'Numéro de série';

  @override
  String get connected => 'Connecté';

  @override
  String get privacyPolicyTitle => 'Politique de confidentialité';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label copied';
  }

  @override
  String get noApiKeysYet => 'Pas encore de clés API. Créez-en une pour intégrer votre application.';

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
  String get debugAndDiagnostics => 'Débogage et diagnostics';

  @override
  String get autoDeletesAfter3Days => 'Suppression automatique après 3 jours';

  @override
  String get helpsDiagnoseIssues => 'Aide à diagnostiquer les problèmes';

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
  String get realTimeTranscript => 'Transcription en temps réel';

  @override
  String get experimental => 'Expérimental';

  @override
  String get transcriptionDiagnostics => 'Diagnostics de transcription';

  @override
  String get detailedDiagnosticMessages => 'Messages de diagnostic détaillés';

  @override
  String get autoCreateSpeakers => 'Créer automatiquement les locuteurs';

  @override
  String get autoCreateWhenNameDetected => 'Auto-create when name detected';

  @override
  String get followUpQuestions => 'Questions de suivi';

  @override
  String get suggestQuestionsAfterConversations => 'Suggérer des questions après les conversations';

  @override
  String get goalTracker => 'Suivi des objectifs';

  @override
  String get trackPersonalGoalsOnHomepage => 'Track your personal goals on homepage';

  @override
  String get dailyReflection => 'Réflexion quotidienne';

  @override
  String get get9PmReminderToReflect => 'Get a 9 PM reminder to reflect on your day';

  @override
  String get actionItemDescriptionCannotBeEmpty => 'La description de l\'élément d\'action ne peut pas être vide';

  @override
  String get saved => 'Enregistré';

  @override
  String get overdue => 'En retard';

  @override
  String get failedToUpdateDueDate => 'Échec de la mise à jour de la date d\'échéance';

  @override
  String get markIncomplete => 'Marquer comme incomplet';

  @override
  String get editDueDate => 'Modifier la date d\'échéance';

  @override
  String get setDueDate => 'Définir la date d\'échéance';

  @override
  String get clearDueDate => 'Effacer la date d\'échéance';

  @override
  String get failedToClearDueDate => 'Échec de l\'effacement de la date d\'échéance';

  @override
  String get mondayAbbr => 'Lun';

  @override
  String get tuesdayAbbr => 'Mar';

  @override
  String get wednesdayAbbr => 'Mer';

  @override
  String get thursdayAbbr => 'Jeu';

  @override
  String get fridayAbbr => 'Ven';

  @override
  String get saturdayAbbr => 'Sam';

  @override
  String get sundayAbbr => 'Dim';

  @override
  String get howDoesItWork => 'Comment ça marche ?';

  @override
  String get sdCardSyncDescription => 'La synchronisation de la carte SD importera vos souvenirs de la carte SD vers l\'application';

  @override
  String get checksForAudioFiles => 'Vérifie les fichiers audio sur la carte SD';

  @override
  String get omiSyncsAudioFiles => 'Omi synchronise ensuite les fichiers audio avec le serveur';

  @override
  String get serverProcessesAudio => 'Le serveur traite les fichiers audio et crée des souvenirs';

  @override
  String get youreAllSet => 'Vous êtes prêt !';

  @override
  String get welcomeToOmiDescription => 'Bienvenue sur Omi ! Votre compagnon IA est prêt à vous aider avec les conversations, les tâches et plus encore.';

  @override
  String get startUsingOmi => 'Commencer à utiliser Omi';

  @override
  String get back => 'Retour';

  @override
  String get keyboardShortcuts => 'Raccourcis Clavier';

  @override
  String get toggleControlBar => 'Basculer la barre de contrôle';

  @override
  String get pressKeys => 'Appuyez sur les touches...';

  @override
  String get cmdRequired => '⌘ requis';

  @override
  String get invalidKey => 'Touche invalide';

  @override
  String get space => 'Espace';

  @override
  String get search => 'Rechercher';

  @override
  String get searchPlaceholder => 'Rechercher...';

  @override
  String get untitledConversation => 'Conversation sans titre';

  @override
  String countRemaining(String count) {
    return '$count restants';
  }

  @override
  String get addGoal => 'Ajouter un objectif';

  @override
  String get editGoal => 'Modifier l\'objectif';

  @override
  String get icon => 'Icône';

  @override
  String get goalTitle => 'Titre de l\'objectif';

  @override
  String get current => 'Actuel';

  @override
  String get target => 'Objectif';

  @override
  String get saveGoal => 'Enregistrer';

  @override
  String get goals => 'Objectifs';

  @override
  String get tapToAddGoal => 'Appuyez pour ajouter un objectif';

  @override
  String welcomeBack(String name) {
    return 'Bon retour, $name';
  }

  @override
  String get yourConversations => 'Vos conversations';

  @override
  String get reviewAndManageConversations => 'Consultez et gérez vos conversations capturées';

  @override
  String get startCapturingConversations => 'Commencez à capturer des conversations avec votre appareil Omi pour les voir ici.';

  @override
  String get useMobileAppToCapture => 'Utilisez votre application mobile pour capturer de l\'audio';

  @override
  String get conversationsProcessedAutomatically => 'Les conversations sont traitées automatiquement';

  @override
  String get getInsightsInstantly => 'Obtenez des informations et des résumés instantanément';

  @override
  String get showAll => 'Tout afficher →';

  @override
  String get noTasksForToday => 'Aucune tâche pour aujourd\'hui.\\nDemandez à Omi plus de tâches ou créez-les manuellement.';

  @override
  String get dailyScore => 'SCORE QUOTIDIEN';

  @override
  String get dailyScoreDescription => 'Un score pour vous aider à mieux vous concentrer sur l\'exécution.';

  @override
  String get searchResults => 'Résultats de recherche';

  @override
  String get actionItems => 'Éléments d\'action';

  @override
  String get tasksToday => 'Aujourd\'hui';

  @override
  String get tasksTomorrow => 'Demain';

  @override
  String get tasksNoDeadline => 'Sans échéance';

  @override
  String get tasksLater => 'Plus tard';

  @override
  String get loadingTasks => 'Chargement des tâches...';

  @override
  String get tasks => 'Tâches';

  @override
  String get swipeTasksToIndent => 'Balayez les tâches pour indenter, faites glisser entre les catégories';

  @override
  String get create => 'Créer';

  @override
  String get noTasksYet => 'Aucune tâche pour l\'instant';

  @override
  String get tasksFromConversationsWillAppear => 'Les tâches de vos conversations apparaîtront ici.\nCliquez sur Créer pour en ajouter une manuellement.';

  @override
  String get monthJan => 'Jan';

  @override
  String get monthFeb => 'Fév';

  @override
  String get monthMar => 'Mar';

  @override
  String get monthApr => 'Avr';

  @override
  String get monthMay => 'Mai';

  @override
  String get monthJun => 'Juin';

  @override
  String get monthJul => 'Juil';

  @override
  String get monthAug => 'Août';

  @override
  String get monthSep => 'Sep';

  @override
  String get monthOct => 'Oct';

  @override
  String get monthNov => 'Nov';

  @override
  String get monthDec => 'Déc';

  @override
  String get timePM => 'PM';

  @override
  String get timeAM => 'AM';

  @override
  String get actionItemUpdatedSuccessfully => 'Tâche mise à jour avec succès';

  @override
  String get actionItemCreatedSuccessfully => 'Tâche créée avec succès';

  @override
  String get actionItemDeletedSuccessfully => 'Tâche supprimée avec succès';

  @override
  String get deleteActionItem => 'Supprimer la tâche';

  @override
  String get deleteActionItemConfirmation => 'Êtes-vous sûr de vouloir supprimer cette tâche ? Cette action ne peut pas être annulée.';

  @override
  String get enterActionItemDescription => 'Entrez la description de la tâche...';

  @override
  String get markAsCompleted => 'Marquer comme terminée';

  @override
  String get setDueDateAndTime => 'Définir la date et l\'heure d\'échéance';

  @override
  String get reloadingApps => 'Rechargement des applications...';

  @override
  String get loadingApps => 'Chargement des applications...';

  @override
  String get browseInstallCreateApps => 'Parcourir, installer et créer des applications';

  @override
  String get all => 'Tous';

  @override
  String get open => 'Ouvrir';

  @override
  String get install => 'Installer';

  @override
  String get noAppsAvailable => 'Aucune application disponible';

  @override
  String get unableToLoadApps => 'Impossible de charger les applications';

  @override
  String get tryAdjustingSearchTermsOrFilters => 'Essayez d\'ajuster vos termes de recherche ou vos filtres';

  @override
  String get checkBackLaterForNewApps => 'Revenez plus tard pour de nouvelles applications';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => 'Veuillez vérifier votre connexion Internet et réessayer';

  @override
  String get createNewApp => 'Créer une nouvelle application';

  @override
  String get buildSubmitCustomOmiApp => 'Créez et soumettez votre application Omi personnalisée';

  @override
  String get submittingYourApp => 'Soumission de votre application...';

  @override
  String get preparingFormForYou => 'Préparation du formulaire pour vous...';

  @override
  String get appDetails => 'Détails de l\'application';

  @override
  String get paymentDetails => 'Détails de paiement';

  @override
  String get previewAndScreenshots => 'Aperçu et captures d\'écran';

  @override
  String get appCapabilities => 'Capacités de l\'application';

  @override
  String get aiPrompts => 'Invites IA';

  @override
  String get chatPrompt => 'Invite de chat';

  @override
  String get chatPromptPlaceholder => 'Vous êtes une application géniale, votre travail consiste à répondre aux questions des utilisateurs et à les faire se sentir bien...';

  @override
  String get conversationPrompt => 'Invite de conversation';

  @override
  String get conversationPromptPlaceholder => 'Vous êtes une application géniale, vous recevrez une transcription et un résumé d\'une conversation...';

  @override
  String get notificationScopes => 'Portées de notification';

  @override
  String get appPrivacyAndTerms => 'Confidentialité et conditions de l\'application';

  @override
  String get makeMyAppPublic => 'Rendre mon application publique';

  @override
  String get submitAppTermsAgreement => 'En soumettant cette application, j\'accepte les Conditions d\'utilisation et la Politique de confidentialité d\'Omi AI';

  @override
  String get submitApp => 'Soumettre l\'application';

  @override
  String get needHelpGettingStarted => 'Besoin d\'aide pour commencer ?';

  @override
  String get clickHereForAppBuildingGuides => 'Cliquez ici pour les guides de création d\'applications et la documentation';

  @override
  String get submitAppQuestion => 'Soumettre l\'application ?';

  @override
  String get submitAppPublicDescription => 'Votre application sera examinée et rendue publique. Vous pouvez commencer à l\'utiliser immédiatement, même pendant l\'examen !';

  @override
  String get submitAppPrivateDescription => 'Votre application sera examinée et mise à votre disposition en privé. Vous pouvez commencer à l\'utiliser immédiatement, même pendant l\'examen !';

  @override
  String get startEarning => 'Commencez à gagner ! 💰';

  @override
  String get connectStripeOrPayPal => 'Connectez Stripe ou PayPal pour recevoir des paiements pour votre application.';

  @override
  String get connectNow => 'Connecter maintenant';

  @override
  String installsCount(String count) {
    return '$count+ installations';
  }

  @override
  String get uninstallApp => 'Désinstaller l\'application';

  @override
  String get subscribe => 'S\'abonner';

  @override
  String get dataAccessNotice => 'Avis d\'accès aux données';

  @override
  String get dataAccessWarning => 'Cette application accédera à vos données. Omi AI n\'est pas responsable de la manière dont vos données sont utilisées, modifiées ou supprimées par cette application';

  @override
  String get installApp => 'Installer l\'application';

  @override
  String get betaTesterNotice => 'Vous êtes un testeur bêta pour cette application. Elle n\'est pas encore publique. Elle sera publique une fois approuvée.';

  @override
  String get appUnderReviewOwner => 'Votre application est en cours de révision et visible uniquement pour vous. Elle sera publique une fois approuvée.';

  @override
  String get appRejectedNotice => 'Votre application a été rejetée. Veuillez mettre à jour les détails de l\'application et la soumettre à nouveau pour révision.';

  @override
  String get setupSteps => 'Étapes de configuration';

  @override
  String get setupInstructions => 'Instructions de configuration';

  @override
  String get integrationInstructions => 'Instructions d\'intégration';

  @override
  String get preview => 'Aperçu';

  @override
  String get aboutTheApp => 'À propos de l\'application';

  @override
  String get aboutThePersona => 'À propos du persona';

  @override
  String get chatPersonality => 'Personnalité du chat';

  @override
  String get ratingsAndReviews => 'Notes et avis';

  @override
  String get noRatings => 'aucune note';

  @override
  String ratingsCount(String count) {
    return '$count+ notes';
  }

  @override
  String get errorActivatingApp => 'Erreur lors de l\'activation de l\'application';

  @override
  String get integrationSetupRequired => 'S\'il s\'agit d\'une application d\'intégration, assurez-vous que la configuration est terminée.';

  @override
  String get installed => 'Installé';

  @override
  String get appIdLabel => 'ID de l\'application';

  @override
  String get appNameLabel => 'Nom de l\'application';

  @override
  String get appNamePlaceholder => 'Mon application géniale';

  @override
  String get pleaseEnterAppName => 'Veuillez saisir le nom de l\'application';

  @override
  String get categoryLabel => 'Catégorie';

  @override
  String get selectCategory => 'Sélectionner une catégorie';

  @override
  String get descriptionLabel => 'Description';

  @override
  String get appDescriptionPlaceholder => 'Mon application géniale est une application formidable qui fait des choses incroyables. C\'est la meilleure application !';

  @override
  String get pleaseProvideValidDescription => 'Veuillez fournir une description valide';

  @override
  String get appPricingLabel => 'Tarification de l\'application';

  @override
  String get noneSelected => 'Aucune sélection';

  @override
  String get appIdCopiedToClipboard => 'ID de l\'application copié dans le presse-papiers';

  @override
  String get appCategoryModalTitle => 'Catégorie de l\'application';

  @override
  String get pricingFree => 'Gratuit';

  @override
  String get pricingPaid => 'Payant';

  @override
  String get loadingCapabilities => 'Chargement des fonctionnalités...';

  @override
  String get filterInstalled => 'Installées';

  @override
  String get filterMyApps => 'Mes applications';

  @override
  String get clearSelection => 'Effacer la sélection';

  @override
  String get filterCategory => 'Catégorie';

  @override
  String get rating4PlusStars => '4+ étoiles';

  @override
  String get rating3PlusStars => '3+ étoiles';

  @override
  String get rating2PlusStars => '2+ étoiles';

  @override
  String get rating1PlusStars => '1+ étoile';

  @override
  String get filterRating => 'Évaluation';

  @override
  String get filterCapabilities => 'Fonctionnalités';

  @override
  String get noNotificationScopesAvailable => 'Aucun périmètre de notification disponible';

  @override
  String get popularApps => 'Applications populaires';

  @override
  String get pleaseProvidePrompt => 'Veuillez fournir une invite';

  @override
  String chatWithAppName(String appName) {
    return 'Chat avec $appName';
  }

  @override
  String get defaultAiAssistant => 'Assistant IA par défaut';

  @override
  String get readyToChat => '✨ Prêt à discuter !';

  @override
  String get connectionNeeded => '🌐 Connexion nécessaire';

  @override
  String get startConversation => 'Commencez une conversation et laissez la magie opérer';

  @override
  String get checkInternetConnection => 'Veuillez vérifier votre connexion Internet';

  @override
  String get wasThisHelpful => 'Cela vous a-t-il été utile ?';

  @override
  String get thankYouForFeedback => 'Merci pour vos commentaires !';

  @override
  String get maxFilesUploadError => 'Vous ne pouvez télécharger que 4 fichiers à la fois';

  @override
  String get attachedFiles => '📎 Fichiers joints';

  @override
  String get takePhoto => 'Prendre une photo';

  @override
  String get captureWithCamera => 'Capturer avec l\'appareil photo';

  @override
  String get selectImages => 'Sélectionner des images';

  @override
  String get chooseFromGallery => 'Choisir dans la galerie';

  @override
  String get selectFile => 'Sélectionner un fichier';

  @override
  String get chooseAnyFileType => 'Choisir n\'importe quel type de fichier';

  @override
  String get cannotReportOwnMessages => 'Vous ne pouvez pas signaler vos propres messages';

  @override
  String get messageReportedSuccessfully => '✅ Message signalé avec succès';

  @override
  String get confirmReportMessage => 'Êtes-vous sûr de vouloir signaler ce message ?';

  @override
  String get selectChatAssistant => 'Sélectionner un assistant de chat';

  @override
  String get enableMoreApps => 'Activer plus d\'applications';

  @override
  String get chatCleared => 'Chat effacé';

  @override
  String get clearChatTitle => 'Effacer le chat ?';

  @override
  String get confirmClearChat => 'Êtes-vous sûr de vouloir effacer le chat ? Cette action ne peut pas être annulée.';

  @override
  String get copy => 'Copier';

  @override
  String get share => 'Partager';

  @override
  String get report => 'Signaler';

  @override
  String get microphonePermissionRequired => 'L\'autorisation du microphone est requise pour l\'enregistrement vocal.';

  @override
  String get microphonePermissionDenied => 'Autorisation du microphone refusée. Veuillez accorder l\'autorisation dans Préférences Système > Confidentialité et sécurité > Microphone.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return 'Échec de la vérification de l\'autorisation du microphone : $error';
  }

  @override
  String get failedToTranscribeAudio => 'Échec de la transcription audio';

  @override
  String get transcribing => 'Transcription...';

  @override
  String get transcriptionFailed => 'Transcription échouée';

  @override
  String get discardedConversation => 'Conversation rejetée';

  @override
  String get at => 'à';

  @override
  String get from => 'de';

  @override
  String get copied => 'Copié !';

  @override
  String get copyLink => 'Copier le lien';

  @override
  String get hideTranscript => 'Masquer la transcription';

  @override
  String get viewTranscript => 'Afficher la transcription';

  @override
  String get conversationDetails => 'Détails de la conversation';

  @override
  String get transcript => 'Transcription';

  @override
  String segmentsCount(int count) {
    return '$count segments';
  }

  @override
  String get noTranscriptAvailable => 'Aucune transcription disponible';

  @override
  String get noTranscriptMessage => 'Cette conversation n\'a pas de transcription.';

  @override
  String get conversationUrlCouldNotBeGenerated => 'L\'URL de la conversation n\'a pas pu être générée.';

  @override
  String get failedToGenerateConversationLink => 'Échec de la génération du lien de conversation';

  @override
  String get failedToGenerateShareLink => 'Échec de la génération du lien de partage';

  @override
  String get reloadingConversations => 'Rechargement des conversations...';

  @override
  String get user => 'Utilisateur';

  @override
  String get starred => 'Favoris';

  @override
  String get date => 'Date';

  @override
  String get noResultsFound => 'Aucun résultat trouvé';

  @override
  String get tryAdjustingSearchTerms => 'Essayez d\'ajuster vos termes de recherche';

  @override
  String get starConversationsToFindQuickly => 'Ajoutez des conversations aux favoris pour les retrouver rapidement ici';

  @override
  String noConversationsOnDate(String date) {
    return 'Aucune conversation le $date';
  }

  @override
  String get trySelectingDifferentDate => 'Essayez de sélectionner une autre date';

  @override
  String get conversations => 'Conversations';

  @override
  String get chat => 'Chat';

  @override
  String get actions => 'Actions';

  @override
  String get syncAvailable => 'Synchronisation disponible';

  @override
  String get referAFriend => 'Recommander un ami';

  @override
  String get help => 'Aide';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Passer à Pro';

  @override
  String get getOmiDevice => 'Obtenir un appareil Omi';

  @override
  String get wearableAiCompanion => 'Compagnon IA portable';

  @override
  String get loadingMemories => 'Chargement des souvenirs...';

  @override
  String get allMemories => 'Tous les souvenirs';

  @override
  String get aboutYou => 'À propos de vous';

  @override
  String get manual => 'Manuel';

  @override
  String get loadingYourMemories => 'Chargement de vos souvenirs...';

  @override
  String get createYourFirstMemory => 'Créez votre premier souvenir pour commencer';

  @override
  String get tryAdjustingFilter => 'Essayez d\'ajuster votre recherche ou votre filtre';

  @override
  String get whatWouldYouLikeToRemember => 'Que voulez-vous retenir?';

  @override
  String get category => 'Catégorie';

  @override
  String get public => 'Public';

  @override
  String get failedToSaveCheckConnection => 'Échec de l\'enregistrement. Vérifiez votre connexion.';

  @override
  String get createMemory => 'Créer un souvenir';

  @override
  String get deleteMemoryConfirmation => 'Êtes-vous sûr de vouloir supprimer ce souvenir? Cette action ne peut pas être annulée.';

  @override
  String get makePrivate => 'Rendre privé';

  @override
  String get organizeAndControlMemories => 'Organisez et contrôlez vos souvenirs';

  @override
  String get total => 'Total';

  @override
  String get makeAllMemoriesPrivate => 'Rendre tous les souvenirs privés';

  @override
  String get setAllMemoriesToPrivate => 'Définir tous les souvenirs comme privés';

  @override
  String get makeAllMemoriesPublic => 'Rendre tous les souvenirs publics';

  @override
  String get setAllMemoriesToPublic => 'Définir tous les souvenirs comme publics';

  @override
  String get permanentlyRemoveAllMemories => 'Supprimer définitivement tous les souvenirs d\'Omi';

  @override
  String get allMemoriesAreNowPrivate => 'Tous les souvenirs sont maintenant privés';

  @override
  String get allMemoriesAreNowPublic => 'Tous les souvenirs sont maintenant publics';

  @override
  String get clearOmisMemory => 'Effacer la mémoire d\'Omi';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Êtes-vous sûr de vouloir effacer la mémoire d\'Omi? Cette action ne peut pas être annulée et supprimera définitivement tous les $count souvenirs.';
  }

  @override
  String get omisMemoryCleared => 'La mémoire d\'Omi à votre sujet a été effacée';

  @override
  String get welcomeToOmi => 'Bienvenue sur Omi';

  @override
  String get continueWithApple => 'Continuer avec Apple';

  @override
  String get continueWithGoogle => 'Continuer avec Google';

  @override
  String get byContinuingYouAgree => 'En continuant, vous acceptez nos ';

  @override
  String get termsOfService => 'Conditions de service';

  @override
  String get and => ' et ';

  @override
  String get dataAndPrivacy => 'Données et confidentialité';

  @override
  String get secureAuthViaAppleId => 'Authentification sécurisée via Apple ID';

  @override
  String get secureAuthViaGoogleAccount => 'Authentification sécurisée via compte Google';

  @override
  String get whatWeCollect => 'Ce que nous collectons';

  @override
  String get dataCollectionMessage => 'En continuant, vos conversations, enregistrements et informations personnelles seront stockés en toute sécurité sur nos serveurs pour fournir des informations alimentées par l\'IA et activer toutes les fonctionnalités de l\'application.';

  @override
  String get dataProtection => 'Protection des données';

  @override
  String get yourDataIsProtected => 'Vos données sont protégées et régies par notre ';

  @override
  String get pleaseSelectYourPrimaryLanguage => 'Veuillez sélectionner votre langue principale';

  @override
  String get chooseYourLanguage => 'Choisissez votre langue';

  @override
  String get selectPreferredLanguageForBestExperience => 'Sélectionnez votre langue préférée pour la meilleure expérience Omi';

  @override
  String get searchLanguages => 'Rechercher des langues...';

  @override
  String get selectALanguage => 'Sélectionnez une langue';

  @override
  String get tryDifferentSearchTerm => 'Essayez un autre terme de recherche';

  @override
  String get pleaseEnterYourName => 'Veuillez entrer votre nom';

  @override
  String get nameMustBeAtLeast2Characters => 'Le nom doit comporter au moins 2 caractères';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed => 'Dites-nous comment vous souhaitez être appelé. Cela aide à personnaliser votre expérience Omi.';

  @override
  String charactersCount(int count) {
    return '$count caractères';
  }

  @override
  String get enableFeaturesForBestExperience => 'Activez les fonctionnalités pour la meilleure expérience Omi sur votre appareil.';

  @override
  String get microphoneAccess => 'Accès au microphone';

  @override
  String get recordAudioConversations => 'Enregistrer les conversations audio';

  @override
  String get microphoneAccessDescription => 'Omi a besoin d\'un accès au microphone pour enregistrer vos conversations et fournir des transcriptions.';

  @override
  String get screenRecording => 'Enregistrement d\'écran';

  @override
  String get captureSystemAudioFromMeetings => 'Capturer l\'audio système des réunions';

  @override
  String get screenRecordingDescription => 'Omi a besoin de l\'autorisation d\'enregistrement d\'écran pour capturer l\'audio système de vos réunions basées sur le navigateur.';

  @override
  String get accessibility => 'Accessibilité';

  @override
  String get detectBrowserBasedMeetings => 'Détecter les réunions basées sur le navigateur';

  @override
  String get accessibilityDescription => 'Omi a besoin de l\'autorisation d\'accessibilité pour détecter quand vous rejoignez des réunions Zoom, Meet ou Teams dans votre navigateur.';

  @override
  String get pleaseWait => 'Veuillez patienter...';

  @override
  String get joinTheCommunity => 'Rejoignez la communauté !';

  @override
  String get loadingProfile => 'Chargement du profil...';

  @override
  String get profileSettings => 'Paramètres du profil';

  @override
  String get noEmailSet => 'Aucun e-mail défini';

  @override
  String get userIdCopiedToClipboard => 'ID utilisateur copié';

  @override
  String get yourInformation => 'Vos Informations';

  @override
  String get setYourName => 'Définir votre nom';

  @override
  String get changeYourName => 'Changer votre nom';

  @override
  String get manageYourOmiPersona => 'Gérer votre persona Omi';

  @override
  String get voiceAndPeople => 'Voix et Personnes';

  @override
  String get teachOmiYourVoice => 'Apprenez à Omi votre voix';

  @override
  String get tellOmiWhoSaidIt => 'Dites à Omi qui l\'a dit 🗣️';

  @override
  String get payment => 'Paiement';

  @override
  String get addOrChangeYourPaymentMethod => 'Ajouter ou modifier le mode de paiement';

  @override
  String get preferences => 'Préférences';

  @override
  String get helpImproveOmiBySharing => 'Aidez à améliorer Omi en partageant des données analytiques anonymisées';

  @override
  String get deleteAccount => 'Supprimer le Compte';

  @override
  String get deleteYourAccountAndAllData => 'Supprimez votre compte et toutes les données';

  @override
  String get clearLogs => 'Effacer les journaux';

  @override
  String get debugLogsCleared => 'Journaux de débogage effacés';

  @override
  String get exportConversations => 'Exporter les conversations';

  @override
  String get exportAllConversationsToJson => 'Exportez toutes vos conversations dans un fichier JSON.';

  @override
  String get conversationsExportStarted => 'Exportation des conversations démarrée. Cela peut prendre quelques secondes, veuillez patienter.';

  @override
  String get mcpDescription => 'Pour connecter Omi à d\'autres applications pour lire, rechercher et gérer vos souvenirs et conversations. Créez une clé pour commencer.';

  @override
  String get apiKeys => 'Clés API';

  @override
  String errorLabel(String error) {
    return 'Erreur : $error';
  }

  @override
  String get noApiKeysFound => 'Aucune clé API trouvée. Créez-en une pour commencer.';

  @override
  String get advancedSettings => 'Paramètres avancés';

  @override
  String get triggersWhenNewConversationCreated => 'Se déclenche lors de la création d\'une nouvelle conversation.';

  @override
  String get triggersWhenNewTranscriptReceived => 'Se déclenche lors de la réception d\'une nouvelle transcription.';

  @override
  String get realtimeAudioBytes => 'Octets audio en temps réel';

  @override
  String get triggersWhenAudioBytesReceived => 'Se déclenche lors de la réception d\'octets audio.';

  @override
  String get everyXSeconds => 'Toutes les x secondes';

  @override
  String get triggersWhenDaySummaryGenerated => 'Se déclenche lors de la génération du résumé du jour.';

  @override
  String get tryLatestExperimentalFeatures => 'Essayez les dernières fonctionnalités expérimentales de l\'équipe Omi.';

  @override
  String get transcriptionServiceDiagnosticStatus => 'État de diagnostic du service de transcription';

  @override
  String get enableDetailedDiagnosticMessages => 'Activer les messages de diagnostic détaillés du service de transcription';

  @override
  String get autoCreateAndTagNewSpeakers => 'Créer et étiqueter automatiquement les nouveaux intervenants';

  @override
  String get automaticallyCreateNewPerson => 'Créer automatiquement une nouvelle personne lorsqu\'un nom est détecté dans la transcription.';

  @override
  String get pilotFeatures => 'Fonctionnalités pilotes';

  @override
  String get pilotFeaturesDescription => 'Ces fonctionnalités sont des tests et aucun support n\'est garanti.';

  @override
  String get suggestFollowUpQuestion => 'Suggérer une question de suivi';

  @override
  String get saveSettings => 'Enregistrer les Paramètres';

  @override
  String get syncingDeveloperSettings => 'Synchronisation des paramètres développeur...';

  @override
  String get summary => 'Résumé';

  @override
  String get auto => 'Automatique';

  @override
  String get noSummaryForApp => 'Aucun résumé disponible pour cette application. Essayez une autre application pour de meilleurs résultats.';

  @override
  String get tryAnotherApp => 'Essayer une autre application';

  @override
  String generatedBy(String appName) {
    return 'Généré par $appName';
  }

  @override
  String get overview => 'Vue d\'ensemble';

  @override
  String get otherAppResults => 'Résultats d\'autres applications';

  @override
  String get unknownApp => 'Application inconnue';

  @override
  String get noSummaryAvailable => 'Aucun résumé disponible';

  @override
  String get conversationNoSummaryYet => 'Cette conversation n\'a pas encore de résumé.';

  @override
  String get chooseSummarizationApp => 'Choisir l\'application de résumé';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName définie comme application de résumé par défaut';
  }

  @override
  String get letOmiChooseAutomatically => 'Laissez Omi choisir automatiquement la meilleure application';

  @override
  String get deleteConversationConfirmation => 'Êtes-vous sûr de vouloir supprimer cette conversation ? Cette action ne peut pas être annulée.';

  @override
  String get conversationDeleted => 'Conversation supprimée';

  @override
  String get generatingLink => 'Génération du lien...';

  @override
  String get editConversation => 'Modifier la conversation';

  @override
  String get conversationLinkCopiedToClipboard => 'Lien de la conversation copié dans le presse-papiers';

  @override
  String get conversationTranscriptCopiedToClipboard => 'Transcription de la conversation copiée dans le presse-papiers';

  @override
  String get editConversationDialogTitle => 'Modifier la conversation';

  @override
  String get changeTheConversationTitle => 'Modifier le titre de la conversation';

  @override
  String get conversationTitle => 'Titre de la conversation';

  @override
  String get enterConversationTitle => 'Saisissez le titre de la conversation...';

  @override
  String get conversationTitleUpdatedSuccessfully => 'Titre de la conversation mis à jour avec succès';

  @override
  String get failedToUpdateConversationTitle => 'Échec de la mise à jour du titre de la conversation';

  @override
  String get errorUpdatingConversationTitle => 'Erreur lors de la mise à jour du titre de la conversation';

  @override
  String get settingUp => 'Configuration...';

  @override
  String get startYourFirstRecording => 'Commencez votre premier enregistrement';

  @override
  String get preparingSystemAudioCapture => 'Préparation de la capture audio système';

  @override
  String get clickTheButtonToCaptureAudio => 'Cliquez sur le bouton pour capturer l\'audio pour les transcriptions en direct, les informations IA et l\'enregistrement automatique.';

  @override
  String get reconnecting => 'Reconnexion...';

  @override
  String get recordingPaused => 'Enregistrement en pause';

  @override
  String get recordingActive => 'Enregistrement actif';

  @override
  String get startRecording => 'Démarrer l\'enregistrement';

  @override
  String resumingInCountdown(String countdown) {
    return 'Reprise dans ${countdown}s...';
  }

  @override
  String get tapPlayToResume => 'Appuyez sur lecture pour reprendre';

  @override
  String get listeningForAudio => 'Écoute de l\'audio...';

  @override
  String get preparingAudioCapture => 'Préparation de la capture audio';

  @override
  String get clickToBeginRecording => 'Cliquez pour commencer l\'enregistrement';

  @override
  String get translated => 'traduit';

  @override
  String get liveTranscript => 'Transcription en direct';

  @override
  String segmentsSingular(String count) {
    return '$count segment';
  }

  @override
  String segmentsPlural(String count) {
    return '$count segments';
  }

  @override
  String get startRecordingToSeeTranscript => 'Démarrez l\'enregistrement pour voir la transcription en direct';

  @override
  String get paused => 'En pause';

  @override
  String get initializing => 'Initialisation...';

  @override
  String get recording => 'Enregistrement';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return 'Microphone changé. Reprise dans ${countdown}s';
  }

  @override
  String get clickPlayToResumeOrStop => 'Cliquez sur lecture pour reprendre ou arrêter pour terminer';

  @override
  String get settingUpSystemAudioCapture => 'Configuration de la capture audio système';

  @override
  String get capturingAudioAndGeneratingTranscript => 'Capture audio et génération de la transcription';

  @override
  String get clickToBeginRecordingSystemAudio => 'Cliquez pour commencer l\'enregistrement audio système';

  @override
  String get you => 'Vous';

  @override
  String speakerWithId(String speakerId) {
    return 'Locuteur $speakerId';
  }

  @override
  String get translatedByOmi => 'traduit par omi';

  @override
  String get backToConversations => 'Retour aux conversations';

  @override
  String get systemAudio => 'Système';

  @override
  String get mic => 'Micro';

  @override
  String audioInputSetTo(String deviceName) {
    return 'Entrée audio définie sur $deviceName';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return 'Erreur lors du changement de périphérique audio : $error';
  }

  @override
  String get selectAudioInput => 'Sélectionner l\'entrée audio';

  @override
  String get loadingDevices => 'Chargement des périphériques...';

  @override
  String get settingsHeader => 'PARAMÈTRES';

  @override
  String get plansAndBilling => 'Plans et Facturation';

  @override
  String get calendarIntegration => 'Intégration du Calendrier';

  @override
  String get dailySummary => 'Résumé Quotidien';

  @override
  String get developer => 'Développeur';

  @override
  String get about => 'À propos';

  @override
  String get selectTime => 'Sélectionner l\'Heure';

  @override
  String get accountGroup => 'Compte';

  @override
  String get signOutQuestion => 'Se Déconnecter ?';

  @override
  String get signOutConfirmation => 'Êtes-vous sûr de vouloir vous déconnecter ?';

  @override
  String get customVocabularyHeader => 'VOCABULAIRE PERSONNALISÉ';

  @override
  String get addWordsDescription => 'Ajoutez des mots qu\'Omi devrait reconnaître pendant la transcription.';

  @override
  String get enterWordsHint => 'Entrez des mots (séparés par des virgules)';

  @override
  String get dailySummaryHeader => 'RÉSUMÉ QUOTIDIEN';

  @override
  String get dailySummaryTitle => 'Résumé Quotidien';

  @override
  String get dailySummaryDescription => 'Obtenez un résumé personnalisé de vos conversations';

  @override
  String get deliveryTime => 'Heure de Livraison';

  @override
  String get deliveryTimeDescription => 'Quand recevoir votre résumé quotidien';

  @override
  String get subscription => 'Abonnement';

  @override
  String get viewPlansAndUsage => 'Voir Plans et Utilisation';

  @override
  String get viewPlansDescription => 'Gérez votre abonnement et consultez les statistiques d\'utilisation';

  @override
  String get addOrChangePaymentMethod => 'Ajoutez ou modifiez votre méthode de paiement';

  @override
  String get displayOptions => 'Options d\'affichage';

  @override
  String get showMeetingsInMenuBar => 'Afficher les réunions dans la barre de menu';

  @override
  String get displayUpcomingMeetingsDescription => 'Afficher les réunions à venir dans la barre de menu';

  @override
  String get showEventsWithoutParticipants => 'Afficher les événements sans participants';

  @override
  String get includePersonalEventsDescription => 'Inclure les événements personnels sans participants';

  @override
  String get upcomingMeetings => 'RÉUNIONS À VENIR';

  @override
  String get checkingNext7Days => 'Vérification des 7 prochains jours';

  @override
  String get shortcuts => 'Raccourcis';

  @override
  String get shortcutChangeInstruction => 'Cliquez sur un raccourci pour le modifier. Appuyez sur Échap pour annuler.';

  @override
  String get configurePersonaDescription => 'Configurez votre persona IA';

  @override
  String get configureSTTProvider => 'Configurer le fournisseur STT';

  @override
  String get setConversationEndDescription => 'Définir quand les conversations se terminent automatiquement';

  @override
  String get importDataDescription => 'Importer des données d\'autres sources';

  @override
  String get exportConversationsDescription => 'Exporter les conversations en JSON';

  @override
  String get exportingConversations => 'Exportation des conversations...';

  @override
  String get clearNodesDescription => 'Effacer tous les nœuds et connexions';

  @override
  String get deleteKnowledgeGraphQuestion => 'Supprimer le graphe de connaissances ?';

  @override
  String get deleteKnowledgeGraphWarning => 'Cela supprimera toutes les données dérivées du graphe de connaissances. Vos souvenirs originaux restent en sécurité.';

  @override
  String get connectOmiWithAI => 'Connectez Omi aux assistants IA';

  @override
  String get noAPIKeys => 'Aucune clé API. Créez-en une pour commencer.';

  @override
  String get autoCreateWhenDetected => 'Créer automatiquement lorsque le nom est détecté';

  @override
  String get trackPersonalGoals => 'Suivre les objectifs personnels sur la page d\'accueil';

  @override
  String get dailyReflectionDescription => 'Rappel à 21h pour réfléchir sur votre journée';

  @override
  String get endpointURL => 'URL du point de terminaison';

  @override
  String get links => 'Liens';

  @override
  String get discordMemberCount => 'Plus de 8 000 membres sur Discord';

  @override
  String get userInformation => 'Informations utilisateur';

  @override
  String get capabilities => 'Capacités';

  @override
  String get previewScreenshots => 'Aperçu des captures';

  @override
  String get holdOnPreparingForm => 'Patientez, nous préparons le formulaire pour vous';

  @override
  String get bySubmittingYouAgreeToOmi => 'En soumettant, vous acceptez les ';

  @override
  String get termsAndPrivacyPolicy => 'Conditions et Politique de Confidentialité';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => 'Aide à diagnostiquer les problèmes. Supprimé automatiquement après 3 jours.';

  @override
  String get manageYourApp => 'Gérer votre application';

  @override
  String get updatingYourApp => 'Mise à jour de votre application';

  @override
  String get fetchingYourAppDetails => 'Récupération des détails de votre application';

  @override
  String get updateAppQuestion => 'Mettre à jour l\'application ?';

  @override
  String get updateAppConfirmation => 'Êtes-vous sûr de vouloir mettre à jour votre application ? Les modifications seront appliquées après examen par notre équipe.';

  @override
  String get updateApp => 'Mettre à jour l\'application';

  @override
  String get createAndSubmitNewApp => 'Créer et soumettre une nouvelle application';

  @override
  String appsCount(String count) {
    return 'Applications ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return 'Applications privées ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return 'Applications publiques ($count)';
  }

  @override
  String get newVersionAvailable => 'Nouvelle version disponible  🎉';

  @override
  String get no => 'Non';

  @override
  String get subscriptionCancelledSuccessfully => 'Abonnement annulé avec succès. Il restera actif jusqu\'à la fin de la période de facturation en cours.';

  @override
  String get failedToCancelSubscription => 'Échec de l\'annulation de l\'abonnement. Veuillez réessayer.';

  @override
  String get invalidPaymentUrl => 'URL de paiement invalide';

  @override
  String get permissionsAndTriggers => 'Autorisations et déclencheurs';

  @override
  String get chatFeatures => 'Fonctionnalités de chat';

  @override
  String get uninstall => 'Désinstaller';

  @override
  String get installs => 'INSTALLATIONS';

  @override
  String get priceLabel => 'PRIX';

  @override
  String get updatedLabel => 'MIS À JOUR';

  @override
  String get createdLabel => 'CRÉÉ';

  @override
  String get featuredLabel => 'EN VEDETTE';

  @override
  String get cancelSubscriptionQuestion => 'Annuler l\'abonnement ?';

  @override
  String get cancelSubscriptionConfirmation => 'Êtes-vous sûr de vouloir annuler votre abonnement ? Vous continuerez à avoir accès jusqu\'à la fin de votre période de facturation actuelle.';

  @override
  String get cancelSubscriptionButton => 'Annuler l\'abonnement';

  @override
  String get cancelling => 'Annulation...';

  @override
  String get betaTesterMessage => 'Vous êtes un testeur bêta pour cette application. Elle n\'est pas encore publique. Elle sera publique une fois approuvée.';

  @override
  String get appUnderReviewMessage => 'Votre application est en cours d\'examen et visible uniquement par vous. Elle sera publique une fois approuvée.';

  @override
  String get appRejectedMessage => 'Votre application a été rejetée. Veuillez mettre à jour les détails et soumettre à nouveau.';

  @override
  String get invalidIntegrationUrl => 'URL d\'intégration invalide';

  @override
  String get tapToComplete => 'Appuyez pour terminer';

  @override
  String get invalidSetupInstructionsUrl => 'URL des instructions de configuration invalide';

  @override
  String get pushToTalk => 'Appuyez pour parler';

  @override
  String get summaryPrompt => 'Invite de résumé';

  @override
  String get pleaseSelectARating => 'Veuillez sélectionner une note';

  @override
  String get reviewAddedSuccessfully => 'Avis ajouté avec succès 🚀';

  @override
  String get reviewUpdatedSuccessfully => 'Avis mis à jour avec succès 🚀';

  @override
  String get failedToSubmitReview => 'Échec de l\'envoi de l\'avis. Veuillez réessayer.';

  @override
  String get addYourReview => 'Ajoutez votre avis';

  @override
  String get editYourReview => 'Modifier votre avis';

  @override
  String get writeAReviewOptional => 'Écrire un avis (optionnel)';

  @override
  String get submitReview => 'Soumettre l\'avis';

  @override
  String get updateReview => 'Mettre à jour l\'avis';

  @override
  String get yourReview => 'Votre avis';

  @override
  String get anonymousUser => 'Utilisateur anonyme';

  @override
  String get issueActivatingApp => 'Un problème est survenu lors de l\'activation de cette application. Veuillez réessayer.';

  @override
  String get dataAccessNoticeDescription => 'Cette application accédera à vos données. Omi AI n\'est pas responsable de la façon dont vos données sont utilisées, modifiées ou supprimées par cette application';

  @override
  String get copyUrl => 'Copier l\'URL';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => 'Lun';

  @override
  String get weekdayTue => 'Mar';

  @override
  String get weekdayWed => 'Mer';

  @override
  String get weekdayThu => 'Jeu';

  @override
  String get weekdayFri => 'Ven';

  @override
  String get weekdaySat => 'Sam';

  @override
  String get weekdaySun => 'Dim';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return 'Intégration $serviceName bientôt disponible';
  }

  @override
  String alreadyExportedTo(String platform) {
    return 'Déjà exporté vers $platform';
  }

  @override
  String get anotherPlatform => 'une autre plateforme';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return 'Veuillez vous authentifier avec $serviceName dans Paramètres > Intégrations des tâches';
  }

  @override
  String addingToService(String serviceName) {
    return 'Ajout à $serviceName...';
  }

  @override
  String addedToService(String serviceName) {
    return 'Ajouté à $serviceName';
  }

  @override
  String failedToAddToService(String serviceName) {
    return 'Échec de l\'ajout à $serviceName';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Autorisation refusée pour Apple Reminders';

  @override
  String failedToCreateApiKey(String error) {
    return 'Échec de la création de la clé API du fournisseur : $error';
  }

  @override
  String get createAKey => 'Créer une clé';

  @override
  String get apiKeyRevokedSuccessfully => 'Clé API révoquée avec succès';

  @override
  String failedToRevokeApiKey(String error) {
    return 'Échec de la révocation de la clé API : $error';
  }

  @override
  String get omiApiKeys => 'Clés API Omi';

  @override
  String get apiKeysDescription => 'Les clés API sont utilisées pour l\'authentification lorsque votre application communique avec le serveur OMI. Elles permettent à votre application de créer des souvenirs et d\'accéder à d\'autres services OMI en toute sécurité.';

  @override
  String get aboutOmiApiKeys => 'À propos des clés API Omi';

  @override
  String get yourNewKey => 'Votre nouvelle clé :';

  @override
  String get copyToClipboard => 'Copier dans le presse-papiers';

  @override
  String get pleaseCopyKeyNow => 'Veuillez le copier maintenant et le noter dans un endroit sûr. ';

  @override
  String get willNotSeeAgain => 'Vous ne pourrez plus le voir.';

  @override
  String get revokeKey => 'Révoquer la clé';

  @override
  String get revokeApiKeyQuestion => 'Révoquer la clé API ?';

  @override
  String get revokeApiKeyWarning => 'Cette action ne peut pas être annulée. Les applications utilisant cette clé ne pourront plus accéder à l\'API.';

  @override
  String get revoke => 'Révoquer';

  @override
  String get whatWouldYouLikeToCreate => 'Que souhaitez-vous créer ?';

  @override
  String get createAnApp => 'Créer une application';

  @override
  String get createAndShareYourApp => 'Créez et partagez votre application';

  @override
  String get createMyClone => 'Créer mon clone';

  @override
  String get createYourDigitalClone => 'Créez votre clone numérique';

  @override
  String get itemApp => 'Application';

  @override
  String get itemPersona => 'Persona';

  @override
  String keepItemPublic(String item) {
    return 'Garder $item public';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return 'Rendre $item public ?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return 'Rendre $item privé ?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return 'Si vous rendez $item public, il pourra être utilisé par tout le monde';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return 'Si vous rendez $item privé maintenant, il cessera de fonctionner pour tout le monde et ne sera visible que pour vous';
  }

  @override
  String get manageApp => 'Gérer l\'application';

  @override
  String get updatePersonaDetails => 'Mettre à jour les détails du persona';

  @override
  String deleteItemTitle(String item) {
    return 'Supprimer $item';
  }

  @override
  String deleteItemQuestion(String item) {
    return 'Supprimer $item ?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return 'Êtes-vous sûr de vouloir supprimer ce $item ? Cette action est irréversible.';
  }

  @override
  String get revokeKeyQuestion => 'Révoquer la clé ?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return 'Êtes-vous sûr de vouloir révoquer la clé \"$keyName\" ? Cette action est irréversible.';
  }

  @override
  String get createNewKey => 'Créer une nouvelle clé';

  @override
  String get keyNameHint => 'ex. Claude Desktop';

  @override
  String get pleaseEnterAName => 'Veuillez entrer un nom.';

  @override
  String failedToCreateKeyWithError(String error) {
    return 'Échec de la création de la clé : $error';
  }

  @override
  String get failedToCreateKeyTryAgain => 'Échec de la création de la clé. Veuillez réessayer.';

  @override
  String get keyCreated => 'Clé créée';

  @override
  String get keyCreatedMessage => 'Votre nouvelle clé a été créée. Veuillez la copier maintenant. Vous ne pourrez plus la voir.';

  @override
  String get keyWord => 'Clé';

  @override
  String get externalAppAccess => 'Accès des applications externes';

  @override
  String get externalAppAccessDescription => 'Les applications installées suivantes ont des intégrations externes et peuvent accéder à vos données, telles que les conversations et les souvenirs.';

  @override
  String get noExternalAppsHaveAccess => 'Aucune application externe n\'a accès à vos données.';

  @override
  String get maximumSecurityE2ee => 'Sécurité maximale (E2EE)';

  @override
  String get e2eeDescription => 'Le chiffrement de bout en bout est la référence en matière de confidentialité. Lorsqu\'il est activé, vos données sont chiffrées sur votre appareil avant d\'être envoyées à nos serveurs. Cela signifie que personne, pas même Omi, ne peut accéder à votre contenu.';

  @override
  String get importantTradeoffs => 'Compromis importants :';

  @override
  String get e2eeTradeoff1 => '• Certaines fonctionnalités comme les intégrations d\'applications externes peuvent être désactivées.';

  @override
  String get e2eeTradeoff2 => '• Si vous perdez votre mot de passe, vos données ne peuvent pas être récupérées.';

  @override
  String get featureComingSoon => 'Cette fonctionnalité arrive bientôt !';

  @override
  String get migrationInProgressMessage => 'Migration en cours. Vous ne pouvez pas modifier le niveau de protection tant qu\'elle n\'est pas terminée.';

  @override
  String get migrationFailed => 'Échec de la migration';

  @override
  String migratingFromTo(String source, String target) {
    return 'Migration de $source vers $target';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total objets';
  }

  @override
  String get secureEncryption => 'Chiffrement sécurisé';

  @override
  String get secureEncryptionDescription => 'Vos données sont chiffrées avec une clé unique sur nos serveurs, hébergés sur Google Cloud. Cela signifie que votre contenu brut est inaccessible à quiconque, y compris le personnel d\'Omi ou Google, directement depuis la base de données.';

  @override
  String get endToEndEncryption => 'Chiffrement de bout en bout';

  @override
  String get e2eeCardDescription => 'Activez pour une sécurité maximale où seul vous pouvez accéder à vos données. Appuyez pour en savoir plus.';

  @override
  String get dataAlwaysEncrypted => 'Quel que soit le niveau, vos données sont toujours chiffrées au repos et en transit.';

  @override
  String get readOnlyScope => 'Lecture seule';

  @override
  String get fullAccessScope => 'Accès complet';

  @override
  String get readScope => 'Lecture';

  @override
  String get writeScope => 'Écriture';

  @override
  String get apiKeyCreated => 'Clé API créée !';

  @override
  String get saveKeyWarning => 'Enregistrez cette clé maintenant ! Vous ne pourrez plus la voir.';

  @override
  String get yourApiKey => 'VOTRE CLÉ API';

  @override
  String get tapToCopy => 'Appuyez pour copier';

  @override
  String get copyKey => 'Copier la clé';

  @override
  String get createApiKey => 'Créer une clé API';

  @override
  String get accessDataProgrammatically => 'Accédez à vos données par programmation';

  @override
  String get keyNameLabel => 'NOM DE LA CLÉ';

  @override
  String get keyNamePlaceholder => 'ex., Mon intégration';

  @override
  String get permissionsLabel => 'AUTORISATIONS';

  @override
  String get permissionsInfoNote => 'R = Lecture, W = Écriture. Lecture seule par défaut si rien n\'est sélectionné.';

  @override
  String get developerApi => 'API développeur';

  @override
  String get createAKeyToGetStarted => 'Créez une clé pour commencer';

  @override
  String errorWithMessage(String error) {
    return 'Erreur : $error';
  }

  @override
  String get omiTraining => 'Formation Omi';

  @override
  String get trainingDataProgram => 'Programme de données d\'entraînement';

  @override
  String get getOmiUnlimitedFree => 'Obtenez Omi Illimité gratuitement en contribuant vos données pour entraîner des modèles d\'IA.';

  @override
  String get trainingDataBullets => '• Vos données aident à améliorer les modèles d\'IA\n• Seules les données non sensibles sont partagées\n• Processus entièrement transparent';

  @override
  String get learnMoreAtOmiTraining => 'En savoir plus sur omi.me/training';

  @override
  String get agreeToContributeData => 'Je comprends et j\'accepte de contribuer mes données pour l\'entraînement de l\'IA';

  @override
  String get submitRequest => 'Soumettre la demande';

  @override
  String get thankYouRequestUnderReview => 'Merci ! Votre demande est en cours d\'examen. Nous vous informerons une fois approuvée.';

  @override
  String planRemainsActiveUntil(String date) {
    return 'Votre forfait restera actif jusqu\'au $date. Après cela, vous perdrez l\'accès à vos fonctionnalités illimitées. Êtes-vous sûr ?';
  }

  @override
  String get confirmCancellation => 'Confirmer l\'annulation';

  @override
  String get keepMyPlan => 'Garder mon forfait';

  @override
  String get subscriptionSetToCancel => 'Votre abonnement est programmé pour être annulé à la fin de la période.';

  @override
  String get switchedToOnDevice => 'Passé à la transcription sur l\'appareil';

  @override
  String get couldNotSwitchToFreePlan => 'Impossible de passer au forfait gratuit. Veuillez réessayer.';

  @override
  String get couldNotLoadPlans => 'Impossible de charger les forfaits disponibles. Veuillez réessayer.';

  @override
  String get selectedPlanNotAvailable => 'Le forfait sélectionné n\'est pas disponible. Veuillez réessayer.';

  @override
  String get upgradeToAnnualPlan => 'Passer au forfait annuel';

  @override
  String get importantBillingInfo => 'Informations de facturation importantes :';

  @override
  String get monthlyPlanContinues => 'Votre forfait mensuel actuel continuera jusqu\'à la fin de votre période de facturation';

  @override
  String get paymentMethodCharged => 'Votre méthode de paiement existante sera débitée automatiquement à la fin de votre forfait mensuel';

  @override
  String get annualSubscriptionStarts => 'Votre abonnement annuel de 12 mois débutera automatiquement après le prélèvement';

  @override
  String get thirteenMonthsCoverage => 'Vous bénéficierez de 13 mois de couverture au total (mois en cours + 12 mois annuels)';

  @override
  String get confirmUpgrade => 'Confirmer la mise à niveau';

  @override
  String get confirmPlanChange => 'Confirmer le changement de forfait';

  @override
  String get confirmAndProceed => 'Confirmer et continuer';

  @override
  String get upgradeScheduled => 'Mise à niveau programmée';

  @override
  String get changePlan => 'Changer de forfait';

  @override
  String get upgradeAlreadyScheduled => 'Votre mise à niveau vers le forfait annuel est déjà programmée';

  @override
  String get youAreOnUnlimitedPlan => 'Vous êtes sur le forfait Illimité.';

  @override
  String get yourOmiUnleashed => 'Votre Omi, libéré. Passez à l\'illimité pour des possibilités infinies.';

  @override
  String planEndedOn(String date) {
    return 'Votre forfait s\'est terminé le $date.\\nRéabonnez-vous maintenant - vous serez facturé immédiatement pour une nouvelle période de facturation.';
  }

  @override
  String planSetToCancelOn(String date) {
    return 'Votre forfait est programmé pour être annulé le $date.\\nRéabonnez-vous maintenant pour conserver vos avantages - pas de frais jusqu\'au $date.';
  }

  @override
  String get annualPlanStartsAutomatically => 'Votre forfait annuel débutera automatiquement à la fin de votre forfait mensuel.';

  @override
  String planRenewsOn(String date) {
    return 'Votre forfait se renouvelle le $date.';
  }

  @override
  String get unlimitedConversations => 'Conversations illimitées';

  @override
  String get askOmiAnything => 'Demandez à Omi n\'importe quoi sur votre vie';

  @override
  String get unlockOmiInfiniteMemory => 'Débloquez la mémoire infinie d\'Omi';

  @override
  String get youreOnAnnualPlan => 'Vous êtes sur le forfait annuel';

  @override
  String get alreadyBestValuePlan => 'Vous avez déjà le forfait au meilleur rapport qualité-prix. Aucun changement nécessaire.';

  @override
  String get unableToLoadPlans => 'Impossible de charger les forfaits';

  @override
  String get checkConnectionTryAgain => 'Veuillez vérifier votre connexion et réessayer';

  @override
  String get useFreePlan => 'Utiliser le forfait gratuit';

  @override
  String get continueText => 'Continuer';

  @override
  String get resubscribe => 'Se réabonner';

  @override
  String get couldNotOpenPaymentSettings => 'Impossible d\'ouvrir les paramètres de paiement. Veuillez réessayer.';

  @override
  String get managePaymentMethod => 'Gérer le mode de paiement';

  @override
  String get cancelSubscription => 'Annuler l\'abonnement';

  @override
  String endsOnDate(String date) {
    return 'Se termine le $date';
  }

  @override
  String get active => 'Actif';

  @override
  String get freePlan => 'Forfait gratuit';

  @override
  String get configure => 'Configurer';

  @override
  String get privacyInformation => 'Informations de confidentialité';

  @override
  String get yourPrivacyMattersToUs => 'Votre vie privée nous tient à cœur';

  @override
  String get privacyIntroText => 'Chez Omi, nous prenons votre vie privée très au sérieux. Nous voulons être transparents sur les données que nous collectons et comment nous les utilisons. Voici ce que vous devez savoir :';

  @override
  String get whatWeTrack => 'Ce que nous suivons';

  @override
  String get anonymityAndPrivacy => 'Anonymat et confidentialité';

  @override
  String get optInAndOptOutOptions => 'Options d\'acceptation et de refus';

  @override
  String get ourCommitment => 'Notre engagement';

  @override
  String get commitmentText => 'Nous nous engageons à n\'utiliser les données collectées que pour améliorer Omi pour vous. Votre vie privée et votre confiance sont primordiales pour nous.';

  @override
  String get thankYouText => 'Merci d\'être un utilisateur précieux d\'Omi. Si vous avez des questions ou des préoccupations, n\'hésitez pas à nous contacter à team@basedhardware.com.';

  @override
  String get wifiSyncSettings => 'Paramètres de synchronisation WiFi';

  @override
  String get enterHotspotCredentials => 'Entrez les identifiants du point d\'accès de votre téléphone';

  @override
  String get wifiSyncUsesHotspot => 'La synchronisation WiFi utilise votre téléphone comme point d\'accès. Trouvez le nom et le mot de passe dans Réglages > Partage de connexion.';

  @override
  String get hotspotNameSsid => 'Nom du point d\'accès (SSID)';

  @override
  String get exampleIphoneHotspot => 'ex. Point d\'accès iPhone';

  @override
  String get password => 'Mot de passe';

  @override
  String get enterHotspotPassword => 'Entrez le mot de passe du point d\'accès';

  @override
  String get saveCredentials => 'Enregistrer les identifiants';

  @override
  String get clearCredentials => 'Effacer les identifiants';

  @override
  String get pleaseEnterHotspotName => 'Veuillez entrer un nom de point d\'accès';

  @override
  String get wifiCredentialsSaved => 'Identifiants WiFi enregistrés';

  @override
  String get wifiCredentialsCleared => 'Identifiants WiFi effacés';

  @override
  String summaryGeneratedForDate(String date) {
    return 'Résumé généré pour $date';
  }

  @override
  String get failedToGenerateSummaryCheckConversations => 'Échec de la génération du résumé. Assurez-vous d\'avoir des conversations pour ce jour.';

  @override
  String get summaryNotFound => 'Résumé non trouvé';

  @override
  String get yourDaysJourney => 'Votre parcours du jour';

  @override
  String get highlights => 'Points forts';

  @override
  String get unresolvedQuestions => 'Questions non résolues';

  @override
  String get decisions => 'Décisions';

  @override
  String get learnings => 'Apprentissages';

  @override
  String get autoDeletesAfterThreeDays => 'Suppression automatique après 3 jours.';

  @override
  String get knowledgeGraphDeletedSuccessfully => 'Graphe de connaissances supprimé avec succès';

  @override
  String get exportStartedMayTakeFewSeconds => 'Exportation commencée. Cela peut prendre quelques secondes...';

  @override
  String get knowledgeGraphDeleteDescription => 'Ceci supprimera toutes les données dérivées du graphe de connaissances (nœuds et connexions). Vos souvenirs originaux resteront en sécurité. Le graphe sera reconstruit au fil du temps ou à la prochaine demande.';
}
