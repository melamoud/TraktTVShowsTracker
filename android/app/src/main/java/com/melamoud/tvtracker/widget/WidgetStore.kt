package com.melamoud.tvtracker.widget

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.melamoud.tvtracker.data.api.dto.WidgetItemDto

enum class WidgetMode(val api: String, val title: String) {
    SHOWS("shows", "Shows Progress"),
    MOVIES("movies", "Movies"),
    ALERTS("alerts", "Alerts");

    fun next(): WidgetMode = when (this) {
        SHOWS -> MOVIES
        MOVIES -> ALERTS
        ALERTS -> SHOWS
    }

    companion object {
        fun fromApi(value: String?) = entries.firstOrNull { it.api == value } ?: SHOWS
    }
}

class WidgetStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private val gson = Gson()
    private val listType = object : TypeToken<List<WidgetItemDto>>() {}.type

    fun mode(widgetId: Int): WidgetMode = WidgetMode.fromApi(prefs.getString(key("mode", widgetId), WidgetMode.SHOWS.api))

    fun setMode(widgetId: Int, mode: WidgetMode) {
        prefs.edit().putString(key("mode", widgetId), mode.api).apply()
    }

    fun items(widgetId: Int): List<WidgetItemDto> {
        val raw = prefs.getString(key("items", widgetId), null) ?: return emptyList()
        return runCatching { gson.fromJson<List<WidgetItemDto>>(raw, listType) }.getOrNull().orEmpty()
    }

    fun setItems(widgetId: Int, items: List<WidgetItemDto>) {
        prefs.edit().putString(key("items", widgetId), gson.toJson(items)).apply()
    }

    fun message(widgetId: Int): String? = prefs.getString(key("message", widgetId), null)

    fun setMessage(widgetId: Int, message: String?) {
        prefs.edit().putString(key("message", widgetId), message).apply()
    }

    fun expanded(widgetId: Int): Set<String> {
        return prefs.getStringSet(key("expanded", widgetId), emptySet())?.toSet().orEmpty()
    }

    fun toggleExpanded(widgetId: Int, groupKey: String) {
        val cur = expanded(widgetId).toMutableSet()
        if (!cur.add(groupKey)) cur.remove(groupKey)
        prefs.edit().putStringSet(key("expanded", widgetId), cur).apply()
    }

    fun drop(widgetId: Int) {
        prefs.edit()
            .remove(key("mode", widgetId))
            .remove(key("items", widgetId))
            .remove(key("message", widgetId))
            .remove(key("expanded", widgetId))
            .apply()
    }

    private fun key(name: String, widgetId: Int) = "${name}_$widgetId"

    companion object {
        private const val PREFS = "tvtracker_widget"
    }
}
