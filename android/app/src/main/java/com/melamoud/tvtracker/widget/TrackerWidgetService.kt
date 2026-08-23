package com.melamoud.tvtracker.widget

import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.Intent
import android.view.View
import android.widget.RemoteViews
import android.widget.RemoteViewsService
import androidx.core.graphics.drawable.toBitmap
import coil.request.ImageRequest
import coil.request.SuccessResult
import com.melamoud.tvtracker.R
import kotlinx.coroutines.runBlocking
import com.melamoud.tvtracker.TvTrackerApp
import com.melamoud.tvtracker.data.api.absoluteUrl
import com.melamoud.tvtracker.data.api.dto.WidgetItemDto

class TrackerWidgetService : RemoteViewsService() {
    override fun onGetViewFactory(intent: Intent): RemoteViewsFactory {
        val widgetId = intent.getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID)
        return TrackerWidgetFactory(applicationContext, widgetId)
    }
}

private class TrackerWidgetFactory(
    private val context: Context,
    private val widgetId: Int,
) : RemoteViewsService.RemoteViewsFactory {
    private val store = WidgetStore(context)
    private var rows: List<WidgetItemDto> = emptyList()

    override fun onCreate() {}

    override fun onDataSetChanged() {
        rows = WidgetRepository.visibleRows(store, widgetId)
    }

    override fun onDestroy() {
        rows = emptyList()
    }

    override fun getCount(): Int = rows.size

    override fun getViewAt(position: Int): RemoteViews {
        val item = rows.getOrNull(position) ?: return RemoteViews(context.packageName, R.layout.widget_row)
        val views = RemoteViews(context.packageName, R.layout.widget_row)
        val child = item.kind == "child"
        views.setViewPadding(R.id.widget_row, if (child) 28 else 4, 4, 4, 4)
        views.setTextViewText(R.id.widget_row_title, item.title)
        views.setTextViewText(R.id.widget_row_subtitle, item.subtitle.orEmpty())
        views.setViewVisibility(
            R.id.widget_row_subtitle,
            if (item.subtitle.isNullOrBlank()) View.GONE else View.VISIBLE,
        )
        views.setTextViewText(R.id.widget_row_remaining, item.remainingLabel.orEmpty())
        views.setViewVisibility(
            R.id.widget_row_remaining,
            if (item.remainingLabel.isNullOrBlank()) View.GONE else View.VISIBLE,
        )
        views.setImageViewResource(R.id.widget_poster, R.drawable.widget_poster_bg)
        loadPoster(views, item.posterUrl)

        val expanded = item.groupKey != null && item.groupKey in store.expanded(widgetId)
        views.setViewVisibility(R.id.widget_expand, if (item.expandable) View.VISIBLE else View.GONE)
        if (item.expandable) {
            views.setImageViewResource(
                R.id.widget_expand,
                if (expanded) R.drawable.widget_collapse else R.drawable.widget_expand,
            )
            views.setOnClickFillInIntent(R.id.widget_expand, WidgetIntents.fillToggle(item))
        }
        views.setViewVisibility(R.id.widget_watch, if (item.canWatch) View.VISIBLE else View.GONE)
        if (item.canWatch) {
            views.setOnClickFillInIntent(R.id.widget_watch, WidgetIntents.fillWatch(item))
        }
        val open = WidgetIntents.fillOpen(item)
        views.setOnClickFillInIntent(R.id.widget_text, open)
        views.setOnClickFillInIntent(R.id.widget_poster, open)
        views.setOnClickFillInIntent(R.id.widget_row_title, open)
        return views
    }

    private fun loadPoster(views: RemoteViews, posterUrl: String?) {
        val url = absoluteUrl(TvTrackerApp.from(context).container.baseUrl, posterUrl) ?: return
        val bitmap = runBlocking {
            val result = TvTrackerApp.from(context).container.imageLoader.execute(
                ImageRequest.Builder(context)
                    .data(url)
                    .size(84, 124)
                    .allowHardware(false)
                    .build(),
            )
            (result as? SuccessResult)?.drawable?.toBitmap()
        } ?: return
        views.setImageViewBitmap(R.id.widget_poster, bitmap)
    }

    override fun getLoadingView(): RemoteViews? = null
    override fun getViewTypeCount(): Int = 1
    override fun getItemId(position: Int): Long = rows.getOrNull(position)?.id.hashCode().toLong()
    override fun hasStableIds(): Boolean = true
}
