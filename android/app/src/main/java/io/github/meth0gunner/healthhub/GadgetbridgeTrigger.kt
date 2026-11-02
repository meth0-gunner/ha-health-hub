package io.github.meth0gunner.healthhub

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import androidx.core.content.ContextCompat
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Asks Gadgetbridge to fetch the latest data from the band and export its
 * database, using Gadgetbridge's Intent API (Settings → Intent API in
 * Gadgetbridge: allow activity sync and database export).
 *
 * See https://gadgetbridge.org/internals/automations/intents
 */
class GadgetbridgeTrigger(private val context: Context) {

    /** What happened, for the sync report. */
    data class Outcome(val synced: Boolean, val exported: Boolean) {
        val text: String
            get() = when {
                synced && exported -> "band synced and exported"
                exported -> "exported (no sync-finished signal from the band)"
                else -> "no answer from Gadgetbridge; is its Intent API turned on?"
            }
    }

    /** Sync the band, then export. Uses the export file's change as a fallback signal. */
    suspend fun syncAndExport(exportVersion: () -> String?): Outcome {
        val events = Channel<String>(Channel.UNLIMITED)
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(c: Context, intent: Intent) {
                intent.action?.let { events.trySend(it) }
            }
        }
        val filter = IntentFilter().apply {
            addAction(SYNC_FINISHED)
            addAction(EXPORT_OK)
            addAction(EXPORT_FAILED)
        }
        ContextCompat.registerReceiver(context, receiver, filter, ContextCompat.RECEIVER_EXPORTED)
        try {
            send(ACTIVITY_SYNC)
            val synced = withTimeoutOrNull(SYNC_TIMEOUT_MS) {
                while (events.receive() != SYNC_FINISHED) { /* keep waiting */ }
                true
            } ?: false

            val before = exportVersion()
            // Gadgetbridge's documentation names this command two ways; send the
            // second only if the first gets no answer.
            for (command in listOf(TRIGGER_EXPORT, TRIGGER_DATABASE_EXPORT)) {
                send(command)
                val result: Boolean? = withTimeoutOrNull(EXPORT_TIMEOUT_MS) {
                    var answer: Boolean? = null
                    while (answer == null) {
                        val event = withTimeoutOrNull(POLL_MS) { events.receive() }
                        answer = when {
                            event == EXPORT_OK -> true
                            event == EXPORT_FAILED -> false
                            exportVersion() != before -> {
                                delay(SETTLE_MS) // let Gadgetbridge finish writing
                                true
                            }
                            else -> null
                        }
                    }
                    answer
                }
                if (result != null) return Outcome(synced, result)
            }
            return Outcome(synced, exported = false)
        } finally {
            context.unregisterReceiver(receiver)
            events.close()
        }
    }

    private fun send(action: String) {
        context.sendBroadcast(Intent(action).setPackage(PACKAGE))
    }

    companion object {
        const val PACKAGE = "nodomain.freeyourgadget.gadgetbridge"
        private const val ACTIVITY_SYNC = "$PACKAGE.command.ACTIVITY_SYNC"
        private const val TRIGGER_EXPORT = "$PACKAGE.command.TRIGGER_EXPORT"
        private const val TRIGGER_DATABASE_EXPORT = "$PACKAGE.command.TRIGGER_DATABASE_EXPORT"
        private const val SYNC_FINISHED = "$PACKAGE.action.ACTIVITY_SYNC_FINISH"
        private const val EXPORT_OK = "$PACKAGE.action.DATABASE_EXPORT_SUCCESS"
        private const val EXPORT_FAILED = "$PACKAGE.action.DATABASE_EXPORT_FAIL"

        private const val SYNC_TIMEOUT_MS = 90_000L
        private const val EXPORT_TIMEOUT_MS = 45_000L
        private const val POLL_MS = 2_000L
        private const val SETTLE_MS = 3_000L
    }
}
