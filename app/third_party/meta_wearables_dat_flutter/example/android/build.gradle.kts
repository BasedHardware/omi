import java.util.Properties

// Repositories MUST be declared at project level here (not only in
// `settings.gradle.kts > dependencyResolutionManagement`). Flutter's
// Gradle plugin auto-injects `download.flutter.io` as a project-level
// repository, and Gradle's default `PREFER_PROJECT` mode then ignores
// settings-level repos entirely. As a result, if we don't list
// `google()`, `mavenCentral()`, and the GitHub Packages Maven repo
// here, the consumer build will only resolve through
// `download.flutter.io` and fail to find every other artifact.
val localProperties =
    Properties().apply {
        val localPropertiesFile = rootDir.resolve("local.properties")
        if (localPropertiesFile.exists()) {
            localPropertiesFile.inputStream().use { load(it) }
        }
    }

allprojects {
    repositories {
        google()
        mavenCentral()
        maven {
            url = uri("https://maven.pkg.github.com/facebook/meta-wearables-dat-android")
            credentials {
                username = ""
                password = System.getenv("GITHUB_TOKEN")
                    ?: localProperties.getProperty("github_token")
                    ?: ""
            }
        }
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
