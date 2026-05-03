// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Portuguese (`pt`).
class AppLocalizationsPt extends AppLocalizations {
  AppLocalizationsPt([String locale = 'pt']) : super(locale);

  @override
  String get appName => 'Nooto';

  @override
  String welcomeBrandLine(String brand) {
    return 'Bem-vindo ao $brand';
  }

  @override
  String get welcomeTaglinePrefix => 'Inteligência pessoal que transforma ';

  @override
  String get welcomeTaglineEmphasis => 'pensamento em ação.';

  @override
  String get welcomeContinueWithApple => 'Continuar com Apple';

  @override
  String get welcomeContinueWithGoogle => 'Continuar com Google';

  @override
  String get welcomeWaitingForBrowser => 'Aguardando o navegador…';

  @override
  String get welcomeAgreeFooter =>
      'Ao continuar você concorda com nossos Termos e Política de Privacidade.';

  @override
  String get onboardingPromptHintTyped => 'Digite sua resposta…';

  @override
  String get onboardingPromptHintTap =>
      'Toque em uma opção acima para continuar';

  @override
  String get onboardingOpenerName => 'Oi — como você quer que eu te chame?';

  @override
  String onboardingOpenerLanguage(String name) {
    return 'Prazer em te conhecer, $name. Em qual idioma você quer que eu fale?';
  }

  @override
  String get onboardingOpenerMicrophone =>
      'Vou precisar do seu microfone para ouvir o que importa.';

  @override
  String get onboardingOpenerNotifications =>
      'Tudo bem se eu te avisar quando algo precisar da sua atenção?';

  @override
  String get onboardingOpenerBackground =>
      'Funciono melhor se puder continuar ouvindo em segundo plano.';

  @override
  String get onboardingOpenerLocation =>
      'Quer que eu marque onde as coisas acontecem? Opcional — pode pular.';

  @override
  String get onboardingOpenerDevice =>
      'Tem um aparelho Nooto com você? Podemos conectar depois — o pareamento chega na próxima fase.';

  @override
  String get onboardingOpenerSpeechProfile =>
      'Deixa eu aprender sua voz para te reconhecer no meio de outras.';

  @override
  String get onboardingOpenerAcknowledge => 'Tudo pronto. Vamos lá.';

  @override
  String get onboardingSkipped => 'Claro, podemos fazer isso depois.';

  @override
  String get onboardingChipMoreLanguages => 'Mais idiomas…';

  @override
  String get onboardingChipSkipForNow => 'Pular por agora';

  @override
  String get onboardingChipPairLater => 'Vou parear depois';

  @override
  String get onboardingAckLetsGo => 'Vamos lá';

  @override
  String get onboardingAckGotIt => 'Entendi';

  @override
  String get onboardingPermissionAllow => 'Permitir';

  @override
  String get onboardingPermissionPending => 'Pendente';

  @override
  String get onboardingPermissionGranted => 'Permitido';

  @override
  String get onboardingPermissionDenied => 'Negado';

  @override
  String get onboardingPermissionDeniedAction => 'Abrir ajustes';

  @override
  String get onboardingPermissionLabelMicrophone => 'Acesso ao microfone';

  @override
  String get onboardingPermissionLabelMicrophoneHelper =>
      'O áudio é processado no seu dispositivo; só a transcrição sai.';

  @override
  String get onboardingPermissionLabelNotifications => 'Acesso a notificações';

  @override
  String get onboardingPermissionLabelNotificationsHelper =>
      'Só avisos úteis e silenciosos — nunca ruído.';

  @override
  String get onboardingPermissionLabelBackground =>
      'Atividade em segundo plano';

  @override
  String get onboardingPermissionLabelBackgroundHelper =>
      'Permite que o Nooto continue ativo enquanto você usa outros apps.';

  @override
  String get onboardingPermissionLabelLocation => 'Localização';

  @override
  String get onboardingPermissionLabelLocationHelper =>
      'Marca conversas com o local em que aconteceram. Opcional.';

  @override
  String get onboardingSpeechCardTitle => 'Leia isto em voz alta';

  @override
  String get onboardingSpeechCardBody =>
      'Quando estiver pronto, segure o botão e leia isto em voz normal por uns cinco segundos.';

  @override
  String get onboardingSpeechCardSample =>
      'Oi, estou configurando o Nooto. É assim que minha voz soa numa sala normal.';

  @override
  String get onboardingSpeechRecording => 'Ouvindo…';

  @override
  String get onboardingSpeechCaptured => 'Voz capturada ✓';

  @override
  String get onboardingSpeechSkip => 'Pular por agora';

  @override
  String get shellTabHome => 'Início';

  @override
  String get shellTabChat => 'Chat';

  @override
  String get shellTabLibrary => 'Biblioteca';

  @override
  String get shellTabPlan => 'Plano';

  @override
  String get shellTabApps => 'Apps';

  @override
  String shellComingSoonTitle(String tab) {
    return '$tab chega em breve';
  }

  @override
  String get shellComingSoonBody =>
      'Esta tela chega em uma fase futura. Por enquanto, o Nooto v2 é só o fluxo de boas-vindas e onboarding.';

  @override
  String get todayCardHeader => 'Hoje';

  @override
  String todayCardCountPartial(int visible, int total) {
    return '$visible de $total';
  }

  @override
  String todayCardCountFull(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count itens',
      one: '1 item',
    );
    return '$_temp0';
  }

  @override
  String get todayCardSeeAll => 'Ver tudo';

  @override
  String get todayCardSeeAllSemantics => 'Ver todas as ações, abre a aba Plano';
}
