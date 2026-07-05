import java.util.Properties

pluginManagement {
    val flutterSdkPath =
        run {
            val properties = java.util.Properties()
            file("local.properties").inputStream().use { properties.load(it) }
            val flutterSdkPath = properties.getProperty("flutter.sdk")
            require(flutterSdkPath != null) { "flutter.sdk not set in local.properties" }
            flutterSdkPath
        }

    includeBuild("$flutterSdkPath/packages/flutter_tools/gradle")

    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

plugins {
    id("dev.flutter.flutter-plugin-loader") version "1.0.0"
    id("com.android.application") version "8.11.1" apply false
    id("org.jetbrains.kotlin.android") version "2.2.20" apply false
}

// meta_wearables_dat_flutter consumes Meta's official Android DAT SDK from
// GitHub Packages Maven. A GitHub personal access token with the
// `read:packages` scope is required: set `GITHUB_TOKEN` in the environment
// or add `github_token=<token>` to `local.properties`.
val localProperties =
    Properties().apply {
        val localPropertiesFile = rootDir.resolve("local.properties")
        if (localPropertiesFile.exists()) {
            localPropertiesFile.inputStream().use { load(it) }
        }
    }

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        maven {
            url = uri("https://maven.pkg.github.com/facebook/meta-wearables-dat-android")
            credentials {
                username = "" // not needed
                password = System.getenv("GITHUB_TOKEN")
                    ?: localProperties.getProperty("github_token")
                    ?: ""
            }
        }
    }
}

include(":app")
