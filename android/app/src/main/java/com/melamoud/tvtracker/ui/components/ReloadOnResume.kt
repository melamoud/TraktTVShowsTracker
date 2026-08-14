package com.melamoud.tvtracker.ui.components

import androidx.compose.runtime.Composable
import androidx.lifecycle.compose.LifecycleResumeEffect

@Composable
fun ReloadOnResume(onResume: () -> Unit) {
    LifecycleResumeEffect(Unit) {
        onResume()
        onPauseOrDispose { }
    }
}
