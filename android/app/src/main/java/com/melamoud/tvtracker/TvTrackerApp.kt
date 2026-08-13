package com.melamoud.tvtracker

import android.app.Application
import coil.ImageLoader
import coil.ImageLoaderFactory
import com.melamoud.tvtracker.di.AppContainer

class TvTrackerApp : Application(), ImageLoaderFactory {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }

    override fun newImageLoader(): ImageLoader = container.imageLoader

    companion object {
        fun from(context: android.content.Context): TvTrackerApp =
            context.applicationContext as TvTrackerApp
    }
}
