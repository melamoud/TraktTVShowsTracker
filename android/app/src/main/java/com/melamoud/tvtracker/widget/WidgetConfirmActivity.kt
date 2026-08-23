package com.melamoud.tvtracker.widget

import android.app.AlertDialog
import android.appwidget.AppWidgetManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import com.melamoud.tvtracker.R
import com.melamoud.tvtracker.TvTrackerApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class WidgetConfirmActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val title = intent.getStringExtra(WidgetIntents.EXTRA_TITLE).orEmpty()
        val mediaType = intent.getStringExtra(WidgetIntents.EXTRA_MEDIA_TYPE)
        val traktId = intent.getIntExtra(WidgetIntents.EXTRA_TRAKT_ID, 0)
        val season = intent.getIntExtra(WidgetIntents.EXTRA_SEASON, -1).takeIf { it >= 0 }
        val episode = intent.getIntExtra(WidgetIntents.EXTRA_EPISODE, -1).takeIf { it >= 0 }
        val episodeTrakt = intent.getIntExtra(WidgetIntents.EXTRA_EPISODE_TRAKT, 0).takeIf { it > 0 }
        val widgetId = intent.getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID)
        val episodeLabel = if (season != null && episode != null) {
            listOfNotNull(title, "S${season}E$episode").joinToString(" ")
        } else title
        val message = if (mediaType == "show") {
            getString(R.string.widget_mark_episode, episodeLabel)
        } else {
            getString(R.string.widget_mark_movie, title)
        }
        AlertDialog.Builder(this)
            .setTitle(getString(R.string.mark_watched))
            .setMessage(message)
            .setPositiveButton(R.string.mark_watched) { _, _ ->
                CoroutineScope(Dispatchers.IO).launch {
                    val repo = TvTrackerApp.from(this@WidgetConfirmActivity).container.catalogRepository
                    if (mediaType == "show" && traktId > 0 && season != null && episode != null) {
                        val ids = linkedMapOf<String, Any>()
                        episodeTrakt?.let { ids["trakt"] = it }
                        repo.episodeWatched(ids, traktId, season, episode, true)
                    } else if (mediaType == "movie" && traktId > 0) {
                        repo.watched("movie", traktId, true)
                    }
                    if (widgetId != AppWidgetManager.INVALID_APPWIDGET_ID) {
                        WidgetRepository.refresh(this@WidgetConfirmActivity, widgetId)
                        withContext(Dispatchers.Main) {
                            TrackerWidgetProvider.bind(
                                this@WidgetConfirmActivity,
                                AppWidgetManager.getInstance(this@WidgetConfirmActivity),
                                widgetId,
                            )
                            TrackerWidgetProvider.notifyList(this@WidgetConfirmActivity, widgetId)
                        }
                    }
                    withContext(Dispatchers.Main) { finish() }
                }
            }
            .setNegativeButton(android.R.string.cancel) { _, _ -> finish() }
            .setOnCancelListener { finish() }
            .show()
    }
}
