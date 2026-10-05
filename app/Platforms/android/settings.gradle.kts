pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

val repoRoot: File = settingsDir.resolve("../../..").canonicalFile
val skipstone: File = listOf(".build/scratch-platforms/plugins/outputs", ".build/plugins/outputs")
    .map { repoRoot.resolve(it) }
    .filter { it.isDirectory }
    .flatMap { it.listFiles()?.toList().orEmpty() }
    .map { it.resolve("OmiUI/destination/skipstone") }
    .firstOrNull { it.resolve("settings.gradle.kts").isFile }
    ?: throw GradleException("Skipstone output missing under $repoRoot/.build; run `swift build --scratch-path .build/scratch-platforms` from the repo root first.")

apply(from = skipstone.resolve("settings.gradle.kts"))
includeBuild(skipstone)

rootProject.name = "omi-v5-android"
include(":app")
