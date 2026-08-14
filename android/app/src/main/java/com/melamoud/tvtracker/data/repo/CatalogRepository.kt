package com.melamoud.tvtracker.data.repo

import com.melamoud.tvtracker.data.api.AuthLog
import com.melamoud.tvtracker.data.api.TvTrackerApi
import com.melamoud.tvtracker.data.api.dto.ActionRequest
import com.melamoud.tvtracker.data.api.dto.AlertsResponse
import com.melamoud.tvtracker.data.api.dto.ListsResponse
import com.melamoud.tvtracker.data.api.dto.MyMediaResponse
import com.melamoud.tvtracker.data.api.dto.ProgressResponse
import com.melamoud.tvtracker.data.api.dto.SearchResponse

class CatalogRepository(private val api: TvTrackerApi) {
    suspend fun myMedia(
        kind: String,
        filter: String? = null,
        avail: String? = null,
        query: String? = null,
        display: String? = null,
        page: Int = 1,
        refresh: Boolean = false,
        lists: List<String>? = null,
    ): Result<MyMediaResponse> = runCatching {
        api.myMedia(
            kind = kind,
            filter = filter,
            avail = avail,
            query = query?.takeIf { it.length >= 2 },
            display = display,
            page = page,
            refresh = if (refresh) 1 else null,
            listsSet = if (lists != null) 1 else null,
            lists = lists,
        )
    }.recoverCatching { e ->
        throw IllegalStateException(AuthLog.userMessage(e), e)
    }

    suspend fun search(
        query: String,
        type: String,
        page: Int,
        hideWatched: Boolean,
        hideLists: Boolean,
    ): Result<SearchResponse> = runCatching {
        api.search(
            query = query,
            type = type,
            page = page,
            hideWatched = if (hideWatched) 1 else 0,
            hideLists = if (hideLists) 1 else 0,
        )
    }.recoverCatching { e ->
        throw IllegalStateException(AuthLog.userMessage(e), e)
    }

    suspend fun progress(traktId: Int, refresh: Boolean = false): Result<ProgressResponse> =
        runCatching { api.progress(traktId, if (refresh) 1 else null) }
            .recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun unreadAlerts(): Int =
        runCatching { api.me().user?.unreadAlerts ?: 0 }.getOrDefault(0)

    suspend fun alerts(hideRead: Boolean): Result<AlertsResponse> =
        runCatching { api.alerts(if (hideRead) 1 else 0) }
            .recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun alertRead(id: Int, read: Boolean) = runCatching {
        if (read) api.alertRead(id) else api.alertUnread(id)
    }

    suspend fun alertsReadAll() = runCatching { api.alertsReadAll() }

    suspend fun pin(mediaType: String, traktId: Int, pin: Boolean) = runCatching {
        api.pin(mediaType, traktId, ActionRequest(action = if (pin) "pin" else "unpin"))
    }

    suspend fun watched(mediaType: String, traktId: Int, watched: Boolean) = runCatching {
        api.watched(mediaType, traktId, ActionRequest(action = if (watched) "add" else "remove"))
    }

    suspend fun rating(mediaType: String, traktId: Int, rating: Int?) = runCatching {
        api.rating(mediaType, traktId, ActionRequest(rating = rating, action = if (rating == null) "clear" else null))
    }

    suspend fun favorite(mediaType: String, traktId: Int, favorite: Boolean) = runCatching {
        api.favorite(mediaType, traktId, ActionRequest(action = if (favorite) "add" else "remove"))
    }

    suspend fun listsGet(mediaType: String, traktId: Int): Result<ListsResponse> =
        runCatching { api.listsGet(mediaType, traktId) }

    suspend fun listsSet(mediaType: String, traktId: Int, selected: List<String>): Result<ListsResponse> =
        runCatching { api.listsSet(mediaType, traktId, ActionRequest(selected = selected)) }

    suspend fun episodeWatched(
        ids: Map<String, Any>,
        showTraktId: Int,
        season: Int,
        episode: Int,
        watched: Boolean,
    ) = runCatching {
        api.episodeWatched(
            ActionRequest(
                action = if (watched) "add" else "remove",
                ids = ids,
                showTraktId = showTraktId,
                season = season,
                episode = episode,
            )
        )
    }

    suspend fun seasonWatched(traktId: Int, season: Int, watched: Boolean) = runCatching {
        if (watched) api.seasonWatched(traktId, season) else api.seasonUnwatched(traktId, season)
    }
}
