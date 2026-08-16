package com.melamoud.tvtracker.data.api

import com.melamoud.tvtracker.data.api.dto.ActionRequest
import com.melamoud.tvtracker.data.api.dto.AlertsResponse
import com.melamoud.tvtracker.data.api.dto.AuthCompleteRequest
import com.melamoud.tvtracker.data.api.dto.AuthStartResponse
import com.melamoud.tvtracker.data.api.dto.FavoriteResponse
import com.melamoud.tvtracker.data.api.dto.ListsResponse
import com.melamoud.tvtracker.data.api.dto.MeResponse
import com.melamoud.tvtracker.data.api.dto.MyMediaResponse
import com.melamoud.tvtracker.data.api.dto.PinResponse
import com.melamoud.tvtracker.data.api.dto.ProgressResponse
import com.melamoud.tvtracker.data.api.dto.RatingResponse
import com.melamoud.tvtracker.data.api.dto.SearchResponse
import com.melamoud.tvtracker.data.api.dto.SimpleResponse
import com.melamoud.tvtracker.data.api.dto.WatchedResponse
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface TvTrackerApi {
    @GET("/api/v1/auth/start")
    suspend fun authStart(): AuthStartResponse

    @POST("/api/v1/auth/complete")
    suspend fun authComplete(@Body body: AuthCompleteRequest): MeResponse

    @POST("/api/v1/logout")
    suspend fun logout(): SimpleResponse

    @GET("/api/v1/me")
    suspend fun me(): MeResponse

    @GET("/api/v1/my/{kind}")
    suspend fun myMedia(
        @Path("kind") kind: String,
        @Query("filter") filter: String? = null,
        @Query("avail") avail: String? = null,
        @Query("q") query: String? = null,
        @Query("display") display: String? = null,
        @Query("page") page: Int = 1,
        @Query("per_page") perPage: Int? = null,
        @Query("refresh") refresh: Int? = null,
        @Query("lists_set") listsSet: Int? = null,
        @Query("lists") lists: List<String>? = null,
    ): MyMediaResponse

    @GET("/api/v1/search")
    suspend fun search(
        @Query("q") query: String,
        @Query("type") type: String = "both",
        @Query("page") page: Int = 1,
        @Query("hide_watched") hideWatched: Int? = null,
        @Query("hide_lists") hideLists: Int? = null,
        @Query("year") year: String? = null,
        @Query("genre") genre: List<String>? = null,
        @Query("genres_set") genresSet: Int? = null,
    ): SearchResponse

    @GET("/api/v1/shows/{traktId}/progress")
    suspend fun progress(
        @Path("traktId") traktId: Int,
        @Query("refresh") refresh: Int? = null,
    ): ProgressResponse

    @GET("/api/v1/alerts")
    suspend fun alerts(
        @Query("hide_read") hideRead: Int? = null,
    ): AlertsResponse

    @POST("/api/v1/alerts/read-all")
    suspend fun alertsReadAll(): SimpleResponse

    @POST("/api/v1/alerts/{id}/read")
    suspend fun alertRead(@Path("id") id: Int): SimpleResponse

    @POST("/api/v1/alerts/{id}/unread")
    suspend fun alertUnread(@Path("id") id: Int): SimpleResponse

    @POST("/api/v1/pin/{mediaType}/{traktId}")
    suspend fun pin(
        @Path("mediaType") mediaType: String,
        @Path("traktId") traktId: Int,
        @Body body: ActionRequest,
    ): PinResponse

    @POST("/api/v1/watched/{mediaType}/{traktId}")
    suspend fun watched(
        @Path("mediaType") mediaType: String,
        @Path("traktId") traktId: Int,
        @Body body: ActionRequest,
    ): WatchedResponse

    @POST("/api/v1/rating/{mediaType}/{traktId}")
    suspend fun rating(
        @Path("mediaType") mediaType: String,
        @Path("traktId") traktId: Int,
        @Body body: ActionRequest,
    ): RatingResponse

    @POST("/api/v1/favorite/{mediaType}/{traktId}")
    suspend fun favorite(
        @Path("mediaType") mediaType: String,
        @Path("traktId") traktId: Int,
        @Body body: ActionRequest,
    ): FavoriteResponse

    @GET("/api/v1/lists/membership/{mediaType}/{traktId}")
    suspend fun listsGet(
        @Path("mediaType") mediaType: String,
        @Path("traktId") traktId: Int,
    ): ListsResponse

    @POST("/api/v1/lists/membership/{mediaType}/{traktId}")
    suspend fun listsSet(
        @Path("mediaType") mediaType: String,
        @Path("traktId") traktId: Int,
        @Body body: ActionRequest,
    ): ListsResponse

    @POST("/api/v1/episode/watched")
    suspend fun episodeWatched(@Body body: ActionRequest): WatchedResponse

    @POST("/api/v1/shows/{traktId}/seasons/{season}/watched")
    suspend fun seasonWatched(
        @Path("traktId") traktId: Int,
        @Path("season") season: Int,
    ): WatchedResponse

    @POST("/api/v1/shows/{traktId}/seasons/{season}/unwatched")
    suspend fun seasonUnwatched(
        @Path("traktId") traktId: Int,
        @Path("season") season: Int,
    ): WatchedResponse
}
