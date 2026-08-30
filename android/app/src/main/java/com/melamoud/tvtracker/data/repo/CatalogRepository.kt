package com.melamoud.tvtracker.data.repo

import com.melamoud.tvtracker.data.api.AuthLog
import com.melamoud.tvtracker.data.api.TvTrackerApi
import com.melamoud.tvtracker.data.api.dto.ActionRequest
import com.melamoud.tvtracker.data.api.dto.AlertsResponse
import com.melamoud.tvtracker.data.api.dto.CommentResponse
import com.melamoud.tvtracker.data.api.dto.FavoriteActorResponse
import com.melamoud.tvtracker.data.api.dto.FeedbackResponse
import com.melamoud.tvtracker.data.api.dto.FoundOnChoicesResponse
import com.melamoud.tvtracker.data.api.dto.FoundOnResponse
import com.melamoud.tvtracker.data.api.dto.LatestMediaResponse
import com.melamoud.tvtracker.data.api.dto.ListsResponse
import com.melamoud.tvtracker.data.api.dto.MediaDetailResponse
import com.melamoud.tvtracker.data.api.dto.MyMediaResponse
import com.melamoud.tvtracker.data.api.dto.PreferencesResponse
import com.melamoud.tvtracker.data.api.dto.PreferencesSaveRequest
import com.melamoud.tvtracker.data.api.dto.ProgressResponse
import com.melamoud.tvtracker.data.api.dto.RecommendedMediaResponse
import com.melamoud.tvtracker.data.api.dto.SearchResponse
import com.melamoud.tvtracker.data.api.dto.SimpleResponse
import com.melamoud.tvtracker.data.api.dto.SyncCatalogResponse
import com.melamoud.tvtracker.data.api.dto.WidgetResponse

class CatalogRepository(private val api: TvTrackerApi) {
    suspend fun preferences(): Result<PreferencesResponse> =
        runCatching { api.preferences() }
            .recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun savePreferences(body: PreferencesSaveRequest): Result<SimpleResponse> =
        runCatching { api.savePreferences(body) }

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
        hideWatched: Boolean? = null,
        hideLists: Boolean? = null,
        year: String? = null,
        genres: List<String>? = null,
        persistGenres: Boolean = false,
        actor: Int? = null,
        actorQ: String? = null,
    ): Result<SearchResponse> = runCatching {
        api.search(
            query = query,
            type = type,
            page = page,
            hideWatched = hideWatched?.let { if (it) 1 else 0 },
            hideLists = hideLists?.let { if (it) 1 else 0 },
            year = year,
            genre = genres?.takeIf { persistGenres },
            genresSet = if (persistGenres) 1 else null,
            actor = actor,
            actorQ = actorQ,
        )
    }.recoverCatching { e ->
        throw IllegalStateException(AuthLog.userMessage(e), e)
    }

    suspend fun progress(traktId: Int, refresh: Boolean = false): Result<ProgressResponse> =
        runCatching { api.progress(traktId, if (refresh) 1 else null) }
            .recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun widget(mode: String): Result<WidgetResponse> =
        runCatching { api.widget(mode) }
            .recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun unreadAlerts(): Int =
        runCatching { api.me().user?.unreadAlerts ?: 0 }.getOrDefault(0)

    suspend fun alerts(
        hideRead: Boolean? = null,
        sort: String? = null,
        groupShows: Boolean? = null,
    ): Result<AlertsResponse> =
        runCatching {
            api.alerts(
                hideRead?.let { if (it) 1 else 0 },
                sort,
                groupShows?.let { if (it) 1 else 0 },
            )
        }
            .recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun alertRead(id: Int, read: Boolean) = runCatching {
        if (read) api.alertRead(id) else api.alertUnread(id)
    }

    suspend fun alertsReadAll() = runCatching { api.alertsReadAll() }

    suspend fun pin(mediaType: String, traktId: Int, pin: Boolean) = runCatching {
        api.pin(mediaType, traktId, ActionRequest(action = if (pin) "pin" else "unpin"))
    }

    suspend fun alertsPin(mediaType: String, traktId: Int, pin: Boolean) = runCatching {
        api.alertsPin(mediaType, traktId, ActionRequest(action = if (pin) "pin" else "unpin"))
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

    suspend fun catalogDetail(mediaType: String, traktId: Int): Result<MediaDetailResponse> =
        runCatching { api.catalogDetail(mediaType, traktId) }
            .recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun foundOnChoices(title: String? = null, year: Int? = null): Result<FoundOnChoicesResponse> =
        runCatching { api.foundOnChoices(title, year) }
            .recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun foundOn(mediaType: String, traktId: Int, labels: List<String>): Result<FoundOnResponse> =
        runCatching { api.foundOn(mediaType, traktId, ActionRequest(serviceLabels = labels)) }
            .recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun favoriteActor(personId: Int, favorite: Boolean): Result<FavoriteActorResponse> =
        runCatching {
            api.favoriteActor(personId, ActionRequest(action = if (favorite) "add" else "remove"))
        }.recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun feedback(mediaType: String, traktId: Int): Result<FeedbackResponse> =
        runCatching { api.feedback(mediaType, traktId) }
            .recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun comment(
        mediaType: String,
        traktId: Int,
        text: String,
        spoiler: Boolean,
        commentId: Int?,
    ): Result<CommentResponse> =
        runCatching {
            api.comment(
                mediaType,
                traktId,
                ActionRequest(comment = text, spoiler = spoiler, commentId = commentId),
            )
        }.recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun latestMedia(
        kind: String,
        query: String? = null,
        page: Int = 1,
        avail: String? = null,
        hideWatched: Boolean? = null,
        hideLists: Boolean? = null,
        matchOnly: Boolean? = null,
        recentYears: Boolean? = null,
        perPage: Int? = null,
        loadOlder: Boolean? = null,
    ): Result<LatestMediaResponse> = runCatching {
        api.latestMedia(
            kind = kind,
            query = query?.takeIf { it.length >= 2 },
            page = page,
            avail = avail,
            hideWatched = hideWatched?.let { if (it) 1 else 0 },
            hideLists = hideLists?.let { if (it) 1 else 0 },
            matchOnly = matchOnly?.let { if (it) 1 else 0 },
            recentYears = recentYears?.let { if (it) 1 else 0 },
            perPage = perPage,
            loadOlder = loadOlder?.let { if (it) 1 else 0 },
        )
    }.recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun recommendations(
        kind: String,
        query: String? = null,
        page: Int = 1,
        avail: String? = null,
        category: String? = null,
        hideWatched: Boolean? = null,
        hideWishlist: Boolean? = null,
        onMyServices: Boolean? = null,
        matchOnly: Boolean? = null,
        perPage: Int? = null,
    ): Result<RecommendedMediaResponse> = runCatching {
        api.recommendations(
            kind = kind,
            query = query?.takeIf { it.length >= 2 },
            page = page,
            avail = avail,
            category = category,
            hideWatched = hideWatched?.let { if (it) 1 else 0 },
            hideWishlist = hideWishlist?.let { if (it) 1 else 0 },
            onMyServices = onMyServices?.let { if (it) 1 else 0 },
            matchOnly = matchOnly?.let { if (it) 1 else 0 },
            perPage = perPage,
        )
    }.recoverCatching { e -> throw IllegalStateException(AuthLog.userMessage(e), e) }

    suspend fun reviewMarkerSet(mediaType: String, traktId: Int) = runCatching {
        api.reviewMarkerSet(mediaType, traktId)
    }

    suspend fun reviewMarkerClear(mediaType: String) = runCatching {
        api.reviewMarkerClear(mediaType)
    }

    suspend fun reviewMarkerCaughtUp(mediaType: String) = runCatching {
        api.reviewMarkerCaughtUp(mediaType)
    }

    suspend fun syncCatalog(mediaType: String) = runCatching {
        api.syncCatalog(mediaType)
    }

    suspend fun hideRecommendation(mediaType: String, traktId: Int) = runCatching {
        api.hideRecommendation(mediaType, traktId)
    }
}
