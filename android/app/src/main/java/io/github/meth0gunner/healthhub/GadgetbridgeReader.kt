package io.github.meth0gunner.healthhub

import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import org.json.JSONArray
import org.json.JSONObject

/**
 * Reads exactly what Home Assistant's sync plan asks for from a Gadgetbridge
 * export. It knows nothing about Gadgetbridge's tables itself: table and column
 * names all come from the plan, so a Gadgetbridge change is fixed on the Home
 * Assistant side. Mirrors tools/sync_export.py, which has the tests.
 */
class GadgetbridgeReader(private val db: SQLiteDatabase) {

    private fun columnsOf(table: String): Set<String> {
        val names = mutableSetOf<String>()
        db.rawQuery("PRAGMA table_info(${quote(table)})", null).use { c ->
            val nameIndex = c.getColumnIndexOrThrow("name")
            while (c.moveToNext()) names.add(c.getString(nameIndex))
        }
        return names
    }

    fun readDevices(plan: JSONObject): JSONArray {
        val spec = plan.getJSONObject("device_table")
        val table = spec.getString("name")
        val present = columnsOf(table)
        val cols = spec.getJSONArray("columns").strings().filter { it in present }
        val out = JSONArray()
        if (cols.isEmpty()) return out
        db.rawQuery("SELECT ${cols.joinToString { quote(it) }} FROM ${quote(table)}", null).use { c ->
            while (c.moveToNext()) {
                val obj = JSONObject()
                cols.forEachIndexed { i, name -> obj.put(name, value(c, i)) }
                out.put(obj)
            }
        }
        return out
    }

    /**
     * Calls [send] with (columns, rows) batches for one table in the plan, oldest
     * first. Columns this Gadgetbridge version lacks are skipped. Rows sharing a
     * timestamp are paged with an offset so none are lost at a batch boundary.
     */
    fun readTable(table: JSONObject, maxRows: Int, send: (List<String>, JSONArray) -> Unit): Int {
        val name = table.getString("name")
        val tsCol = table.getString("ts_column")
        val present = columnsOf(name)
        if (present.isEmpty() || tsCol !in present) return 0
        val cols = table.getJSONArray("columns").strings().filter { it in present }
        val order = listOf(tsCol) + listOf("DEVICE_ID", "BATTERY_INDEX", "_id")
            .filter { it in cols && it != tsCol }
        val sql = "SELECT ${cols.joinToString { quote(it) }} FROM ${quote(name)}" +
            " WHERE ${quote(tsCol)} >= ? ORDER BY ${order.joinToString { quote(it) }} LIMIT ? OFFSET ?"
        val tsIndex = cols.indexOf(tsCol)

        var since = table.getLong("since")
        var offset = 0
        var total = 0
        while (true) {
            val rows = JSONArray()
            var last = 0L
            var sameAsLast = 0
            db.rawQuery(sql, arrayOf(since.toString(), maxRows.toString(), offset.toString())).use { c ->
                while (c.moveToNext()) {
                    val row = JSONArray()
                    for (i in cols.indices) row.put(value(c, i))
                    rows.put(row)
                    val ts = c.getLong(tsIndex)
                    if (ts == last) sameAsLast++ else { last = ts; sameAsLast = 1 }
                }
            }
            if (rows.length() == 0) return total
            send(cols, rows)
            total += rows.length()
            if (rows.length() < maxRows) return total
            offset = if (last == since) offset + sameAsLast else sameAsLast
            since = last
        }
    }

    private fun value(c: Cursor, i: Int): Any = when (c.getType(i)) {
        Cursor.FIELD_TYPE_INTEGER -> c.getLong(i)
        Cursor.FIELD_TYPE_FLOAT -> c.getDouble(i)
        Cursor.FIELD_TYPE_STRING -> c.getString(i)
        else -> JSONObject.NULL // NULL, and binary data, which is never needed
    }

    private fun quote(name: String) = "\"" + name.replace("\"", "\"\"") + "\""

    private fun JSONArray.strings(): List<String> = (0 until length()).map { getString(it) }
}
