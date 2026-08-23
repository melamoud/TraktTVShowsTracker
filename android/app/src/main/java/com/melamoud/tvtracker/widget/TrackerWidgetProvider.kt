package com.melamoud.tvtracker.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.view.View
import android.widget.RemoteViews
import com.melamoud.tvtracker.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

private val widgetScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

class TrackerWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        appWidgetIds.forEach { id ->
            bind(context, appWidgetManager, id)
            refresh(context, id)
        }
    }

    override fun onDeleted(context: Context, appWidgetIds: IntArray) {
        val store = WidgetStore(context)
        appWidgetIds.forEach(store::drop)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        val widgetId = intent.getIntExtra(
            AppWidgetManager.EXTRA_APPWIDGET_ID,
            AppWidgetManager.INVALID_APPWIDGET_ID,
        )
        when (intent.action) {
            WidgetIntents.ACTION_CYCLE -> if (widgetId != AppWidgetManager.INVALID_APPWIDGET_ID) {
                val store = WidgetStore(context)
                store.setMode(widgetId, store.mode(widgetId).next())
                refresh(context, widgetId)
            }
            WidgetIntents.ACTION_REFRESH -> if (widgetId != AppWidgetManager.INVALID_APPWIDGET_ID) {
                refresh(context, widgetId)
            }
            WidgetIntents.ACTION_ITEM -> handleItem(context, intent, widgetId)
        }
    }

    private fun handleItem(context: Context, intent: Intent, widgetId: Int) {
        when (intent.getStringExtra(WidgetIntents.EXTRA_ITEM_ACTION)) {
            WidgetIntents.TOGGLE -> {
                val key = intent.getStringExtra(WidgetIntents.EXTRA_GROUP_KEY) ?: return
                WidgetStore(context).toggleExpanded(widgetId, key)
                notifyList(context, widgetId)
            }
            WidgetIntents.WATCH -> {
                val confirm = Intent(context, WidgetConfirmActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    putExtras(intent)
                    putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
                }
                context.startActivity(confirm)
            }
            WidgetIntents.OPEN -> {
                val kind = intent.getStringExtra(WidgetIntents.EXTRA_KIND)
                val mediaType = intent.getStringExtra(WidgetIntents.EXTRA_MEDIA_TYPE)
                val traktId = intent.getIntExtra(WidgetIntents.EXTRA_TRAKT_ID, 0).takeIf { it > 0 }
                val dest = when {
                    kind == "group" || mediaType == "show" || mediaType == "movie" -> "detail"
                    kind == "alert" || kind == "child" -> if (mediaType != null && traktId != null) "detail" else "alerts"
                    else -> WidgetStore(context).mode(widgetId).api
                }
                context.startActivity(WidgetIntents.openApp(context, dest, mediaType, traktId))
            }
        }
    }

    private fun refresh(context: Context, widgetId: Int) {
        val pending = goAsync()
        widgetScope.launch {
            try {
                WidgetRepository.refresh(context, widgetId)
                val manager = AppWidgetManager.getInstance(context)
                bind(context, manager, widgetId)
                manager.notifyAppWidgetViewDataChanged(widgetId, R.id.widget_list)
            } finally {
                pending.finish()
            }
        }
    }

    companion object {
        fun requestRefresh(context: Context) {
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, TrackerWidgetProvider::class.java))
            if (ids.isEmpty()) return
            val intent = Intent(context, TrackerWidgetProvider::class.java).apply {
                action = AppWidgetManager.ACTION_APPWIDGET_UPDATE
                putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, ids)
            }
            context.sendBroadcast(intent)
        }

        fun notifyList(context: Context, widgetId: Int) {
            AppWidgetManager.getInstance(context)
                .notifyAppWidgetViewDataChanged(widgetId, R.id.widget_list)
        }

        fun bind(context: Context, manager: AppWidgetManager, widgetId: Int) {
            val store = WidgetStore(context)
            val mode = store.mode(widgetId)
            val views = RemoteViews(context.packageName, R.layout.widget_root)
            views.setTextViewText(
                R.id.widget_title,
                context.getString(R.string.widget_header_title, context.getString(R.string.app_name), mode.title),
            )
            val empty = store.message(widgetId) ?: context.getString(R.string.widget_empty)
            views.setTextViewText(R.id.widget_empty, empty)
            views.setViewVisibility(
                R.id.widget_empty,
                if (store.items(widgetId).isEmpty()) View.VISIBLE else View.GONE,
            )
            val service = Intent(context, TrackerWidgetService::class.java).apply {
                putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
                data = Uri.parse("tvtracker-widget://list/$widgetId")
            }
            views.setRemoteAdapter(R.id.widget_list, service)
            views.setEmptyView(R.id.widget_list, R.id.widget_empty)
            views.setPendingIntentTemplate(R.id.widget_list, WidgetIntents.itemTemplate(context, widgetId))
            views.setOnClickPendingIntent(R.id.widget_mode, WidgetIntents.providerIntent(context, WidgetIntents.ACTION_CYCLE, widgetId))
            views.setOnClickPendingIntent(R.id.widget_refresh, WidgetIntents.providerIntent(context, WidgetIntents.ACTION_REFRESH, widgetId))
            val openTab = WidgetIntents.openApp(context, mode.api)
            views.setOnClickPendingIntent(
                R.id.widget_brand,
                PendingIntent.getActivity(
                    context,
                    widgetId + 1000,
                    openTab,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                ),
            )
            manager.updateAppWidget(widgetId, views)
        }
    }
}
