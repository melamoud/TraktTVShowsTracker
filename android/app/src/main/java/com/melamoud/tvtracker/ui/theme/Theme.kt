package com.melamoud.tvtracker.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Primary = Color(0xFF3DD6C6)
val AccentGold = Color(0xFFF0B429)
val Background = Color(0xFF0B0D12)
val Surface = Color(0xFF141821)
val SurfaceAlt = Color(0xFF1C2230)
val TextPrimary = Color(0xFFE8EDF7)
val TextMuted = Color(0xFF9AA6BF)
val Danger = Color(0xFFFF6B7A)
val Ok = Color(0xFF6DDF8B)
val Line = Color(0xFF2A3345)

private val DarkColors = darkColorScheme(
    primary = Primary,
    onPrimary = Color(0xFF0B0D12),
    secondary = AccentGold,
    onSecondary = Color(0xFF1A1200),
    background = Background,
    onBackground = TextPrimary,
    surface = Surface,
    onSurface = TextPrimary,
    surfaceVariant = SurfaceAlt,
    onSurfaceVariant = TextMuted,
    error = Danger,
    onError = Color.White,
    outline = Line,
)

@Composable
fun TvTrackerTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColors,
        typography = Typography(),
        content = content,
    )
}
