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
  String get copyTranscript => '대화록 복사';

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
  String get noInternetConnection => '인터넷 연결 없음';

  @override
  String get unableToDeleteConversation => '대화를 삭제할 수 없습니다';

  @override
  String get somethingWentWrong => '문제가 발생했습니다! 나중에 다시 시도해 주세요.';

  @override
  String get copyErrorMessage => '오류 메시지 복사';

  @override
  String get errorCopied => '오류 메시지가 클립보드에 복사되었습니다';

  @override
  String get remaining => '남음';

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
  String get askOmi => 'Omi에게 질문';

  @override
  String get done => '완료';

  @override
  String get disconnected => '연결 끊김';

  @override
  String get searching => '검색 중...';

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
  String get noConversationsYet => '아직 대화가 없습니다';

  @override
  String get noStarredConversations => '즐겨찾기한 대화가 없습니다';

  @override
  String get starConversationHint => '대화를 즐겨찾기하려면 대화를 열고 헤더의 별 아이콘을 탭하세요.';

  @override
  String get searchConversations => '대화 검색...';

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
  String get messageCopied => '✨ 메시지가 클립보드에 복사되었습니다';

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
  String get searchApps => '앱 검색...';

  @override
  String get myApps => '내 앱';

  @override
  String get installedApps => '설치된 앱';

  @override
  String get unableToFetchApps => '앱을 가져올 수 없습니다 :(\n\n인터넷 연결을 확인하고 다시 시도해 주세요.';

  @override
  String get aboutOmi => 'Omi 소개';

  @override
  String get privacyPolicy => '개인정보 처리방침';

  @override
  String get visitWebsite => '웹사이트 방문';

  @override
  String get helpOrInquiries => '도움말 또는 문의?';

  @override
  String get joinCommunity => '커뮤니티에 참여하세요!';

  @override
  String get membersAndCounting => '8000+명의 회원이 있으며 계속 증가하고 있습니다.';

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
  String get customVocabulary => '사용자 정의 어휘';

  @override
  String get identifyingOthers => '다른 사람 식별';

  @override
  String get paymentMethods => '결제 방법';

  @override
  String get conversationDisplay => '대화 표시';

  @override
  String get dataPrivacy => '데이터 개인정보 보호';

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
  String get manufacturer => '제조업체';

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
  String get deviceUnpairedMessage => '기기 페어링이 해제되었습니다. 설정 > Bluetooth로 이동하여 기기를 삭제하면 페어링 해제가 완료됩니다.';

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
  String get createKey => '키 생성';

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
  String get knowledgeGraphDeleted => '지식 그래프가 삭제되었습니다';

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
  String get urlCopied => 'URL 복사됨';

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
  String get intervalSeconds => '간격 (초)';

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
  String get memories => '추억';

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
  String get visibility => '공개 설정';

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
  String get noUpcomingMeetings => '예정된 회의 없음';

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
  String get saveChanges => '변경사항 저장';

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
  String get makePublic => '공개로 변경';

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
  String get dontShowAgain => '다시 표시하지 않음';

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
  String get speechProfileIntro => 'Omi가 당신의 목표와 목소리를 배워야 합니다. 나중에 수정할 수 있습니다.';

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
  String get personalGrowthJourney => '모든 말을 듣는 AI와 함께하는 개인 성장 여정.';

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
  String get deleteActionItemTitle => '실행 항목 삭제';

  @override
  String get deleteActionItemMessage => '이 실행 항목을 삭제하시겠습니까?';

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
  String get searchMemories => '추억 검색...';

  @override
  String get memoryDeleted => '기억이 삭제되었습니다.';

  @override
  String get undo => '실행 취소';

  @override
  String get noMemoriesYet => '🧠 아직 추억이 없습니다';

  @override
  String get noAutoMemories => '아직 자동 추출된 기억이 없습니다';

  @override
  String get noManualMemories => '아직 수동 기억이 없습니다';

  @override
  String get noMemoriesInCategories => '이 카테고리에 기억이 없습니다';

  @override
  String get noMemoriesFound => '🔍 추억을 찾을 수 없습니다';

  @override
  String get addFirstMemory => '첫 번째 기억 추가';

  @override
  String get clearMemoryTitle => 'Omi의 기억 지우기';

  @override
  String get clearMemoryMessage => 'Omi의 기억을 지우시겠습니까? 이 작업은 되돌릴 수 없습니다.';

  @override
  String get clearMemoryButton => '메모리 지우기';

  @override
  String get memoryClearedSuccess => 'Omi의 기억이 지워졌습니다';

  @override
  String get noMemoriesToDelete => '삭제할 메모리가 없습니다';

  @override
  String get createMemoryTooltip => '새 기억 만들기';

  @override
  String get createActionItemTooltip => '새 작업 항목 만들기';

  @override
  String get memoryManagement => '메모리 관리';

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
  String get deleteAllMemories => '모든 메모리 삭제';

  @override
  String get allMemoriesPrivateResult => '모든 기억이 이제 비공개입니다';

  @override
  String get allMemoriesPublicResult => '모든 기억이 이제 공개입니다';

  @override
  String get newMemory => '✨ 새 메모리';

  @override
  String get editMemory => '✏️ 메모리 편집';

  @override
  String get memoryContentHint => '아이스크림 먹는 걸 좋아해요...';

  @override
  String get failedToSaveMemory => '저장에 실패했습니다. 연결을 확인하세요.';

  @override
  String get saveMemory => '기억 저장';

  @override
  String get retry => '다시 시도';

  @override
  String get createActionItem => '작업 항목 생성';

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
  String get completed => '완료';

  @override
  String get markComplete => '완료로 표시';

  @override
  String get actionItemDeleted => '실행 항목이 삭제되었습니다';

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

  @override
  String get translationNotice => '번역 안내';

  @override
  String get translationNoticeMessage => 'Omi는 대화를 기본 언어로 번역합니다. 설정 → 프로필에서 언제든지 업데이트할 수 있습니다.';

  @override
  String get pleaseCheckInternetConnection => '인터넷 연결을 확인하고 다시 시도해주세요';

  @override
  String get pleaseSelectReason => '이유를 선택해주세요';

  @override
  String get tellUsMoreWhatWentWrong => '무엇이 잘못되었는지 자세히 알려주세요...';

  @override
  String get selectText => '텍스트 선택';

  @override
  String maximumGoalsAllowed(int count) {
    return '최대 $count개의 목표 허용';
  }

  @override
  String get conversationCannotBeMerged => '이 대화는 병합할 수 없습니다(잠김 또는 이미 병합 중)';

  @override
  String get pleaseEnterFolderName => '폴더 이름을 입력하세요';

  @override
  String get failedToCreateFolder => '폴더 생성 실패';

  @override
  String get failedToUpdateFolder => '폴더 업데이트 실패';

  @override
  String get folderName => '폴더 이름';

  @override
  String get descriptionOptional => '설명 (선택사항)';

  @override
  String get failedToDeleteFolder => '폴더 삭제 실패';

  @override
  String get editFolder => '폴더 편집';

  @override
  String get deleteFolder => '폴더 삭제';

  @override
  String get transcriptCopiedToClipboard => '스크립트가 클립보드에 복사되었습니다';

  @override
  String get summaryCopiedToClipboard => '요약이 클립보드에 복사되었습니다';

  @override
  String get conversationUrlCouldNotBeShared => '대화 URL을 공유할 수 없습니다.';

  @override
  String get urlCopiedToClipboard => 'URL이 클립보드에 복사되었습니다';

  @override
  String get exportTranscript => '스크립트 내보내기';

  @override
  String get exportSummary => '요약 내보내기';

  @override
  String get exportButton => '내보내기';

  @override
  String get actionItemsCopiedToClipboard => '작업 항목이 클립보드에 복사되었습니다';

  @override
  String get summarize => '요약';

  @override
  String get generateSummary => '요약 생성';

  @override
  String get conversationNotFoundOrDeleted => '대화를 찾을 수 없거나 삭제되었습니다';

  @override
  String get deleteMemory => '메모리 삭제';

  @override
  String get thisActionCannotBeUndone => '이 작업은 취소할 수 없습니다.';

  @override
  String memoriesCount(int count) {
    return '$count개의 추억';
  }

  @override
  String get noMemoriesInCategory => '이 카테고리에는 아직 메모리가 없습니다';

  @override
  String get addYourFirstMemory => '첫 추억 추가';

  @override
  String get firmwareDisconnectUsb => 'USB 연결 해제';

  @override
  String get firmwareUsbWarning => '업데이트 중 USB 연결은 기기를 손상시킬 수 있습니다.';

  @override
  String get firmwareBatteryAbove15 => '배터리 15% 이상';

  @override
  String get firmwareEnsureBattery => '기기 배터리가 15%인지 확인하세요.';

  @override
  String get firmwareStableConnection => '안정적인 연결';

  @override
  String get firmwareConnectWifi => 'WiFi 또는 모바일 데이터에 연결하세요.';

  @override
  String failedToStartUpdate(String error) {
    return '업데이트 시작 실패: $error';
  }

  @override
  String get beforeUpdateMakeSure => '업데이트 전에 확인하세요:';

  @override
  String get confirmed => '확인됨!';

  @override
  String get release => '놓기';

  @override
  String get slideToUpdate => '업데이트하려면 밀기';

  @override
  String copiedToClipboard(String title) {
    return '$title이(가) 클립보드에 복사되었습니다';
  }

  @override
  String get batteryLevel => '배터리 수준';

  @override
  String get productUpdate => '제품 업데이트';

  @override
  String get offline => '오프라인';

  @override
  String get available => '사용 가능';

  @override
  String get unpairDeviceDialogTitle => '기기 페어링 해제';

  @override
  String get unpairDeviceDialogMessage =>
      '기기 페어링을 해제하여 다른 전화기에 연결할 수 있도록 합니다. 설정 > Bluetooth로 이동하여 기기를 삭제하여 프로세스를 완료해야 합니다.';

  @override
  String get unpair => '페어링 해제';

  @override
  String get unpairAndForgetDevice => '페어링 해제 및 기기 삭제';

  @override
  String get unknownDevice => '알 수 없는 장치';

  @override
  String get unknown => '알 수 없음';

  @override
  String get productName => '제품명';

  @override
  String get serialNumber => '일련번호';

  @override
  String get connected => '연결됨';

  @override
  String get privacyPolicyTitle => '개인정보 보호정책';

  @override
  String get omiSttProvider => 'Omi';

  @override
  String labelCopied(String label) {
    return '$label 복사됨';
  }

  @override
  String get noApiKeysYet => '아직 API 키가 없습니다. 앱과 통합하려면 하나를 만드세요.';

  @override
  String get createKeyToGetStarted => '시작하려면 키를 만드세요';

  @override
  String get persona => '페르소나';

  @override
  String get configureYourAiPersona => 'AI 페르소나 구성';

  @override
  String get configureSttProvider => 'STT 제공업체 구성';

  @override
  String get setWhenConversationsAutoEnd => '대화가 자동 종료되는 시점 설정';

  @override
  String get importDataFromOtherSources => '다른 소스에서 데이터 가져오기';

  @override
  String get debugAndDiagnostics => '디버그 및 진단';

  @override
  String get autoDeletesAfter3Days => '3일 후 자동 삭제';

  @override
  String get helpsDiagnoseIssues => '문제 진단에 도움';

  @override
  String get exportStartedMessage => '내보내기가 시작되었습니다. 몇 초 정도 걸릴 수 있습니다...';

  @override
  String get exportConversationsToJson => '대화를 JSON 파일로 내보내기';

  @override
  String get knowledgeGraphDeletedSuccess => '지식 그래프가 성공적으로 삭제되었습니다';

  @override
  String failedToDeleteGraph(String error) {
    return '그래프 삭제 실패: $error';
  }

  @override
  String get clearAllNodesAndConnections => '모든 노드와 연결 지우기';

  @override
  String get addToClaudeDesktopConfig => 'claude_desktop_config.json에 추가';

  @override
  String get connectAiAssistantsToData => 'AI 어시스턴트를 데이터에 연결';

  @override
  String get useYourMcpApiKey => 'MCP API 키 사용';

  @override
  String get realTimeTranscript => '실시간 대화 내용';

  @override
  String get experimental => '실험적';

  @override
  String get transcriptionDiagnostics => '전사 진단';

  @override
  String get detailedDiagnosticMessages => '자세한 진단 메시지';

  @override
  String get autoCreateSpeakers => '발화자 자동 생성';

  @override
  String get autoCreateWhenNameDetected => '이름 감지 시 자동 생성';

  @override
  String get followUpQuestions => '후속 질문';

  @override
  String get suggestQuestionsAfterConversations => '대화 후 질문 제안';

  @override
  String get goalTracker => '목표 추적기';

  @override
  String get trackPersonalGoalsOnHomepage => '홈페이지에서 개인 목표 추적';

  @override
  String get dailyReflection => '일일 성찰';

  @override
  String get get9PmReminderToReflect => '오후 9시에 하루를 되돌아보는 알림 받기';

  @override
  String get actionItemDescriptionCannotBeEmpty => '실행 항목 설명은 비워둘 수 없습니다';

  @override
  String get saved => '저장됨';

  @override
  String get overdue => '기한 초과';

  @override
  String get failedToUpdateDueDate => '마감일 업데이트 실패';

  @override
  String get markIncomplete => '미완료로 표시';

  @override
  String get editDueDate => '마감일 편집';

  @override
  String get setDueDate => '마감일 설정';

  @override
  String get clearDueDate => '마감일 지우기';

  @override
  String get failedToClearDueDate => '마감일 지우기 실패';

  @override
  String get mondayAbbr => '월';

  @override
  String get tuesdayAbbr => '화';

  @override
  String get wednesdayAbbr => '수';

  @override
  String get thursdayAbbr => '목';

  @override
  String get fridayAbbr => '금';

  @override
  String get saturdayAbbr => '토';

  @override
  String get sundayAbbr => '일';

  @override
  String get howDoesItWork => '어떻게 작동하나요?';

  @override
  String get sdCardSyncDescription => 'SD 카드 동기화는 SD 카드에서 앱으로 추억을 가져옵니다';

  @override
  String get checksForAudioFiles => 'SD 카드에서 오디오 파일 확인';

  @override
  String get omiSyncsAudioFiles => 'Omi는 그런 다음 오디오 파일을 서버와 동기화합니다';

  @override
  String get serverProcessesAudio => '서버가 오디오 파일을 처리하고 추억을 만듭니다';

  @override
  String get youreAllSet => '준비 완료!';

  @override
  String get welcomeToOmiDescription => 'Omi에 오신 것을 환영합니다! AI 동반자가 대화, 작업 등을 도와드릴 준비가 되었습니다.';

  @override
  String get startUsingOmi => 'Omi 사용 시작';

  @override
  String get back => '뒤로';

  @override
  String get keyboardShortcuts => '키보드 단축키';

  @override
  String get toggleControlBar => '제어 표시줄 전환';

  @override
  String get pressKeys => '키를 누르세요...';

  @override
  String get cmdRequired => '⌘ 필요';

  @override
  String get invalidKey => '잘못된 키';

  @override
  String get space => '스페이스';

  @override
  String get search => '검색';

  @override
  String get searchPlaceholder => '검색...';

  @override
  String get untitledConversation => '제목 없는 대화';

  @override
  String countRemaining(String count) {
    return '$count 남음';
  }

  @override
  String get addGoal => '목표 추가';

  @override
  String get editGoal => '목표 편집';

  @override
  String get icon => '아이콘';

  @override
  String get goalTitle => '목표 제목';

  @override
  String get current => '현재';

  @override
  String get target => '목표';

  @override
  String get saveGoal => '저장';

  @override
  String get goals => '목표';

  @override
  String get tapToAddGoal => '탭하여 목표 추가';

  @override
  String welcomeBack(String name) {
    return '환영합니다, $name님';
  }

  @override
  String get yourConversations => '대화 내역';

  @override
  String get reviewAndManageConversations => '녹음된 대화를 검토하고 관리하세요';

  @override
  String get startCapturingConversations => 'Omi 장치로 대화를 캡처하여 여기에서 보세요.';

  @override
  String get useMobileAppToCapture => '모바일 앱을 사용하여 오디오를 캡처하세요';

  @override
  String get conversationsProcessedAutomatically => '대화는 자동으로 처리됩니다';

  @override
  String get getInsightsInstantly => '즉시 인사이트와 요약을 얻으세요';

  @override
  String get showAll => '모두 표시 →';

  @override
  String get noTasksForToday => '오늘의 작업이 없습니다.\\nOmi에게 더 많은 작업을 요청하거나 수동으로 생성하세요.';

  @override
  String get dailyScore => '일일 점수';

  @override
  String get dailyScoreDescription => '실행에 더 잘 집중할 수 있도록 도와주는 점수입니다.';

  @override
  String get searchResults => '검색 결과';

  @override
  String get actionItems => '실행 항목';

  @override
  String get tasksToday => '오늘';

  @override
  String get tasksTomorrow => '내일';

  @override
  String get tasksNoDeadline => '마감일 없음';

  @override
  String get tasksLater => '나중에';

  @override
  String get loadingTasks => '작업 로드 중...';

  @override
  String get tasks => '작업';

  @override
  String get swipeTasksToIndent => '작업을 스와이프하여 들여쓰기, 카테고리 간 드래그';

  @override
  String get create => '만들기';

  @override
  String get noTasksYet => '아직 작업이 없습니다';

  @override
  String get tasksFromConversationsWillAppear => '대화의 작업이 여기에 표시됩니다.\n수동으로 추가하려면 만들기를 클릭하세요.';

  @override
  String get monthJan => '1월';

  @override
  String get monthFeb => '2월';

  @override
  String get monthMar => '3월';

  @override
  String get monthApr => '4월';

  @override
  String get monthMay => '5월';

  @override
  String get monthJun => '6월';

  @override
  String get monthJul => '7월';

  @override
  String get monthAug => '8월';

  @override
  String get monthSep => '9월';

  @override
  String get monthOct => '10월';

  @override
  String get monthNov => '11월';

  @override
  String get monthDec => '12월';

  @override
  String get timePM => '오후';

  @override
  String get timeAM => '오전';

  @override
  String get actionItemUpdatedSuccessfully => '작업 항목이 성공적으로 업데이트되었습니다';

  @override
  String get actionItemCreatedSuccessfully => '작업 항목이 성공적으로 생성되었습니다';

  @override
  String get actionItemDeletedSuccessfully => '작업 항목이 성공적으로 삭제되었습니다';

  @override
  String get deleteActionItem => '작업 항목 삭제';

  @override
  String get deleteActionItemConfirmation => '이 작업 항목을 삭제하시겠습니까? 이 작업은 취소할 수 없습니다.';

  @override
  String get enterActionItemDescription => '작업 항목 설명 입력...';

  @override
  String get markAsCompleted => '완료로 표시';

  @override
  String get setDueDateAndTime => '마감일 및 시간 설정';

  @override
  String get reloadingApps => '앱 다시 로드 중...';

  @override
  String get loadingApps => '앱 로드 중...';

  @override
  String get browseInstallCreateApps => '앱 탐색, 설치 및 생성';

  @override
  String get all => '전체';

  @override
  String get open => '열기';

  @override
  String get install => '설치';

  @override
  String get noAppsAvailable => '사용 가능한 앱이 없습니다';

  @override
  String get unableToLoadApps => '앱을 로드할 수 없습니다';

  @override
  String get tryAdjustingSearchTermsOrFilters => '검색어나 필터를 조정해 보세요';

  @override
  String get checkBackLaterForNewApps => '나중에 새로운 앱을 확인하세요';

  @override
  String get pleaseCheckInternetConnectionAndTryAgain => '인터넷 연결을 확인하고 다시 시도하세요';

  @override
  String get createNewApp => '새 앱 만들기';

  @override
  String get buildSubmitCustomOmiApp => '사용자 정의 Omi 앱을 빌드하고 제출하세요';

  @override
  String get submittingYourApp => '앱을 제출하는 중...';

  @override
  String get preparingFormForYou => '양식을 준비하는 중...';

  @override
  String get appDetails => '앱 세부정보';

  @override
  String get paymentDetails => '결제 세부정보';

  @override
  String get previewAndScreenshots => '미리보기 및 스크린샷';

  @override
  String get appCapabilities => '앱 기능';

  @override
  String get aiPrompts => 'AI 프롬프트';

  @override
  String get chatPrompt => '채팅 프롬프트';

  @override
  String get chatPromptPlaceholder => '당신은 멋진 앱입니다. 사용자 질문에 응답하고 기분 좋게 만드는 것이 당신의 일입니다...';

  @override
  String get conversationPrompt => '대화 프롬프트';

  @override
  String get conversationPromptPlaceholder => '당신은 멋진 앱입니다. 대화의 전사 및 요약이 제공됩니다...';

  @override
  String get notificationScopes => '알림 범위';

  @override
  String get appPrivacyAndTerms => '앱 개인정보 보호 및 약관';

  @override
  String get makeMyAppPublic => '내 앱을 공개로 만들기';

  @override
  String get submitAppTermsAgreement => '이 앱을 제출함으로써 Omi AI의 서비스 약관 및 개인정보 보호정책에 동의합니다';

  @override
  String get submitApp => '앱 제출';

  @override
  String get needHelpGettingStarted => '시작하는 데 도움이 필요하신가요?';

  @override
  String get clickHereForAppBuildingGuides => '앱 빌드 가이드 및 문서를 보려면 여기를 클릭하세요';

  @override
  String get submitAppQuestion => '앱을 제출하시겠습니까?';

  @override
  String get submitAppPublicDescription => '앱이 검토되어 공개됩니다. 검토 중에도 즉시 사용을 시작할 수 있습니다!';

  @override
  String get submitAppPrivateDescription => '앱이 검토되어 비공개로 제공됩니다. 검토 중에도 즉시 사용을 시작할 수 있습니다!';

  @override
  String get startEarning => '수익 시작! 💰';

  @override
  String get connectStripeOrPayPal => 'Stripe 또는 PayPal을 연결하여 앱에 대한 결제를 받으세요.';

  @override
  String get connectNow => '지금 연결';

  @override
  String installsCount(String count) {
    return '$count+회 설치';
  }

  @override
  String get uninstallApp => '앱 제거';

  @override
  String get subscribe => '구독';

  @override
  String get dataAccessNotice => '데이터 접근 알림';

  @override
  String get dataAccessWarning => '이 앱은 귀하의 데이터에 접근합니다. Omi AI는 이 앱이 귀하의 데이터를 사용, 수정 또는 삭제하는 방법에 대해 책임지지 않습니다';

  @override
  String get installApp => '앱 설치';

  @override
  String get betaTesterNotice => '귀하는 이 앱의 베타 테스터입니다. 아직 공개되지 않았습니다. 승인되면 공개됩니다.';

  @override
  String get appUnderReviewOwner => '귀하의 앱이 검토 중이며 귀하만 볼 수 있습니다. 승인되면 공개됩니다.';

  @override
  String get appRejectedNotice => '귀하의 앱이 거부되었습니다. 앱 세부정보를 업데이트하고 검토를 위해 다시 제출하세요.';

  @override
  String get setupSteps => '설정 단계';

  @override
  String get setupInstructions => '설정 지침';

  @override
  String get integrationInstructions => '통합 지침';

  @override
  String get preview => '미리보기';

  @override
  String get aboutTheApp => '앱 정보';

  @override
  String get aboutThePersona => '페르소나 정보';

  @override
  String get chatPersonality => '채팅 성격';

  @override
  String get ratingsAndReviews => '평점 및 리뷰';

  @override
  String get noRatings => '평점 없음';

  @override
  String ratingsCount(String count) {
    return '$count+개의 평점';
  }

  @override
  String get errorActivatingApp => '앱 활성화 오류';

  @override
  String get integrationSetupRequired => '이것이 통합 앱인 경우 설정이 완료되었는지 확인하세요.';

  @override
  String get installed => '설치됨';

  @override
  String get appIdLabel => '앱 ID';

  @override
  String get appNameLabel => '앱 이름';

  @override
  String get appNamePlaceholder => '나의 멋진 앱';

  @override
  String get pleaseEnterAppName => '앱 이름을 입력하세요';

  @override
  String get categoryLabel => '카테고리';

  @override
  String get selectCategory => '카테고리 선택';

  @override
  String get descriptionLabel => '설명';

  @override
  String get appDescriptionPlaceholder => '나의 멋진 앱은 놀라운 일을 하는 훌륭한 앱입니다. 최고의 앱입니다!';

  @override
  String get pleaseProvideValidDescription => '유효한 설명을 입력하세요';

  @override
  String get appPricingLabel => '앱 가격';

  @override
  String get noneSelected => '선택 안 함';

  @override
  String get appIdCopiedToClipboard => '앱 ID가 클립보드에 복사되었습니다';

  @override
  String get appCategoryModalTitle => '앱 카테고리';

  @override
  String get pricingFree => '무료';

  @override
  String get pricingPaid => '유료';

  @override
  String get loadingCapabilities => '기능 로드 중...';

  @override
  String get filterInstalled => '설치됨';

  @override
  String get filterMyApps => '내 앱';

  @override
  String get clearSelection => '선택 해제';

  @override
  String get filterCategory => '카테고리';

  @override
  String get rating4PlusStars => '4+별';

  @override
  String get rating3PlusStars => '3+별';

  @override
  String get rating2PlusStars => '2+별';

  @override
  String get rating1PlusStars => '1+별';

  @override
  String get filterRating => '평점';

  @override
  String get filterCapabilities => '기능';

  @override
  String get noNotificationScopesAvailable => '사용 가능한 알림 범위 없음';

  @override
  String get popularApps => '인기 앱';

  @override
  String get pleaseProvidePrompt => '프롬프트를 입력하세요';

  @override
  String chatWithAppName(String appName) {
    return '$appName와 채팅';
  }

  @override
  String get defaultAiAssistant => '기본 AI 어시스턴트';

  @override
  String get readyToChat => '✨ 채팅 준비 완료!';

  @override
  String get connectionNeeded => '🌐 연결 필요';

  @override
  String get startConversation => '대화를 시작하고 마법을 시작하세요';

  @override
  String get checkInternetConnection => '인터넷 연결을 확인하세요';

  @override
  String get wasThisHelpful => '도움이 되었나요?';

  @override
  String get thankYouForFeedback => '피드백 감사합니다!';

  @override
  String get maxFilesUploadError => '한 번에 4개의 파일만 업로드할 수 있습니다';

  @override
  String get attachedFiles => '📎 첨부 파일';

  @override
  String get takePhoto => '사진 찍기';

  @override
  String get captureWithCamera => '카메라로 촬영';

  @override
  String get selectImages => '이미지 선택';

  @override
  String get chooseFromGallery => '갤러리에서 선택';

  @override
  String get selectFile => '파일 선택';

  @override
  String get chooseAnyFileType => '모든 파일 유형 선택';

  @override
  String get cannotReportOwnMessages => '자신의 메시지는 신고할 수 없습니다';

  @override
  String get messageReportedSuccessfully => '✅ 메시지가 성공적으로 신고되었습니다';

  @override
  String get confirmReportMessage => '이 메시지를 신고하시겠습니까?';

  @override
  String get selectChatAssistant => '채팅 어시스턴트 선택';

  @override
  String get enableMoreApps => '더 많은 앱 활성화';

  @override
  String get chatCleared => '채팅이 삭제되었습니다';

  @override
  String get clearChatTitle => '채팅 삭제?';

  @override
  String get confirmClearChat => '채팅을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.';

  @override
  String get copy => '복사';

  @override
  String get share => '공유';

  @override
  String get report => '신고';

  @override
  String get microphonePermissionRequired => '음성 녹음을 위해 마이크 권한이 필요합니다.';

  @override
  String get microphonePermissionDenied => '마이크 권한이 거부되었습니다. 시스템 환경설정 > 개인정보 보호 및 보안 > 마이크에서 권한을 부여하세요.';

  @override
  String failedToCheckMicrophonePermission(String error) {
    return '마이크 권한 확인 실패: $error';
  }

  @override
  String get failedToTranscribeAudio => '오디오 텍스트 변환 실패';

  @override
  String get transcribing => '텍스트 변환 중...';

  @override
  String get transcriptionFailed => '텍스트 변환 실패';

  @override
  String get discardedConversation => '폐기된 대화';

  @override
  String get at => '시각';

  @override
  String get from => '부터';

  @override
  String get copied => '복사됨!';

  @override
  String get copyLink => '링크 복사';

  @override
  String get hideTranscript => '텍스트 숨기기';

  @override
  String get viewTranscript => '텍스트 보기';

  @override
  String get conversationDetails => '대화 세부정보';

  @override
  String get transcript => '텍스트';

  @override
  String segmentsCount(int count) {
    return '$count개 세그먼트';
  }

  @override
  String get noTranscriptAvailable => '사용 가능한 텍스트가 없습니다';

  @override
  String get noTranscriptMessage => '이 대화에는 텍스트가 없습니다.';

  @override
  String get conversationUrlCouldNotBeGenerated => '대화 URL을 생성할 수 없습니다.';

  @override
  String get failedToGenerateConversationLink => '대화 링크 생성 실패';

  @override
  String get failedToGenerateShareLink => '공유 링크 생성 실패';

  @override
  String get reloadingConversations => '대화 다시 로드 중...';

  @override
  String get user => '사용자';

  @override
  String get starred => '즐겨찾기';

  @override
  String get date => '날짜';

  @override
  String get noResultsFound => '결과를 찾을 수 없습니다';

  @override
  String get tryAdjustingSearchTerms => '검색어를 조정해 보세요';

  @override
  String get starConversationsToFindQuickly => '대화를 즐겨찾기에 추가하면 여기에서 빠르게 찾을 수 있습니다';

  @override
  String noConversationsOnDate(String date) {
    return '$date에 대화가 없습니다';
  }

  @override
  String get trySelectingDifferentDate => '다른 날짜를 선택해 보세요';

  @override
  String get conversations => '대화';

  @override
  String get chat => '채팅';

  @override
  String get actions => '액션';

  @override
  String get syncAvailable => '동기화 가능';

  @override
  String get referAFriend => '친구 추천';

  @override
  String get help => '도움말';

  @override
  String get pro => 'Pro';

  @override
  String get upgradeToPro => 'Pro로 업그레이드';

  @override
  String get getOmiDevice => 'Omi 기기 받기';

  @override
  String get wearableAiCompanion => '웨어러블 AI 컴패니언';

  @override
  String get loadingMemories => '추억 로드 중...';

  @override
  String get allMemories => '모든 추억';

  @override
  String get aboutYou => '당신에 대해';

  @override
  String get manual => '수동';

  @override
  String get loadingYourMemories => '추억을 로드하는 중...';

  @override
  String get createYourFirstMemory => '첫 추억을 만들어 시작하세요';

  @override
  String get tryAdjustingFilter => '검색어나 필터를 조정해 보세요';

  @override
  String get whatWouldYouLikeToRemember => '무엇을 기억하고 싶으세요?';

  @override
  String get category => '카테고리';

  @override
  String get public => '공개';

  @override
  String get failedToSaveCheckConnection => '저장 실패. 연결을 확인하세요.';

  @override
  String get createMemory => '메모리 만들기';

  @override
  String get deleteMemoryConfirmation => '이 메모리를 삭제하시겠습니까? 이 작업은 취소할 수 없습니다.';

  @override
  String get makePrivate => '비공개로 변경';

  @override
  String get organizeAndControlMemories => '메모리를 정리하고 관리하세요';

  @override
  String get total => '전체';

  @override
  String get makeAllMemoriesPrivate => '모든 메모리를 비공개로 설정';

  @override
  String get setAllMemoriesToPrivate => '모든 메모리를 비공개로 설정';

  @override
  String get makeAllMemoriesPublic => '모든 메모리를 공개로 설정';

  @override
  String get setAllMemoriesToPublic => '모든 메모리를 공개로 설정';

  @override
  String get permanentlyRemoveAllMemories => 'Omi에서 모든 메모리를 영구적으로 제거';

  @override
  String get allMemoriesAreNowPrivate => '모든 메모리가 비공개로 설정되었습니다';

  @override
  String get allMemoriesAreNowPublic => '모든 메모리가 공개로 설정되었습니다';

  @override
  String get clearOmisMemory => 'Omi의 메모리 지우기';

  @override
  String clearMemoryConfirmation(int count) {
    return 'Omi의 메모리를 지우시겠습니까? 이 작업은 취소할 수 없으며 모든 $count개의 메모리를 영구적으로 삭제합니다.';
  }

  @override
  String get omisMemoryCleared => '당신에 대한 Omi의 메모리가 지워졌습니다';

  @override
  String get welcomeToOmi => 'Omi에 오신 것을 환영합니다';

  @override
  String get continueWithApple => 'Apple로 계속하기';

  @override
  String get continueWithGoogle => 'Google로 계속하기';

  @override
  String get byContinuingYouAgree => '계속하면 ';

  @override
  String get termsOfService => '서비스 약관';

  @override
  String get and => ' 및 ';

  @override
  String get dataAndPrivacy => '데이터 및 개인정보';

  @override
  String get secureAuthViaAppleId => 'Apple ID를 통한 안전한 인증';

  @override
  String get secureAuthViaGoogleAccount => 'Google 계정을 통한 안전한 인증';

  @override
  String get whatWeCollect => '수집하는 정보';

  @override
  String get dataCollectionMessage => '계속하면 대화, 녹음 및 개인 정보가 AI 기반 인사이트를 제공하고 모든 앱 기능을 활성화하기 위해 서버에 안전하게 저장됩니다.';

  @override
  String get dataProtection => '데이터 보호';

  @override
  String get yourDataIsProtected => '귀하의 데이터는 보호되며 ';

  @override
  String get pleaseSelectYourPrimaryLanguage => '기본 언어를 선택하세요';

  @override
  String get chooseYourLanguage => '언어를 선택하세요';

  @override
  String get selectPreferredLanguageForBestExperience => '최고의 Omi 경험을 위해 선호하는 언어를 선택하세요';

  @override
  String get searchLanguages => '언어 검색...';

  @override
  String get selectALanguage => '언어 선택';

  @override
  String get tryDifferentSearchTerm => '다른 검색어를 시도해보세요';

  @override
  String get pleaseEnterYourName => '이름을 입력하세요';

  @override
  String get nameMustBeAtLeast2Characters => '이름은 최소 2자 이상이어야 합니다';

  @override
  String get tellUsHowYouWouldLikeToBeAddressed => '어떻게 불리기를 원하시는지 알려주세요. 이는 Omi 경험을 개인화하는 데 도움이 됩니다.';

  @override
  String charactersCount(int count) {
    return '$count자';
  }

  @override
  String get enableFeaturesForBestExperience => '기기에서 최고의 Omi 경험을 위해 기능을 활성화하세요.';

  @override
  String get microphoneAccess => '마이크 액세스';

  @override
  String get recordAudioConversations => '오디오 대화 녹음';

  @override
  String get microphoneAccessDescription => 'Omi는 대화를 녹음하고 전사를 제공하기 위해 마이크 액세스가 필요합니다.';

  @override
  String get screenRecording => '화면 녹화';

  @override
  String get captureSystemAudioFromMeetings => '회의에서 시스템 오디오 캡처';

  @override
  String get screenRecordingDescription => 'Omi는 브라우저 기반 회의에서 시스템 오디오를 캡처하기 위해 화면 녹화 권한이 필요합니다.';

  @override
  String get accessibility => '접근성';

  @override
  String get detectBrowserBasedMeetings => '브라우저 기반 회의 감지';

  @override
  String get accessibilityDescription => 'Omi는 브라우저에서 Zoom, Meet 또는 Teams 회의에 참여할 때를 감지하기 위해 접근성 권한이 필요합니다.';

  @override
  String get pleaseWait => '잠시만 기다려 주세요...';

  @override
  String get joinTheCommunity => '커뮤니티에 참여하세요!';

  @override
  String get loadingProfile => '프로필 로딩 중...';

  @override
  String get profileSettings => '프로필 설정';

  @override
  String get noEmailSet => '이메일이 설정되지 않음';

  @override
  String get userIdCopiedToClipboard => '사용자 ID가 복사되었습니다';

  @override
  String get yourInformation => '귀하의 정보';

  @override
  String get setYourName => '이름 설정';

  @override
  String get changeYourName => '이름 변경';

  @override
  String get manageYourOmiPersona => 'Omi 페르소나 관리';

  @override
  String get voiceAndPeople => '음성 및 사람';

  @override
  String get teachOmiYourVoice => 'Omi에게 목소리 가르치기';

  @override
  String get tellOmiWhoSaidIt => '누가 말했는지 Omi에게 알려주기 🗣️';

  @override
  String get payment => '결제';

  @override
  String get addOrChangeYourPaymentMethod => '결제 방법 추가 또는 변경';

  @override
  String get preferences => '환경설정';

  @override
  String get helpImproveOmiBySharing => '익명화된 분석 데이터를 공유하여 Omi 개선 돕기';

  @override
  String get deleteAccount => '계정 삭제';

  @override
  String get deleteYourAccountAndAllData => '계정 및 모든 데이터 삭제';

  @override
  String get clearLogs => '로그 지우기';

  @override
  String get debugLogsCleared => '디버그 로그가 지워졌습니다';

  @override
  String get exportConversations => '대화 내보내기';

  @override
  String get exportAllConversationsToJson => '모든 대화를 JSON 파일로 내보냅니다.';

  @override
  String get conversationsExportStarted => '대화 내보내기가 시작되었습니다. 몇 초 정도 걸릴 수 있으니 기다려 주세요.';

  @override
  String get mcpDescription => 'Omi를 다른 애플리케이션과 연결하여 기억과 대화를 읽고, 검색하고, 관리합니다. 시작하려면 키를 생성하세요.';

  @override
  String get apiKeys => 'API 키';

  @override
  String errorLabel(String error) {
    return '오류: $error';
  }

  @override
  String get noApiKeysFound => 'API 키를 찾을 수 없습니다. 시작하려면 하나를 생성하세요.';

  @override
  String get advancedSettings => '고급 설정';

  @override
  String get triggersWhenNewConversationCreated => '새 대화가 생성되면 트리거됩니다.';

  @override
  String get triggersWhenNewTranscriptReceived => '새 녹취록을 받으면 트리거됩니다.';

  @override
  String get realtimeAudioBytes => '실시간 오디오 바이트';

  @override
  String get triggersWhenAudioBytesReceived => '오디오 바이트를 받으면 트리거됩니다.';

  @override
  String get everyXSeconds => 'x초마다';

  @override
  String get triggersWhenDaySummaryGenerated => '일일 요약이 생성되면 트리거됩니다.';

  @override
  String get tryLatestExperimentalFeatures => 'Omi 팀의 최신 실험적 기능을 사용해 보세요.';

  @override
  String get transcriptionServiceDiagnosticStatus => '녹취 서비스 진단 상태';

  @override
  String get enableDetailedDiagnosticMessages => '녹취 서비스의 상세한 진단 메시지 활성화';

  @override
  String get autoCreateAndTagNewSpeakers => '새 화자 자동 생성 및 태그 지정';

  @override
  String get automaticallyCreateNewPerson => '녹취록에서 이름이 감지되면 자동으로 새 사람을 생성합니다.';

  @override
  String get pilotFeatures => '파일럿 기능';

  @override
  String get pilotFeaturesDescription => '이러한 기능은 테스트이며 지원이 보장되지 않습니다.';

  @override
  String get suggestFollowUpQuestion => '후속 질문 제안';

  @override
  String get saveSettings => '설정 저장';

  @override
  String get syncingDeveloperSettings => '개발자 설정 동기화 중...';

  @override
  String get summary => '요약';

  @override
  String get auto => '자동';

  @override
  String get noSummaryForApp => '이 앱에 사용할 수 있는 요약이 없습니다. 더 나은 결과를 얻으려면 다른 앱을 시도하세요.';

  @override
  String get tryAnotherApp => '다른 앱 시도';

  @override
  String generatedBy(String appName) {
    return '$appName에서 생성';
  }

  @override
  String get overview => '개요';

  @override
  String get otherAppResults => '다른 앱 결과';

  @override
  String get unknownApp => '알 수 없는 앱';

  @override
  String get noSummaryAvailable => '사용 가능한 요약 없음';

  @override
  String get conversationNoSummaryYet => '이 대화에는 아직 요약이 없습니다.';

  @override
  String get chooseSummarizationApp => '요약 앱 선택';

  @override
  String setAsDefaultSummarizationApp(String appName) {
    return '$appName이(가) 기본 요약 앱으로 설정되었습니다';
  }

  @override
  String get letOmiChooseAutomatically => 'Omi가 자동으로 최적의 앱을 선택하도록 허용';

  @override
  String get deleteConversationConfirmation => '이 대화를 삭제하시겠습니까? 이 작업은 취소할 수 없습니다.';

  @override
  String get conversationDeleted => '대화가 삭제되었습니다';

  @override
  String get generatingLink => '링크 생성 중...';

  @override
  String get editConversation => '대화 편집';

  @override
  String get conversationLinkCopiedToClipboard => '대화 링크가 클립보드에 복사되었습니다';

  @override
  String get conversationTranscriptCopiedToClipboard => '대화록이 클립보드에 복사되었습니다';

  @override
  String get editConversationDialogTitle => '대화 편집';

  @override
  String get changeTheConversationTitle => '대화 제목 변경';

  @override
  String get conversationTitle => '대화 제목';

  @override
  String get enterConversationTitle => '대화 제목 입력...';

  @override
  String get conversationTitleUpdatedSuccessfully => '대화 제목이 성공적으로 업데이트되었습니다';

  @override
  String get failedToUpdateConversationTitle => '대화 제목 업데이트 실패';

  @override
  String get errorUpdatingConversationTitle => '대화 제목 업데이트 중 오류 발생';

  @override
  String get settingUp => '설정 중...';

  @override
  String get startYourFirstRecording => '첫 번째 녹음 시작';

  @override
  String get preparingSystemAudioCapture => '시스템 오디오 캡처 준비 중';

  @override
  String get clickTheButtonToCaptureAudio => '라이브 자막, AI 인사이트 및 자동 저장을 위해 오디오를 캡처하려면 버튼을 클릭하세요.';

  @override
  String get reconnecting => '재연결 중...';

  @override
  String get recordingPaused => '녹음 일시중지됨';

  @override
  String get recordingActive => '녹음 중';

  @override
  String get startRecording => '녹음 시작';

  @override
  String resumingInCountdown(String countdown) {
    return '$countdown초 후 재개...';
  }

  @override
  String get tapPlayToResume => '재개하려면 재생을 탭하세요';

  @override
  String get listeningForAudio => '오디오 듣는 중...';

  @override
  String get preparingAudioCapture => '오디오 캡처 준비 중';

  @override
  String get clickToBeginRecording => '녹음을 시작하려면 클릭하세요';

  @override
  String get translated => '번역됨';

  @override
  String get liveTranscript => '라이브 자막';

  @override
  String segmentsSingular(String count) {
    return '$count개 세그먼트';
  }

  @override
  String segmentsPlural(String count) {
    return '$count개 세그먼트';
  }

  @override
  String get startRecordingToSeeTranscript => '라이브 자막을 보려면 녹음을 시작하세요';

  @override
  String get paused => '일시중지됨';

  @override
  String get initializing => '초기화 중...';

  @override
  String get recording => '녹음 중';

  @override
  String microphoneChangedResumingIn(String countdown) {
    return '마이크가 변경되었습니다. $countdown초 후 재개';
  }

  @override
  String get clickPlayToResumeOrStop => '재개하려면 재생, 종료하려면 중지를 클릭하세요';

  @override
  String get settingUpSystemAudioCapture => '시스템 오디오 캡처 설정 중';

  @override
  String get capturingAudioAndGeneratingTranscript => '오디오 캡처 및 자막 생성 중';

  @override
  String get clickToBeginRecordingSystemAudio => '시스템 오디오 녹음을 시작하려면 클릭하세요';

  @override
  String get you => '나';

  @override
  String speakerWithId(String speakerId) {
    return '화자 $speakerId';
  }

  @override
  String get translatedByOmi => 'omi가 번역함';

  @override
  String get backToConversations => '대화로 돌아가기';

  @override
  String get systemAudio => '시스템';

  @override
  String get mic => '마이크';

  @override
  String audioInputSetTo(String deviceName) {
    return '오디오 입력이 $deviceName(으)로 설정됨';
  }

  @override
  String errorSwitchingAudioDevice(String error) {
    return '오디오 장치 전환 오류: $error';
  }

  @override
  String get selectAudioInput => '오디오 입력 선택';

  @override
  String get loadingDevices => '장치 로드 중...';

  @override
  String get settingsHeader => '설정';

  @override
  String get plansAndBilling => '플랜 및 결제';

  @override
  String get calendarIntegration => '캘린더 통합';

  @override
  String get dailySummary => '일일 요약';

  @override
  String get developer => '개발자';

  @override
  String get about => '정보';

  @override
  String get selectTime => '시간 선택';

  @override
  String get accountGroup => '계정';

  @override
  String get signOutQuestion => '로그아웃하시겠습니까?';

  @override
  String get signOutConfirmation => '정말 로그아웃하시겠습니까?';

  @override
  String get customVocabularyHeader => '사용자 정의 어휘';

  @override
  String get addWordsDescription => '전사 중에 Omi가 인식해야 하는 단어를 추가하세요.';

  @override
  String get enterWordsHint => '단어 입력 (쉼표로 구분)';

  @override
  String get dailySummaryHeader => '일일 요약';

  @override
  String get dailySummaryTitle => '일일 요약';

  @override
  String get dailySummaryDescription => '대화의 맞춤형 요약을 받으세요';

  @override
  String get deliveryTime => '전송 시간';

  @override
  String get deliveryTimeDescription => '일일 요약을 받을 시간';

  @override
  String get subscription => '구독';

  @override
  String get viewPlansAndUsage => '플랜 및 사용량 보기';

  @override
  String get viewPlansDescription => '구독을 관리하고 사용 통계를 확인하세요';

  @override
  String get addOrChangePaymentMethod => '결제 방법 추가 또는 변경';

  @override
  String get displayOptions => '표시 옵션';

  @override
  String get showMeetingsInMenuBar => '메뉴 바에 회의 표시';

  @override
  String get displayUpcomingMeetingsDescription => '메뉴 바에 예정된 회의 표시';

  @override
  String get showEventsWithoutParticipants => '참가자가 없는 이벤트 표시';

  @override
  String get includePersonalEventsDescription => '참석자가 없는 개인 이벤트 포함';

  @override
  String get upcomingMeetings => '예정된 회의';

  @override
  String get checkingNext7Days => '다음 7일 확인 중';

  @override
  String get shortcuts => '단축키';

  @override
  String get shortcutChangeInstruction => '단축키를 클릭하여 변경합니다. Escape를 눌러 취소합니다.';

  @override
  String get configurePersonaDescription => 'AI 페르소나 구성';

  @override
  String get configureSTTProvider => 'STT 제공업체 구성';

  @override
  String get setConversationEndDescription => '대화가 자동으로 종료되는 시기 설정';

  @override
  String get importDataDescription => '다른 소스에서 데이터 가져오기';

  @override
  String get exportConversationsDescription => '대화를 JSON으로 내보내기';

  @override
  String get exportingConversations => '대화 내보내는 중...';

  @override
  String get clearNodesDescription => '모든 노드와 연결 지우기';

  @override
  String get deleteKnowledgeGraphQuestion => '지식 그래프를 삭제하시겠습니까?';

  @override
  String get deleteKnowledgeGraphWarning => '파생된 모든 지식 그래프 데이터가 삭제됩니다. 원래 메모리는 안전하게 유지됩니다.';

  @override
  String get connectOmiWithAI => 'Omi를 AI 어시스턴트와 연결';

  @override
  String get noAPIKeys => 'API 키가 없습니다. 시작하려면 하나를 만드세요.';

  @override
  String get autoCreateWhenDetected => '이름이 감지되면 자동 생성';

  @override
  String get trackPersonalGoals => '홈페이지에서 개인 목표 추적';

  @override
  String get dailyReflectionDescription => '오후 9시에 하루를 돌아보는 알림';

  @override
  String get endpointURL => '엔드포인트 URL';

  @override
  String get links => '링크';

  @override
  String get discordMemberCount => 'Discord에 8000명 이상의 회원';

  @override
  String get userInformation => '사용자 정보';

  @override
  String get capabilities => '기능';

  @override
  String get previewScreenshots => '스크린샷 미리보기';

  @override
  String get holdOnPreparingForm => '잠시만요, 양식을 준비하고 있습니다';

  @override
  String get bySubmittingYouAgreeToOmi => '제출하면 Omi ';

  @override
  String get termsAndPrivacyPolicy => '이용약관 및 개인정보 처리방침';

  @override
  String get helpsDiagnoseIssuesAutoDeletes => '문제 진단에 도움이 됩니다. 3일 후 자동 삭제됩니다.';

  @override
  String get manageYourApp => '앱 관리';

  @override
  String get updatingYourApp => '앱 업데이트 중';

  @override
  String get fetchingYourAppDetails => '앱 세부정보 가져오는 중';

  @override
  String get updateAppQuestion => '앱을 업데이트하시겠습니까?';

  @override
  String get updateAppConfirmation => '앱을 업데이트하시겠습니까? 변경 사항은 팀 검토 후 반영됩니다.';

  @override
  String get updateApp => '앱 업데이트';

  @override
  String get createAndSubmitNewApp => '새 앱 만들기 및 제출';

  @override
  String appsCount(String count) {
    return '앱 ($count)';
  }

  @override
  String privateAppsCount(String count) {
    return '비공개 앱 ($count)';
  }

  @override
  String publicAppsCount(String count) {
    return '공개 앱 ($count)';
  }

  @override
  String get newVersionAvailable => '새 버전 사용 가능  🎉';

  @override
  String get no => '아니요';

  @override
  String get subscriptionCancelledSuccessfully => '구독이 성공적으로 취소되었습니다. 현재 결제 기간이 끝날 때까지 유효합니다.';

  @override
  String get failedToCancelSubscription => '구독 취소에 실패했습니다. 다시 시도해 주세요.';

  @override
  String get invalidPaymentUrl => '잘못된 결제 URL';

  @override
  String get permissionsAndTriggers => '권한 및 트리거';

  @override
  String get chatFeatures => '채팅 기능';

  @override
  String get uninstall => '제거';

  @override
  String get installs => '설치 수';

  @override
  String get priceLabel => '가격';

  @override
  String get updatedLabel => '업데이트됨';

  @override
  String get createdLabel => '생성됨';

  @override
  String get featuredLabel => '추천';

  @override
  String get cancelSubscriptionQuestion => '구독을 취소하시겠습니까?';

  @override
  String get cancelSubscriptionConfirmation => '구독을 취소하시겠습니까? 현재 결제 기간이 끝날 때까지 계속 이용할 수 있습니다.';

  @override
  String get cancelSubscriptionButton => '구독 취소';

  @override
  String get cancelling => '취소 중...';

  @override
  String get betaTesterMessage => '이 앱의 베타 테스터입니다. 아직 공개되지 않았습니다. 승인 후 공개됩니다.';

  @override
  String get appUnderReviewMessage => '앱이 검토 중이며 본인에게만 표시됩니다. 승인 후 공개됩니다.';

  @override
  String get appRejectedMessage => '앱이 거부되었습니다. 세부 정보를 업데이트하고 다시 제출해 주세요.';

  @override
  String get invalidIntegrationUrl => '잘못된 통합 URL';

  @override
  String get tapToComplete => '탭하여 완료';

  @override
  String get invalidSetupInstructionsUrl => '잘못된 설정 안내 URL';

  @override
  String get pushToTalk => '말하려면 누르기';

  @override
  String get summaryPrompt => '요약 프롬프트';

  @override
  String get pleaseSelectARating => '평점을 선택해 주세요';

  @override
  String get reviewAddedSuccessfully => '리뷰가 성공적으로 추가되었습니다 🚀';

  @override
  String get reviewUpdatedSuccessfully => '리뷰가 성공적으로 업데이트되었습니다 🚀';

  @override
  String get failedToSubmitReview => '리뷰 제출에 실패했습니다. 다시 시도해 주세요.';

  @override
  String get addYourReview => '리뷰 추가';

  @override
  String get editYourReview => '리뷰 수정';

  @override
  String get writeAReviewOptional => '리뷰 작성 (선택사항)';

  @override
  String get submitReview => '리뷰 제출';

  @override
  String get updateReview => '리뷰 업데이트';

  @override
  String get yourReview => '내 리뷰';

  @override
  String get anonymousUser => '익명 사용자';

  @override
  String get issueActivatingApp => '이 앱을 활성화하는 데 문제가 발생했습니다. 다시 시도해 주세요.';

  @override
  String get dataAccessNoticeDescription => '이 앱은 귀하의 데이터에 액세스합니다. Omi AI는 이 앱에 의한 데이터 사용, 수정 또는 삭제에 대해 책임지지 않습니다';

  @override
  String get copyUrl => 'URL 복사';

  @override
  String get txtFormat => 'TXT';

  @override
  String get pdfFormat => 'PDF';

  @override
  String get weekdayMon => '월';

  @override
  String get weekdayTue => '화';

  @override
  String get weekdayWed => '수';

  @override
  String get weekdayThu => '목';

  @override
  String get weekdayFri => '금';

  @override
  String get weekdaySat => '토';

  @override
  String get weekdaySun => '일';

  @override
  String serviceIntegrationComingSoon(String serviceName) {
    return '$serviceName 연동 곧 출시 예정';
  }

  @override
  String alreadyExportedTo(String platform) {
    return '$platform에 이미 내보냄';
  }

  @override
  String get anotherPlatform => '다른 플랫폼';

  @override
  String pleaseAuthenticateWithService(String serviceName) {
    return '설정 > 작업 통합에서 $serviceName으로 인증해 주세요';
  }

  @override
  String addingToService(String serviceName) {
    return '$serviceName에 추가 중...';
  }

  @override
  String addedToService(String serviceName) {
    return '$serviceName에 추가됨';
  }

  @override
  String failedToAddToService(String serviceName) {
    return '$serviceName에 추가 실패';
  }

  @override
  String get permissionDeniedForAppleReminders => 'Apple 미리 알림 권한이 거부됨';

  @override
  String failedToCreateApiKey(String error) {
    return '공급자 API 키 생성 실패: $error';
  }

  @override
  String get createAKey => '키 생성';

  @override
  String get apiKeyRevokedSuccessfully => 'API 키가 성공적으로 취소됨';

  @override
  String failedToRevokeApiKey(String error) {
    return 'API 키 취소 실패: $error';
  }

  @override
  String get omiApiKeys => 'Omi API 키';

  @override
  String get apiKeysDescription =>
      'API 키는 앱이 OMI 서버와 통신할 때 인증에 사용됩니다. 애플리케이션이 메모리를 생성하고 다른 OMI 서비스에 안전하게 접근할 수 있게 합니다.';

  @override
  String get aboutOmiApiKeys => 'Omi API 키 정보';

  @override
  String get yourNewKey => '새 키:';

  @override
  String get copyToClipboard => '클립보드에 복사';

  @override
  String get pleaseCopyKeyNow => '지금 복사하여 안전한 곳에 적어두세요. ';

  @override
  String get willNotSeeAgain => '다시 볼 수 없습니다.';

  @override
  String get revokeKey => '키 취소';

  @override
  String get revokeApiKeyQuestion => 'API 키를 취소하시겠습니까?';

  @override
  String get revokeApiKeyWarning => '이 작업은 취소할 수 없습니다. 이 키를 사용하는 애플리케이션은 더 이상 API에 접근할 수 없습니다.';

  @override
  String get revoke => '취소';

  @override
  String get whatWouldYouLikeToCreate => '무엇을 만들고 싶으신가요?';

  @override
  String get createAnApp => '앱 만들기';

  @override
  String get createAndShareYourApp => '앱을 만들고 공유하세요';

  @override
  String get createMyClone => '내 클론 만들기';

  @override
  String get createYourDigitalClone => '디지털 클론을 만드세요';

  @override
  String get itemApp => '앱';

  @override
  String get itemPersona => '페르소나';

  @override
  String keepItemPublic(String item) {
    return '$item을 공개로 유지';
  }

  @override
  String makeItemPublicQuestion(String item) {
    return '$item을 공개로 설정하시겠습니까?';
  }

  @override
  String makeItemPrivateQuestion(String item) {
    return '$item을 비공개로 설정하시겠습니까?';
  }

  @override
  String makeItemPublicExplanation(String item) {
    return '$item을 공개로 설정하면 모든 사람이 사용할 수 있습니다';
  }

  @override
  String makeItemPrivateExplanation(String item) {
    return '$item을 비공개로 설정하면 모든 사람에게 작동이 중지되고 본인만 볼 수 있습니다';
  }

  @override
  String get manageApp => '앱 관리';

  @override
  String get updatePersonaDetails => '페르소나 세부 정보 업데이트';

  @override
  String deleteItemTitle(String item) {
    return '$item 삭제';
  }

  @override
  String deleteItemQuestion(String item) {
    return '$item을 삭제하시겠습니까?';
  }

  @override
  String deleteItemConfirmation(String item) {
    return '이 $item을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.';
  }

  @override
  String get revokeKeyQuestion => '키를 취소하시겠습니까?';

  @override
  String revokeKeyConfirmation(String keyName) {
    return '\"$keyName\" 키를 취소하시겠습니까? 이 작업은 되돌릴 수 없습니다.';
  }

  @override
  String get createNewKey => '새 키 만들기';

  @override
  String get keyNameHint => '예: Claude Desktop';

  @override
  String get pleaseEnterAName => '이름을 입력하세요.';

  @override
  String failedToCreateKeyWithError(String error) {
    return '키 생성 실패: $error';
  }

  @override
  String get failedToCreateKeyTryAgain => '키 생성에 실패했습니다. 다시 시도해 주세요.';

  @override
  String get keyCreated => '키가 생성되었습니다';

  @override
  String get keyCreatedMessage => '새 키가 생성되었습니다. 지금 복사하세요. 다시 볼 수 없습니다.';

  @override
  String get keyWord => '키';

  @override
  String get externalAppAccess => '외부 앱 접근';

  @override
  String get externalAppAccessDescription => '다음 설치된 앱은 외부 통합이 있으며 대화 및 기억과 같은 데이터에 접근할 수 있습니다.';

  @override
  String get noExternalAppsHaveAccess => '외부 앱이 데이터에 접근할 수 없습니다.';

  @override
  String get maximumSecurityE2ee => '최대 보안 (E2EE)';

  @override
  String get e2eeDescription =>
      '엔드투엔드 암호화는 개인정보 보호의 최고 기준입니다. 활성화되면 데이터가 서버로 전송되기 전에 기기에서 암호화됩니다. 이는 Omi를 포함한 그 누구도 귀하의 콘텐츠에 접근할 수 없음을 의미합니다.';

  @override
  String get importantTradeoffs => '중요한 절충 사항:';

  @override
  String get e2eeTradeoff1 => '• 외부 앱 통합과 같은 일부 기능이 비활성화될 수 있습니다.';

  @override
  String get e2eeTradeoff2 => '• 비밀번호를 분실하면 데이터를 복구할 수 없습니다.';

  @override
  String get featureComingSoon => '이 기능은 곧 제공됩니다!';

  @override
  String get migrationInProgressMessage => '마이그레이션이 진행 중입니다. 완료될 때까지 보호 수준을 변경할 수 없습니다.';

  @override
  String get migrationFailed => '마이그레이션 실패';

  @override
  String migratingFromTo(String source, String target) {
    return '$source에서 $target으로 마이그레이션 중';
  }

  @override
  String objectsCount(String processed, String total) {
    return '$processed / $total 개체';
  }

  @override
  String get secureEncryption => '안전한 암호화';

  @override
  String get secureEncryptionDescription =>
      '귀하의 데이터는 Google Cloud에서 호스팅되는 당사 서버에서 귀하만의 고유한 키로 암호화됩니다. 이는 Omi 직원이나 Google을 포함한 누구도 데이터베이스에서 직접 귀하의 원시 콘텐츠에 접근할 수 없음을 의미합니다.';

  @override
  String get endToEndEncryption => '엔드투엔드 암호화';

  @override
  String get e2eeCardDescription => '최대 보안을 위해 활성화하면 본인만 데이터에 접근할 수 있습니다. 자세히 알아보려면 탭하세요.';

  @override
  String get dataAlwaysEncrypted => '레벨에 관계없이 데이터는 항상 저장 시 및 전송 중에 암호화됩니다.';

  @override
  String get readOnlyScope => '읽기 전용';

  @override
  String get fullAccessScope => '전체 액세스';

  @override
  String get readScope => '읽기';

  @override
  String get writeScope => '쓰기';

  @override
  String get apiKeyCreated => 'API 키가 생성되었습니다!';

  @override
  String get saveKeyWarning => '지금 이 키를 저장하세요! 다시 볼 수 없습니다.';

  @override
  String get yourApiKey => '귀하의 API 키';

  @override
  String get tapToCopy => '탭하여 복사';

  @override
  String get copyKey => '키 복사';

  @override
  String get createApiKey => 'API 키 생성';

  @override
  String get accessDataProgrammatically => '프로그래밍 방식으로 데이터 액세스';

  @override
  String get keyNameLabel => '키 이름';

  @override
  String get keyNamePlaceholder => '예: 내 앱 연동';

  @override
  String get permissionsLabel => '권한';

  @override
  String get permissionsInfoNote => 'R = 읽기, W = 쓰기. 선택하지 않으면 기본적으로 읽기 전용.';

  @override
  String get developerApi => '개발자 API';

  @override
  String get createAKeyToGetStarted => '시작하려면 키를 만드세요';

  @override
  String errorWithMessage(String error) {
    return '오류: $error';
  }

  @override
  String get omiTraining => 'Omi 훈련';

  @override
  String get trainingDataProgram => '훈련 데이터 프로그램';

  @override
  String get getOmiUnlimitedFree => '데이터를 제공하여 AI 모델 훈련에 기여하면 Omi Unlimited를 무료로 받으세요.';

  @override
  String get trainingDataBullets => '• 귀하의 데이터가 AI 모델 개선에 도움이 됩니다\n• 민감하지 않은 데이터만 공유됩니다\n• 완전히 투명한 프로세스';

  @override
  String get learnMoreAtOmiTraining => 'omi.me/training에서 자세히 알아보기';

  @override
  String get agreeToContributeData => 'AI 훈련을 위해 데이터를 제공하는 것에 대해 이해하고 동의합니다';

  @override
  String get submitRequest => '요청 제출';

  @override
  String get thankYouRequestUnderReview => '감사합니다! 요청이 검토 중입니다. 승인 후 알려드리겠습니다.';

  @override
  String planRemainsActiveUntil(String date) {
    return '플랜은 $date까지 활성 상태로 유지됩니다. 그 이후에는 무제한 기능에 대한 액세스 권한을 잃게 됩니다. 확실합니까?';
  }

  @override
  String get confirmCancellation => '취소 확인';

  @override
  String get keepMyPlan => '내 플랜 유지';

  @override
  String get subscriptionSetToCancel => '구독이 기간 종료 시 취소되도록 설정되었습니다.';

  @override
  String get switchedToOnDevice => '기기 내 전사로 전환됨';

  @override
  String get couldNotSwitchToFreePlan => '무료 플랜으로 전환할 수 없습니다. 다시 시도해 주세요.';

  @override
  String get couldNotLoadPlans => '사용 가능한 플랜을 로드할 수 없습니다. 다시 시도해 주세요.';

  @override
  String get selectedPlanNotAvailable => '선택한 플랜을 사용할 수 없습니다. 다시 시도해 주세요.';

  @override
  String get upgradeToAnnualPlan => '연간 플랜으로 업그레이드';

  @override
  String get importantBillingInfo => '중요한 결제 정보:';

  @override
  String get monthlyPlanContinues => '현재 월간 플랜은 결제 기간이 끝날 때까지 계속됩니다';

  @override
  String get paymentMethodCharged => '월간 플랜이 종료되면 기존 결제 수단으로 자동 청구됩니다';

  @override
  String get annualSubscriptionStarts => '12개월 연간 구독은 결제 후 자동으로 시작됩니다';

  @override
  String get thirteenMonthsCoverage => '총 13개월의 혜택을 받게 됩니다 (현재 월 + 연간 12개월)';

  @override
  String get confirmUpgrade => '업그레이드 확인';

  @override
  String get confirmPlanChange => '플랜 변경 확인';

  @override
  String get confirmAndProceed => '확인 및 진행';

  @override
  String get upgradeScheduled => '업그레이드 예정됨';

  @override
  String get changePlan => '플랜 변경';

  @override
  String get upgradeAlreadyScheduled => '연간 플랜으로의 업그레이드가 이미 예정되어 있습니다';

  @override
  String get youAreOnUnlimitedPlan => '현재 Unlimited 플랜을 사용 중입니다.';

  @override
  String get yourOmiUnleashed => '당신의 Omi, 해방되다. 무한한 가능성을 위해 Unlimited로.';

  @override
  String planEndedOn(String date) {
    return '플랜이 $date에 종료되었습니다.\\n지금 재구독하세요 - 새 청구 기간에 대해 즉시 청구됩니다.';
  }

  @override
  String planSetToCancelOn(String date) {
    return '플랜이 $date에 취소될 예정입니다.\\n혜택을 유지하려면 지금 재구독하세요 - $date까지 요금이 청구되지 않습니다.';
  }

  @override
  String get annualPlanStartsAutomatically => '월간 플랜이 종료되면 연간 플랜이 자동으로 시작됩니다.';

  @override
  String planRenewsOn(String date) {
    return '플랜이 $date에 갱신됩니다.';
  }

  @override
  String get unlimitedConversations => '무제한 대화';

  @override
  String get askOmiAnything => 'Omi에게 당신의 삶에 대해 무엇이든 물어보세요';

  @override
  String get unlockOmiInfiniteMemory => 'Omi의 무한 메모리 잠금 해제';

  @override
  String get youreOnAnnualPlan => '연간 플랜을 사용 중입니다';

  @override
  String get alreadyBestValuePlan => '이미 가장 가성비 좋은 플랜을 사용 중입니다. 변경이 필요하지 않습니다.';

  @override
  String get unableToLoadPlans => '플랜을 로드할 수 없습니다';

  @override
  String get checkConnectionTryAgain => '연결을 확인하고 다시 시도해 주세요';

  @override
  String get useFreePlan => '무료 플랜 사용';

  @override
  String get continueText => '계속';

  @override
  String get resubscribe => '재구독';

  @override
  String get couldNotOpenPaymentSettings => '결제 설정을 열 수 없습니다. 다시 시도해 주세요.';

  @override
  String get managePaymentMethod => '결제 수단 관리';

  @override
  String get cancelSubscription => '구독 취소';

  @override
  String endsOnDate(String date) {
    return '$date에 종료';
  }

  @override
  String get active => '활성';

  @override
  String get freePlan => '무료 플랜';

  @override
  String get configure => '구성';

  @override
  String get privacyInformation => '개인정보 안내';

  @override
  String get yourPrivacyMattersToUs => '당신의 개인정보는 우리에게 중요합니다';

  @override
  String get privacyIntroText =>
      'Omi에서는 귀하의 개인정보를 매우 중요하게 생각합니다. 수집하는 데이터와 사용 방법에 대해 투명하게 알려드리고자 합니다. 알아야 할 사항은 다음과 같습니다:';

  @override
  String get whatWeTrack => '추적 항목';

  @override
  String get anonymityAndPrivacy => '익명성과 개인정보';

  @override
  String get optInAndOptOutOptions => '수신 동의 및 거부 옵션';

  @override
  String get ourCommitment => '우리의 약속';

  @override
  String get commitmentText => '우리는 수집한 데이터를 Omi를 더 나은 제품으로 만드는 데만 사용할 것을 약속합니다. 귀하의 개인정보와 신뢰는 우리에게 가장 중요합니다.';

  @override
  String get thankYouText => 'Omi의 소중한 사용자가 되어 주셔서 감사합니다. 질문이나 우려 사항이 있으시면 team@basedhardware.com으로 연락해 주세요.';

  @override
  String get wifiSyncSettings => 'WiFi 동기화 설정';

  @override
  String get enterHotspotCredentials => '휴대폰 핫스팟 자격 증명 입력';

  @override
  String get wifiSyncUsesHotspot => 'WiFi 동기화는 휴대폰을 핫스팟으로 사용합니다. 설정 > 개인용 핫스팟에서 이름과 비밀번호를 찾으세요.';

  @override
  String get hotspotNameSsid => '핫스팟 이름 (SSID)';

  @override
  String get exampleIphoneHotspot => '예: iPhone 핫스팟';

  @override
  String get password => '비밀번호';

  @override
  String get enterHotspotPassword => '핫스팟 비밀번호 입력';

  @override
  String get saveCredentials => '자격 증명 저장';

  @override
  String get clearCredentials => '자격 증명 지우기';

  @override
  String get pleaseEnterHotspotName => '핫스팟 이름을 입력하세요';

  @override
  String get wifiCredentialsSaved => 'WiFi 자격 증명이 저장됨';

  @override
  String get wifiCredentialsCleared => 'WiFi 자격 증명이 지워짐';

  @override
  String summaryGeneratedForDate(String date) {
    return '$date 요약이 생성되었습니다';
  }

  @override
  String get failedToGenerateSummaryCheckConversations => '요약 생성에 실패했습니다. 해당 날짜의 대화가 있는지 확인하세요.';

  @override
  String get summaryNotFound => '요약을 찾을 수 없습니다';

  @override
  String get yourDaysJourney => '오늘의 여정';

  @override
  String get highlights => '하이라이트';

  @override
  String get unresolvedQuestions => '미해결 질문';

  @override
  String get decisions => '결정';

  @override
  String get learnings => '배움';

  @override
  String get autoDeletesAfterThreeDays => '3일 후 자동 삭제됩니다.';

  @override
  String get knowledgeGraphDeletedSuccessfully => '지식 그래프가 성공적으로 삭제됨';

  @override
  String get exportStartedMayTakeFewSeconds => '내보내기가 시작되었습니다. 몇 초 정도 걸릴 수 있습니다...';

  @override
  String get knowledgeGraphDeleteDescription =>
      '이렇게 하면 모든 파생 지식 그래프 데이터(노드 및 연결)가 삭제됩니다. 원본 기억은 안전하게 유지됩니다. 그래프는 시간이 지나면서 또는 다음 요청 시 다시 구축됩니다.';

  @override
  String get configureDailySummaryDigest => '일일 작업 요약 구성';

  @override
  String accessesDataTypes(String dataTypes) {
    return '$dataTypes 접근';
  }

  @override
  String triggeredByType(String triggerType) {
    return '$triggerType에 의해 트리거됨';
  }

  @override
  String accessesAndTriggeredBy(String accessDescription, String triggerDescription) {
    return '$accessDescription 및 $triggerDescription.';
  }

  @override
  String isTriggeredBy(String triggerDescription) {
    return '$triggerDescription.';
  }

  @override
  String get noSpecificDataAccessConfigured => '특정 데이터 액세스가 구성되지 않았습니다.';

  @override
  String get basicPlanDescription => '1,200 프리미엄 분 + 무제한 온디바이스';

  @override
  String get minutes => '분';

  @override
  String get omiHas => 'Omi:';

  @override
  String get premiumMinutesUsed => '프리미엄 분 사용됨.';

  @override
  String get setupOnDevice => '온디바이스 설정';

  @override
  String get forUnlimitedFreeTranscription => '무제한 무료 전사를 위해.';

  @override
  String premiumMinsLeft(int count) {
    return '프리미엄 $count분 남음.';
  }

  @override
  String get alwaysAvailable => '항상 사용 가능.';

  @override
  String get importHistory => '가져오기 기록';

  @override
  String get noImportsYet => '아직 가져오기 없음';

  @override
  String get selectZipFileToImport => '가져올 .zip 파일을 선택하세요!';

  @override
  String get otherDevicesComingSoon => '다른 기기 곧 지원 예정';

  @override
  String get deleteAllLimitlessConversations => '모든 Limitless 대화를 삭제하시겠습니까?';

  @override
  String get deleteAllLimitlessWarning => '이렇게 하면 Limitless에서 가져온 모든 대화가 영구적으로 삭제됩니다. 이 작업은 취소할 수 없습니다.';

  @override
  String deletedLimitlessConversations(int count) {
    return 'Limitless 대화 $count개 삭제됨';
  }

  @override
  String get failedToDeleteConversations => '대화 삭제 실패';

  @override
  String get deleteImportedData => '가져온 데이터 삭제';

  @override
  String get statusPending => '대기 중';

  @override
  String get statusProcessing => '처리 중';

  @override
  String get statusCompleted => '완료됨';

  @override
  String get statusFailed => '실패';

  @override
  String nConversations(int count) {
    return '$count개의 대화';
  }

  @override
  String get pleaseEnterName => '이름을 입력하세요';

  @override
  String get nameMustBeBetweenCharacters => '이름은 2~40자여야 합니다';

  @override
  String get deleteSampleQuestion => '샘플을 삭제하시겠습니까?';

  @override
  String deleteSampleConfirmation(String name) {
    return '$name의 샘플을 삭제하시겠습니까?';
  }

  @override
  String get confirmDeletion => '삭제 확인';

  @override
  String deletePersonConfirmation(String name) {
    return '$name을(를) 삭제하시겠습니까? 이렇게 하면 관련된 모든 음성 샘플도 제거됩니다.';
  }

  @override
  String get howItWorksTitle => '어떻게 작동하나요?';

  @override
  String get howPeopleWorks => '사람이 생성되면 대화 기록으로 이동하여 해당 세그먼트를 할당할 수 있습니다. 그러면 Omi가 그들의 음성도 인식할 수 있습니다!';

  @override
  String get tapToDelete => '탭하여 삭제';

  @override
  String get newTag => '신규';

  @override
  String get needHelpChatWithUs => '도움이 필요하신가요? 채팅으로 문의하세요';

  @override
  String get localStorageEnabled => '로컬 저장소 활성화됨';

  @override
  String get localStorageDisabled => '로컬 저장소 비활성화됨';

  @override
  String failedToUpdateSettings(String error) {
    return '설정 업데이트 실패: $error';
  }

  @override
  String get privacyNotice => '개인정보 보호 안내';

  @override
  String get recordingsMayCaptureOthers => '녹음 시 다른 사람의 목소리가 녹음될 수 있습니다. 활성화하기 전에 모든 참가자의 동의를 받으세요.';

  @override
  String get enable => '활성화';

  @override
  String get storeAudioOnPhone => '휴대폰에 오디오 저장';

  @override
  String get on => '켜짐';

  @override
  String get storeAudioDescription => '모든 오디오 녹음을 휴대폰에 로컬로 저장하세요. 비활성화하면 저장 공간 절약을 위해 실패한 업로드만 유지됩니다.';

  @override
  String get enableLocalStorage => '로컬 저장소 활성화';

  @override
  String get cloudStorageEnabled => '클라우드 저장소 활성화됨';

  @override
  String get cloudStorageDisabled => '클라우드 저장소 비활성화됨';

  @override
  String get enableCloudStorage => '클라우드 저장소 활성화';

  @override
  String get storeAudioOnCloud => '클라우드에 오디오 저장';

  @override
  String get cloudStorageDialogMessage => '실시간 녹음이 말하는 동안 개인 클라우드 저장소에 저장됩니다.';

  @override
  String get storeAudioCloudDescription => '말하는 동안 실시간 녹음을 개인 클라우드 저장소에 저장하세요. 오디오는 실시간으로 안전하게 캡처 및 저장됩니다.';

  @override
  String get downloadingFirmware => '펌웨어 다운로드 중';

  @override
  String get installingFirmware => '펌웨어 설치 중';

  @override
  String get firmwareUpdateWarning => '앱을 닫거나 기기를 끄지 마세요. 기기가 손상될 수 있습니다.';

  @override
  String get firmwareUpdated => '펌웨어 업데이트됨';

  @override
  String restartDeviceToComplete(Object deviceName) {
    return '업데이트를 완료하려면 $deviceName을(를) 다시 시작하세요.';
  }

  @override
  String get yourDeviceIsUpToDate => '기기가 최신 상태입니다';

  @override
  String get currentVersion => '현재 버전';

  @override
  String get latestVersion => '최신 버전';

  @override
  String get whatsNew => '새로운 기능';

  @override
  String get installUpdate => '업데이트 설치';

  @override
  String get updateNow => '지금 업데이트';

  @override
  String get updateGuide => '업데이트 가이드';

  @override
  String get checkingForUpdates => '업데이트 확인 중';

  @override
  String get checkingFirmwareVersion => '펌웨어 버전 확인 중...';

  @override
  String get firmwareUpdate => '펌웨어 업데이트';

  @override
  String get payments => '결제';

  @override
  String get connectPaymentMethodInfo => '아래에서 결제 수단을 연결하여 앱 수익금을 받기 시작하세요.';

  @override
  String get selectedPaymentMethod => '선택된 결제 수단';

  @override
  String get availablePaymentMethods => '사용 가능한 결제 수단';

  @override
  String get activeStatus => '활성';

  @override
  String get connectedStatus => '연결됨';

  @override
  String get notConnectedStatus => '연결 안 됨';

  @override
  String get setActive => '활성으로 설정';

  @override
  String get getPaidThroughStripe => 'Stripe를 통해 앱 판매 수익을 받으세요';

  @override
  String get monthlyPayouts => '월별 지급';

  @override
  String get monthlyPayoutsDescription => '수익이 \$10에 도달하면 매월 계좌로 직접 지급받습니다';

  @override
  String get secureAndReliable => '안전하고 신뢰할 수 있음';

  @override
  String get stripeSecureDescription => 'Stripe는 앱 수익의 안전하고 적시 전송을 보장합니다';

  @override
  String get selectYourCountry => '국가를 선택하세요';

  @override
  String get countrySelectionPermanent => '국가 선택은 영구적이며 나중에 변경할 수 없습니다.';

  @override
  String get byClickingConnectNow => '\"지금 연결\"을 클릭하면 다음에 동의하는 것입니다';

  @override
  String get stripeConnectedAccountAgreement => 'Stripe 연결 계정 계약';

  @override
  String get errorConnectingToStripe => 'Stripe 연결 오류! 나중에 다시 시도해 주세요.';

  @override
  String get connectingYourStripeAccount => 'Stripe 계정 연결 중';

  @override
  String get stripeOnboardingInstructions => '브라우저에서 Stripe 온보딩 프로세스를 완료하세요. 완료되면 이 페이지가 자동으로 업데이트됩니다.';

  @override
  String get failedTryAgain => '실패했나요? 다시 시도';

  @override
  String get illDoItLater => '나중에 할게요';

  @override
  String get successfullyConnected => '연결 성공!';

  @override
  String get stripeReadyForPayments => 'Stripe 계정이 결제를 받을 준비가 되었습니다. 바로 앱 판매 수익을 얻기 시작할 수 있습니다.';

  @override
  String get updateStripeDetails => 'Stripe 세부 정보 업데이트';

  @override
  String get errorUpdatingStripeDetails => 'Stripe 세부 정보 업데이트 오류! 나중에 다시 시도해 주세요.';

  @override
  String get updatePayPal => 'PayPal 업데이트';

  @override
  String get setUpPayPal => 'PayPal 설정';

  @override
  String get updatePayPalAccountDetails => 'PayPal 계정 세부 정보 업데이트';

  @override
  String get connectPayPalToReceivePayments => 'PayPal 계정을 연결하여 앱 결제 수신을 시작하세요';

  @override
  String get paypalEmail => 'PayPal 이메일';

  @override
  String get paypalMeLink => 'PayPal.me 링크';

  @override
  String get stripeRecommendation => '귀하의 국가에서 Stripe를 사용할 수 있다면 더 빠르고 쉬운 지급을 위해 사용을 강력히 권장합니다.';

  @override
  String get updatePayPalDetails => 'PayPal 세부 정보 업데이트';

  @override
  String get savePayPalDetails => 'PayPal 세부 정보 저장';

  @override
  String get pleaseEnterPayPalEmail => 'PayPal 이메일을 입력하세요';

  @override
  String get pleaseEnterPayPalMeLink => 'PayPal.me 링크를 입력하세요';

  @override
  String get doNotIncludeHttpInLink => '링크에 http, https 또는 www를 포함하지 마세요';

  @override
  String get pleaseEnterValidPayPalMeLink => '유효한 PayPal.me 링크를 입력하세요';

  @override
  String get pleaseEnterValidEmail => '유효한 이메일 주소를 입력해 주세요';

  @override
  String get syncingYourRecordings => '녹음 동기화 중';

  @override
  String get syncYourRecordings => '녹음 동기화';

  @override
  String get syncNow => '지금 동기화';

  @override
  String get error => '오류';

  @override
  String get speechSamples => '음성 샘플';

  @override
  String additionalSampleIndex(String index) {
    return '추가 샘플 $index';
  }

  @override
  String durationSeconds(String seconds) {
    return '길이: $seconds초';
  }

  @override
  String get additionalSpeechSampleRemoved => '추가 음성 샘플이 삭제되었습니다';

  @override
  String get consentDataMessage =>
      '계속하면 이 앱과 공유하는 모든 데이터(대화, 녹음, 개인 정보 포함)가 당사 서버에 안전하게 저장되어 AI 기반 인사이트를 제공하고 모든 앱 기능을 활성화합니다.';

  @override
  String get tasksEmptyStateMessage => '대화에서 생성된 작업이 여기에 표시됩니다.\n수동으로 만들려면 +를 탭하세요.';

  @override
  String get clearChatAction => '채팅 삭제';

  @override
  String get enableApps => '앱 활성화';

  @override
  String get omiAppName => 'Omi';

  @override
  String get showMore => '더 보기 ↓';

  @override
  String get showLess => '접기 ↑';

  @override
  String get loadingYourRecording => '녹음을 불러오는 중...';

  @override
  String get photoDiscardedMessage => '이 사진은 중요하지 않아 삭제되었습니다.';

  @override
  String get analyzing => '분석 중...';

  @override
  String get searchCountries => '국가 검색...';

  @override
  String get checkingAppleWatch => 'Apple Watch 확인 중...';

  @override
  String get installOmiOnAppleWatch => 'Apple Watch에\nOmi 설치';

  @override
  String get installOmiOnAppleWatchDescription => 'Omi와 함께 Apple Watch를 사용하려면 먼저 시계에 Omi 앱을 설치해야 합니다.';

  @override
  String get openOmiOnAppleWatch => 'Apple Watch에서\nOmi 열기';

  @override
  String get openOmiOnAppleWatchDescription => 'Omi 앱이 Apple Watch에 설치되어 있습니다. 앱을 열고 시작을 탭하세요.';

  @override
  String get openWatchApp => 'Watch 앱 열기';

  @override
  String get iveInstalledAndOpenedTheApp => '앱을 설치하고 열었습니다';

  @override
  String get unableToOpenWatchApp =>
      'Apple Watch 앱을 열 수 없습니다. Apple Watch에서 Watch 앱을 수동으로 열고 \"사용 가능한 앱\" 섹션에서 Omi를 설치하세요.';

  @override
  String get appleWatchConnectedSuccessfully => 'Apple Watch가 성공적으로 연결되었습니다!';

  @override
  String get appleWatchNotReachable => 'Apple Watch에 아직 연결할 수 없습니다. 시계에서 Omi 앱이 열려 있는지 확인하세요.';

  @override
  String errorCheckingConnection(String error) {
    return '연결 확인 오류: $error';
  }

  @override
  String get muted => '음소거';

  @override
  String get processNow => '지금 처리';

  @override
  String get finishedConversation => '대화 종료?';

  @override
  String get stopRecordingConfirmation => '녹음을 중지하고 지금 대화를 요약하시겠습니까?';

  @override
  String get conversationEndsManually => '대화는 수동으로만 종료됩니다.';

  @override
  String conversationSummarizedAfterMinutes(int minutes, String suffix) {
    return '대화는 $minutes분$suffix 무음 후 요약됩니다.';
  }

  @override
  String get dontAskAgain => '다시 묻지 않기';

  @override
  String get waitingForTranscriptOrPhotos => '녹취록 또는 사진 대기 중...';

  @override
  String get noSummaryYet => '아직 요약 없음';

  @override
  String hints(String text) {
    return '힌트: $text';
  }

  @override
  String get testConversationPrompt => '대화 프롬프트 테스트';

  @override
  String get prompt => '프롬프트';

  @override
  String get result => '결과';

  @override
  String get compareTranscripts => '녹취록 비교';

  @override
  String get notHelpful => '도움이 안 됨';

  @override
  String get exportTasksWithOneTap => '한 번의 탭으로 작업 내보내기!';

  @override
  String get inProgress => '진행 중';

  @override
  String get photos => '사진';

  @override
  String get rawData => '원시 데이터';

  @override
  String get content => '콘텐츠';

  @override
  String get noContentToDisplay => '표시할 콘텐츠가 없습니다';

  @override
  String get noSummary => '요약 없음';

  @override
  String get updateOmiFirmware => 'omi 펌웨어 업데이트';

  @override
  String get anErrorOccurredTryAgain => '오류가 발생했습니다. 다시 시도해 주세요.';

  @override
  String get welcomeBackSimple => '다시 오신 것을 환영합니다';

  @override
  String get addVocabularyDescription => '기록 중 Omi가 인식해야 할 단어를 추가하세요.';

  @override
  String get enterWordsCommaSeparated => '단어 입력 (쉼표로 구분)';

  @override
  String get whenToReceiveDailySummary => '일일 요약을 받을 시간';

  @override
  String get checkingNextSevenDays => '향후 7일 확인 중';

  @override
  String failedToDeleteError(String error) {
    return '삭제 실패: $error';
  }

  @override
  String get developerApiKeys => '개발자 API 키';

  @override
  String get noApiKeysCreateOne => 'API 키가 없습니다. 시작하려면 하나를 만드세요.';

  @override
  String get commandRequired => '⌘ 필요';

  @override
  String get spaceKey => '스페이스';

  @override
  String loadMoreRemaining(String count) {
    return '더 보기 ($count개 남음)';
  }

  @override
  String wrappedTopPercentUser(String percentile) {
    return '상위 $percentile% 사용자';
  }

  @override
  String get wrappedMinutes => '분';

  @override
  String get wrappedConversations => '대화';

  @override
  String get wrappedDaysActive => '활동일';

  @override
  String get wrappedYouTalkedAbout => '이야기한 주제';

  @override
  String get wrappedActionItems => '할 일';

  @override
  String get wrappedTasksCreated => '생성된 작업';

  @override
  String get wrappedCompleted => '완료';

  @override
  String wrappedCompletionRate(String rate) {
    return '$rate% 완료율';
  }

  @override
  String get wrappedYourTopDays => '최고의 날들';

  @override
  String get wrappedBestMoments => '최고의 순간';

  @override
  String get wrappedMyBuddies => '내 친구들';

  @override
  String get wrappedCouldntStopTalkingAbout => '멈출 수 없었던 이야기';

  @override
  String get wrappedShow => '프로그램';

  @override
  String get wrappedMovie => '영화';

  @override
  String get wrappedBook => '책';

  @override
  String get wrappedCelebrity => '유명인';

  @override
  String get wrappedFood => '음식';

  @override
  String get wrappedMovieRecs => '친구를 위한 영화 추천';

  @override
  String get wrappedBiggest => '가장 큰';

  @override
  String get wrappedStruggle => '도전';

  @override
  String get wrappedButYouPushedThrough => '하지만 해냈어요 💪';

  @override
  String get wrappedWin => '승리';

  @override
  String get wrappedYouDidIt => '해냈어요! 🎉';

  @override
  String get wrappedTopPhrases => '자주 쓴 말 Top 5';

  @override
  String get wrappedMins => '분';

  @override
  String get wrappedConvos => '대화';

  @override
  String get wrappedDays => '일';

  @override
  String get wrappedMyBuddiesLabel => '내 친구들';

  @override
  String get wrappedObsessionsLabel => '빠진 것들';

  @override
  String get wrappedStruggleLabel => '도전';

  @override
  String get wrappedWinLabel => '승리';

  @override
  String get wrappedTopPhrasesLabel => '자주 쓴 말';

  @override
  String get wrappedLetsHitRewind => '당신의 한 해를 되감아 봐요';

  @override
  String get wrappedGenerateMyWrapped => '내 Wrapped 생성';

  @override
  String get wrappedProcessingDefault => '처리 중...';

  @override
  String get wrappedCreatingYourStory => '당신의\n2025 이야기 만드는 중...';

  @override
  String get wrappedSomethingWentWrong => '문제가\n발생했어요';

  @override
  String get wrappedAnErrorOccurred => '오류가 발생했습니다';

  @override
  String get wrappedTryAgain => '다시 시도';

  @override
  String get wrappedNoDataAvailable => '데이터가 없습니다';

  @override
  String get wrappedOmiLifeRecap => 'Omi 라이프 요약';

  @override
  String get wrappedSwipeUpToBegin => '위로 스와이프하여 시작';

  @override
  String get wrappedShareText => '나의 2025, Omi가 기억해요 ✨ omi.me/wrapped';

  @override
  String get wrappedFailedToShare => '공유에 실패했습니다. 다시 시도해주세요.';

  @override
  String get wrappedFailedToStartGeneration => '생성 시작에 실패했습니다. 다시 시도해주세요.';

  @override
  String get wrappedStarting => '시작 중...';

  @override
  String get wrappedShare => '공유';

  @override
  String get wrappedShareYourWrapped => 'Wrapped 공유하기';

  @override
  String get wrappedMy2025 => '나의 2025';

  @override
  String get wrappedRememberedByOmi => 'Omi가 기억해요';

  @override
  String get wrappedMostFunDay => '가장 즐거운';

  @override
  String get wrappedMostProductiveDay => '가장 생산적인';

  @override
  String get wrappedMostIntenseDay => '가장 강렬한';

  @override
  String get wrappedFunniestMoment => '가장 웃긴';

  @override
  String get wrappedMostCringeMoment => '가장 민망한';

  @override
  String get wrappedMinutesLabel => '분';

  @override
  String get wrappedConversationsLabel => '대화';

  @override
  String get wrappedDaysActiveLabel => '활동일';

  @override
  String get wrappedTasksGenerated => '생성된 작업';

  @override
  String get wrappedTasksCompleted => '완료된 작업';

  @override
  String get wrappedTopFivePhrases => 'Top 5 문구';

  @override
  String get wrappedAGreatDay => '멋진 하루';

  @override
  String get wrappedGettingItDone => '해내기';

  @override
  String get wrappedAChallenge => '도전';

  @override
  String get wrappedAHilariousMoment => '웃긴 순간';

  @override
  String get wrappedThatAwkwardMoment => '그 민망한 순간';

  @override
  String get wrappedYouHadFunnyMoments => '올해 웃긴 순간들이 있었어요!';

  @override
  String get wrappedWeveAllBeenThere => '누구나 경험하는 거예요!';

  @override
  String get wrappedFriend => '친구';

  @override
  String get wrappedYourBuddy => '당신의 친구!';

  @override
  String get wrappedNotMentioned => '언급 없음';

  @override
  String get wrappedTheHardPart => '어려운 부분';

  @override
  String get wrappedPersonalGrowth => '개인 성장';

  @override
  String get wrappedFunDay => '즐거운';

  @override
  String get wrappedProductiveDay => '생산적';

  @override
  String get wrappedIntenseDay => '강렬한';

  @override
  String get wrappedFunnyMomentTitle => '웃긴 순간';

  @override
  String get wrappedCringeMomentTitle => '민망한 순간';

  @override
  String get wrappedYouTalkedAboutBadge => '이야기한 주제';

  @override
  String get wrappedCompletedLabel => '완료';

  @override
  String get wrappedMyBuddiesCard => '내 친구들';

  @override
  String get wrappedBuddiesLabel => '친구들';

  @override
  String get wrappedObsessionsLabelUpper => '관심사';

  @override
  String get wrappedStruggleLabelUpper => '고난';

  @override
  String get wrappedWinLabelUpper => '승리';

  @override
  String get wrappedTopPhrasesLabelUpper => 'TOP 문구';

  @override
  String get wrappedYourHeader => '당신의';

  @override
  String get wrappedTopDaysHeader => '최고의 날들';

  @override
  String get wrappedYourTopDaysBadge => '당신의 최고의 날들';

  @override
  String get wrappedBestHeader => '최고의';

  @override
  String get wrappedMomentsHeader => '순간';

  @override
  String get wrappedBestMomentsBadge => '최고의 순간';

  @override
  String get wrappedBiggestHeader => '가장 큰';

  @override
  String get wrappedStruggleHeader => '고난';

  @override
  String get wrappedWinHeader => '승리';

  @override
  String get wrappedButYouPushedThroughEmoji => '하지만 해냈어요 💪';

  @override
  String get wrappedYouDidItEmoji => '해냈어요! 🎉';

  @override
  String get wrappedHours => '시간';

  @override
  String get wrappedActions => '액션';

  @override
  String get multipleSpeakersDetected => '여러 화자가 감지되었습니다';

  @override
  String get multipleSpeakersDescription => '녹음에 여러 화자가 있는 것 같습니다. 조용한 장소에 있는지 확인하고 다시 시도해 주세요.';

  @override
  String get invalidRecordingDetected => '잘못된 녹음이 감지되었습니다';

  @override
  String get notEnoughSpeechDescription => '음성이 충분히 감지되지 않았습니다. 더 많이 말씀하시고 다시 시도해 주세요.';

  @override
  String get speechDurationDescription => '최소 5초 이상, 90초 이하로 말씀해 주세요.';

  @override
  String get connectionLostDescription => '연결이 끊어졌습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.';

  @override
  String get howToTakeGoodSample => '좋은 샘플을 얻는 방법은?';

  @override
  String get goodSampleInstructions =>
      '1. 조용한 장소에 있는지 확인하세요.\n2. 명확하고 자연스럽게 말하세요.\n3. 기기가 목에 자연스러운 위치에 있는지 확인하세요.\n\n생성 후에는 언제든지 개선하거나 다시 할 수 있습니다.';

  @override
  String get noDeviceConnectedUseMic => '연결된 기기가 없습니다. 휴대폰 마이크를 사용합니다.';

  @override
  String get doItAgain => '다시 하기';

  @override
  String get listenToSpeechProfile => '내 음성 프로필 듣기 ➡️';

  @override
  String get recognizingOthers => '다른 사람 인식 👀';

  @override
  String get keepGoingGreat => '계속하세요, 잘하고 있어요';

  @override
  String get somethingWentWrongTryAgain => '문제가 발생했습니다! 나중에 다시 시도해 주세요.';

  @override
  String get uploadingVoiceProfile => '음성 프로필 업로드 중....';

  @override
  String get memorizingYourVoice => '목소리를 기억하는 중...';

  @override
  String get personalizingExperience => '경험을 맞춤 설정하는 중...';

  @override
  String get keepSpeakingUntil100 => '100%가 될 때까지 계속 말씀하세요.';

  @override
  String get greatJobAlmostThere => '잘하고 있어요, 거의 다 됐어요';

  @override
  String get soCloseJustLittleMore => '거의 다 왔어요, 조금만 더';

  @override
  String get notificationFrequency => '알림 빈도';

  @override
  String get controlNotificationFrequency => 'Omi가 사전 알림을 보내는 빈도를 제어합니다.';
}
