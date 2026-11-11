package dev.jerry.watchdog;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.util.TypedValue;
import android.widget.TextView;

/** Shared look: same palette and font as the PC app. */
final class Ui {
    static final int BG = Color.rgb(12, 12, 12);
    static final int TEXT = Color.rgb(242, 242, 242);
    static final int MUTED = Color.rgb(125, 125, 125);
    static final int ACCENT = Color.rgb(79, 168, 255);
    static final int ART = Color.rgb(160, 205, 255);
    static final int RED = Color.rgb(255, 97, 89);

    private static Typeface black, regular;

    static Typeface orbitron(Context c, boolean heavy) {
        if (black == null) {
            try {
                black = new Typeface.Builder(c.getAssets(), "Orbitron.ttf").setFontVariationSettings("'wght' 900").build();
                regular = new Typeface.Builder(c.getAssets(), "Orbitron.ttf").setFontVariationSettings("'wght' 500").build();
            } catch (Exception e) {
                black = Typeface.DEFAULT_BOLD;
                regular = Typeface.DEFAULT;
            }
        }
        return heavy ? black : regular;
    }

    static TextView text(Context c, String s, float sp, int color, boolean heavy, float letterSpacing) {
        TextView t = new TextView(c);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(color);
        t.setTypeface(orbitron(c, heavy));
        t.setLetterSpacing(letterSpacing);
        t.setIncludeFontPadding(false);
        return t;
    }

    static TextView mono(Context c, String s, float sp, int color) {
        TextView t = new TextView(c);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(color);
        t.setTypeface(Typeface.MONOSPACE);
        return t;
    }

    static int dp(Context c, float dp) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, dp, c.getResources().getDisplayMetrics()));
    }

    static GradientDrawable pill(Context c, int fill, int stroke) {
        GradientDrawable d = new GradientDrawable();
        d.setCornerRadius(dp(c, 14));
        d.setColor(fill);
        d.setStroke(dp(c, 1), stroke);
        return d;
    }

    static String hms(long s) {
        if (s < 0) s = 0;
        return String.format(java.util.Locale.US, "%02d:%02d:%02d", s / 3600, (s % 3600) / 60, s % 60);
    }
}
