package com.melamoud.tvtracker.ui.components

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.melamoud.tvtracker.ui.theme.TextPrimary

/**
 * One-line action buttons that swipe sideways when they don't fit.
 * No scrollbar. An arrow sits on an edge that still has buttons off-screen.
 */
@Composable
fun ScrollableActionRow(
    modifier: Modifier = Modifier,
    itemSpacing: Dp = 6.dp,
    content: @Composable RowScope.() -> Unit,
) {
    val scroll = rememberScrollState()
    val showLeft by remember { derivedStateOf { scroll.canScrollBackward } }
    val showRight by remember { derivedStateOf { scroll.canScrollForward } }
    Box(modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .graphicsLayer { compositingStrategy = CompositingStrategy.Offscreen }
                .drawWithContent {
                    drawContent()
                    val fade = 28.dp.toPx()
                    if (scroll.canScrollBackward) {
                        drawRect(
                            brush = Brush.horizontalGradient(
                                0f to Color.Transparent,
                                1f to Color.Black,
                                startX = 0f,
                                endX = fade,
                            ),
                            blendMode = BlendMode.DstIn,
                        )
                    }
                    if (scroll.canScrollForward) {
                        drawRect(
                            brush = Brush.horizontalGradient(
                                0f to Color.Black,
                                1f to Color.Transparent,
                                startX = size.width - fade,
                                endX = size.width,
                            ),
                            blendMode = BlendMode.DstIn,
                        )
                    }
                }
                .horizontalScroll(scroll)
                .padding(end = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(itemSpacing),
            content = content,
        )
        if (showLeft) {
            Icon(
                Icons.AutoMirrored.Filled.KeyboardArrowLeft,
                contentDescription = null,
                tint = TextPrimary,
                modifier = Modifier.align(Alignment.CenterStart).size(20.dp),
            )
        }
        if (showRight) {
            Icon(
                Icons.AutoMirrored.Filled.KeyboardArrowRight,
                contentDescription = null,
                tint = TextPrimary,
                modifier = Modifier.align(Alignment.CenterEnd).size(20.dp),
            )
        }
    }
}
