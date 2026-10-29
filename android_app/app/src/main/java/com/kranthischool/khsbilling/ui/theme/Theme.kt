package com.kranthischool.khsbilling.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val IndigoPrimary = Color(0xFF4338CA)
val IndigoDark = Color(0xFF312E81)
val EmeraldSecondary = Color(0xFF059669)
val EmeraldDark = Color(0xFF047857)
val AmberAccent = Color(0xFFD97706)
val BackgroundLight = Color(0xFFF8FAFC)
val SurfaceLight = Color(0xFFFFFFFF)

private val LightColorScheme = lightColorScheme(
    primary = IndigoPrimary,
    secondary = EmeraldSecondary,
    tertiary = AmberAccent,
    background = BackgroundLight,
    surface = SurfaceLight,
    onPrimary = Color.White,
    onSecondary = Color.White,
    onSurface = Color(0xFF1E293B)
)

private val DarkColorScheme = darkColorScheme(
    primary = IndigoDark,
    secondary = EmeraldDark,
    tertiary = AmberAccent,
    background = Color(0xFF0F172A),
    surface = Color(0xFF1E293B),
    onPrimary = Color.White,
    onSecondary = Color.White,
    onSurface = Color(0xFFF1F5F9)
)

@Composable
fun KhsBillingTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}
