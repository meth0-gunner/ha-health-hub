package io.github.meth0gunner.healthhub

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Sync now, on request from Home Assistant. The Health page's Sync now button
 * asks the HA Companion app to send this broadcast (command_broadcast_intent).
 */
class SyncNowReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION) return
        if (AppSettings(context).isConfigured) SyncWorker.runNow(context)
    }

    companion object {
        const val ACTION = "io.github.meth0gunner.healthhub.SYNC_NOW"
    }
}
