package com.melamoud.tvtracker.ui.progress

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.melamoud.tvtracker.R
import com.melamoud.tvtracker.ui.components.ReloadOnResume
import com.melamoud.tvtracker.ui.components.ReviewDialog
import com.melamoud.tvtracker.ui.components.ServerRefreshBox
import com.melamoud.tvtracker.ui.theme.Ok
import com.melamoud.tvtracker.ui.theme.Primary
import com.melamoud.tvtracker.ui.theme.TextMuted

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProgressScreen(
    viewModel: ProgressViewModel,
    onBack: () -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val open = remember { mutableStateMapOf<Int, Boolean>() }
    val data = state.data
    var menuExpanded by remember { mutableStateOf(false) }
    ReloadOnResume(viewModel::refreshFromTrakt)

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text(data?.title ?: "Progress") },
            navigationIcon = {
                IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") }
            },
            actions = {
                IconButton(onClick = viewModel::refreshFromTrakt) {
                    Icon(Icons.Default.Refresh, contentDescription = stringResource(R.string.refresh))
                }
                Box {
                    IconButton(onClick = { menuExpanded = true }) {
                        Icon(Icons.Default.MoreVert, contentDescription = stringResource(R.string.more))
                    }
                    DropdownMenu(
                        expanded = menuExpanded,
                        onDismissRequest = { menuExpanded = false },
                    ) {
                        DropdownMenuItem(
                            text = { Text("Refresh from Trakt") },
                            onClick = { menuExpanded = false; viewModel.refreshFromTrakt() },
                        )
                    }
                }
            },
        )
        ServerRefreshBox(
            isRefreshing = state.loading && data != null,
            onRefresh = viewModel::refreshFromTrakt,
            modifier = Modifier.weight(1f),
        ) {
            when {
                state.loading && data == null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                state.error != null && data == null -> Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(state.error ?: "")
                    OutlinedButton(onClick = viewModel::reload) { Text("Retry") }
                }
                data != null -> LazyColumn(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    item {
                        Text(
                            "${data.progressCompleted} / ${data.progressAired} aired episodes watched",
                            color = Ok,
                            fontWeight = FontWeight.SemiBold,
                        )
                        data.nextEpisode?.let { next ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    "Next up S${next.season}E${next.number} — ${next.title.orEmpty()}",
                                    modifier = Modifier.weight(1f),
                                )
                                val ep = data.seasons
                                    .firstOrNull { it.number == next.season }
                                    ?.episodes
                                    ?.firstOrNull { it.number == next.number }
                                if (ep != null) {
                                    TextButton(onClick = { viewModel.toggleEpisode(ep, next.season ?: 0) }, enabled = !state.busy) {
                                        Text(if (ep.watched) "Watched" else "Watch")
                                    }
                                }
                            }
                        }
                    }
                    items(data.seasons, key = { it.number }) { season ->
                        val expanded = open[season.number] ?: season.defaultOpen
                        Column {
                            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                TextButton(onClick = { open[season.number] = !expanded }) {
                                    Text("${season.label}  ${season.completed}/${season.aired}", fontWeight = FontWeight.SemiBold)
                                }
                                if (season.aired > 0 && !season.allWatched) {
                                    TextButton(onClick = { viewModel.toggleSeason(season.number, true) }, enabled = !state.busy) {
                                        Text("Mark season watched")
                                    }
                                } else if (season.allWatched) {
                                    TextButton(onClick = { viewModel.toggleSeason(season.number, false) }, enabled = !state.busy) {
                                        Text("Unwatch season")
                                    }
                                }
                            }
                            if (expanded) {
                                season.episodes.forEach { ep ->
                                    Row(
                                        Modifier.fillMaxWidth().padding(start = 12.dp, top = 4.dp, bottom = 4.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                    ) {
                                        Column(Modifier.weight(1f)) {
                                            Text(
                                                "E${ep.number}  ${ep.title.orEmpty()}",
                                                color = if (ep.watched) TextMuted else MaterialTheme.colorScheme.onSurface,
                                            )
                                            Text(ep.airLabel.orEmpty(), color = if (ep.aired) TextMuted else Primary, style = MaterialTheme.typography.bodySmall)
                                        }
                                        TextButton(
                                            onClick = { viewModel.toggleEpisode(ep, season.number) },
                                            enabled = !state.busy && ep.aired,
                                        ) { Text(if (ep.watched) "Watched" else "Watch") }
                                        TextButton(
                                            onClick = { viewModel.openReview(ep) },
                                            enabled = !state.busy,
                                        ) { Text("Rate") }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    state.reviewTarget?.let { ep ->
        ReviewDialog(
            currentRating = null,
            currentComment = null,
            onSave = { rating, comment, spoiler -> viewModel.applyReview(rating, comment, spoiler) },
            onDismiss = viewModel::dismissReview,
        )
    }
}
