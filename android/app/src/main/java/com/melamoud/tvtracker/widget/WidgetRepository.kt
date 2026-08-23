package com.melamoud.tvtracker.widget

import android.content.Context
import com.melamoud.tvtracker.TvTrackerApp
import com.melamoud.tvtracker.data.api.dto.WidgetItemDto

object WidgetRepository {
    fun visibleRows(store: WidgetStore, widgetId: Int): List<WidgetItemDto> {
        val expanded = store.expanded(widgetId)
        val out = mutableListOf<WidgetItemDto>()
        for (item in store.items(widgetId)) {
            out.add(item)
            if (item.kind == "group" && item.groupKey in expanded) {
                out.addAll(item.items)
            }
        }
        return out
    }

    suspend fun refresh(context: Context, widgetId: Int) {
        val app = TvTrackerApp.from(context)
        val store = WidgetStore(context)
        val mode = store.mode(widgetId)
        if (!app.container.sessionStore.isLoggedIn()) {
            store.setItems(widgetId, emptyList())
            store.setMessage(widgetId, "Open the app and sign in.")
            return
        }
        val result = app.container.catalogRepository.widget(mode.api)
        result.fold(
            onSuccess = {
                store.setItems(widgetId, it.items)
                store.setMessage(
                    widgetId,
                    if (it.items.isEmpty()) "Nothing to show." else null,
                )
            },
            onFailure = {
                store.setMessage(widgetId, it.message ?: "Could not refresh.")
            },
        )
    }
}
