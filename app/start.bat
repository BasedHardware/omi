@echo off
SETLOCAL ENABLEEXTENSIONS
SETLOCAL ENABLEDELAYEDEXPANSION

REM 👋 Yo folks! Welcome to the OMI Mobile Project - We're hiring! Join us on Discord: http://discord.omi.me

echo ================================================
echo       🔧 OMI ANDROID SETUP - DEV & PROD
echo ================================================

echo Prerequisites:
echo - Flutter SDK
echo - Dart SDK
echo - Android Studio
echo - NDK 26.3.11579264 or above (to build Opus for ARM Devices)
echo - Opus Codec: https://opus-codec.org
echo.
echo Usages:
echo - setup.bat android
echo.

REM Set API base URL
set API_BASE_URL=https://omi.neo.eu.com/

REM ===============================
REM Create required directories
REM ===============================
echo Creating directory structure...
mkdir android\app\src\dev 2>nul
mkdir android\app\src\prod 2>nul
mkdir lib 2>nul

REM ===============================
REM Setup Firebase - Dev
REM ===============================
echo Setting up Firebase - Dev environment...
copy /Y setup\prebuilt\firebase_options.dart lib\firebase_options_dev.dart >nul
copy /Y setup\prebuilt\google-services.json android\app\src\dev\ >nul

REM ===============================
REM Setup Firebase - Prod
REM ===============================
echo Setting up Firebase - Prod environment...
copy /Y setup\prebuilt\firebase_options.dart lib\firebase_options_prod.dart >nul
copy /Y setup\prebuilt\google-services.json android\app\src\prod\ >nul

REM ===============================
REM Create environment files
REM ===============================
echo Creating .env files...
echo API_BASE_URL=%API_BASE_URL%> .dev.env
echo API_BASE_URL=%API_BASE_URL%> .prod.env

REM ===============================
REM Set up Android Keystore
REM ===============================
echo Setting up Android keystore...
copy /Y setup\prebuilt\key.properties android\ >nul

REM ===============================
REM Install Flutter dependencies & build
REM ===============================
echo Running Flutter pub get and build_runner...
flutter pub get && dart run build_runner build

IF %ERRORLEVEL% NEQ 0 (
  echo ❌ Build failed.
  EXIT /B 1
)

echo ✅ Android setup completed successfully for both dev and prod.

ENDLOCAL
