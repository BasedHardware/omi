import org.jetbrains.kotlin.gradle.dsl.JvmTarget

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
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// <repo>/app/Platforms/android/app → repo root is four levels up.
val repoRoot: File = file("../../../..")
val skipstoneOutput: File = repoRoot.resolve(".build/scratch-platforms/plugins/outputs")

android {
    namespace = "omi.v5.host"
    compileSdk = 35

    defaultConfig {
        applicationId = "org.reactjs.native.omi-v5-android" // mirrors the RN `com.rnruntime` slot with the v5 namespace
        minSdk = 26          // Skip requires java.time + API 26+ surfaces
        targetSdk = 35
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

    sourceSets {
        getByName("main") {
            // Skipstone output for the shared package and the Skip runtimes
            // it depends on (all generated, never committed). Each entry is
            // the `src/main` tree of the transpiled module.
            val modules = listOf(
                "omi-v5-v5-swift/OmiKit/destination/skipstone/OmiKit",
                "omi-v5-v5-swift/OmiUI/destination/skipstone/OmiUI",
                "skip-model/SkipModel/destination/skipstone/SkipModel",
                "skip-lib/SkipLib/destination/skipstone/SkipLib",
                "skip-foundation/SkipFoundation/destination/skipstone/SkipFoundation",
                "skip-ui/SkipUI/destination/skipstone/SkipUI",
            )
            for (module in modules) {
                kotlin.srcDir(skipstoneOutput.resolve(module).resolve("src/main"))
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_17)
        }
    }

    buildFeatures {
        compose = true
    }

    packaging {
        resources.excludes += setOf("META-INF/*.kotlin_module")
    }
}

dependencies {
    // Compose host runtime for the transpiled SkipUI root.
    val composeBom = platform("androidx.compose:compose-bom:2024.09.03")
    implementation(composeBom)
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-runtime-kotlin:2.8.6")

    // skip-lib / skip-foundation / skip-ui Kotlin sources expect these.
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")
}
