package io.github.meth0gunner.healthhub

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Something went wrong that retrying later might fix (network, HA restarting). */
class RetryableException(message: String, cause: Throwable? = null) : Exception(message, cause)

/** Something the user has to fix (wrong address, bad token, missing export). */
class ConfigException(message: String) : Exception(message)

/** Talks to the Health Hub integration in Home Assistant. */
class HaClient(baseUrl: String, private val token: String) {
    private val base = baseUrl.trimEnd('/') + "/api/health_hub/sync"

    fun getPlan(): JSONObject = request("GET", "$base/plan", null)

    fun postBatch(batch: JSONObject): JSONObject = request("POST", "$base/batch", batch)

    private fun request(method: String, url: String, body: JSONObject?): JSONObject {
        val conn = try {
            URL(url).openConnection() as HttpURLConnection
        } catch (e: Exception) {
            throw ConfigException("The Home Assistant address doesn't look right")
        }
        try {
            conn.requestMethod = method
            conn.connectTimeout = 20_000
            conn.readTimeout = 120_000
            conn.setRequestProperty("Authorization", "Bearer $token")
            conn.setRequestProperty("Accept", "application/json")
            if (body != null) {
                val bytes = body.toString().toByteArray(Charsets.UTF_8)
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.setFixedLengthStreamingMode(bytes.size)
                conn.outputStream.use { it.write(bytes) }
            }
            val code = conn.responseCode
            val text = (if (code in 200..299) conn.inputStream else conn.errorStream)
                ?.bufferedReader()?.use { it.readText() } ?: ""
            when {
                code in 200..299 -> return JSONObject(text)
                code == 401 -> throw ConfigException("Home Assistant rejected the access token")
                code == 403 -> throw ConfigException("The access token must belong to an admin user")
                code == 404 -> throw ConfigException(
                    "Health Hub isn't installed in Home Assistant (or the address is wrong)"
                )
                code == 400 -> throw ConfigException("Home Assistant refused the data: ${message(text)}")
                else -> throw RetryableException("Home Assistant replied $code: ${message(text)}")
            }
        } catch (e: IOException) {
            throw RetryableException("Couldn't reach Home Assistant (${e.javaClass.simpleName})", e)
        } finally {
            conn.disconnect()
        }
    }

    private fun message(text: String): String =
        try {
            JSONObject(text).optString("message", text)
        } catch (e: Exception) {
            text.take(200)
        }
}
