package com.melamoud.tvtracker.data.api.dto

import com.google.gson.annotations.SerializedName

data class UserDto(
    val id: Int,
    val username: String,
    @SerializedName("is_admin") val isAdmin: Boolean = false,
    @SerializedName("csrf_token") val csrfToken: String? = null,
    @SerializedName("unread_alerts") val unreadAlerts: Int = 0,
)

data class SimpleResponse(
    val success: Boolean,
    val message: String? = null,
)

data class AuthStartResponse(
    val success: Boolean,
    val message: String? = null,
    @SerializedName("authorize_url") val authorizeUrl: String? = null,
)

data class AuthCompleteRequest(
    val token: String,
)

data class MeResponse(
    val success: Boolean,
    val message: String? = null,
    val user: UserDto? = null,
)

data class AvailDto(
    val upcoming: Boolean = false,
    val theater: Boolean = false,
    val streaming: Boolean = false,
    @SerializedName("on_my_services") val onMyServices: Boolean = false,
    @SerializedName("released_at") val releasedAt: String? = null,
)

data class AvailChipDto(
    val kind: String? = null,
    val label: String? = null,
)

data class NextEpDto(
    val date: String? = null,
    val label: String? = null,
    val title: String? = null,
)

data class MediaItemDto(
    @SerializedName("media_type") val mediaType: String? = null,
    @SerializedName("trakt_id") val traktId: Int = 0,
    val title: String = "",
    val year: Int? = null,
    val overview: String? = null,
    @SerializedName("poster_url") val posterUrl: String? = null,
    val genres: List<String> = emptyList(),
    val watched: Boolean = false,
    @SerializedName("on_watchlist") val onWatchlist: Boolean = false,
    @SerializedName("list_names") val listNames: List<String> = emptyList(),
    val pinned: Boolean = false,
    val rating: Int? = null,
    val favorited: Boolean = false,
    @SerializedName("progress_percent") val progressPercent: Double? = null,
    @SerializedName("episodes_aired") val episodesAired: Int? = null,
    @SerializedName("episodes_completed") val episodesCompleted: Int? = null,
    @SerializedName("next_episode_season") val nextEpisodeSeason: Int? = null,
    @SerializedName("next_episode_number") val nextEpisodeNumber: Int? = null,
    @SerializedName("next_episode_title") val nextEpisodeTitle: String? = null,
    @SerializedName("next_ep") val nextEp: NextEpDto? = null,
    @SerializedName("my_providers") val myProviders: List<String> = emptyList(),
    @SerializedName("other_providers") val otherProviders: List<String> = emptyList(),
    @SerializedName("found_on") val foundOn: List<String> = emptyList(),
    val avail: AvailDto? = null,
    @SerializedName("avail_chips") val availChips: List<AvailChipDto> = emptyList(),
    @SerializedName("imdb_id") val imdbId: String? = null,
    @SerializedName("trailer_url") val trailerUrl: String? = null,
    val slug: String? = null,
    val network: String? = null,
    val runtime: Int? = null,
)

data class FilterListDto(
    val id: String,
    val name: String,
    val kind: String? = null,
    val selected: Boolean = false,
)

data class MyMediaResponse(
    val success: Boolean,
    val message: String? = null,
    @SerializedName("media_type") val mediaType: String? = null,
    val items: List<MediaItemDto> = emptyList(),
    val filter: String? = null,
    @SerializedName("filter_lists") val filterLists: List<FilterListDto> = emptyList(),
    @SerializedName("selected_lists") val selectedLists: List<String> = emptyList(),
    @SerializedName("selected_names") val selectedNames: List<String> = emptyList(),
    val page: Int = 1,
    val pages: Int = 1,
    @SerializedName("per_page") val perPage: Int = 50,
    val total: Int = 0,
    val q: String? = null,
    val avail: String? = null,
    val display: String? = null,
    val title: String? = null,
)

data class SearchResponse(
    val success: Boolean,
    val message: String? = null,
    val q: String? = null,
    @SerializedName("search_type") val searchType: String? = null,
    val items: List<MediaItemDto> = emptyList(),
    val page: Int = 1,
    val pages: Int = 1,
    @SerializedName("per_page") val perPage: Int = 20,
    val total: Int = 0,
    @SerializedName("hide_watched") val hideWatched: Boolean = true,
    @SerializedName("hide_lists") val hideLists: Boolean = true,
    @SerializedName("fetch_error") val fetchError: String? = null,
)

data class EpisodeIdsDto(
    val trakt: Int? = null,
    val tvdb: Int? = null,
    val imdb: String? = null,
    val tmdb: Int? = null,
)

data class EpisodeDto(
    val number: Int = 0,
    val title: String? = null,
    val ids: EpisodeIdsDto? = null,
    @SerializedName("trakt_id") val traktId: Int? = null,
    val watched: Boolean = false,
    val aired: Boolean = true,
    @SerializedName("air_label") val airLabel: String? = null,
)

data class SeasonDto(
    val number: Int = 0,
    val label: String? = null,
    @SerializedName("is_specials") val isSpecials: Boolean = false,
    val episodes: List<EpisodeDto> = emptyList(),
    @SerializedName("all_watched") val allWatched: Boolean = false,
    val aired: Int = 0,
    val completed: Int = 0,
    @SerializedName("default_open") val defaultOpen: Boolean = false,
)

data class NextEpisodeDto(
    val season: Int? = null,
    val number: Int? = null,
    val title: String? = null,
    val ids: EpisodeIdsDto? = null,
)

data class ProgressResponse(
    val success: Boolean,
    val message: String? = null,
    @SerializedName("trakt_id") val traktId: Int = 0,
    val title: String? = null,
    @SerializedName("poster_url") val posterUrl: String? = null,
    @SerializedName("progress_aired") val progressAired: Int = 0,
    @SerializedName("progress_completed") val progressCompleted: Int = 0,
    @SerializedName("next_episode") val nextEpisode: NextEpisodeDto? = null,
    val seasons: List<SeasonDto> = emptyList(),
)

data class AlertItemDto(
    val id: Int = 0,
    @SerializedName("alert_type") val alertType: String? = null,
    @SerializedName("type_label") val typeLabel: String? = null,
    val title: String = "",
    val message: String? = null,
    val link: String? = null,
    @SerializedName("media_type") val mediaType: String? = null,
    @SerializedName("trakt_id") val traktId: Int? = null,
    @SerializedName("payload_key") val payloadKey: String? = null,
    @SerializedName("is_read") val isRead: Boolean = false,
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("poster_url") val posterUrl: String? = null,
    @SerializedName("media_title") val mediaTitle: String? = null,
    @SerializedName("my_providers") val myProviders: List<String> = emptyList(),
    @SerializedName("other_providers") val otherProviders: List<String> = emptyList(),
    @SerializedName("found_on") val foundOn: List<String> = emptyList(),
)

data class AlertsResponse(
    val success: Boolean,
    val message: String? = null,
    @SerializedName("unread_count") val unreadCount: Int = 0,
    @SerializedName("hide_read") val hideRead: Boolean = true,
    val items: List<AlertItemDto> = emptyList(),
)

data class ActionRequest(
    val action: String? = null,
    val rating: Int? = null,
    val selected: List<String>? = null,
    val ids: Map<String, Any>? = null,
    @SerializedName("show_trakt_id") val showTraktId: Int? = null,
    val season: Int? = null,
    val episode: Int? = null,
)

data class PinResponse(
    val success: Boolean,
    val message: String? = null,
    val pinned: Boolean = false,
)

data class WatchedResponse(
    val success: Boolean,
    val message: String? = null,
    val watched: Boolean = false,
    val added: Int? = null,
    val deleted: Int? = null,
    val season: Int? = null,
)

data class RatingResponse(
    val success: Boolean,
    val message: String? = null,
    val rating: Int? = null,
)

data class FavoriteResponse(
    val success: Boolean,
    val message: String? = null,
    val favorited: Boolean = false,
)

data class ListMembershipDto(
    val id: String,
    val name: String,
    val kind: String? = null,
    val selected: Boolean = false,
    @SerializedName("on_list") val onList: Boolean = false,
)

data class ListsResponse(
    val success: Boolean,
    val message: String? = null,
    val title: String? = null,
    val lists: List<ListMembershipDto> = emptyList(),
    val defaults: List<String> = emptyList(),
    @SerializedName("on_watchlist") val onWatchlist: Boolean? = null,
    val selected: List<String>? = null,
)
