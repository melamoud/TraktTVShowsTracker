# Android app

The TV Tracker Android app connects to the same server as the website (`tvtracker.melamoud.com`) and uses your Trakt login.

## What it does

- **My Shows / My Movies** — the same list filters as the web (status, Lists…, Upcoming / Theater / Streaming, title search), each as a compact dropdown with checkmarks. Choices are remembered on the server (same as the website). **List** vs **Newest aired** is the same server sort as the website (pins on top; movies by release date; shows by latest episode air date). Switching that menu reloads from the server. Cards show **Found on** (tap a service to open it, same as the website), **Progress**, and **Watch**; pin, set lists, **Found on…**, rate, and favorite are in the ⋮ menu. Tap the card to open the **title page**.
- **Search** — find titles on Trakt and add them to your lists. **Type** and **Filters** are compact menus (defaults hide already-watched and already-listed titles; those choices are remembered). Filters also include **Year** (`2018` or `2015-2020`) and multi-select **Genres**; a title is still required. Tap a result for the title page. The ⋮ menu includes **Found on…**, same as My.
- **Alerts** — the same in-app alerts as the website, including **Found on** (tap to open the service), streaming lines, purple **Preference match** genre/keyword tags when the title matches your filters, and poster badges: **Episode** / **Season** / **Streaming** / **Movie** / **List** / **Actor** / **Admin**. **List** means you added the title to a list. **Actor** is a newly listed title with a favorite actor. **Streaming** means a new service, not a new episode. Episode titles look like **The Agency S3E5**. **Pin** a show or movie so all of its alerts stay at the top (the show, not one episode). **Progress** is on every show-linked alert (one line, same height as **Mark read** / **Pin**). **Newest first** / **Oldest first** and **Grouped by show** match the website. Grouped rows have a **Show N alerts** control. After you mark episodes watched on Progress, Alerts reloads when you go back. Hide-read is remembered. Tap the card to open the title page.
- **Title page** — movie/show detail matching the website: overview, genres, preference/list/watched tags, streaming and Found on (with **Found on…** to edit), lists / rate / favorite / review / watched, IMDb / Trailer / Homepage / Trakt, and cast (favorite actor + search that actor’s titles). Shows have **Series progress**.
- **Progress** — mark episodes or a whole season watched / unwatched. Writes to Trakt.
- **Home-screen widget** — long-press the home screen → Widgets → **TV Tracker**. Resize it for more rows and width. The header shows the app icon and **TV Tracker ·** mode; the swap button cycles **Shows Progress** / **Movies** / **Alerts**. The list scrolls. **Shows Progress** only lists shows that still have a next episode to watch. Tap a title or poster to open that show, movie, or alert in the app. The checkmark asks before marking the next episode (Shows) or the movie (Movies) watched. Alerts start grouped; tap the arrow to expand a show. Alert posters load from the server without opening the title page first. Refresh on the widget reloads from the server (same cache as the app).

Latest movies/shows and Recommended screens are website-only for now.

## Refresh

Pull down on any list, or tap the refresh icon. That reloads from the TV Tracker server (the same cache the website uses). It does **not** force a Trakt pull. Lists also reload when you return to them (including after Progress).

## Login

There is no local password. Tap **Login with TraktTV**, authorize in the browser, then the app opens again to finish. If the browser stays open, tap **Open TV Tracker**.

Stay signed in until you tap **Log out**.
