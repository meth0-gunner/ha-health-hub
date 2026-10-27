package io.github.meth0gunner.healthhub

import android.content.Context
import android.net.Uri
import androidx.core.content.edit

/** Everything the app remembers, in private storage excluded from backups. */
class AppSettings(context: Context) {
    private val prefs = context.getSharedPreferences("health_hub", Context.MODE_PRIVATE)

    var haUrl: String
        get() = prefs.getString("ha_url", "") ?: ""
        set(value) = prefs.edit { putString("ha_url", value.trim().trimEnd('/')) }

    var token: String
        get() = prefs.getString("token", "") ?: ""
        set(value) = prefs.edit { putString("token", value.trim()) }

    var exportFolder: Uri?
        get() = prefs.getString("export_folder", null)?.let(Uri::parse)
        set(value) = prefs.edit { putString("export_folder", value?.toString()) }

    var exportFileName: String
        get() = prefs.getString("export_file", DEFAULT_EXPORT_NAME) ?: DEFAULT_EXPORT_NAME
        set(value) = prefs.edit { putString("export_file", value.trim().ifEmpty { DEFAULT_EXPORT_NAME }) }

    var backgroundSync: Boolean
        get() = prefs.getBoolean("background_sync", true)
        set(value) = prefs.edit { putBoolean("background_sync", value) }

    /** Export file version last sent in full, to skip unchanged exports. */
    var lastSentExport: String?
        get() = prefs.getString("last_sent_export", null)
        set(value) = prefs.edit { putString("last_sent_export", value) }

    var lastAttempt: Long
        get() = prefs.getLong("last_attempt", 0)
        set(value) = prefs.edit { putLong("last_attempt", value) }

    var lastSuccess: Long
        get() = prefs.getLong("last_success", 0)
        set(value) = prefs.edit { putLong("last_success", value) }

    var lastResult: String
        get() = prefs.getString("last_result", "") ?: ""
        set(value) = prefs.edit { putString("last_result", value) }

    val isConfigured: Boolean
        get() = haUrl.isNotEmpty() && token.isNotEmpty() && exportFolder != null

    companion object {
        const val DEFAULT_EXPORT_NAME = "Gadgetbridge"
    }
}
