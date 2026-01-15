// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Korean (`ko`).
class AppLocalizationsKo extends AppLocalizations {
  AppLocalizationsKo([String locale = 'ko']) : super(locale);

  @override
  String get appTitle => 'Omi';

  @override
  String get conversationTab => '대화';

  @override
  String get transcriptTab => '녹취록';

  @override
  String get actionItemsTab => '할 일';

  @override
  String get deleteConversationTitle => '대화를 삭제하시겠습니까?';

  @override
  String get deleteConversationMessage => '이 대화를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.';

  @override
  String get confirm => '확인';

  @override
  String get cancel => '취소';

  @override
  String get ok => '확인';

  @override
  String get delete => '삭제';

  @override
  String get add => '추가';

  @override
  String get update => '업데이트';

  @override
  String get save => '저장';

  @override
  String get edit => '편집';

  @override
  String get close => '닫기';

  @override
  String get clear => '지우기';

  @override
  String get copyTranscript => '녹취록 복사';

  @override
  String get copySummary => '요약 복사';

  @override
  String get testPrompt => '프롬프트 테스트';

  @override
  String get reprocessConversation => '대화 재처리';

  @override
  String get deleteConversation => '대화 삭제';

  @override
  String get contentCopied => '콘텐츠가 클립보드에 복사되었습니다';

  @override
  String get failedToUpdateStarred => '즐겨찾기 상태 업데이트에 실패했습니다.';

  @override
  String get conversationUrlNotShared => '대화 URL을 공유할 수 없습니다.';

  @override
  String get errorProcessingConversation => '대화 처리 중 오류가 발생했습니다. 나중에 다시 시도해 주세요.';

  @override
  String get noInternetConnection => '인터넷 연결을 확인하고 다시 시도해 주세요.';

  @override
  String get unableToDeleteConversation => '대화를 삭제할 수 없습니다';

  @override
  String get somethingWentWrong => '문제가 발생했습니다! 나중에 다시 시도해 주세요.';

  @override
  String get copyErrorMessage => '오류 메시지 복사';

  @override
  String get errorCopied => '오류 메시지가 클립보드에 복사되었습니다';

  @override
  String get remaining => '남은';

  @override
  String get loading => '로딩 중...';

  @override
  String get loadingDuration => '지속 시간 로딩 중...';

  @override
  String secondsCount(int count) {
    return '$count초';
  }

  @override
  String get people => '사람들';

  @override
  String get addNewPerson => '새로운 사람 추가';

  @override
  String get editPerson => '사람 편집';

  @override
  String get createPersonHint => '새로운 사람을 만들고 Omi가 그들의 음성을 인식하도록 학습시키세요!';

  @override
  String get speechProfile => '음성 프로필';

  @override
  String sampleNumber(int number) {
    return '샘플 $number';
  }

  @override
  String get settings => '설정';

  @override
  String get language => '언어';

  @override
  String get selectLanguage => '언어 선택';

  @override
  String get deleting => '삭제 중...';

  @override
  String get pleaseCompleteAuthentication => '브라우저에서 인증을 완료해 주세요. 완료되면 앱으로 돌아가세요.';

  @override
  String get failedToStartAuthentication => '인증 시작에 실패했습니다';

  @override
  String get importStarted => '가져오기가 시작되었습니다! 완료되면 알려드리겠습니다.';

  @override
  String get failedToStartImport => '가져오기 시작에 실패했습니다. 다시 시도해 주세요.';

  @override
  String get couldNotAccessFile => '선택한 파일에 접근할 수 없습니다';

  @override
  String get askOmi => 'Omi에게 질문하기';

  @override
  String get done => '완료';

  @override
  String get disconnected => '연결 끊김';

  @override
  String get searching => '검색 중';

  @override
  String get connectDevice => '기기 연결';

  @override
  String get monthlyLimitReached => '월간 한도에 도달했습니다.';

  @override
  String get checkUsage => '사용량 확인';

  @override
  String get syncingRecordings => '녹음 동기화 중';

  @override
  String get recordingsToSync => '동기화할 녹음';

  @override
  String get allCaughtUp => '모두 완료';

  @override
  String get sync => '동기화';

  @override
  String get pendantUpToDate => '펜던트가 최신 상태입니다';

  @override
  String get allRecordingsSynced => '모든 녹음이 동기화되었습니다';

  @override
  String get syncingInProgress => '동기화 진행 중';

  @override
  String get readyToSync => '동기화 준비 완료';

  @override
  String get tapSyncToStart => '동기화를 탭하여 시작하세요';

  @override
  String get pendantNotConnected => '펜던트가 연결되지 않았습니다. 동기화하려면 연결하세요.';

  @override
  String get everythingSynced => '모든 항목이 이미 동기화되었습니다.';

  @override
  String get recordingsNotSynced => '아직 동기화되지 않은 녹음이 있습니다.';

  @override
  String get syncingBackground => '백그라운드에서 녹음을 계속 동기화하겠습니다.';

  @override
  String get noConversationsYet => '아직 대화가 없습니다.';

  @override
  String get noStarredConversations => '아직 즐겨찾기한 대화가 없습니다.';

  @override
  String get starConversationHint => '대화를 즐겨찾기하려면 대화를 열고 헤더의 별 아이콘을 탭하세요.';

  @override
  String get searchConversations => '대화 검색';

  @override
  String selectedCount(int count, Object s) {
    return '$count개 선택됨';
  }

  @override
  String get merge => '병합';

  @override
  String get mergeConversations => '대화 병합';

  @override
  String mergeConversationsMessage(int count) {
    return '$count개의 대화를 하나로 결합합니다. 모든 내용이 병합되고 재생성됩니다.';
  }

  @override
  String get mergingInBackground => '백그라운드에서 병합 중입니다. 잠시 시간이 걸릴 수 있습니다.';

  @override
  String get failedToStartMerge => '병합 시작에 실패했습니다';

  @override
  String get askAnything => '무엇이든 물어보세요';

  @override
  String get noMessagesYet => '아직 메시지가 없습니다!\n대화를 시작해보는 건 어떨까요?';

  @override
  String get deletingMessages => 'Omi의 메모리에서 메시지를 삭제하는 중...';

  @override
  String get messageCopied => '메시지가 클립보드에 복사되었습니다.';

  @override
  String get cannotReportOwnMessage => '자신의 메시지는 신고할 수 없습니다.';

  @override
  String get reportMessage => '메시지 신고';

  @override
  String get reportMessageConfirm => '이 메시지를 신고하시겠습니까?';

  @override
  String get messageReported => '메시지가 성공적으로 신고되었습니다.';

  @override
  String get thankYouFeedback => '피드백 감사합니다!';

  @override
  String get clearChat => '채팅을 지우시겠습니까?';

  @override
  String get clearChatConfirm => '채팅을 지우시겠습니까? 이 작업은 되돌릴 수 없습니다.';

  @override
  String get maxFilesLimit => '한 번에 최대 4개의 파일만 업로드할 수 있습니다';

  @override
  String get chatWithOmi => 'Omi와 채팅하기';

  @override
  String get apps => '앱';

  @override
  String get noAppsFound => '앱을 찾을 수 없습니다';

  @override
  String get tryAdjustingSearch => '검색어나 필터를 조정해 보세요';

  @override
  String get createYourOwnApp => '나만의 앱 만들기';

  @override
  String get buildAndShareApp => '맞춤형 앱을 만들고 공유하세요';

  @override
  String get searchApps => '1500개 이상의 앱 검색';

  @override
  String get myApps => '내 앱';

  @override
  String get installedApps => '설치된 앱';

  @override
  String get unableToFetchApps => '앱을 가져올 수 없습니다 :(\n\n인터넷 연결을 확인하고 다시 시도해 주세요.';

  @override
  String get aboutOmi => 'Omi 정보';

  @override
  String get privacyPolicy => '개인정보 처리방침';

  @override
  String get visitWebsite => '웹사이트 방문';

  @override
  String get helpOrInquiries => '도움말 또는 문의사항이 있으신가요?';

  @override
  String get joinCommunity => '커뮤니티에 참여하세요!';

  @override
  String get membersAndCounting => '8000명 이상의 멤버가 함께하고 있습니다.';

  @override
  String get deleteAccountTitle => '계정 삭제';

  @override
  String get deleteAccountConfirm => '계정을 삭제하시겠습니까?';

  @override
  String get cannotBeUndone => '이 작업은 되돌릴 수 없습니다.';

  @override
  String get allDataErased => '모든 기억과 대화가 영구적으로 삭제됩니다.';

  @override
  String get appsDisconnected => '앱 및 통합 기능이 즉시 연결 해제됩니다.';

  @override
  String get exportBeforeDelete => '계정을 삭제하기 전에 데이터를 내보낼 수 있지만, 삭제된 후에는 복구할 수 없습니다.';

  @override
  String get deleteAccountCheckbox => '계정 삭제는 영구적이며 기억과 대화를 포함한 모든 데이터가 손실되어 복구할 수 없음을 이해합니다.';

  @override
  String get areYouSure => '정말 확실하신가요?';

  @override
  String get deleteAccountFinal => '이 작업은 되돌릴 수 없으며 계정과 관련된 모든 데이터가 영구적으로 삭제됩니다. 계속하시겠습니까?';

  @override
  String get deleteNow => '지금 삭제';

  @override
  String get goBack => '돌아가기';

  @override
  String get checkBoxToConfirm => '계정 삭제가 영구적이고 되돌릴 수 없음을 이해했음을 확인하려면 체크박스를 선택하세요.';

  @override
  String get profile => '프로필';

  @override
  String get name => '이름';

  @override
  String get email => '이메일';

  @override
  String get customVocabulary => '사용자 지정 어휘';

  @override
  String get identifyingOthers => '다른 사람 식별';

  @override
  String get paymentMethods => '결제 수단';

  @override
  String get conversationDisplay => '대화 표시';

  @override
  String get dataPrivacy => '데이터 및 개인정보';

  @override
  String get userId => '사용자 ID';

  @override
  String get notSet => '설정되지 않음';

  @override
  String get userIdCopied => '사용자 ID가 클립보드에 복사되었습니다';

  @override
  String get systemDefault => '시스템 기본값';

  @override
  String get planAndUsage => '플랜 및 사용량';

  @override
  String get offlineSync => '오프라인 동기화';

  @override
  String get deviceSettings => '기기 설정';

  @override
  String get chatTools => '채팅 도구';

  @override
  String get feedbackBug => '피드백 / 버그';

  @override
  String get helpCenter => '고객센터';

  @override
  String get developerSettings => '개발자 설정';

  @override
  String get getOmiForMac => 'Mac용 Omi 다운로드';

  @override
  String get referralProgram => '추천 프로그램';

  @override
  String get signOut => '로그아웃';

  @override
  String get appAndDeviceCopied => '앱 및 기기 정보가 복사되었습니다';

  @override
  String get wrapped2025 => 'Wrapped 2025';

  @override
  String get yourPrivacyYourControl => '당신의 개인정보, 당신의 제어';

  @override
  String get privacyIntro => 'Omi는 귀하의 개인정보 보호에 최선을 다하고 있습니다. 이 페이지에서 데이터 저장 및 사용 방법을 제어할 수 있습니다.';

  @override
  String get learnMore => '자세히 알아보기...';

  @override
  String get dataProtectionLevel => '데이터 보호 수준';

  @override
  String get dataProtectionDesc => '귀하의 데이터는 기본적으로 강력한 암호화로 보호됩니다. 아래에서 설정 및 향후 개인정보 옵션을 검토하세요.';

  @override
  String get appAccess => '앱 접근';

  @override
  String get appAccessDesc => '다음 앱이 귀하의 데이터에 접근할 수 있습니다. 앱을 탭하여 권한을 관리하세요.';

  @override
  String get noAppsExternalAccess => '설치된 앱 중 귀하의 데이터에 외부 접근 권한이 있는 앱이 없습니다.';

  @override
  String get deviceName => '기기 이름';

  @override
  String get deviceId => '기기 ID';

  @override
  String get firmware => '펌웨어';

  @override
  String get sdCardSync => 'SD 카드 동기화';

  @override
  String get hardwareRevision => '하드웨어 버전';

  @override
  String get modelNumber => '모델 번호';

  @override
  String get manufacturer => '제조사';

  @override
  String get doubleTap => '더블 탭';

  @override
  String get ledBrightness => 'LED 밝기';

  @override
  String get micGain => '마이크 게인';

  @override
  String get disconnect => '연결 해제';

  @override
  String get forgetDevice => '기기 삭제';

  @override
  String get chargingIssues => '충전 문제';

  @override
  String get disconnectDevice => '기기 연결 해제';

  @override
  String get unpairDevice => '기기 페어링 해제';

  @override
  String get unpairAndForget => '기기 페어링 해제 및 삭제';

  @override
  String get deviceDisconnectedMessage => 'Omi 기기의 연결이 해제되었습니다 😔';

  @override
  String get deviceUnpairedMessage => '기기 페어링이 해제되었습니다. 페어링 해제를 완료하려면 설정 > 블루투스로 이동하여 기기를 삭제하세요.';

  @override
  String get unpairDialogTitle => '기기 페어링 해제';

  @override
  String get unpairDialogMessage => '다른 휴대폰에 연결할 수 있도록 기기의 페어링을 해제합니다. 프로세스를 완료하려면 설정 > 블루투스로 이동하여 기기를 삭제해야 합니다.';

  @override
  String get deviceNotConnected => '기기가 연결되지 않음';

  @override
  String get connectDeviceMessage => 'Omi 기기를 연결하여\n기기 설정 및 사용자 지정에 접근하세요';

  @override
  String get deviceInfoSection => '기기 정보';

  @override
  String get customizationSection => '사용자 지정';

  @override
  String get hardwareSection => '하드웨어';

  @override
  String get v2Undetected => 'V2를 감지할 수 없음';

  @override
  String get v2UndetectedMessage => 'V1 기기를 사용하고 있거나 기기가 연결되지 않았습니다. SD 카드 기능은 V2 기기에서만 사용할 수 있습니다.';

  @override
  String get endConversation => '대화 종료';

  @override
  String get pauseResume => '일시정지/재개';

  @override
  String get starConversation => '대화 즐겨찾기';

  @override
  String get doubleTapAction => '더블 탭 동작';

  @override
  String get endAndProcess => '대화 종료 및 처리';

  @override
  String get pauseResumeRecording => '녹음 일시정지/재개';

  @override
  String get starOngoing => '진행 중인 대화 즐겨찾기';

  @override
  String get off => '끄기';

  @override
  String get max => '최대';

  @override
  String get mute => '음소거';

  @override
  String get quiet => '조용함';

  @override
  String get normal => '보통';

  @override
  String get high => '높음';

  @override
  String get micGainDescMuted => '마이크가 음소거되었습니다';

  @override
  String get micGainDescLow => '매우 조용함 - 시끄러운 환경용';

  @override
  String get micGainDescModerate => '조용함 - 보통 소음용';

  @override
  String get micGainDescNeutral => '중립 - 균형 잡힌 녹음';

  @override
  String get micGainDescSlightlyBoosted => '약간 증폭 - 일반 사용';

  @override
  String get micGainDescBoosted => '증폭 - 조용한 환경용';

  @override
  String get micGainDescHigh => '높음 - 멀리 있거나 부드러운 목소리용';

  @override
  String get micGainDescVeryHigh => '매우 높음 - 매우 조용한 소스용';

  @override
  String get micGainDescMax => '최대 - 주의해서 사용';

  @override
  String get developerSettingsTitle => '개발자 설정';

  @override
  String get saving => '저장 중...';

  @override
  String get personaConfig => 'AI 페르소나 구성';

  @override
  String get beta => '베타';

  @override
  String get transcription => '음성 변환';

  @override
  String get transcriptionConfig => 'STT 제공업체 구성';

  @override
  String get conversationTimeout => '대화 시간 제한';

  @override
  String get conversationTimeoutConfig => '대화 자동 종료 시간 설정';

  @override
  String get importData => '데이터 가져오기';

  @override
  String get importDataConfig => '다른 소스에서 데이터 가져오기';

  @override
  String get debugDiagnostics => '디버그 및 진단';

  @override
  String get endpointUrl => '엔드포인트 URL';

  @override
  String get noApiKeys => '아직 API 키가 없습니다';

  @override
  String get createKeyToStart => '시작하려면 키를 만드세요';

  @override
  String get createKey => '키 만들기';

  @override
  String get docs => '문서';

  @override
  String get yourOmiInsights => 'Omi 인사이트';

  @override
  String get today => '오늘';

  @override
  String get thisMonth => '이번 달';

  @override
  String get thisYear => '올해';

  @override
  String get allTime => '전체 기간';

  @override
  String get noActivityYet => '아직 활동이 없습니다';

  @override
  String get startConversationToSeeInsights => 'Omi와 대화를 시작하여\n사용량 인사이트를 확인하세요.';

  @override
  String get listening => '청취';

  @override
  String get listeningSubtitle => 'Omi가 적극적으로 청취한 총 시간입니다.';

  @override
  String get understanding => '이해';

  @override
  String get understandingSubtitle => '대화에서 이해한 단어 수입니다.';

  @override
  String get providing => '제공';

  @override
  String get providingSubtitle => '자동으로 캡처된 할 일 및 메모입니다.';

  @override
  String get remembering => '기억';

  @override
  String get rememberingSubtitle => '당신을 위해 기억된 사실과 세부 정보입니다.';

  @override
  String get unlimitedPlan => '무제한 플랜';

  @override
  String get managePlan => '플랜 관리';

  @override
  String cancelAtPeriodEnd(String date) {
    return '플랜이 $date에 취소됩니다.';
  }

  @override
  String renewsOn(String date) {
    return '플랜이 $date에 갱신됩니다.';
  }

  @override
  String get basicPlan => '무료 플랜';

  @override
  String usageLimitMessage(String used, int limit) {
    return '$limit분 중 $used분 사용';
  }

  @override
  String get upgrade => '업그레이드';

  @override
  String get upgradeToUnlimited => '무제한으로 업그레이드';

  @override
  String basicPlanDesc(int limit) {
    return '플랜에는 매월 $limit분의 무료 시간이 포함됩니다. 무제한으로 업그레이드하세요.';
  }

  @override
  String get shareStatsMessage => '내 Omi 통계를 공유합니다! (omi.me - 항상 켜져 있는 AI 어시스턴트)';

  @override
  String get sharePeriodToday => '오늘 Omi는:';

  @override
  String get sharePeriodMonth => '이번 달 Omi는:';

  @override
  String get sharePeriodYear => '올해 Omi는:';

  @override
  String get sharePeriodAllTime => '지금까지 Omi는:';

  @override
  String shareStatsListened(String minutes) {
    return '🎧 $minutes분 동안 청취했습니다';
  }

  @override
  String shareStatsWords(String words) {
    return '🧠 $words개의 단어를 이해했습니다';
  }

  @override
  String shareStatsInsights(String count) {
    return '✨ $count개의 인사이트를 제공했습니다';
  }

  @override
  String shareStatsMemories(String count) {
    return '📚 $count개의 기억을 저장했습니다';
  }

  @override
  String get debugLogs => '디버그 로그';

  @override
  String get debugLogsAutoDelete => '3일 후 자동 삭제됩니다.';

  @override
  String get debugLogsDesc => '문제 진단에 도움이 됩니다';

  @override
  String get noLogFilesFound => '로그 파일을 찾을 수 없습니다.';

  @override
  String get omiDebugLog => 'Omi 디버그 로그';

  @override
  String get logShared => '로그가 공유되었습니다';

  @override
  String get selectLogFile => '로그 파일 선택';

  @override
  String get shareLogs => '로그 공유';

  @override
  String get debugLogCleared => '디버그 로그가 지워졌습니다';

  @override
  String get exportStarted => '내보내기가 시작되었습니다. 몇 초 정도 걸릴 수 있습니다...';

  @override
  String get exportAllData => '모든 데이터 내보내기';

  @override
  String get exportDataDesc => '대화를 JSON 파일로 내보내기';

  @override
  String get exportedConversations => 'Omi에서 내보낸 대화';

  @override
  String get exportShared => '내보내기가 공유되었습니다';

  @override
  String get deleteKnowledgeGraphTitle => '지식 그래프를 삭제하시겠습니까?';

  @override
  String get deleteKnowledgeGraphMessage =>
      '파생된 모든 지식 그래프 데이터(노드 및 연결)가 삭제됩니다. 원본 기억은 안전하게 유지됩니다. 그래프는 시간이 지나면 다시 구축되거나 다음 요청 시 재구축됩니다.';

  @override
  String get knowledgeGraphDeleted => '지식 그래프가 성공적으로 삭제되었습니다';

  @override
  String deleteGraphFailed(String error) {
    return '그래프 삭제 실패: $error';
  }

  @override
  String get deleteKnowledgeGraph => '지식 그래프 삭제';

  @override
  String get deleteKnowledgeGraphDesc => '모든 노드 및 연결 지우기';

  @override
  String get mcp => 'MCP';

  @override
  String get mcpServer => 'MCP 서버';

  @override
  String get mcpServerDesc => 'AI 어시스턴트를 데이터에 연결';

  @override
  String get serverUrl => '서버 URL';

  @override
  String get urlCopied => 'URL이 복사되었습니다';

  @override
  String get apiKeyAuth => 'API 키 인증';

  @override
  String get header => '헤더';

  @override
  String get authorizationBearer => 'Authorization: Bearer <key>';

  @override
  String get oauth => 'OAuth';

  @override
  String get clientId => '클라이언트 ID';

  @override
  String get clientSecret => '클라이언트 시크릿';

  @override
  String get useMcpApiKey => 'MCP API 키 사용';

  @override
  String get webhooks => '웹훅';

  @override
  String get conversationEvents => '대화 이벤트';

  @override
  String get newConversationCreated => '새 대화가 생성됨';

  @override
  String get realtimeTranscript => '실시간 녹취록';

  @override
  String get transcriptReceived => '녹취록 수신됨';

  @override
  String get audioBytes => '오디오 바이트';

  @override
  String get audioDataReceived => '오디오 데이터 수신됨';

  @override
  String get intervalSeconds => '간격(초)';

  @override
  String get daySummary => '일일 요약';

  @override
  String get summaryGenerated => '요약 생성됨';

  @override
  String get claudeDesktop => 'Claude Desktop';

  @override
  String get addToClaudeConfig => 'claude_desktop_config.json에 추가';

  @override
  String get copyConfig => '구성 복사';

  @override
  String get configCopied => '구성이 클립보드에 복사되었습니다';

  @override
  String get listeningMins => '청취(분)';

  @override
  String get understandingWords => '이해(단어)';

  @override
  String get insights => '인사이트';

  @override
  String get memories => '기억';

  @override
  String minsUsedThisMonth(String used, int limit) {
    return '이번 달 $limit분 중 $used분 사용';
  }

  @override
  String wordsUsedThisMonth(String used, String limit) {
    return '이번 달 $limit단어 중 $used단어 사용';
  }

  @override
  String insightsUsedThisMonth(String used, String limit) {
    return '이번 달 $limit개 중 $used개의 인사이트 획득';
  }

  @override
  String memoriesUsedThisMonth(String used, String limit) {
    return '이번 달 $limit개 중 $used개의 기억 생성';
  }

  @override
  String get visibility => '가시성';

  @override
  String get visibilitySubtitle => '목록에 표시할 대화 제어';

  @override
  String get showShortConversations => '짧은 대화 표시';

  @override
  String get showShortConversationsDesc => '임계값보다 짧은 대화 표시';

  @override
  String get showDiscardedConversations => '폐기된 대화 표시';

  @override
  String get showDiscardedConversationsDesc => '폐기된 것으로 표시된 대화 포함';

  @override
  String get shortConversationThreshold => '짧은 대화 임계값';

  @override
  String get shortConversationThresholdSubtitle => '이보다 짧은 대화는 위에서 활성화하지 않는 한 숨겨집니다';

  @override
  String get durationThreshold => '지속 시간 임계값';

  @override
  String get durationThresholdDesc => '이보다 짧은 대화 숨기기';

  @override
  String minLabel(int count) {
    return '$count분';
  }

  @override
  String get customVocabularyTitle => '사용자 지정 어휘';

  @override
  String get addWords => '단어 추가';

  @override
  String get addWordsDesc => '이름, 용어 또는 일반적이지 않은 단어';

  @override
  String get vocabularyHint => 'Omi, Callie, OpenAI';

  @override
  String get connect => '연결';

  @override
  String get comingSoon => '곧 출시';

  @override
  String get chatToolsFooter => '채팅에서 데이터 및 지표를 보려면 앱을 연결하세요.';

  @override
  String get completeAuthInBrowser => '브라우저에서 인증을 완료해 주세요. 완료되면 앱으로 돌아가세요.';

  @override
  String failedToStartAuth(String appName) {
    return '$appName 인증 시작에 실패했습니다';
  }

  @override
  String disconnectAppTitle(String appName) {
    return '$appName의 연결을 해제하시겠습니까?';
  }

  @override
  String disconnectAppMessage(String appName) {
    return '$appName과의 연결을 해제하시겠습니까? 언제든지 다시 연결할 수 있습니다.';
  }

  @override
  String disconnectedFrom(String appName) {
    return '$appName과의 연결이 해제되었습니다';
  }

  @override
  String get failedToDisconnect => '연결 해제 실패';

  @override
  String connectTo(String appName) {
    return '$appName에 연결';
  }

  @override
  String authAccessMessage(String appName) {
    return 'Omi가 $appName 데이터에 접근하도록 권한을 부여해야 합니다. 인증을 위해 브라우저가 열립니다.';
  }

  @override
  String get continueAction => '계속';

  @override
  String get languageTitle => '언어';

  @override
  String get primaryLanguage => '기본 언어';

  @override
  String get automaticTranslation => '자동 번역';

  @override
  String get detectLanguages => '10개 이상의 언어 감지';

  @override
  String get authorizeSavingRecordings => '녹음 저장 권한 부여';

  @override
  String get thanksForAuthorizing => '권한을 부여해 주셔서 감사합니다!';

  @override
  String get needYourPermission => '귀하의 권한이 필요합니다';

  @override
  String get alreadyGavePermission => '녹음 저장 권한을 이미 부여하셨습니다. 필요한 이유를 다시 안내드립니다:';

  @override
  String get wouldLikePermission => '음성 녹음 저장 권한을 부여해 주세요. 그 이유는 다음과 같습니다:';

  @override
  String get improveSpeechProfile => '음성 프로필 개선';

  @override
  String get improveSpeechProfileDesc => '녹음을 사용하여 개인 음성 프로필을 추가로 학습하고 향상시킵니다.';

  @override
  String get trainFamilyProfiles => '친구 및 가족 프로필 학습';

  @override
  String get trainFamilyProfilesDesc => '녹음은 친구와 가족을 인식하고 프로필을 만드는 데 도움이 됩니다.';

  @override
  String get enhanceTranscriptAccuracy => '녹취록 정확도 향상';

  @override
  String get enhanceTranscriptAccuracyDesc => '모델이 개선됨에 따라 녹음에 대한 더 나은 변환 결과를 제공할 수 있습니다.';

  @override
  String get legalNotice =>
      '법적 고지: 음성 데이터 녹음 및 저장의 합법성은 위치 및 이 기능 사용 방법에 따라 다를 수 있습니다. 현지 법률 및 규정을 준수하는지 확인하는 것은 귀하의 책임입니다.';

  @override
  String get alreadyAuthorized => '이미 승인됨';

  @override
  String get authorize => '권한 부여';

  @override
  String get revokeAuthorization => '권한 취소';

  @override
  String get authorizationSuccessful => '권한 부여 성공!';

  @override
  String get failedToAuthorize => '권한 부여에 실패했습니다. 다시 시도해 주세요.';

  @override
  String get authorizationRevoked => '권한이 취소되었습니다.';

  @override
  String get recordingsDeleted => '녹음이 삭제되었습니다.';

  @override
  String get failedToRevoke => '권한 취소에 실패했습니다. 다시 시도해 주세요.';

  @override
  String get permissionRevokedTitle => '권한 취소됨';

  @override
  String get permissionRevokedMessage => '기존 녹음도 모두 삭제하시겠습니까?';

  @override
  String get yes => '예';

  @override
  String get editName => '이름 편집';

  @override
  String get howShouldOmiCallYou => 'Omi가 어떻게 불러드릴까요?';

  @override
  String get enterYourName => '이름을 입력하세요';

  @override
  String get nameCannotBeEmpty => '이름은 비워둘 수 없습니다';

  @override
  String get nameUpdatedSuccessfully => '이름이 성공적으로 업데이트되었습니다!';

  @override
  String get calendarSettings => '캘린더 설정';

  @override
  String get calendarProviders => '캘린더 제공업체';

  @override
  String get macOsCalendar => 'macOS 캘린더';

  @override
  String get connectMacOsCalendar => '로컬 macOS 캘린더 연결';

  @override
  String get googleCalendar => 'Google 캘린더';

  @override
  String get syncGoogleAccount => 'Google 계정과 동기화';

  @override
  String get showMeetingsMenuBar => '메뉴 바에 예정된 회의 표시';

  @override
  String get showMeetingsMenuBarDesc => 'macOS 메뉴 바에 다음 회의 및 시작까지의 시간 표시';

  @override
  String get showEventsNoParticipants => '참가자가 없는 이벤트 표시';

  @override
  String get showEventsNoParticipantsDesc => '활성화하면 참가자나 비디오 링크가 없는 이벤트가 Coming Up에 표시됩니다.';

  @override
  String get yourMeetings => '내 회의';

  @override
  String get refresh => '새로고침';

  @override
  String get noUpcomingMeetings => '예정된 회의를 찾을 수 없습니다';

  @override
  String get checkingNextDays => '향후 30일 확인';

  @override
  String get tomorrow => '내일';

  @override
  String get googleCalendarComingSoon => 'Google 캘린더 통합이 곧 출시됩니다!';

  @override
  String connectedAsUser(String userId) {
    return '다음 사용자로 연결됨: $userId';
  }

  @override
  String get defaultWorkspace => '기본 워크스페이스';

  @override
  String get tasksCreatedInWorkspace => '작업이 이 워크스페이스에 생성됩니다';

  @override
  String get defaultProjectOptional => '기본 프로젝트(선택 사항)';

  @override
  String get leaveUnselectedTasks => '프로젝트 없이 작업을 생성하려면 선택하지 마세요';

  @override
  String get noProjectsInWorkspace => '이 워크스페이스에서 프로젝트를 찾을 수 없습니다';

  @override
  String get conversationTimeoutDesc => '대화를 자동으로 종료하기 전에 대기할 침묵 시간을 선택하세요:';

  @override
  String get timeout2Minutes => '2분';

  @override
  String get timeout2MinutesDesc => '2분간 침묵 후 대화 종료';

  @override
  String get timeout5Minutes => '5분';

  @override
  String get timeout5MinutesDesc => '5분간 침묵 후 대화 종료';

  @override
  String get timeout10Minutes => '10분';

  @override
  String get timeout10MinutesDesc => '10분간 침묵 후 대화 종료';

  @override
  String get timeout30Minutes => '30분';

  @override
  String get timeout30MinutesDesc => '30분간 침묵 후 대화 종료';

  @override
  String get timeout4Hours => '4시간';

  @override
  String get timeout4HoursDesc => '4시간 침묵 후 대화 종료';

  @override
  String get conversationEndAfterHours => '이제 4시간 침묵 후 대화가 종료됩니다';

  @override
  String conversationEndAfterMinutes(int minutes) {
    return '이제 $minutes분 침묵 후 대화가 종료됩니다';
  }

  @override
  String get tellUsPrimaryLanguage => '기본 언어를 알려주세요';

  @override
  String get languageForTranscription => '더 정확한 변환과 맞춤형 경험을 위해 언어를 설정하세요.';

  @override
  String get singleLanguageModeInfo => '단일 언어 모드가 활성화되었습니다. 정확도 향상을 위해 번역이 비활성화됩니다.';

  @override
  String get searchLanguageHint => '이름 또는 코드로 언어 검색';

  @override
  String get noLanguagesFound => '언어를 찾을 수 없습니다';

  @override
  String get skip => '건너뛰기';

  @override
  String languageSetTo(String language) {
    return '언어가 $language(으)로 설정되었습니다';
  }

  @override
  String get failedToSetLanguage => '언어 설정 실패';

  @override
  String appSettings(String appName) {
    return '$appName 설정';
  }

  @override
  String disconnectFromApp(String appName) {
    return '$appName과의 연결을 해제하시겠습니까?';
  }

  @override
  String disconnectFromAppDesc(String appName) {
    return '$appName 인증이 제거됩니다. 다시 사용하려면 다시 연결해야 합니다.';
  }

  @override
  String connectedToApp(String appName) {
    return '$appName에 연결됨';
  }

  @override
  String get account => '계정';

  @override
  String actionItemsSyncedTo(String appName) {
    return '할 일 항목이 $appName 계정과 동기화됩니다';
  }

  @override
  String get defaultSpace => '기본 스페이스';

  @override
  String get selectSpaceInWorkspace => '워크스페이스에서 스페이스 선택';

  @override
  String get noSpacesInWorkspace => '이 워크스페이스에서 스페이스를 찾을 수 없습니다';

  @override
  String get defaultList => '기본 목록';

  @override
  String get tasksAddedToList => '작업이 이 목록에 추가됩니다';

  @override
  String get noListsInSpace => '이 스페이스에서 목록을 찾을 수 없습니다';

  @override
  String failedToLoadRepos(String error) {
    return '저장소 로드 실패: $error';
  }

  @override
  String get defaultRepoSaved => '기본 저장소가 저장되었습니다';

  @override
  String get failedToSaveDefaultRepo => '기본 저장소 저장 실패';

  @override
  String get defaultRepository => '기본 저장소';

  @override
  String get selectDefaultRepoDesc => '이슈 생성을 위한 기본 저장소를 선택하세요. 이슈 생성 시 다른 저장소를 지정할 수도 있습니다.';

  @override
  String get noReposFound => '저장소를 찾을 수 없습니다';

  @override
  String get private => '비공개';

  @override
  String updatedDate(String date) {
    return '$date 업데이트됨';
  }

  @override
  String get yesterday => '어제';

  @override
  String daysAgo(int count) {
    return '$count일 전';
  }

  @override
  String get oneWeekAgo => '1주일 전';

  @override
  String weeksAgo(int count) {
    return '$count주 전';
  }

  @override
  String get oneMonthAgo => '1개월 전';

  @override
  String monthsAgo(int count) {
    return '$count개월 전';
  }

  @override
  String get issuesCreatedInRepo => '이슈가 기본 저장소에 생성됩니다';

  @override
  String get taskIntegrations => '작업 통합';

  @override
  String get configureSettings => '설정 구성';

  @override
  String get completeAuthBrowser => '브라우저에서 인증을 완료해 주세요. 완료되면 앱으로 돌아가세요.';

  @override
  String failedToStartAppAuth(String appName) {
    return '$appName 인증 시작에 실패했습니다';
  }

  @override
  String connectToAppTitle(String appName) {
    return '$appName에 연결';
  }

  @override
  String authorizeOmiForTasks(String appName) {
    return '$appName 계정에서 작업을 생성하도록 Omi에 권한을 부여해야 합니다. 인증을 위해 브라우저가 열립니다.';
  }

  @override
  String get continueButton => '계속';

  @override
  String appIntegration(String appName) {
    return '$appName 통합';
  }

  @override
  String integrationComingSoon(String appName) {
    return '$appName과의 통합이 곧 출시됩니다! 더 많은 작업 관리 옵션을 제공하기 위해 열심히 노력하고 있습니다.';
  }

  @override
  String get gotIt => '알겠습니다';

  @override
  String get tasksExportedOneApp => '작업은 한 번에 하나의 앱으로 내보낼 수 있습니다.';

  @override
  String get completeYourUpgrade => '업그레이드 완료';

  @override
  String get importConfiguration => '구성 가져오기';

  @override
  String get exportConfiguration => '구성 내보내기';

  @override
  String get bringYourOwn => '직접 가져오기';

  @override
  String get payYourSttProvider => 'Omi를 자유롭게 사용하세요. STT 제공업체에 직접 비용을 지불하기만 하면 됩니다.';

  @override
  String get freeMinutesMonth => '월 1,200분 무료 포함. ';

  @override
  String get omiUnlimited => 'Omi Unlimited';

  @override
  String get hostRequired => '호스트가 필요합니다';

  @override
  String get validPortRequired => '유효한 포트가 필요합니다';

  @override
  String get validWebsocketUrlRequired => '유효한 WebSocket URL이 필요합니다(wss://)';

  @override
  String get apiUrlRequired => 'API URL이 필요합니다';

  @override
  String get apiKeyRequired => 'API 키가 필요합니다';

  @override
  String get invalidJsonConfig => '잘못된 JSON 구성';

  @override
  String errorSaving(String error) {
    return '저장 오류: $error';
  }

  @override
  String get configCopiedToClipboard => '구성이 클립보드에 복사되었습니다';

  @override
  String get pasteJsonConfig => '아래에 JSON 구성을 붙여넣으세요:';

  @override
  String get addApiKeyAfterImport => '가져오기 후 자신의 API 키를 추가해야 합니다';

  @override
  String get paste => '붙여넣기';

  @override
  String get import => '가져오기';

  @override
  String get invalidProviderInConfig => '구성의 제공업체가 잘못되었습니다';

  @override
  String importedConfig(String providerName) {
    return '$providerName 구성을 가져왔습니다';
  }

  @override
  String invalidJson(String error) {
    return '잘못된 JSON: $error';
  }

  @override
  String get provider => '제공업체';

  @override
  String get live => '실시간';

  @override
  String get onDevice => '기기에서';

  @override
  String get apiUrl => 'API URL';

  @override
  String get enterSttHttpEndpoint => 'STT HTTP 엔드포인트를 입력하세요';

  @override
  String get websocketUrl => 'WebSocket URL';

  @override
  String get enterLiveSttWebsocket => '실시간 STT WebSocket 엔드포인트를 입력하세요';

  @override
  String get apiKey => 'API 키';

  @override
  String get enterApiKey => 'API 키를 입력하세요';

  @override
  String get storedLocallyNeverShared => '로컬에 저장되며 절대 공유되지 않습니다';

  @override
  String get host => '호스트';

  @override
  String get port => '포트';

  @override
  String get advanced => '고급';

  @override
  String get configuration => '구성';

  @override
  String get requestConfiguration => '요청 구성';

  @override
  String get responseSchema => '응답 스키마';

  @override
  String get modified => '수정됨';

  @override
  String get resetRequestConfig => '요청 구성을 기본값으로 재설정';

  @override
  String get logs => '로그';

  @override
  String get logsCopied => '로그가 복사되었습니다';

  @override
  String get noLogsYet => '아직 로그가 없습니다. 녹음을 시작하여 사용자 지정 STT 활동을 확인하세요.';

  @override
  String deviceUsesCodec(String deviceName, String codecReason) {
    return '$deviceName은(는) $codecReason을(를) 사용합니다. Omi가 사용됩니다.';
  }

  @override
  String get omiTranscription => 'Omi 음성 변환';

  @override
  String get bestInClassTranscription => '설정이 필요 없는 최고 수준의 음성 변환';

  @override
  String get instantSpeakerLabels => '즉시 화자 레이블 지정';

  @override
  String get languageTranslation => '100개 이상의 언어 번역';

  @override
  String get optimizedForConversation => '대화에 최적화';

  @override
  String get autoLanguageDetection => '자동 언어 감지';

  @override
  String get highAccuracy => '높은 정확도';

  @override
  String get privacyFirst => '개인정보 보호 우선';

  @override
  String get saveChanges => '변경 사항 저장';

  @override
  String get resetToDefault => '기본값으로 재설정';

  @override
  String get viewTemplate => '템플릿 보기';

  @override
  String get trySomethingLike => '다음과 같이 시도해 보세요...';

  @override
  String get tryIt => '시도해 보기';

  @override
  String get creatingPlan => '계획 생성 중';

  @override
  String get developingLogic => '로직 개발 중';

  @override
  String get designingApp => '앱 디자인 중';

  @override
  String get generatingIconStep => '아이콘 생성 중';

  @override
  String get finalTouches => '최종 마무리';

  @override
  String get processing => '처리 중...';

  @override
  String get features => '기능';

  @override
  String get creatingYourApp => '앱을 만드는 중...';

  @override
  String get generatingIcon => '아이콘 생성 중...';

  @override
  String get whatShouldWeMake => '무엇을 만들까요?';

  @override
  String get appName => '앱 이름';

  @override
  String get description => '설명';

  @override
  String get publicLabel => '공개';

  @override
  String get privateLabel => '비공개';

  @override
  String get free => '무료';

  @override
  String get perMonth => '/ 월';

  @override
  String get tailoredConversationSummaries => '맞춤형 대화 요약';

  @override
  String get customChatbotPersonality => '사용자 지정 챗봇 성격';

  @override
  String get makePublic => '공개하기';

  @override
  String get anyoneCanDiscover => '누구나 앱을 찾을 수 있습니다';

  @override
  String get onlyYouCanUse => '본인만 이 앱을 사용할 수 있습니다';

  @override
  String get paidApp => '유료 앱';

  @override
  String get usersPayToUse => '사용자가 앱을 사용하려면 비용을 지불합니다';

  @override
  String get freeForEveryone => '모두에게 무료';

  @override
  String get perMonthLabel => '/ 월';

  @override
  String get creating => '생성 중...';

  @override
  String get createApp => '앱 만들기';

  @override
  String get searchingForDevices => '기기 검색 중...';

  @override
  String devicesFoundNearby(int count) {
    return '근처에서 $count개의 기기 발견';
  }

  @override
  String get pairingSuccessful => '페어링 성공';

  @override
  String errorConnectingAppleWatch(String error) {
    return 'Apple Watch 연결 오류: $error';
  }

  @override
  String get dontShowAgain => '다시 표시하지 않기';

  @override
  String get iUnderstand => '이해했습니다';

  @override
  String get enableBluetooth => '블루투스 활성화';

  @override
  String get bluetoothNeeded => 'Omi가 웨어러블에 연결하려면 블루투스가 필요합니다. 블루투스를 활성화하고 다시 시도해 주세요.';

  @override
  String get contactSupport => '지원팀에 문의하시겠습니까?';

  @override
  String get connectLater => '나중에 연결';

  @override
  String get grantPermissions => '권한 부여';

  @override
  String get backgroundActivity => '백그라운드 활동';

  @override
  String get backgroundActivityDesc => '더 나은 안정성을 위해 Omi가 백그라운드에서 실행되도록 허용';

  @override
  String get locationAccess => '위치 접근';

  @override
  String get locationAccessDesc => '완전한 경험을 위해 백그라운드 위치 활성화';

  @override
  String get notifications => '알림';

  @override
  String get notificationsDesc => '정보를 받기 위해 알림 활성화';

  @override
  String get locationServiceDisabled => '위치 서비스 비활성화됨';

  @override
  String get locationServiceDisabledDesc => '위치 서비스가 비활성화되어 있습니다. 설정 > 개인정보 보호 및 보안 > 위치 서비스로 이동하여 활성화하세요';

  @override
  String get backgroundLocationDenied => '백그라운드 위치 접근 거부됨';

  @override
  String get backgroundLocationDeniedDesc => '기기 설정으로 이동하여 위치 권한을 \"항상 허용\"으로 설정하세요';

  @override
  String get lovingOmi => 'Omi가 마음에 드시나요?';

  @override
  String get leaveReviewIos => 'App Store에 리뷰를 남겨 더 많은 사람들에게 다가가도록 도와주세요. 귀하의 피드백은 저희에게 큰 의미가 있습니다!';

  @override
  String get leaveReviewAndroid => 'Google Play 스토어에 리뷰를 남겨 더 많은 사람들에게 다가가도록 도와주세요. 귀하의 피드백은 저희에게 큰 의미가 있습니다!';

  @override
  String get rateOnAppStore => 'App Store에서 평가하기';

  @override
  String get rateOnGooglePlay => 'Google Play에서 평가하기';

  @override
  String get maybeLater => '나중에';

  @override
  String get speechProfileIntro => 'Omi가 귀하의 목표와 음성을 학습해야 합니다. 나중에 수정할 수 있습니다.';

  @override
  String get getStarted => '시작하기';

  @override
  String get allDone => '모두 완료!';

  @override
  String get keepGoing => '계속하세요, 잘하고 있습니다';

  @override
  String get skipThisQuestion => '이 질문 건너뛰기';

  @override
  String get skipForNow => '지금은 건너뛰기';

  @override
  String get connectionError => '연결 오류';

  @override
  String get connectionErrorDesc => '서버 연결에 실패했습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.';

  @override
  String get invalidRecordingMultipleSpeakers => '잘못된 녹음 감지됨';

  @override
  String get multipleSpeakersDesc => '녹음에 여러 명의 화자가 있는 것 같습니다. 조용한 장소에 있는지 확인하고 다시 시도하세요.';

  @override
  String get tooShortDesc => '음성이 충분히 감지되지 않았습니다. 더 많이 말하고 다시 시도하세요.';

  @override
  String get invalidRecordingDesc => '최소 5초 이상 90초 이하로 말씀해 주세요.';

  @override
  String get areYouThere => '계십니까?';

  @override
  String get noSpeechDesc => '음성을 감지할 수 없습니다. 최소 10초 이상 3분 이하로 말씀해 주세요.';

  @override
  String get connectionLost => '연결 끊김';

  @override
  String get connectionLostDesc => '연결이 중단되었습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.';

  @override
  String get tryAgain => '다시 시도';

  @override
  String get connectOmiOmiGlass => 'Omi / OmiGlass 연결';

  @override
  String get continueWithoutDevice => '기기 없이 계속';

  @override
  String get permissionsRequired => '권한 필요';

  @override
  String get permissionsRequiredDesc => '이 앱은 제대로 작동하려면 블루투스 및 위치 권한이 필요합니다. 설정에서 활성화하세요.';

  @override
  String get openSettings => '설정 열기';

  @override
  String get wantDifferentName => '다른 이름으로 부르시겠습니까?';

  @override
  String get whatsYourName => '이름이 무엇인가요?';

  @override
  String get speakTranscribeSummarize => '말하기. 변환. 요약.';

  @override
  String get signInWithApple => 'Apple로 로그인';

  @override
  String get signInWithGoogle => 'Google로 로그인';

  @override
  String get byContinuingAgree => '계속하면 다음에 동의하는 것입니다 ';

  @override
  String get termsOfUse => '이용약관';

  @override
  String get omiYourAiCompanion => 'Omi – 당신의 AI 동반자';

  @override
  String get captureEveryMoment => '모든 순간을 기록하세요. AI 기반\n요약을 받으세요. 더 이상 메모할 필요가 없습니다.';

  @override
  String get appleWatchSetup => 'Apple Watch 설정';

  @override
  String get permissionRequestedExclaim => '권한 요청됨!';

  @override
  String get microphonePermission => '마이크 권한';

  @override
  String get permissionGrantedNow => '권한이 부여되었습니다! 이제:\n\n워치에서 Omi 앱을 열고 아래의 \"계속\"을 탭하세요';

  @override
  String get needMicrophonePermission =>
      '마이크 권한이 필요합니다.\n\n1. \"권한 부여\" 탭\n2. iPhone에서 허용\n3. 워치 앱이 닫힙니다\n4. 다시 열고 \"계속\" 탭';

  @override
  String get grantPermissionButton => '권한 부여';

  @override
  String get needHelp => '도움이 필요하신가요?';

  @override
  String get troubleshootingSteps =>
      '문제 해결:\n\n1. 워치에 Omi가 설치되어 있는지 확인\n2. 워치에서 Omi 앱 열기\n3. 권한 팝업 찾기\n4. 메시지가 나타나면 \"허용\" 탭\n5. 워치의 앱이 닫힙니다 - 다시 열기\n6. 돌아와서 iPhone에서 \"계속\" 탭';

  @override
  String get recordingStartedSuccessfully => '녹음이 성공적으로 시작되었습니다!';

  @override
  String get permissionNotGrantedYet => '아직 권한이 부여되지 않았습니다. 마이크 접근을 허용하고 워치에서 앱을 다시 열었는지 확인하세요.';

  @override
  String errorRequestingPermission(String error) {
    return '권한 요청 오류: $error';
  }

  @override
  String errorStartingRecording(String error) {
    return '녹음 시작 오류: $error';
  }

  @override
  String get selectPrimaryLanguage => '기본 언어 선택';

  @override
  String get languageBenefits => '더 정확한 변환과 맞춤형 경험을 위해 언어를 설정하세요';

  @override
  String get whatsYourPrimaryLanguage => '기본 언어가 무엇인가요?';

  @override
  String get selectYourLanguage => '언어를 선택하세요';

  @override
  String get personalGrowthJourney => '당신의 모든 말을 듣는 AI와 함께하는 개인 성장 여정.';

  @override
  String get actionItemsTitle => '할 일';

  @override
  String get actionItemsDescription => '탭하여 편집 • 길게 눌러 선택 • 스와이프하여 작업';

  @override
  String get tabToDo => '할 일';

  @override
  String get tabDone => '완료';

  @override
  String get tabOld => '이전';

  @override
  String get emptyTodoMessage => '🎉 모두 완료!\n대기 중인 작업 항목이 없습니다';

  @override
  String get emptyDoneMessage => '아직 완료된 항목이 없습니다';

  @override
  String get emptyOldMessage => '✅ 오래된 작업 없음';

  @override
  String get noItems => '항목 없음';

  @override
  String get actionItemMarkedIncomplete => '작업 항목이 미완료로 표시되었습니다';

  @override
  String get actionItemCompleted => '작업 항목이 완료되었습니다';

  @override
  String get deleteActionItemTitle => '작업 항목 삭제';

  @override
  String get deleteActionItemMessage => '이 작업 항목을 삭제하시겠습니까?';

  @override
  String get deleteSelectedItemsTitle => '선택한 항목 삭제';

  @override
  String deleteSelectedItemsMessage(int count, String s) {
    return '선택한 $count개의 작업 항목$s을(를) 삭제하시겠습니까?';
  }

  @override
  String actionItemDeletedResult(String description) {
    return '작업 항목 \"$description\"이(가) 삭제되었습니다';
  }

  @override
  String itemsDeletedResult(int count, String s) {
    return '$count개의 작업 항목$s이(가) 삭제되었습니다';
  }

  @override
  String get failedToDeleteItem => '작업 항목 삭제 실패';

  @override
  String get failedToDeleteItems => '항목 삭제 실패';

  @override
  String get failedToDeleteSomeItems => '일부 항목 삭제 실패';

  @override
  String get welcomeActionItemsTitle => '작업 항목 준비 완료';

  @override
  String get welcomeActionItemsDescription => 'AI가 대화에서 작업과 할 일을 자동으로 추출합니다. 생성되면 여기에 표시됩니다.';

  @override
  String get autoExtractionFeature => '대화에서 자동 추출';

  @override
  String get editSwipeFeature => '탭하여 편집, 스와이프하여 완료 또는 삭제';

  @override
  String itemsSelected(int count) {
    return '$count개 선택됨';
  }

  @override
  String get selectAll => '모두 선택';

  @override
  String get deleteSelected => '선택 항목 삭제';

  @override
  String searchMemories(int count) {
    return '$count개의 기억 검색';
  }

  @override
  String get memoryDeleted => '기억이 삭제되었습니다.';

  @override
  String get undo => '실행 취소';

  @override
  String get noMemoriesYet => '아직 기억이 없습니다';

  @override
  String get noAutoMemories => '아직 자동 추출된 기억이 없습니다';

  @override
  String get noManualMemories => '아직 수동 기억이 없습니다';

  @override
  String get noMemoriesInCategories => '이 카테고리에 기억이 없습니다';

  @override
  String get noMemoriesFound => '기억을 찾을 수 없습니다';

  @override
  String get addFirstMemory => '첫 번째 기억 추가';

  @override
  String get clearMemoryTitle => 'Omi의 기억 지우기';

  @override
  String get clearMemoryMessage => 'Omi의 기억을 지우시겠습니까? 이 작업은 되돌릴 수 없습니다.';

  @override
  String get clearMemoryButton => '기억 지우기';

  @override
  String get memoryClearedSuccess => 'Omi의 기억이 지워졌습니다';

  @override
  String get noMemoriesToDelete => '삭제할 기억이 없습니다';

  @override
  String get createMemoryTooltip => '새 기억 만들기';

  @override
  String get createActionItemTooltip => '새 작업 항목 만들기';

  @override
  String get memoryManagement => '기억 관리';

  @override
  String get filterMemories => '기억 필터링';

  @override
  String totalMemoriesCount(int count) {
    return '총 $count개의 기억이 있습니다';
  }

  @override
  String get publicMemories => '공개 기억';

  @override
  String get privateMemories => '비공개 기억';

  @override
  String get makeAllPrivate => '모든 기억을 비공개로 만들기';

  @override
  String get makeAllPublic => '모든 기억을 공개로 만들기';

  @override
  String get deleteAllMemories => '모든 기억 삭제';

  @override
  String get allMemoriesPrivateResult => '모든 기억이 이제 비공개입니다';

  @override
  String get allMemoriesPublicResult => '모든 기억이 이제 공개입니다';

  @override
  String get newMemory => '새 기억';

  @override
  String get editMemory => '기억 편집';

  @override
  String get memoryContentHint => '아이스크림 먹는 걸 좋아해요...';

  @override
  String get failedToSaveMemory => '저장에 실패했습니다. 연결을 확인하세요.';

  @override
  String get saveMemory => '기억 저장';

  @override
  String get retry => '다시 시도';

  @override
  String get createActionItem => '작업 항목 만들기';

  @override
  String get editActionItem => '작업 항목 편집';

  @override
  String get actionItemDescriptionHint => '무엇을 해야 하나요?';

  @override
  String get actionItemDescriptionEmpty => '작업 항목 설명은 비워둘 수 없습니다.';

  @override
  String get actionItemUpdated => '작업 항목이 업데이트되었습니다';

  @override
  String get failedToUpdateActionItem => '작업 항목 업데이트 실패';

  @override
  String get actionItemCreated => '작업 항목이 생성되었습니다';

  @override
  String get failedToCreateActionItem => '작업 항목 생성 실패';

  @override
  String get dueDate => '마감일';

  @override
  String get time => '시간';

  @override
  String get addDueDate => '마감일 추가';

  @override
  String get pressDoneToSave => '완료를 눌러 저장하세요';

  @override
  String get pressDoneToCreate => '완료를 눌러 생성하세요';

  @override
  String get filterAll => '모두';

  @override
  String get filterSystem => '본인 정보';

  @override
  String get filterInteresting => '인사이트';

  @override
  String get filterManual => '수동';

  @override
  String get completed => '완료됨';

  @override
  String get markComplete => '완료로 표시';

  @override
  String get actionItemDeleted => '작업 항목이 삭제되었습니다';

  @override
  String get failedToDeleteActionItem => '작업 항목 삭제 실패';

  @override
  String get deleteActionItemConfirmTitle => '작업 항목 삭제';

  @override
  String get deleteActionItemConfirmMessage => '이 작업 항목을 삭제하시겠습니까?';

  @override
  String get appLanguage => '앱 언어';

  @override
  String get appInterfaceSectionTitle => '앱 인터페이스';

  @override
  String get speechTranscriptionSectionTitle => '음성 및 전사';

  @override
  String get languageSettingsHelperText => '앱 언어는 메뉴와 버튼을 변경합니다. 음성 언어는 녹음이 전사되는 방식에 영향을 줍니다.';
}
