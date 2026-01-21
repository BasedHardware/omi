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
| Arabic | ar | 0 | ✅ DONE |
| Bulgarian | bg | 0 | ✅ DONE |
| Catalan | ca | 0 | ✅ DONE |
| German | de | 0 | ✅ DONE |
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
| Malay | ms | 0 | ✅ DONE |
| Dutch | nl | 0 | ✅ DONE |
| Norwegian | no | 0 | ✅ DONE |
| Polish | pl | 0 | ✅ DONE |
| Portuguese | pt | 0 | ✅ DONE |
| Romanian | ro | 0 | ✅ DONE |
| Russian | ru | 0 | ✅ DONE |
| Slovak | sk | 0 | ✅ DONE |
| Swedish | sv | 0 | ✅ DONE |
| Thai | th | 0 | ✅ DONE |
| Turkish | tr | 0 | ✅ DONE |
| Chinese | zh | 0 | ✅ DONE |

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

#### 1. conversations_page.dart ✅ DONE
**Path:** `app/lib/pages/conversations/conversations_page.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? | Status |
|------|------------------|---------------|---------------|--------|
| 233 | `'Conversations'` | `conversations` | YES | ✅ |

#### 2. move_to_folder_sheet.dart ✅ DONE
**Path:** `app/lib/pages/conversations/widgets/move_to_folder_sheet.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? | Status |
|------|------------------|---------------|---------------|--------|
| 53 | `'Move to Folder'` | `moveToFolder` | YES (added) | ✅ |
| 78 | `'No folders available'` | `noFoldersAvailable` | YES (added) | ✅ |

#### 3. create_folder_sheet.dart ✅ DONE
**Path:** `app/lib/pages/conversations/widgets/create_folder_sheet.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? | Status |
|------|------------------|---------------|---------------|--------|
| 164 | `'Edit Folder'` | `editFolder` | YES | ✅ |
| 164 | `'New Folder'` | `newFolder` | YES (added) | ✅ |
| 185 | `'Save'` | `save` | YES | ✅ |
| 185 | `'Create'` | `create` | YES | ✅ |
| 262 | `'Icon'` | `icon` | YES | ✅ |
| 264 | `'Color'` | `color` | YES (added) | ✅ |

#### 4. processing_capture.dart ✅ DONE
**Path:** `app/lib/pages/conversations/widgets/processing_capture.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? | Status |
|------|------------------|---------------|---------------|--------|
| 201 | `'Waiting for device...'` | `waitingForDevice` | YES (added) | ✅ |
| 221 | `'In progress...'` | `inProgress` | YES | ✅ |
| 221 | `'Say something...'` | `saySomething` | YES (added) | ✅ |
| 236 | `'Paused'` | `paused` | YES | ✅ |
| 326 | `'Listening'` | `listening` | YES | ✅ |
| 364 | `'Initialising System Audio'` | `initialisingSystemAudio` | YES (added) | ✅ |
| 543 | `'Stop Recording'` | `stopRecording` | YES (added) | ✅ |
| 556 | `'Continue Recording'` | `continueRecording` | YES (added) | ✅ |
| 572 | `'Initialising Recorder'` | `initialisingRecorder` | YES (added) | ✅ |
| 586 | `'Pause Recording'` | `pauseRecording` | YES (added) | ✅ |
| 600 | `'Resume Recording'` | `resumeRecording` | YES (added) | ✅ |
| 703 | `'Processing'` | `processing` | YES | ✅ |

#### 5. daily_summaries_list.dart ✅ DONE
**Path:** `app/lib/pages/conversations/widgets/daily_summaries_list.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? | Status |
|------|------------------|---------------|---------------|--------|
| 164 | `'No daily recaps yet'` | `noDailyRecapsYet` | YES (added) | ✅ |
| 173 | `'Your daily recaps will appear here once generated'` | `dailyRecapsDescription` | YES (added) | ✅ |

#### 6. fast_transfer_suggestion_dialog.dart ✅ DONE
**Path:** `app/lib/pages/conversations/sync_widgets/fast_transfer_suggestion_dialog.dart`

| Line | Hardcoded String | Suggested Key | Exists in EN? | Status |
|------|------------------|---------------|---------------|--------|
| 19 | `'Choose Transfer Method'` | `chooseTransferMethod` | YES (added) | ✅ |
| 50 | `'Fast Transfer'` | `fastTransfer` | YES | ✅ |
| 55 | `'~150 KB/s via WiFi'` | `fastTransferSpeed` | YES (added) | ✅ |
| 92 | `'Bluetooth'` | `bluetooth` | YES | ✅ |
| 97 | `'~30 KB/s via BLE'` | `bleSpeed` | YES | ✅ |

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
