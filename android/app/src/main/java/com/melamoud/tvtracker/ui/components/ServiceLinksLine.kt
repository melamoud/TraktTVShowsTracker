package com.melamoud.tvtracker.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import com.melamoud.tvtracker.data.api.dto.ServiceLinkDto
import com.melamoud.tvtracker.ui.theme.AccentGold
import com.melamoud.tvtracker.ui.theme.Primary

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ServiceLinksLine(
    prefix: String,
    links: List<ServiceLinkDto>,
    fallbackLabels: List<String> = emptyList(),
    color: Color = Primary,
    emphasized: Boolean = false,
) {
    val items = if (links.isNotEmpty()) {
        links
    } else {
        fallbackLabels.map { ServiceLinkDto(label = it) }
    }
    if (items.isEmpty()) return
    val uriHandler = LocalUriHandler.current
    val labelColor = if (emphasized) AccentGold else color
    val rowModifier = if (emphasized) {
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(AccentGold.copy(alpha = 0.14f))
            .border(1.dp, AccentGold.copy(alpha = 0.55f), RoundedCornerShape(8.dp))
            .padding(horizontal = 8.dp, vertical = 6.dp)
    } else {
        Modifier
    }
    FlowRow(modifier = rowModifier) {
        Text(
            "$prefix ",
            color = labelColor,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = if (emphasized) FontWeight.Bold else FontWeight.Normal,
        )
        items.forEachIndexed { index, link ->
            val href = link.url
            val clickable = !href.isNullOrBlank()
            Text(
                text = link.label + if (index < items.lastIndex) ", " else "",
                color = labelColor,
                style = MaterialTheme.typography.bodySmall.copy(
                    fontWeight = if (emphasized) FontWeight.SemiBold else FontWeight.Normal,
                    textDecoration = if (clickable) TextDecoration.Underline else TextDecoration.None,
                ),
                modifier = if (clickable) {
                    Modifier.clickable {
                        try {
                            uriHandler.openUri(href)
                        } catch (_: Exception) {
                        }
                    }
                } else {
                    Modifier
                },
            )
        }
    }
}
