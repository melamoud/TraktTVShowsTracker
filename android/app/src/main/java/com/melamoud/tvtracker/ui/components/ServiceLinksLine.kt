package com.melamoud.tvtracker.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.style.TextDecoration
import com.melamoud.tvtracker.data.api.dto.ServiceLinkDto
import com.melamoud.tvtracker.ui.theme.Primary

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ServiceLinksLine(
    prefix: String,
    links: List<ServiceLinkDto>,
    fallbackLabels: List<String> = emptyList(),
    color: Color = Primary,
) {
    val items = if (links.isNotEmpty()) {
        links
    } else {
        fallbackLabels.map { ServiceLinkDto(label = it) }
    }
    if (items.isEmpty()) return
    val uriHandler = LocalUriHandler.current
    FlowRow {
        Text(
            "$prefix ",
            color = color,
            style = MaterialTheme.typography.bodySmall,
        )
        items.forEachIndexed { index, link ->
            val href = link.url
            val clickable = !href.isNullOrBlank()
            Text(
                text = link.label + if (index < items.lastIndex) ", " else "",
                color = color,
                style = MaterialTheme.typography.bodySmall.copy(
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
