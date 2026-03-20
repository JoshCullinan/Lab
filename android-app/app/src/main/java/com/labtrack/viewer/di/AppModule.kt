package com.labtrack.viewer.di

import android.content.Context
import com.labtrack.viewer.data.repository.AuthRepository
import com.labtrack.viewer.data.repository.AuthRepositoryImpl
import com.labtrack.viewer.data.repository.CookieRepository
import com.labtrack.viewer.data.repository.CookieRepositoryImpl
import com.labtrack.viewer.domain.results.PdfParser
import com.labtrack.viewer.domain.webview.WebViewBridge
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideAuthRepository(
        @ApplicationContext context: Context
    ): AuthRepository = AuthRepositoryImpl(context)

    @Provides
    @Singleton
    fun provideCookieRepository(): CookieRepository = CookieRepositoryImpl()

    @Provides
    @Singleton
    fun providePdfParser(
        @ApplicationContext context: Context
    ): PdfParser = PdfParser(context)

    @Provides
    @Singleton
    fun provideWebViewBridge(
        @ApplicationContext context: Context
    ): WebViewBridge = WebViewBridge(context)
}
