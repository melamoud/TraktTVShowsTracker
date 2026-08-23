package com.melamoud.tvtracker.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import com.melamoud.tvtracker.MainActivity
import com.melamoud.tvtracker.data.api.dto.WidgetItemDto

object WidgetIntents {
    const val ACTION_CYCLE = "com.melamoud.tvtracker.widget.CYCLE"
    const val ACTION_REFRESH = "com.melamoud.tvtracker.widget.REFRESH"
    const val ACTION_ITEM = "com.melamoud.tvtracker.widget.ITEM"
    const val EXTRA_ITEM_ACTION = "item_action"
    const val EXTRA_ITEM_ID = "item_id"
    const val EXTRA_GROUP_KEY = "group_key"
    const val EXTRA_KIND = "kind"
    const val EXTRA_TITLE = "title"
    const val EXTRA_MEDIA_TYPE = "media_type"
    const val EXTRA_TRAKT_ID = "trakt_id"
    const val EXTRA_SEASON = "season"
    const val EXTRA_EPISODE = "episode"
    const val EXTRA_EPISODE_TRAKT = "episode_trakt"
    const val OPEN = "open"
    const val WATCH = "watch"
    const val TOGGLE = "toggle"

    fun providerIntent(context: Context, action: String, widgetId: Int): PendingIntent {
        val intent = Intent(context, TrackerWidgetProvider::class.java).apply {
            this.action = action
            putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
            data = Uri.parse("tvtracker-widget://$action/$widgetId")
        }
        return PendingIntent.getBroadcast(
            context,
            widgetId * 10 + action.hashCode(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
        )
    }

    fun itemTemplate(context: Context, widgetId: Int): PendingIntent {
        val intent = Intent(context, TrackerWidgetProvider::class.java).apply {
            action = ACTION_ITEM
            putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
            data = Uri.parse("tvtracker-widget://item/$widgetId")
        }
        return PendingIntent.getBroadcast(
            context,
            widgetId,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
        )
    }

    fun fillOpen(item: WidgetItemDto): Intent {
        return Intent().apply {
            putExtra(EXTRA_ITEM_ACTION, OPEN)
            putExtra(EXTRA_KIND, item.kind)
            putExtra(EXTRA_MEDIA_TYPE, item.mediaType)
            putExtra(EXTRA_TRAKT_ID, item.traktId ?: 0)
        }
    }

    fun fillWatch(item: WidgetItemDto): Intent {
        return Intent().apply {
            putExtra(EXTRA_ITEM_ACTION, WATCH)
            putExtra(EXTRA_KIND, item.kind)
            putExtra(EXTRA_TITLE, item.title)
            putExtra(EXTRA_MEDIA_TYPE, item.mediaType)
            putExtra(EXTRA_TRAKT_ID, item.traktId ?: 0)
            putExtra(EXTRA_SEASON, item.season ?: -1)
            putExtra(EXTRA_EPISODE, item.episode ?: -1)
            putExtra(EXTRA_EPISODE_TRAKT, item.episodeIds?.trakt ?: 0)
        }
    }

    fun fillToggle(item: WidgetItemDto): Intent {
        return Intent().apply {
            putExtra(EXTRA_ITEM_ACTION, TOGGLE)
            putExtra(EXTRA_GROUP_KEY, item.groupKey)
        }
    }

    fun openApp(context: Context, dest: String, mediaType: String? = null, traktId: Int? = null): Intent {
        val path = buildString {
            append("tvtracker://open/")
            append(dest)
            if (!mediaType.isNullOrBlank() && traktId != null && traktId > 0) {
                append('/')
                append(mediaType)
                append('/')
                append(traktId)
            } else if (traktId != null && traktId > 0) {
                append('/')
                append(traktId)
            }
        }
        return Intent(Intent.ACTION_VIEW, Uri.parse(path), context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
    }
}
