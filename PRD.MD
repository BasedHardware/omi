# Localization PRD v3 - Missing Translations & Hardcoded Strings

## Overview

This document tracks the third phase of localization work for the Omi Flutter app. It covers:
1. Missing translation keys in existing ARB files (keys present in English but missing in other languages)
2. Hardcoded strings in Dart code that need localization

## Status: IN PROGRESS

---

## Part 1: Missing ARB Translation Keys

### Summary

Total languages with missing translations: **31**

| Language | Code | Missing Keys | Priority |
|----------|------|--------------|----------|
| Czech | cs | 0 | ✅ DONE |
| Danish | da | 0 | ✅ DONE |
| Arabic | ar | 8 | MEDIUM |
| Bulgarian | bg | 8 | MEDIUM |
| Catalan | ca | 8 | MEDIUM |
| German | de | 8 | MEDIUM |
| Greek | el | 0 | ✅ DONE |
| Spanish | es | 0 | ✅ DONE |
| Estonian | et | 0 | ✅ DONE |
| Finnish | fi | 0 | ✅ DONE |
| French | fr | 0 | ✅ DONE |
| Hindi | hi | 0 | ✅ DONE |
| Hungarian | hu | 0 | ✅ DONE |
| Indonesian | id | 0 | ✅ DONE |
| Italian | it | 0 | ✅ DONE |
| Japanese | ja | 0 | ✅ DONE |
| Korean | ko | 0 | ✅ DONE |
| Lithuanian | lt | 0 | ✅ DONE |
| Latvian | lv | 0 | ✅ DONE |
| Malay | ms | 22 | HIGH |
| Dutch | nl | 22 | HIGH |
| Norwegian | no | 22 | HIGH |
| Polish | pl | 0 | ✅ DONE |
| Portuguese | pt | 0 | ✅ DONE |
| Romanian | ro | 0 | ✅ DONE |
| Russian | ru | 0 | ✅ DONE |
| Slovak | sk | 22 | HIGH |
| Swedish | sv | 0 | ✅ DONE |
| Thai | th | 0 | ✅ DONE |
| Turkish | tr | 22 | HIGH |
| Chinese | zh | 22 | HIGH |

### Missing Keys Breakdown

#### Group A: 31 missing keys (cs, da)
```
autoClosingInSeconds
availableSpace
batteryDrainIncrease
debugModeDetected
deviceNotCompatible
deviceRequirements
download
downloadError
downloadModel
downloadWhisperModel
downloading
editReply
estimatedSize
failedToSendReply
largeModelWarning
localProcessingInfo
model
modelReady
modelRequired
noModelDownloadRequired
noReviewsFound
onDeviceIntensive
onDeviceSlower
performanceReduced
premiumMinutesInfo
redownload
reply
replySentSuccessfully
send
starFilter
writeYourReply
```

#### Group B: 22 missing keys (el, es, et, fi, fr, hi, hu, id, it, ja, ko, lt, lv, ms, nl, no, pl, pt, ro, ru, sk, sv, th, tr, zh)
```
availableSpace
batteryDrainIncrease
deviceRequirements
downloadError
editReply
estimatedSize
failedToSendReply
largeModelWarning
localProcessingInfo
model
modelReady
noModelDownloadRequired
noReviewsFound
onDeviceIntensive
onDeviceSlower
premiumMinutesInfo
redownload
reply
replySentSuccessfully
send
starFilter
writeYourReply
```

#### Group C: 8 missing keys (ar, bg, ca, de)
```
editReply
failedToSendReply
noReviewsFound
reply
replySentSuccessfully
send
starFilter
writeYourReply
```

---

## Part 2: Hardcoded Strings in Dart Code

### Files Requiring Localization

Total Files: **7**
Total Hardcoded Strings: **~30**

#### 1. conversations_page.dart
**Path:** `app/lib/pages/conversations/conversations_page.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? |
|------|------------------|---------------|---------------|
| 233 | `'Conversations'` | `conversations` | YES |

#### 2. move_to_folder_sheet.dart
**Path:** `app/lib/pages/conversations/widgets/move_to_folder_sheet.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? |
|------|------------------|---------------|---------------|
| 53 | `'Move to Folder'` | `moveToFolder` | CHECK |
| 78 | `'No folders available'` | `noFoldersAvailable` | CHECK |

#### 3. create_folder_sheet.dart
**Path:** `app/lib/pages/conversations/widgets/create_folder_sheet.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? |
|------|------------------|---------------|---------------|
| 164 | `'Edit Folder'` | `editFolder` | YES |
| 164 | `'New Folder'` | `newFolder` | CHECK |
| 185 | `'Save'` | `save` | YES |
| 185 | `'Create'` | `create` | YES |
| 262 | `'Icon'` | `icon` | CHECK |
| 264 | `'Color'` | `color` | CHECK |

#### 4. processing_capture.dart
**Path:** `app/lib/pages/conversations/widgets/processing_capture.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? |
|------|------------------|---------------|---------------|
| 201 | `'Waiting for device...'` | `waitingForDevice` | CHECK |
| 221 | `'In progress...'` | `inProgress` | CHECK |
| 221 | `'Say something...'` | `saySomething` | CHECK |
| 236 | `'Paused'` | `paused` | CHECK |
| 326 | `'Listening'` | `listening` | CHECK |
| 364 | `'Initialising System Audio'` | `initialisingSystemAudio` | CHECK |
| 543 | `'Stop Recording'` | `stopRecording` | CHECK |
| 556 | `'Continue Recording'` | `continueRecording` | CHECK |
| 572 | `'Initialising Recorder'` | `initialisingRecorder` | CHECK |
| 586 | `'Pause Recording'` | `pauseRecording` | CHECK |
| 600 | `'Resume Recording'` | `resumeRecording` | CHECK |
| 703 | `'Processing'` | `processing` | CHECK |

#### 5. daily_summaries_list.dart
**Path:** `app/lib/pages/conversations/widgets/daily_summaries_list.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? |
|------|------------------|---------------|---------------|
| 164 | `'No daily recaps yet'` | `noDailyRecapsYet` | CHECK |
| 173 | `'Your daily recaps will appear here once generated'` | `dailyRecapsDescription` | CHECK |

#### 6. fast_transfer_suggestion_dialog.dart
**Path:** `app/lib/pages/conversations/sync_widgets/fast_transfer_suggestion_dialog.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? |
|------|------------------|---------------|---------------|
| 19 | `'Choose Transfer Method'` | `chooseTransferMethod` | CHECK |
| 50 | `'Fast Transfer'` | `fastTransfer` | CHECK |
| 55 | `'~150 KB/s via WiFi'` | `fastTransferSpeed` | CHECK |
| 92 | `'Bluetooth'` | `bluetooth` | CHECK |
| 97 | `'~30 KB/s via BLE'` | `bluetoothSpeed` | CHECK |

#### 7. merge_confirmation_dialog.dart
**Path:** `app/lib/pages/conversations/widgets/merge_confirmation_dialog.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? |
|------|------------------|---------------|---------------|
| 165 | `'Large time gap detected (...)'` | `largeTimeGapDetected` | CHECK |
| 167 | `'Large time gaps detected (...)'` | `largeTimeGapsDetected` | CHECK |

---

## Implementation Plan

### Phase 1: Add Missing Keys to ARB Files
1. Add 31 keys to cs, da
2. Add 22 keys to el, es, et, fi, fr, hi, hu, id, it, ja, ko, lt, lv, ms, nl, no, pl, pt, ro, ru, sk, sv, th, tr, zh
3. Add 8 keys to ar, bg, ca, de

### Phase 2: Localize Hardcoded Strings
1. Check which keys already exist in app_en.arb
2. Add new keys to app_en.arb for missing ones
3. Update Dart files to use context.l10n
4. Add translations to all 33 language ARB files

### Phase 3: Verification
1. Run `flutter gen-l10n` to regenerate localization files
2. Run `app/test.sh` to verify no issues
3. Test app in different locales

---

## Completion Criteria

- [ ] All 31 languages have complete translations matching English keys
- [ ] All hardcoded strings in Dart code replaced with context.l10n calls
- [ ] flutter gen-l10n runs without errors
- [ ] app/test.sh passes

---

## Created
Date: 2026-01-21
Version: 3.0
