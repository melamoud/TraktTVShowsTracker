package com.melamoud.tvtracker.ui.nav

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Tv
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
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
    unreadAlerts: Int,
    onOpenLoginUrl: (String) -> Unit,
    onOauthToken: String?,
    onOauthConsumed: () -> Unit,
    onLoggedIn: (String) -> Unit,
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
    val showChrome = currentRoute?.startsWith("progress/") != true

    Scaffold(
        topBar = {
            if (showChrome) {
                TopAppBar(
                    title = { Text("TV Tracker", color = Color.White) },
                    actions = {
                        Text(username.orEmpty(), color = Color.White.copy(alpha = 0.85f))
                        TextButton(onClick = onLogout) {
                            Text(stringResource(R.string.logout), color = Color.White)
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
                val vm: MyMediaViewModel = viewModel(factory = MyMediaViewModel.factory("shows", container.catalogRepository))
                MyMediaScreen(vm, container.baseUrl, isShows = true) { navController.navigate("progress/$it") }
            }
            composable("movies") {
                val vm: MyMediaViewModel = viewModel(factory = MyMediaViewModel.factory("movies", container.catalogRepository))
                MyMediaScreen(vm, container.baseUrl, isShows = false) {}
            }
            composable("search") {
                val vm: SearchViewModel = viewModel(factory = SearchViewModel.factory(container.catalogRepository))
                SearchScreen(vm, container.baseUrl) { navController.navigate("progress/$it") }
            }
            composable("alerts") {
                val vm: AlertsViewModel = viewModel(factory = AlertsViewModel.factory(container.catalogRepository))
                AlertsScreen(vm, container.baseUrl) { navController.navigate("progress/$it") }
            }
            composable(
                "progress/{traktId}",
                arguments = listOf(navArgument("traktId") { type = NavType.IntType }),
            ) { entry ->
                val traktId = entry.arguments?.getInt("traktId") ?: return@composable
                val vm: ProgressViewModel = viewModel(factory = ProgressViewModel.factory(traktId, container.catalogRepository))
                ProgressScreen(vm, onBack = { navController.popBackStack() })
            }
        }
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
