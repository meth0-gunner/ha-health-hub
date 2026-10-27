package io.github.meth0gunner.healthhub

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import org.json.JSONObject

/** One sync: export → Home Assistant. Blocking; run it off the main thread. */
class SyncEngine(private val context: Context, private val settings: AppSettings) {

    data class Report(val skipped: Boolean, val rowsByTable: Map<String, Int>) {
        val totalRows: Int get() = rowsByTable.values.sum()
    }

    /** @param force send even if the export hasn't changed since the last sync. */
    fun run(force: Boolean): Report {
        val folder = settings.exportFolder
            ?: throw ConfigException("Choose the Gadgetbridge export folder first")
        if (settings.haUrl.isEmpty() || settings.token.isEmpty()) {
            throw ConfigException("Enter the Home Assistant address and access token first")
        }

        val export = ExportFile(context, folder, settings.exportFileName)
        if (!export.exists) {
            throw ConfigException(
                "No file called \"${settings.exportFileName}\" in the chosen folder." +
                    " Check Gadgetbridge's auto-export settings."
            )
        }
        val version = export.version
        if (!force && version == settings.lastSentExport) {
            return Report(skipped = true, rowsByTable = emptyMap())
        }

        val client = HaClient(settings.haUrl, settings.token)
        val plan = client.getPlan()
        if (plan.optInt("protocol") != PROTOCOL_VERSION) {
            throw ConfigException("Update the Health Hub app: Home Assistant expects a newer version")
        }
        val maxRows = plan.optInt("max_rows", 5000)

        val copy = export.copyToCache()
        val counts = linkedMapOf<String, Int>()
        try {
            SQLiteDatabase.openDatabase(
                copy.path,
                null,
                SQLiteDatabase.OPEN_READWRITE or SQLiteDatabase.NO_LOCALIZED_COLLATORS,
            ).use { db ->
                val reader = GadgetbridgeReader(db)
                val devices = reader.readDevices(plan)
                val tables = plan.getJSONArray("tables")
                for (i in 0 until tables.length()) {
                    val table = tables.getJSONObject(i)
                    val name = table.getString("name")
                    val sent = reader.readTable(table, maxRows) { cols, rows ->
                        client.postBatch(
                            JSONObject()
                                .put("protocol", PROTOCOL_VERSION)
                                .put("app_version", BuildConfig.VERSION_NAME)
                                .put("table", name)
                                .put("columns", org.json.JSONArray(cols))
                                .put("rows", rows)
                                .put("devices", devices)
                        )
                    }
                    if (sent > 0) counts[name] = sent
                }
            }
        } finally {
            copy.delete()
        }
        settings.lastSentExport = version
        return Report(skipped = false, rowsByTable = counts)
    }

    companion object {
        const val PROTOCOL_VERSION = 1
    }
}
