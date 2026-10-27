package io.github.meth0gunner.healthhub

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.text.format.DateUtils
import android.text.format.Formatter
import android.view.View
import android.widget.Button
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.work.WorkInfo
import androidx.work.WorkManager
import com.google.android.material.materialswitch.MaterialSwitch
import com.google.android.material.textfield.TextInputEditText
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {

    private lateinit var settings: AppSettings
    private lateinit var haUrl: TextInputEditText
    private lateinit var token: TextInputEditText
    private lateinit var fileName: TextInputEditText
    private lateinit var haStatus: TextView
    private lateinit var exportStatus: TextView
    private lateinit var batteryStatus: TextView
    private lateinit var batteryButton: Button
    private lateinit var backgroundSwitch: MaterialSwitch
    private lateinit var syncButton: Button
    private lateinit var syncStatus: TextView
    private var syncing = false

    private val pickFolder = registerForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri != null) {
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            settings.exportFolder = uri
            settings.lastSentExport = null
            SyncWorker.schedule(this)
            refresh()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        settings = AppSettings(this)

        haUrl = findViewById(R.id.haUrl)
        token = findViewById(R.id.token)
        fileName = findViewById(R.id.fileName)
        haStatus = findViewById(R.id.haStatus)
        exportStatus = findViewById(R.id.exportStatus)
        batteryStatus = findViewById(R.id.batteryStatus)
        batteryButton = findViewById(R.id.batteryButton)
        backgroundSwitch = findViewById(R.id.backgroundSwitch)
        syncButton = findViewById(R.id.syncButton)
        syncStatus = findViewById(R.id.syncStatus)

        findViewById<TextView>(R.id.version).text = "Version ${BuildConfig.VERSION_NAME}"
        haUrl.setText(settings.haUrl)
        token.setText(settings.token)
        fileName.setText(settings.exportFileName)
        backgroundSwitch.isChecked = settings.backgroundSync

        findViewById<Button>(R.id.testButton).setOnClickListener { saveFields(); testConnection() }
        findViewById<Button>(R.id.folderButton).setOnClickListener { pickFolder.launch(null) }
        batteryButton.setOnClickListener { askToIgnoreBatteryOptimisation() }
        backgroundSwitch.setOnCheckedChangeListener { _, checked ->
            settings.backgroundSync = checked
            SyncWorker.schedule(this)
            refresh()
        }
        syncButton.setOnClickListener {
            saveFields()
            SyncWorker.runNow(this)
            syncStatus.text = "Syncing…"
        }

        val wm = WorkManager.getInstance(this)
        wm.getWorkInfosForUniqueWorkLiveData(SyncWorker.NOW).observe(this) { infos ->
            syncing = infos.any { it.state == WorkInfo.State.RUNNING || it.state == WorkInfo.State.ENQUEUED }
            refresh()
        }
        wm.getWorkInfosForUniqueWorkLiveData(SyncWorker.PERIODIC).observe(this) { refresh() }
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    override fun onPause() {
        super.onPause()
        saveFields()
    }

    private fun saveFields() {
        val urlChanged = haUrl.text.toString().trim().trimEnd('/') != settings.haUrl
        settings.haUrl = haUrl.text.toString()
        settings.token = token.text.toString()
        if (fileName.text.toString().trim() != settings.exportFileName) settings.lastSentExport = null
        settings.exportFileName = fileName.text.toString()
        if (urlChanged) settings.lastSentExport = null
        SyncWorker.schedule(this)
    }

    private fun testConnection() {
        haStatus.text = "Testing…"
        lifecycleScope.launch {
            val message = withContext(Dispatchers.IO) {
                try {
                    val plan = HaClient(settings.haUrl, settings.token).getPlan()
                    val tables = plan.getJSONArray("tables").length()
                    "Connected. Home Assistant is ready for $tables kinds of data."
                } catch (e: Exception) {
                    "Not connected: ${e.message}"
                }
            }
            haStatus.text = message
            refresh()
        }
    }

    @SuppressLint("BatteryLife")
    private fun askToIgnoreBatteryOptimisation() {
        val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            .setData(Uri.parse("package:$packageName"))
        startActivity(intent)
    }

    private fun ago(millis: Long): CharSequence =
        if (millis <= 0) "never" else DateUtils.getRelativeTimeSpanString(
            millis, System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS
        )

    private fun refresh() {
        // Export file
        val folder = settings.exportFolder
        exportStatus.text = if (folder == null) {
            "No folder chosen yet."
        } else {
            val export = ExportFile(this, folder, settings.exportFileName)
            if (export.exists) {
                "Found \"${settings.exportFileName}\": ${Formatter.formatShortFileSize(this, export.size)}," +
                    " updated ${ago(export.lastModified)}."
            } else {
                "No file called \"${settings.exportFileName}\" in that folder yet."
            }
        }

        // Battery
        val power = getSystemService(PowerManager::class.java)
        val unrestricted = power.isIgnoringBatteryOptimizations(packageName)
        batteryStatus.text = if (unrestricted) {
            "Background running allowed."
        } else {
            "Android may delay background syncs. Allow background running for reliable hourly syncs."
        }
        batteryButton.visibility = if (unrestricted) View.GONE else View.VISIBLE

        // Sync
        syncButton.isEnabled = settings.isConfigured && !syncing
        syncStatus.text = buildString {
            if (!settings.isConfigured) {
                append("Finish steps 1 and 2 to start syncing.")
                return@buildString
            }
            if (syncing) append("Syncing…\n")
            append("Last successful sync: ${ago(settings.lastSuccess)}\n")
            append("Last attempt: ${ago(settings.lastAttempt)}\n")
            if (settings.lastResult.isNotEmpty()) append(settings.lastResult)
        }
    }
}
