package io.github.meth0gunner.healthhub

import android.content.Context
import android.net.Uri
import androidx.documentfile.provider.DocumentFile
import java.io.File

/** Gadgetbridge's export file, found in the folder the user picked. */
class ExportFile(private val context: Context, folder: Uri, private val name: String) {
    private val document: DocumentFile? =
        DocumentFile.fromTreeUri(context, folder)?.findFile(name)?.takeIf { it.isFile }

    val exists: Boolean get() = document != null
    val lastModified: Long get() = document?.lastModified() ?: 0
    val size: Long get() = document?.length() ?: 0

    /** Identifies this version of the export, to skip re-sending an unchanged file. */
    val version: String get() = "$lastModified:$size"

    /** Copy the export into private storage, so Gadgetbridge can rewrite it meanwhile. */
    fun copyToCache(): File {
        val doc = document ?: throw ConfigException(
            "No file called \"$name\" in the chosen folder. Check Gadgetbridge's auto-export settings."
        )
        val target = File(context.cacheDir, "gadgetbridge-export.db")
        File(context.cacheDir, "gadgetbridge-export.db-journal").delete()
        context.contentResolver.openInputStream(doc.uri)?.use { input ->
            target.outputStream().use { output -> input.copyTo(output) }
        } ?: throw ConfigException("Couldn't open the export file. Choose the folder again.")
        return target
    }
}
