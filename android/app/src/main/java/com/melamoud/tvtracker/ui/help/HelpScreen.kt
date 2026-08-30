package com.melamoud.tvtracker.ui.help

import android.annotation.SuppressLint
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HelpScreen(
    baseUrl: String,
    onBack: () -> Unit,
) {
    var loading by remember { mutableStateOf(true) }
    val helpUrl = remember(baseUrl) { baseUrl.trimEnd('/') + "/help" }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text("Help") },
            navigationIcon = {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                }
            },
        )
        if (loading) {
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        }
        AndroidView(
            factory = { context ->
                WebView(context).apply {
                    @SuppressLint("SetJavaScriptEnabled")
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    webViewClient = object : WebViewClient() {
                        override fun onPageFinished(view: WebView?, url: String?) {
                            loading = false
                        }
                    }
                    loadUrl(helpUrl)
                }
            },
            modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp),
            update = { },
        )
    }
}
