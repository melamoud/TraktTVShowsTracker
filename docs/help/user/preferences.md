# Preferences

## Streaming services

Pick from the default list (Netflix, Prime, …) and/or add a custom service (name, URL, note).

- After save, custom services appear under **Your custom services**
- Check **Remove** next to a custom service, then save, to delete it
- Optionally check **Suggest this service to admin** so it can be added to the shared defaults list

## Favorite actors

On any title detail page, the **Cast** section lists main actors (expand for the full cast). Use **☆ Favorite** on an actor to save them locally.

- Manage removals under Preferences → **Favorite actors**
- Headshots: one TMDB credits lookup per title; each actor image is downloaded into the local actors cache **at most once** and reused on every title
- An actor’s name (or **Titles**) opens Search for their movies/shows, with the same hide-watched / lists / year / genre filters
- Not synced to Trakt favorites. **New title with a favorite actor** alerts (Preferences → Alerts) fire when a newly listed catalog title includes one of these people — the app does **not** poll each actor’s filmography

## Trakt lists in Set lists

Your Trakt **Wishlist** (watchlist) is always first. Personal lists follow.

**When to use Wishlist:** titles you have **not started**. Trakt **removes a title from Wishlist as soon as you watch it** (one movie play, or **one episode** of a show). That is a Trakt rule, not a setting in this app. For shows you are watching or want to keep on My Shows after you finish, use a **personal list**. See [Wishlist vs lists](wishlist).

These settings apply to both **Set lists…** and **My movies / My shows** filters:

| Setting | Meaning |
|--------|---------|
| **Show in menu** | List appears in Set lists… and in the My-page **Lists…** filter menu (Wishlist cannot be hidden; default for personal lists = shown) |
| **Auto-select** | Used by **Apply my defaults** in Set lists…; also pre-checked in My **Lists…** until you change the filter (default = Wishlist only) |
| **Alerts** | In-app alerts (release, streaming, new episode/season) for titles on this list (default = **Wishlist only**). Use this to silence park/archive lists |

**Create / delete lists** (writes to trakt.tv):

- Type a name and **Create on Trakt** — adds a **private** personal list on your Trakt account, then it appears in this table. Check **Alerts** (and Save) if you want notifications for titles you put on it.
- **Delete** on a personal list removes that list and its items **on Trakt**. Wishlist cannot be deleted. Watch history is not touched.

Example: show three lists, but only Wishlist + List 1 auto-selected — Apply my defaults / My movies filter open with those two checked. Leave **Alerts** on Wishlist alone if List 2 is where you park shows you do not want notified about.

On **Set lists…**:

- Checkboxes always show **actual membership** (empty after Remove from all / when not on any list)
- **Apply my defaults** checks Auto-select lists without saving yet
- **Remove from all lists** clears Wishlist + personal lists shown in the menu (after confirm)

## Genres & keywords

These drive the purple **Preference match** highlight and the default Latest **Matches only** filter (genre overlap, keyword hits in title/overview/network). Your streaming services do **not** count toward that highlight — they are for Found-on / “on my services” filters only.

## Hide these genres

A reverse of the list above. Checked genres are **never** shown on **Latest** or **Recommended** movies/shows, and they **never** get in-app alerts — even if the title also matches a liked genre, a keyword, or a favorite actor. Example: hide **animation**, and a new drama with a favorite actor that is also tagged animation stays off those pages and does not alert.

If you check the same genre in both lists, **hide wins** (it is dropped from “genres you care about” on save). My lists, Search, and title pages are unchanged so you can still open something you already saved.

Does not apply to titles with no cached genres yet (nothing to hide on).

## Alerts

Toggle which in-app alert **types** you want. Each type has its own checkbox (all default on):

- Movie release date
- Added to a streaming service (title-level vendors)
- New season on a streaming service
- New episode or season
- Added to a list
- New title with a favorite actor (optional **Only matching my genres or keywords**, default on)
- New user signed up (admins)

Which **lists** can produce release / streaming / episode / season-on-stream alerts is set in the table above under **Alerts** (default Wishlist only). **Added to a list** and **favorite actor** are not list-scoped; uncheck those types to opt out. Favorite-actor alerts default to titles that would be purple on Latest; uncheck **Only matching my genres or keywords** if you want every new catalog title with those actors.

Details: [Alerts](release_alerts).

### First login wizard

If you have no genres/keywords yet, login sends you to a short setup page. Pick at least one genre or keyword (or **Skip for now**). Skipping leaves Latest on the full feed until you set filters.

### Daily reminder

If filters are still empty, a banner appears about once a day:

- **Set up now** — open the wizard  
- **Remind me tomorrow** — snooze 24 hours  
- **Don’t remind me** — permanent off (Latest stays noisy / Matches only empty). You can re-enable under Preferences → Reminders  

### Changing filters later

Saving new genres/keywords prompts you about [review markers](review_markers) (keep, clear, or “caught up as of now”).
