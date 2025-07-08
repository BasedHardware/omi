package com.friend.ios

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.browser.customtabs.CustomTabsIntent
import androidx.work.*
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys
import androidx.biometric.BiometricPrompt
import androidx.biometric.BiometricManager
import androidx.fragment.app.FragmentActivity
import androidx.core.content.ContextCompat
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.MethodChannel.MethodCallHandler
import io.flutter.plugin.common.MethodChannel.Result
import org.json.JSONObject
import java.util.concurrent.Executor
import java.util.concurrent.TimeUnit
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.IvParameterSpec
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore

class CalendarIntegrationPlugin: FlutterPlugin, MethodCallHandler, ActivityAware {
    
    private lateinit var channel: MethodChannel
    private lateinit var context: Context
    private var activity: FragmentActivity? = null
    private val keyAlias = "omi_calendar_tokens"
    
    override fun onAttachedToEngine(flutterPluginBinding: FlutterPlugin.FlutterPluginBinding) {
        channel = MethodChannel(flutterPluginBinding.binaryMessenger, "calendar_integration")
        channel.setMethodCallHandler(this)
        context = flutterPluginBinding.applicationContext
    }
    
    override fun onMethodCall(call: MethodCall, result: Result) {
        when (call.method) {
            "initiateAndroidOAuth" -> initiateAndroidOAuth(call.arguments as? Map<String, Any>, result)
            "storeTokensAndroidKeystore" -> storeTokensInKeystore(call.arguments as? Map<String, Any>, result)
            "retrieveTokensAndroidKeystore" -> retrieveTokensFromKeystore(call.arguments as? Map<String, Any>, result)
            "scheduleAndroidBackgroundRefresh" -> scheduleBackgroundRefresh(call.arguments as? Map<String, Any>, result)
            "handleOAuthInterruption" -> handleOAuthInterruption(call.arguments as? Map<String, Any>, result)
            "checkPlatformCapabilities" -> checkPlatformCapabilities(result)
            else -> result.notImplemented()
        }
    }
    
    private fun initiateAndroidOAuth(arguments: Map<String, Any>?, result: Result) {
        val args = arguments ?: run {
            result.error("INVALID_ARGUMENTS", "Missing arguments", null)
            return
        }
        
        val useCustomTabs = args["use_custom_tabs"] as? Boolean ?: true
        val colorScheme = args["color_scheme"] as? String ?: "light"
        
        // Get auth URL from backend
        val authUrl = getAuthURLFromBackend()
        if (authUrl == null) {
            result.error("AUTH_URL_ERROR", "Failed to get auth URL", null)
            return
        }
        
        if (useCustomTabs && isCustomTabsAvailable()) {
            launchCustomTabs(authUrl, colorScheme, result)
        } else {
            // Fallback to external browser
            launchExternalBrowser(authUrl, result)
        }
    }
    
    private fun launchCustomTabs(authUrl: String, colorScheme: String, result: Result) {
        try {
            val builder = CustomTabsIntent.Builder()
            
            // Set color scheme
            if (colorScheme == "dark") {
                builder.setColorScheme(CustomTabsIntent.COLOR_SCHEME_DARK)
            } else {
                builder.setColorScheme(CustomTabsIntent.COLOR_SCHEME_LIGHT)
            }
            
            // Set primary color to match app theme
            builder.setDefaultColorSchemeParams(
                CustomTabsIntent.ColorSchemeParams.Builder()
                    .setToolbarColor(ContextCompat.getColor(context, R.color.primary_color))
                    .build()
            )
            
            // Enable URL bar hiding
            builder.setUrlBarHidingEnabled(true)
            
            val customTabsIntent = builder.build()
            val sessionId = java.util.UUID.randomUUID().toString()
            
            activity?.let { act ->
                customTabsIntent.launchUrl(act, Uri.parse(authUrl))
                
                result.success(mapOf(
                    "auth_url" to authUrl,
                    "session_id" to sessionId,
                    "method" to "custom_tabs"
                ))
            } ?: run {
                result.error("NO_ACTIVITY", "No activity available", null)
            }
        } catch (e: Exception) {
            result.error("CUSTOM_TABS_ERROR", "Failed to launch Custom Tabs", e.message)
        }
    }
    
    private fun launchExternalBrowser(authUrl: String, result: Result) {
        try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(authUrl))
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            
            if (intent.resolveActivity(context.packageManager) != null) {
                context.startActivity(intent)
                
                result.success(mapOf(
                    "auth_url" to authUrl,
                    "session_id" to java.util.UUID.randomUUID().toString(),
                    "method" to "external_browser"
                ))
            } else {
                result.error("NO_BROWSER", "No browser available", null)
            }
        } catch (e: Exception) {
            result.error("BROWSER_ERROR", "Failed to launch browser", e.message)
        }
    }
    
    private fun storeTokensInKeystore(arguments: Map<String, Any>?, result: Result) {
        val args = arguments ?: run {
            result.error("INVALID_ARGUMENTS", "Missing arguments", null)
            return
        }
        
        val tokens = args["tokens"] as? Map<String, Any> ?: run {
            result.error("INVALID_TOKENS", "Invalid tokens", null)
            return
        }
        
        val requireAuthentication = args["require_authentication"] as? Boolean ?: true
        val hardwareBacked = args["hardware_backed"] as? Boolean ?: true
        
        try {
            // Generate or retrieve secret key from Android Keystore
            val secretKey = getOrCreateSecretKey(requireAuthentication, hardwareBacked)
            
            // Encrypt tokens
            val tokensJson = JSONObject(tokens).toString()
            val encryptedData = encryptData(tokensJson, secretKey)
            
            // Store encrypted data in EncryptedSharedPreferences
            val masterKeyAlias = MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC)
            val sharedPreferences = EncryptedSharedPreferences.create(
                "calendar_tokens",
                masterKeyAlias,
                context,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )
            
            with(sharedPreferences.edit()) {
                putString("encrypted_tokens", encryptedData.first)
                putString("iv", encryptedData.second)
                apply()
            }
            
            result.success(mapOf("success" to true))
        } catch (e: Exception) {
            result.error("KEYSTORE_ERROR", "Failed to store tokens", e.message)
        }
    }
    
    private fun retrieveTokensFromKeystore(arguments: Map<String, Any>?, result: Result) {
        val args = arguments ?: run {
            result.error("INVALID_ARGUMENTS", "Missing arguments", null)
            return
        }
        
        val authPrompt = args["authentication_prompt"] as? String ?: "Access calendar tokens"
        
        try {
            // Check if biometric authentication is available and required
            val biometricManager = BiometricManager.from(context)
            val canUseBiometric = biometricManager.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_WEAK) == BiometricManager.BIOMETRIC_SUCCESS
            
            if (canUseBiometric && activity != null) {
                authenticateAndRetrieveTokens(authPrompt, result)
            } else {
                // Fallback to retrieving without biometric authentication
                retrieveTokensWithoutBiometric(result)
            }
        } catch (e: Exception) {
            result.error("RETRIEVAL_ERROR", "Failed to retrieve tokens", e.message)
        }
    }
    
    private fun authenticateAndRetrieveTokens(prompt: String, result: Result) {
        val activity = this.activity ?: run {
            result.error("NO_ACTIVITY", "No activity available for biometric authentication", null)
            return
        }
        
        val executor: Executor = ContextCompat.getMainExecutor(context)
        val biometricPrompt = BiometricPrompt(activity, executor, object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                super.onAuthenticationError(errorCode, errString)
                result.error("BIOMETRIC_ERROR", "Authentication error: $errString", null)
            }
            
            override fun onAuthenticationSucceeded(authResult: BiometricPrompt.AuthenticationResult) {
                super.onAuthenticationSucceeded(authResult)
                retrieveTokensWithoutBiometric(result)
            }
            
            override fun onAuthenticationFailed() {
                super.onAuthenticationFailed()
                result.error("BIOMETRIC_FAILED", "Authentication failed", null)
            }
        })
        
        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Calendar Integration")
            .setSubtitle(prompt)
            .setNegativeButtonText("Cancel")
            .build()
        
        biometricPrompt.authenticate(promptInfo)
    }
    
    private fun retrieveTokensWithoutBiometric(result: Result) {
        try {
            // Retrieve encrypted data from EncryptedSharedPreferences
            val masterKeyAlias = MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC)
            val sharedPreferences = EncryptedSharedPreferences.create(
                "calendar_tokens",
                masterKeyAlias,
                context,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )
            
            val encryptedTokens = sharedPreferences.getString("encrypted_tokens", null)
            val iv = sharedPreferences.getString("iv", null)
            
            if (encryptedTokens != null && iv != null) {
                // Decrypt tokens
                val secretKey = getOrCreateSecretKey(false, true)
                val decryptedJson = decryptData(encryptedTokens, iv, secretKey)
                
                val tokens = JSONObject(decryptedJson).let { json ->
                    val map = mutableMapOf<String, Any>()
                    val keys = json.keys()
                    while (keys.hasNext()) {
                        val key = keys.next()
                        map[key] = json.get(key)
                    }
                    map
                }
                
                result.success(mapOf("tokens" to tokens))
            } else {
                result.success(mapOf("tokens" to null))
            }
        } catch (e: Exception) {
            result.error("DECRYPTION_ERROR", "Failed to decrypt tokens", e.message)
        }
    }
    
    private fun scheduleBackgroundRefresh(arguments: Map<String, Any>?, result: Result) {
        val args = arguments ?: run {
            result.error("INVALID_ARGUMENTS", "Missing arguments", null)
            return
        }
        
        val workName = args["work_name"] as? String ?: "calendar_token_refresh"
        val flexIntervalHours = (args["flex_interval_hours"] as? Number)?.toLong() ?: 24L
        val requiresNetwork = args["requires_network"] as? Boolean ?: true
        val backoffPolicy = args["backoff_policy"] as? String ?: "exponential"
        
        try {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(if (requiresNetwork) NetworkType.CONNECTED else NetworkType.NOT_REQUIRED)
                .build()
            
            val backoff = if (backoffPolicy == "linear") BackoffPolicy.LINEAR else BackoffPolicy.EXPONENTIAL
            
            val workRequest = PeriodicWorkRequestBuilder<TokenRefreshWorker>(
                flexIntervalHours, TimeUnit.HOURS,
                flexIntervalHours / 6, TimeUnit.HOURS // flex period
            )
                .setConstraints(constraints)
                .setBackoffCriteria(backoff, WorkRequest.MIN_BACKOFF_MILLIS, TimeUnit.MILLISECONDS)
                .build()
            
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork(
                    workName,
                    ExistingPeriodicWorkPolicy.REPLACE,
                    workRequest
                )
            
            result.success(mapOf("success" to true))
        } catch (e: Exception) {
            result.error("WORK_MANAGER_ERROR", "Failed to schedule background work", e.message)
        }
    }
    
    private fun handleOAuthInterruption(arguments: Map<String, Any>?, result: Result) {
        val args = arguments ?: run {
            result.error("INVALID_ARGUMENTS", "Missing arguments", null)
            return
        }
        
        val interruptionType = args["interruption_type"] as? String ?: run {
            result.error("MISSING_INTERRUPTION_TYPE", "Missing interruption type", null)
            return
        }
        
        when (interruptionType) {
            "app_backgrounded" -> result.success(mapOf("can_resume" to true))
            "custom_tabs_dismissed" -> result.success(mapOf("can_resume" to false))
            "network_error" -> result.success(mapOf("can_resume" to true))
            else -> result.success(mapOf("can_resume" to false))
        }
    }
    
    private fun checkPlatformCapabilities(result: Result) {
        val biometricManager = BiometricManager.from(context)
        val biometricAvailable = biometricManager.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_WEAK) == BiometricManager.BIOMETRIC_SUCCESS
        
        result.success(mapOf(
            "custom_tabs" to isCustomTabsAvailable(),
            "keystore_access" to true,
            "work_manager" to true,
            "biometric_authentication" to biometricAvailable,
            "app_links" to true
        ))
    }
    
    // Helper methods
    private fun isCustomTabsAvailable(): Boolean {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse("https://www.google.com"))
        val packageManager = context.packageManager
        val resolveInfos = packageManager.queryIntentActivities(intent, 0)
        
        return resolveInfos.any { resolveInfo ->
            resolveInfo.activityInfo.packageName.contains("chrome") ||
                    resolveInfo.activityInfo.packageName.contains("firefox") ||
                    resolveInfo.activityInfo.packageName.contains("edge")
        }
    }
    
    private fun getAuthURLFromBackend(): String? {
        // This would make an API call to your backend to get the OAuth URL
        // For now, return a placeholder
        return "https://accounts.google.com/oauth2/auth?client_id=your_client_id"
    }
    
    private fun getOrCreateSecretKey(requireAuthentication: Boolean, hardwareBacked: Boolean): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore")
        keyStore.load(null)
        
        if (!keyStore.containsAlias(keyAlias)) {
            val keyGenerator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            val keyGenParameterSpec = KeyGenParameterSpec.Builder(
                keyAlias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setUserAuthenticationRequired(requireAuthentication)
                .apply {
                    if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.N) {
                        setInvalidatedByBiometricEnrollment(false)
                    }
                }
                .build()
            
            keyGenerator.init(keyGenParameterSpec)
            keyGenerator.generateKey()
        }
        
        return keyStore.getKey(keyAlias, null) as SecretKey
    }
    
    private fun encryptData(data: String, secretKey: SecretKey): Pair<String, String> {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, secretKey)
        
        val encryptedData = cipher.doFinal(data.toByteArray())
        val iv = cipher.iv
        
        return Pair(
            android.util.Base64.encodeToString(encryptedData, android.util.Base64.DEFAULT),
            android.util.Base64.encodeToString(iv, android.util.Base64.DEFAULT)
        )
    }
    
    private fun decryptData(encryptedData: String, ivString: String, secretKey: SecretKey): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        val iv = android.util.Base64.decode(ivString, android.util.Base64.DEFAULT)
        val spec = IvParameterSpec(iv)
        
        cipher.init(Cipher.DECRYPT_MODE, secretKey, spec)
        
        val decodedData = android.util.Base64.decode(encryptedData, android.util.Base64.DEFAULT)
        val decryptedData = cipher.doFinal(decodedData)
        
        return String(decryptedData)
    }
    
    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
    }
    
    override fun onAttachedToActivity(binding: ActivityPluginBinding) {
        activity = binding.activity as? FragmentActivity
    }
    
    override fun onDetachedFromActivityForConfigChanges() {
        activity = null
    }
    
    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) {
        activity = binding.activity as? FragmentActivity
    }
    
    override fun onDetachedFromActivity() {
        activity = null
    }
}

// Background worker for token refresh
class TokenRefreshWorker(context: Context, params: WorkerParameters) : Worker(context, params) {
    
    override fun doWork(): Result {
        try {
            // Implement token refresh logic here
            // This would call your backend API to refresh the tokens
            
            // For now, just return success
            return Result.success()
        } catch (e: Exception) {
            return Result.retry()
        }
    }
}