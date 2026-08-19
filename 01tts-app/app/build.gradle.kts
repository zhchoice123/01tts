import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

val apiKeyProperties = Properties()
val apiKeyFile = rootProject.file("api-keys.properties")
if (apiKeyFile.isFile) {
    apiKeyFile.inputStream().use { input -> apiKeyProperties.load(input) }
}

fun quotedBuildConfigValue(name: String): String {
    val raw = apiKeyProperties.getProperty(name, "")
    val escaped = raw.replace("\\", "\\\\").replace("\"", "\\\"")
    return "\"$escaped\""
}

android {
    namespace = "com.example.ttsapp"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.example.ttsapp"
        minSdk = 26
        targetSdk = 36
        versionCode = 15
        versionName = "2.8.3"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField(
            "String",
            "API_BASE_URL",
            "\"${providers.gradleProperty("LISTENING_LAB_API_URL").getOrElse("http://42.192.62.145:8080/")}\"",
        )
        buildConfigField("String", "DEEPSEEK_API_KEY", quotedBuildConfigValue("DEEPSEEK_API_KEY"))
        buildConfigField("String", "MOONSHOT_API_KEY", quotedBuildConfigValue("MOONSHOT_API_KEY"))
        buildConfigField("String", "OPENAI_API_KEY", quotedBuildConfigValue("OPENAI_API_KEY"))
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.06.00")
    implementation(composeBom)
    androidTestImplementation(composeBom)
    implementation("androidx.activity:activity-compose:1.12.4")
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.work:work-runtime-ktx:2.11.1")
    implementation("androidx.media3:media3-exoplayer:1.9.3")
    implementation("androidx.media3:media3-datasource-okhttp:1.9.3")
    implementation("androidx.media3:media3-ui:1.9.3")
    implementation("com.squareup.retrofit2:retrofit:3.0.0")
    implementation("com.squareup.retrofit2:converter-gson:3.0.0")
    implementation("com.squareup.okhttp3:okhttp:5.1.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:5.1.0")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.7.0")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
