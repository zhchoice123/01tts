package com.example.ttsapp

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val Ink = Color(0xFF0D1110)
val InkRaised = Color(0xFF151A18)
val InkSoft = Color(0xFF1D2421)
val Line = Color(0xFF303934)
val Paper = Color(0xFFF3F6F4)
val Muted = Color(0xFFA5B0AA)
val Accent = Color(0xFF55B88A)
val AccentSoft = Color(0xFF18392A)
val Danger = Color(0xFFFF8A80)
val Warning = Color(0xFFE4B86A)

enum class AppThemeStyle(
    val id: String,
    val displayName: String,
    val subtitle: String,
    val colorScheme: ColorScheme,
    val bgGradient: List<Color>,
    val previewBadgeColor: Color,
) {
    DEEP_SPACE_CYBER(
        id = "cyber",
        displayName = "深空赛博",
        subtitle = "暗黑科技 · 紫青霓虹",
        colorScheme = darkColorScheme(
            primary = Color(0xFF8B5CF6),
            onPrimary = Color(0xFFFFFFFF),
            secondary = Color(0xFF06B6D4),
            background = Color(0xFF0B0F19),
            onBackground = Color(0xFFF3F4F6),
            surface = Color(0xFF151A28),
            onSurface = Color(0xFFF3F4F6),
            surfaceVariant = Color(0xFF1E293B),
            onSurfaceVariant = Color(0xFF9CA3AF),
            outline = Color(0xFF6D28D9),
            error = Danger,
        ),
        bgGradient = listOf(Color(0xFF0B0F19), Color(0xFF111827), Color(0xFF0F172A)),
        previewBadgeColor = Color(0xFF8B5CF6)
    ),
    NORDIC_EARTH(
        id = "nordic",
        displayName = "北欧温润",
        subtitle = "燕麦暖白 · 鼠尾陶土",
        colorScheme = lightColorScheme(
            primary = Color(0xFF5B7057),
            onPrimary = Color(0xFFFFFFFF),
            secondary = Color(0xFFC88A6E),
            background = Color(0xFFF5F2EB),
            onBackground = Color(0xFF2C352B),
            surface = Color(0xFFEBE5D8),
            onSurface = Color(0xFF2C352B),
            surfaceVariant = Color(0xFFDFD7C6),
            onSurfaceVariant = Color(0xFF606D5F),
            outline = Color(0xFF8A9A86),
            error = Color(0xFFD9534F),
        ),
        bgGradient = listOf(Color(0xFFF5F2EB), Color(0xFFEBE5D8), Color(0xFFDFD7C6)),
        previewBadgeColor = Color(0xFF5B7057)
    ),
    NEO_POP(
        id = "neopop",
        displayName = "新粗犷波普",
        subtitle = "明黄黑框 · 闯关活力",
        colorScheme = lightColorScheme(
            primary = Color(0xFFD97706),
            onPrimary = Color(0xFFFFFFFF),
            secondary = Color(0xFF0284C7),
            background = Color(0xFFFFFBEB),
            onBackground = Color(0xFF0F172A),
            surface = Color(0xFFFFFFFF),
            onSurface = Color(0xFF0F172A),
            surfaceVariant = Color(0xFFFEF3C7),
            onSurfaceVariant = Color(0xFF475569),
            outline = Color(0xFF0F172A),
            error = Color(0xFFEF4444),
        ),
        bgGradient = listOf(Color(0xFFFFFBEB), Color(0xFFFEF3C7), Color(0xFFFDE68A)),
        previewBadgeColor = Color(0xFFD97706)
    ),
    MIDNIGHT_AURORA(
        id = "aurora",
        displayName = "午夜极光",
        subtitle = "夜幕玄蓝 · 翡翠流光",
        colorScheme = darkColorScheme(
            primary = Color(0xFF10B981),
            onPrimary = Color(0xFF050C1A),
            secondary = Color(0xFF3B82F6),
            background = Color(0xFF050C1A),
            onBackground = Color(0xFFECFDF5),
            surface = Color(0xFF0D1F2D),
            onSurface = Color(0xFFECFDF5),
            surfaceVariant = Color(0xFF064E3B),
            onSurfaceVariant = Color(0xFFA7F3D0),
            outline = Color(0xFF047857),
            error = Danger,
        ),
        bgGradient = listOf(Color(0xFF050C1A), Color(0xFF064E3B), Color(0xFF0284C7)),
        previewBadgeColor = Color(0xFF10B981)
    );

    companion object {
        fun fromId(id: String): AppThemeStyle = entries.find { it.id == id } ?: DEEP_SPACE_CYBER
    }
}

private val typography = Typography(
    headlineMedium = TextStyle(
        fontSize = 28.sp,
        lineHeight = 32.sp,
        fontWeight = FontWeight.SemiBold,
        letterSpacing = (-0.5).sp,
    ),
    titleLarge = TextStyle(
        fontSize = 20.sp,
        lineHeight = 26.sp,
        fontWeight = FontWeight.SemiBold,
    ),
    titleMedium = TextStyle(
        fontSize = 16.sp,
        lineHeight = 22.sp,
        fontWeight = FontWeight.SemiBold,
    ),
    bodyLarge = TextStyle(fontSize = 16.sp, lineHeight = 24.sp),
    bodyMedium = TextStyle(fontSize = 14.sp, lineHeight = 21.sp),
    labelLarge = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.SemiBold),
)

@Composable
fun ListeningTheme(themeId: String = "cyber", content: @Composable () -> Unit) {
    val style = AppThemeStyle.fromId(themeId)
    MaterialTheme(colorScheme = style.colorScheme, typography = typography, content = content)
}
