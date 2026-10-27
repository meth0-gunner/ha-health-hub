package io.github.meth0gunner.healthhub

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

/** Runs a sync in the background and records the outcome for the main screen. */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val settings = AppSettings(applicationContext)
        val force = inputData.getBoolean(KEY_FORCE, false)
        settings.lastAttempt = System.currentTimeMillis()
        try {
            val report = SyncEngine(applicationContext, settings).run(force)
            settings.lastSuccess = System.currentTimeMillis()
            settings.lastResult = when {
                report.skipped -> "Export unchanged since the last sync; nothing to send."
                report.rowsByTable.isEmpty() -> "Up to date; nothing new."
                else -> "Sent ${report.totalRows} rows: " +
                    report.rowsByTable.entries.joinToString { "${friendly(it.key)} ${it.value}" }
            }
            Result.success()
        } catch (e: ConfigException) {
            settings.lastResult = "Needs attention: ${e.message}"
            Result.failure()
        } catch (e: RetryableException) {
            settings.lastResult = "Will retry: ${e.message}"
            if (runAttemptCount < 3) Result.retry() else Result.failure()
        } catch (e: Exception) {
            settings.lastResult = "Error: ${e.javaClass.simpleName}: ${e.message}"
            Result.failure()
        }
    }

    companion object {
        private const val KEY_FORCE = "force"
        const val PERIODIC = "health_hub_hourly"
        const val NOW = "health_hub_now"

        private val networkNeeded = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        /** Start or stop the hourly sync to match the setting. */
        fun schedule(context: Context) {
            val wm = WorkManager.getInstance(context)
            val settings = AppSettings(context)
            if (settings.backgroundSync && settings.isConfigured) {
                val request = PeriodicWorkRequestBuilder<SyncWorker>(1, TimeUnit.HOURS)
                    .setConstraints(networkNeeded)
                    .build()
                wm.enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.UPDATE, request)
            } else {
                wm.cancelUniqueWork(PERIODIC)
            }
        }

        /** Sync once now, sending everything new even if the export looks unchanged. */
        fun runNow(context: Context) {
            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(networkNeeded)
                .setInputData(workDataOf(KEY_FORCE to true))
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(NOW, ExistingWorkPolicy.KEEP, request)
        }

        private fun friendly(table: String) = when (table) {
            "XIAOMI_ACTIVITY_SAMPLE" -> "minutes"
            "XIAOMI_DAILY_SUMMARY_SAMPLE" -> "days"
            "XIAOMI_SLEEP_TIME_SAMPLE" -> "sleeps"
            "XIAOMI_SLEEP_STAGE_SAMPLE" -> "sleep stages"
            "XIAOMI_MANUAL_SAMPLE" -> "spot checks"
            "BATTERY_LEVEL" -> "battery"
            "BASE_ACTIVITY_SUMMARY" -> "workouts"
            else -> table.lowercase()
        }
    }
}
