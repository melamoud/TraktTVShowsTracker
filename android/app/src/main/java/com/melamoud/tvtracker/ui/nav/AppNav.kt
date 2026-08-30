package com.melamoud.tvtracker.ui.nav

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Tv
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.melamoud.tvtracker.R
import com.melamoud.tvtracker.di.AppContainer
import com.melamoud.tvtracker.ui.alerts.AlertsScreen
import com.melamoud.tvtracker.ui.alerts.AlertsViewModel
import com.melamoud.tvtracker.ui.detail.DetailScreen
import com.melamoud.tvtracker.ui.detail.DetailViewModel
import com.melamoud.tvtracker.ui.latest.LatestMediaScreen
import com.melamoud.tvtracker.ui.latest.LatestMediaViewModel
import com.melamoud.tvtracker.ui.login.LoginScreen
import com.melamoud.tvtracker.ui.login.LoginViewModel
import com.melamoud.tvtracker.ui.media.MyMediaScreen
import com.melamoud.tvtracker.ui.media.MyMediaViewModel
import com.melamoud.tvtracker.ui.progress.ProgressScreen
import com.melamoud.tvtracker.ui.progress.ProgressViewModel
import com.melamoud.tvtracker.ui.search.SearchScreen
import com.melamoud.tvtracker.ui.search.SearchViewModel
import com.melamoud.tvtracker.ui.theme.Background
import com.melamoud.tvtracker.ui.theme.Primary

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppNav(
    container: AppContainer,
    loggedIn: Boolean,
    username: String?,
    onOpenLoginUrl: (String) -> Unit,
    onOauthToken: String?,
    onOauthConsumed: () -> Unit,
    onLoggedIn: (String, Int) -> Unit,
    onLogout: () -> Unit,
) {
    if (!loggedIn) {
        val loginVm: LoginViewModel = viewModel(factory = LoginViewModel.factory(container.authRepository))
        LaunchedEffect(onOauthToken) {
            if (!onOauthToken.isNullOrBlank()) {
                loginVm.complete(onOauthToken)
                onOauthConsumed()
            }
        }
        LoginScreen(
            viewModel = loginVm,
            onOpenUrl = onOpenLoginUrl,
            onLoggedIn = onLoggedIn,
        )
        return
    }

    val navController = rememberNavController()
    val backStack by navController.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route
    val showChrome = currentRoute?.startsWith("progress/") != true &&
        currentRoute?.startsWith("detail/") != true
    val unreadAlerts by container.unreadAlerts.collectAsStateWithLifecycle()
    val pendingActor by container.pendingActorSearch.collectAsStateWithLifecycle()
    val pendingOpen by container.pendingOpen.collectAsStateWithLifecycle()
    val onUnread = container::setUnreadAlerts

    fun openDetail(mediaType: String, traktId: Int) {
        navController.navigate("detail/$mediaType/$traktId")
    }
    fun openProgress(traktId: Int) {
        navController.navigate("progress/$traktId")
    }
    fun openActorSearch(personId: Int, name: String) {
        container.requestActorSearch(personId, name)
        navController.navigate("search") {
            popUpTo(navController.graph.findStartDestination().id) { saveState = true }
            launchSingleTop = true
            restoreState = true
        }
    }

    LaunchedEffect(pendingOpen, loggedIn) {
        val open = pendingOpen ?: return@LaunchedEffect
        when (open.dest) {
            "detail" -> {
                val mt = open.mediaType
                val id = open.traktId
                if (mt != null && id != null) navController.navigate("detail/$mt/$id")
            }
            "progress" -> open.traktId?.let { navController.navigate("progress/$it") }
            "shows", "movies", "alerts", "search", "latest_movies", "latest_shows" -> {
                navController.navigate(open.dest) {
                    popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                    launchSingleTop = true
                    restoreState = true
                }
            }
        }
        container.consumePendingOpen()
    }

    Scaffold(
        topBar = {
            if (showChrome) {
                TopAppBar(
                    title = { Text(screenTitle(currentRoute), color = Color.White) },
                    actions = {
                        Text(username.orEmpty(), color = Color.White.copy(alpha = 0.85f))
                        var menuOpen by remember { mutableStateOf(false) }
                        IconButton(onClick = { menuOpen = true }) {
                            Icon(Icons.Default.MoreVert, contentDescription = stringResource(R.string.more))
                        }
                        DropdownMenu(
                            expanded = menuOpen,
                            onDismissRequest = { menuOpen = false },
                        ) {
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.latest_movies)) },
                                onClick = {
                                    menuOpen = false
                                    navController.navigate("latest_movies") {
                                        popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                },
                            )
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.latest_shows)) },
                                onClick = {
                                    menuOpen = false
                                    navController.navigate("latest_shows") {
                                        popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                },
                            )
                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.logout)) },
                                onClick = { menuOpen = false; onLogout() },
                            )
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = Background,
                        titleContentColor = Color.White,
                    ),
                )
            }
        },
        bottomBar = {
            if (showChrome) {
                NavigationBar(containerColor = Background) {
                    fun go(route: String) {
                        navController.navigate(route) {
                            popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                    }
                    NavigationBarItem(
                        selected = currentRoute == "shows",
                        onClick = { go("shows") },
                        icon = { Icon(Icons.Default.Tv, contentDescription = null) },
                        label = { Text(stringResource(R.string.my_shows)) },
                        colors = navColors(),
                    )
                    NavigationBarItem(
                        selected = currentRoute == "movies",
                        onClick = { go("movies") },
                        icon = { Icon(Icons.Default.Movie, contentDescription = null) },
                        label = { Text(stringResource(R.string.my_movies)) },
                        colors = navColors(),
                    )
                    NavigationBarItem(
                        selected = currentRoute == "search",
                        onClick = { go("search") },
                        icon = { Icon(Icons.Default.Search, contentDescription = null) },
                        label = { Text(stringResource(R.string.search)) },
                        colors = navColors(),
                    )
                    NavigationBarItem(
                        selected = currentRoute == "alerts",
                        onClick = { go("alerts") },
                        icon = {
                            BadgedBox(badge = {
                                if (unreadAlerts > 0) Badge { Text(unreadAlerts.toString()) }
                            }) {
                                Icon(Icons.Default.Notifications, contentDescription = null)
                            }
                        },
                        label = { Text(stringResource(R.string.alerts)) },
                        colors = navColors(),
                    )
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = "shows",
            modifier = Modifier.padding(padding),
        ) {
            composable("shows") {
                val vm: MyMediaViewModel = viewModel(
                    factory = MyMediaViewModel.factory("shows", container.catalogRepository, onUnread),
                )
                MyMediaScreen(
                    vm, container.baseUrl, isShows = true,
                    onProgress = ::openProgress,
                    onOpenDetail = ::openDetail,
                )
            }
            composable("movies") {
                val vm: MyMediaViewModel = viewModel(
                    factory = MyMediaViewModel.factory("movies", container.catalogRepository, onUnread),
                )
                MyMediaScreen(
                    vm, container.baseUrl, isShows = false,
                    onProgress = {},
                    onOpenDetail = ::openDetail,
                )
            }
            composable("search") {
                val vm: SearchViewModel = viewModel(
                    factory = SearchViewModel.factory(container.catalogRepository, onUnread),
                )
                SearchScreen(
                    vm,
                    container.baseUrl,
                    pendingActor = pendingActor,
                    onConsumeActor = container::consumePendingActorSearch,
                    onProgress = ::openProgress,
                    onOpenDetail = ::openDetail,
                )
            }
            composable("alerts") {
                val vm: AlertsViewModel = viewModel(
                    factory = AlertsViewModel.factory(container.catalogRepository, onUnread),
                )
                AlertsScreen(
                    vm, container.baseUrl,
                    onProgress = ::openProgress,
                    onOpenDetail = ::openDetail,
                )
            }
            composable("latest_movies") {
                val vm: LatestMediaViewModel = viewModel(
                    factory = LatestMediaViewModel.factory("movies", container.catalogRepository, onUnread),
                )
                LatestMediaScreen(
                    vm, container.baseUrl, isShows = false,
                    onOpenDetail = ::openDetail,
                )
            }
            composable("latest_shows") {
                val vm: LatestMediaViewModel = viewModel(
                    factory = LatestMediaViewModel.factory("shows", container.catalogRepository, onUnread),
                )
                LatestMediaScreen(
                    vm, container.baseUrl, isShows = true,
                    onOpenDetail = ::openDetail,
                )
            }
            composable(
                "detail/{mediaType}/{traktId}",
                arguments = listOf(
                    navArgument("mediaType") { type = NavType.StringType },
                    navArgument("traktId") { type = NavType.IntType },
                ),
            ) { entry ->
                val mediaType = entry.arguments?.getString("mediaType") ?: return@composable
                val traktId = entry.arguments?.getInt("traktId") ?: return@composable
                val vm: DetailViewModel = viewModel(
                    factory = DetailViewModel.factory(mediaType, traktId, container.catalogRepository, onUnread),
                )
                DetailScreen(
                    vm,
                    container.baseUrl,
                    onBack = { navController.popBackStack() },
                    onProgress = ::openProgress,
                    onActorTitles = ::openActorSearch,
                )
            }
            composable(
                "progress/{traktId}",
                arguments = listOf(navArgument("traktId") { type = NavType.IntType }),
            ) { entry ->
                val traktId = entry.arguments?.getInt("traktId") ?: return@composable
                val vm: ProgressViewModel = viewModel(
                    factory = ProgressViewModel.factory(traktId, container.catalogRepository, onUnread),
                )
                ProgressScreen(vm, onBack = { navController.popBackStack() })
            }
        }
    }
}

@Composable
private fun screenTitle(route: String?): String {
    return when (route) {
        "shows" -> stringResource(R.string.my_shows)
        "movies" -> stringResource(R.string.my_movies)
        "search" -> stringResource(R.string.search)
        "alerts" -> stringResource(R.string.alerts)
        "latest_movies" -> stringResource(R.string.latest_movies)
        "latest_shows" -> stringResource(R.string.latest_shows)
        else -> "TV Tracker"
    }
}

@Composable
private fun navColors() = NavigationBarItemDefaults.colors(
    selectedIconColor = Primary,
    selectedTextColor = Color.White,
    unselectedIconColor = Color.White.copy(alpha = 0.7f),
    unselectedTextColor = Color.White.copy(alpha = 0.7f),
    indicatorColor = Color.White.copy(alpha = 0.12f),
)
