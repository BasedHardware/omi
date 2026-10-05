// omi-v5 Android host. Consumes the Skip skipstone Kotlin output (transpiled
// from the OmiKit + OmiUI Swift sources) plus skip-lib/skip-ui runtime
// artifacts, and binds the SAME native-core C++ middleware through JNI.
//
// The skipstone output must exist before this project builds:
//   swift build --scratch-path .build/scratch-platforms   (from repo root)
// which produces:
//   <repo>/.build/scratch-platforms/plugins/outputs/omi-v5-v5-swift/OmiKit/destination/skipstone/OmiKit/src/main
//   <repo>/.build/scratch-platforms/plugins/outputs/omi-v5-v5-swift/OmiUI/destination/skipstone/OmiUI/src/main
// plus the Skip/SkipModel/SkipLib/SkipUI runtime outputs alongside them.

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.fromTarget(libs.versions.jvm.get().toString())
    }
}

android {
    namespace = "omi.v5.host"
    compileSdk = libs.versions.android.sdk.compile.get().toInt()

    defaultConfig {
        applicationId = "org.reactjs.native.omi_v5_android" // mirrors the RN `com.rnruntime` slot with the v5 namespace
        minSdk = libs.versions.android.sdk.min.get().toInt()
        targetSdk = libs.versions.android.sdk.compile.get().toInt()
        versionCode = 1
        versionName = "1.0"
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
        externalNativeBuild {
            cmake {
                cppFlags += "-std=c++20"
                arguments += listOf("-DANDROID_STL=c++_shared")
            }
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.toVersion(libs.versions.jvm.get())
        targetCompatibility = JavaVersion.toVersion(libs.versions.jvm.get())
    }

    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation("omi.ui:OmiUI")
}
