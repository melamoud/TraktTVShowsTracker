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

data class ServiceLinkDto(
    val label: String = "",
    val url: String? = null,
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
    @SerializedName("last_episode_aired_at") val lastEpisodeAiredAt: String? = null,
    @SerializedName("last_episode_label") val lastEpisodeLabel: String? = null,
    @SerializedName("next_ep") val nextEp: NextEpDto? = null,
    @SerializedName("my_providers") val myProviders: List<String> = emptyList(),
    @SerializedName("other_providers") val otherProviders: List<String> = emptyList(),
    @SerializedName("found_on") val foundOn: List<String> = emptyList(),
    @SerializedName("found_on_links") val foundOnLinks: List<ServiceLinkDto> = emptyList(),
    @SerializedName("found_on_choice_links") val foundOnChoiceLinks: List<ServiceLinkDto> = emptyList(),
    @SerializedName("my_provider_links") val myProviderLinks: List<ServiceLinkDto> = emptyList(),
    @SerializedName("other_provider_links") val otherProviderLinks: List<ServiceLinkDto> = emptyList(),
    val avail: AvailDto? = null,
    @SerializedName("avail_chips") val availChips: List<AvailChipDto> = emptyList(),
    @SerializedName("imdb_id") val imdbId: String? = null,
    @SerializedName("trailer_url") val trailerUrl: String? = null,
    val slug: String? = null,
    val network: String? = null,
    val runtime: Int? = null,
    @SerializedName("is_marker") val isMarker: Boolean = false,
    @SerializedName("older_than_marker") val olderThanMarker: Boolean = false,
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
    val calendar: CalendarDto? = null,
    val title: String? = null,
    @SerializedName("found_on_choices") val foundOnChoices: List<String> = emptyList(),
)

data class ReviewMarkerDto(
    @SerializedName("trakt_id") val traktId: Int,
    val title: String,
    @SerializedName("listed_at") val listedAt: String? = null,
)

data class LatestMediaResponse(
    val success: Boolean,
    val message: String? = null,
    @SerializedName("media_type") val mediaType: String? = null,
    val items: List<MediaItemDto> = emptyList(),
    val page: Int = 1,
    val pages: Int = 1,
    @SerializedName("per_page") val perPage: Int = 50,
    val total: Int = 0,
    val q: String? = null,
    val avail: String? = null,
    val title: String? = null,
    @SerializedName("found_on_choices") val foundOnChoices: List<String> = emptyList(),
    @SerializedName("hide_watched") val hideWatched: Boolean = true,
    @SerializedName("hide_lists") val hideLists: Boolean = true,
    @SerializedName("match_only") val matchOnly: Boolean = false,
    @SerializedName("recent_years") val recentYears: Boolean = true,
    @SerializedName("has_more_older") val hasMoreOlder: Boolean = false,
    val marker: ReviewMarkerDto? = null,
    @SerializedName("marker_page") val markerPage: Int? = null,
)

data class SyncCatalogResponse(
    val success: Boolean,
    val message: String? = null,
    val count: Int? = null,
)

data class StreamingServiceDto(
    val id: Int,
    val name: String,
    val selected: Boolean = false,
)

data class CustomServiceDto(
    val id: Int = 0,
    val name: String,
    val url: String? = null,
    @SerializedName("search_template") val searchTemplate: String? = null,
    val note: String? = null,
)

data class PreferencesResponse(
    val success: Boolean,
    val message: String? = null,
    val defaults: List<StreamingServiceDto> = emptyList(),
    val customs: List<CustomServiceDto> = emptyList(),
    @SerializedName("common_genres") val commonGenres: List<String> = emptyList(),
    val genres: List<String> = emptyList(),
    val keywords: List<String> = emptyList(),
    @SerializedName("excluded_genres") val excludedGenres: List<String> = emptyList(),
    val alerts: AlertPrefsDto? = null,
    @SerializedName("favorite_actors") val favoriteActors: List<FavoriteActorDto> = emptyList(),
    @SerializedName("prefs_reminder_disabled") val prefsReminderDisabled: Boolean = false,
)

data class AlertPrefsDto(
    @SerializedName("release_day") val releaseDay: Boolean = true,
    @SerializedName("new_streaming") val newStreaming: Boolean = true,
    @SerializedName("episode_aired") val episodeAired: Boolean = true,
    @SerializedName("list_add") val listAdd: Boolean = true,
    @SerializedName("season_streaming") val seasonStreaming: Boolean = true,
    @SerializedName("favorite_actor") val favoriteActor: Boolean = true,
    @SerializedName("favorite_actor_match_only") val favoriteActorMatchOnly: Boolean = true,
    @SerializedName("new_user_login") val newUserLogin: Boolean = false,
)

data class FavoriteActorDto(
    @SerializedName("trakt_id") val traktId: Int,
    val name: String,
    @SerializedName("headshot_url") val headshotUrl: String? = null,
)

data class PreferencesSaveRequest(
    @SerializedName("service_ids") val serviceIds: List<Int> = emptyList(),
    @SerializedName("remove_custom_ids") val removeCustomIds: List<Int> = emptyList(),
    @SerializedName("custom_services") val customServices: List<CustomServiceDto> = emptyList(),
    val genres: List<String> = emptyList(),
    val keywords: List<String> = emptyList(),
    @SerializedName("excluded_genres") val excludedGenres: List<String> = emptyList(),
    val alerts: AlertPrefsDto? = null,
    @SerializedName("remove_favorite_actor_ids") val removeFavoriteActorIds: List<Int> = emptyList(),
    @SerializedName("prefs_reminder_disabled") val prefsReminderDisabled: Boolean? = null,
)

data class CategoryDto(
    val slug: String,
    val label: String,
)

data class RecommendedMediaResponse(
    val success: Boolean,
    val message: String? = null,
    @SerializedName("media_type") val mediaType: String? = null,
    val items: List<MediaItemDto> = emptyList(),
    val page: Int = 1,
    val pages: Int = 1,
    @SerializedName("per_page") val perPage: Int = 50,
    val total: Int = 0,
    val q: String? = null,
    val avail: String? = null,
    val title: String? = null,
    @SerializedName("found_on_choices") val foundOnChoices: List<String> = emptyList(),
    val categories: List<CategoryDto> = emptyList(),
    val category: String = "all",
    @SerializedName("hide_watched") val hideWatched: Boolean = true,
    @SerializedName("hide_wishlist") val hideWishlist: Boolean = true,
    @SerializedName("on_my_services") val onMyServices: Boolean = false,
    @SerializedName("match_only") val matchOnly: Boolean = false,
    @SerializedName("has_match_prefs") val hasMatchPrefs: Boolean = false,
    @SerializedName("user_service_names") val userServiceNames: List<String> = emptyList(),
    val genres: List<String> = emptyList(),
    val year: String? = null,
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
    val year: String? = null,
    val genres: List<String> = emptyList(),
    @SerializedName("genre_choices") val genreChoices: List<String> = emptyList(),
    @SerializedName("fetch_error") val fetchError: String? = null,
    @SerializedName("actor_q") val actorQ: String? = null,
    @SerializedName("actor_id") val actorId: Int? = null,
    @SerializedName("actor_name") val actorName: String? = null,
    @SerializedName("found_on_choices") val foundOnChoices: List<String> = emptyList(),
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
    val headline: String? = null,
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
    @SerializedName("found_on_links") val foundOnLinks: List<ServiceLinkDto> = emptyList(),
    @SerializedName("my_provider_links") val myProviderLinks: List<ServiceLinkDto> = emptyList(),
    @SerializedName("other_provider_links") val otherProviderLinks: List<ServiceLinkDto> = emptyList(),
    val year: Int? = null,
    @SerializedName("last_episode_aired_at") val lastEpisodeAiredAt: String? = null,
    @SerializedName("last_episode_label") val lastEpisodeLabel: String? = null,
    @SerializedName("kind_label") val kindLabel: String? = null,
    @SerializedName("episode_code") val episodeCode: String? = null,
    @SerializedName("display_title") val displayTitle: String? = null,
    @SerializedName("alerts_pinned") val alertsPinned: Boolean = false,
    val match: MatchDto? = null,
)

data class AlertEntryDto(
    val kind: String = "single",
    @SerializedName("media_type") val mediaType: String? = null,
    @SerializedName("trakt_id") val traktId: Int? = null,
    val title: String? = null,
    @SerializedName("poster_url") val posterUrl: String? = null,
    @SerializedName("kind_label") val kindLabel: String? = null,
    @SerializedName("alerts_pinned") val alertsPinned: Boolean = false,
    @SerializedName("episode_codes") val episodeCodes: List<String> = emptyList(),
    @SerializedName("unread_count") val unreadCount: Int = 0,
    val items: List<AlertItemDto> = emptyList(),
    val item: AlertItemDto? = null,
)

data class AlertsResponse(
    val success: Boolean,
    val message: String? = null,
    @SerializedName("unread_count") val unreadCount: Int = 0,
    @SerializedName("hide_read") val hideRead: Boolean = true,
    val sort: String = "desc",
    @SerializedName("group_shows") val groupShows: Boolean = true,
    val items: List<AlertItemDto> = emptyList(),
    val entries: List<AlertEntryDto> = emptyList(),
)

data class ActionRequest(
    val action: String? = null,
    val rating: Int? = null,
    val selected: List<String>? = null,
    val ids: Map<String, Any>? = null,
    @SerializedName("show_trakt_id") val showTraktId: Int? = null,
    val season: Int? = null,
    val episode: Int? = null,
    @SerializedName("service_labels") val serviceLabels: List<String>? = null,
    val comment: String? = null,
    val spoiler: Boolean? = null,
    @SerializedName("comment_id") val commentId: Int? = null,
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

data class MatchDto(
    val matched: Boolean = false,
    val genres: List<String> = emptyList(),
    val keywords: List<String> = emptyList(),
)

data class CastMemberDto(
    @SerializedName("trakt_id") val traktId: Int = 0,
    val name: String = "",
    val characters: List<String> = emptyList(),
    @SerializedName("episode_count") val episodeCount: Int? = null,
    val favorited: Boolean = false,
    @SerializedName("headshot_url") val headshotUrl: String? = null,
)

data class MediaDetailResponse(
    val success: Boolean,
    val message: String? = null,
    val item: MediaItemDto? = null,
    val homepage: String? = null,
    @SerializedName("trakt_listed_at") val traktListedAt: String? = null,
    @SerializedName("released_at") val releasedAt: String? = null,
    val match: MatchDto? = null,
    val providers: List<String> = emptyList(),
    @SerializedName("found_on_choices") val foundOnChoices: List<String> = emptyList(),
    val cast: List<CastMemberDto> = emptyList(),
    @SerializedName("main_cast_limit") val mainCastLimit: Int = 8,
    @SerializedName("trakt_url") val traktUrl: String? = null,
    @SerializedName("imdb_url") val imdbUrl: String? = null,
)

data class FoundOnResponse(
    val success: Boolean,
    val message: String? = null,
    @SerializedName("found_on") val foundOn: List<String> = emptyList(),
)

data class FoundOnChoicesResponse(
    val success: Boolean,
    val message: String? = null,
    val choices: List<String> = emptyList(),
    @SerializedName("choice_links") val choiceLinks: List<ServiceLinkDto> = emptyList(),
)

data class FeedbackResponse(
    val success: Boolean,
    val message: String? = null,
    val rating: Int? = null,
    val comment: String? = null,
    val spoiler: Boolean = false,
    @SerializedName("comment_id") val commentId: Int? = null,
    val review: Boolean = false,
)

data class CommentResponse(
    val success: Boolean,
    val message: String? = null,
    @SerializedName("comment_id") val commentId: Int? = null,
    val review: Boolean = false,
)

data class WidgetEpisodeIdsDto(
    val trakt: Int? = null,
    val tvdb: Int? = null,
    val tmdb: Int? = null,
    val imdb: String? = null,
)

data class WidgetItemDto(
    val id: String = "",
    val kind: String = "",
    @SerializedName("media_type") val mediaType: String? = null,
    @SerializedName("trakt_id") val traktId: Int? = null,
    val title: String = "",
    @SerializedName("poster_url") val posterUrl: String? = null,
    val subtitle: String? = null,
    @SerializedName("remaining_label") val remainingLabel: String? = null,
    @SerializedName("can_watch") val canWatch: Boolean = false,
    val season: Int? = null,
    val episode: Int? = null,
    @SerializedName("episode_ids") val episodeIds: WidgetEpisodeIdsDto? = null,
    @SerializedName("alert_id") val alertId: Int? = null,
    @SerializedName("group_key") val groupKey: String? = null,
    val expandable: Boolean = false,
    @SerializedName("child_count") val childCount: Int = 0,
    @SerializedName("unread_count") val unreadCount: Int = 0,
    val items: List<WidgetItemDto> = emptyList(),
)

data class WidgetResponse(
    val success: Boolean,
    val message: String? = null,
    val mode: String = "shows",
    val items: List<WidgetItemDto> = emptyList(),
)

data class FavoriteActorResponse(
    val success: Boolean,
    val message: String? = null,
    val favorited: Boolean = false,
    @SerializedName("trakt_id") val traktId: Int? = null,
    val name: String? = null,
)

data class CalendarEventDto(
    @SerializedName("trakt_id") val traktId: Int = 0,
    @SerializedName("media_type") val mediaType: String? = null,
    val title: String = "",
    @SerializedName("poster_url") val posterUrl: String? = null,
    val label: String? = null,
)

data class CalendarDayDto(
    val date: String? = null,
    @SerializedName("in_month") val inMonth: Boolean = true,
    @SerializedName("is_today") val isToday: Boolean = false,
    val events: List<CalendarEventDto> = emptyList(),
)

data class CalendarDto(
    val period: String = "",
    val label: String = "",
    val anchor: String? = null,
    @SerializedName("prev_anchor") val prevAnchor: String? = null,
    @SerializedName("next_anchor") val nextAnchor: String? = null,
    val today: String? = null,
    val weekdays: List<String> = emptyList(),
    @SerializedName("extra_months") val extraMonths: List<String> = emptyList(),
    val days: List<CalendarDayDto> = emptyList(),
)

data class CreateListRequest(
    val name: String,
)

data class AdminStatsDto(
    val users: Int = 0,
    @SerializedName("active_users") val activeUsers: Int = 0,
    @SerializedName("pending_suggestions") val pendingSuggestions: Int = 0,
    val services: Int = 0,
    @SerializedName("alert_events") val alertEvents: Int = 0,
    @SerializedName("tmdb_configured") val tmdbConfigured: Boolean = false,
)

data class AdminDashboardResponse(
    val success: Boolean,
    val message: String? = null,
    val stats: AdminStatsDto = AdminStatsDto(),
)

data class AdminUserDto(
    val id: Int,
    val username: String,
    @SerializedName("is_admin") val isAdmin: Boolean = false,
    @SerializedName("is_active_account") val isActiveAccount: Boolean = true,
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("last_login_at") val lastLoginAt: String? = null,
)

data class AdminUsersResponse(
    val success: Boolean,
    val message: String? = null,
    val users: List<AdminUserDto> = emptyList(),
)

data class AdminActionResponse(
    val success: Boolean,
    val message: String? = null,
    val status: Map<String, Any>? = null,
    @SerializedName("is_active_account") val isActiveAccount: Boolean? = null,
    @SerializedName("is_admin") val isAdmin: Boolean? = null,
    val username: String? = null,
    val notified: Int? = null,
)
