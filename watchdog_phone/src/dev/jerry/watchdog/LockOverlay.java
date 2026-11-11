package dev.jerry.watchdog;

import android.content.Context;
import android.content.Intent;
import android.graphics.PixelFormat;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Full-screen "WATCHDOG V1 ACTIVE" cover, drawn by the accessibility service over every
 *  app that isn't allowed during study mode. It swallows all touches; the only ways out
 *  are its call / emergency buttons (allowed apps) or study mode ending on the PC. */
final class LockOverlay {
    private final Context ctx;
    private final WindowManager wm;
    private final Prefs prefs;
    private final Handler main = new Handler(Looper.getMainLooper());
    private FrameLayout root;
    private TextView timer;
    private boolean shown;

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (!shown) return;
            double start = prefs.startedAt();
            long secs = start > 0 ? (long) (System.currentTimeMillis() / 1000.0 - start) : 0;
            timer.setText(Ui.hms(secs));
            main.postDelayed(this, 1000);
        }
    };

    LockOverlay(Context ctx, Prefs prefs) {
        this.ctx = ctx;
        this.prefs = prefs;
        this.wm = (WindowManager) ctx.getSystemService(Context.WINDOW_SERVICE);
    }

    boolean isShown() { return shown; }

    void show() {
        if (shown) return;
        if (root == null) root = build();
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.OPAQUE);
        lp.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS;
        lp.gravity = Gravity.TOP | Gravity.START;
        try {
            wm.addView(root, lp);
            shown = true;
            main.post(tick);
        } catch (Exception e) {
            shown = false;
        }
    }

    void hide() {
        if (!shown) return;
        shown = false;
        main.removeCallbacks(tick);
        try { wm.removeView(root); } catch (Exception ignored) { }
    }

    private FrameLayout build() {
        Context c = ctx;
        FrameLayout f = new FrameLayout(c);
        f.setBackgroundColor(Ui.BG);
        f.setClickable(true); // swallow every touch
        f.setOnTouchListener((v, e) -> true);

        ImageView art = new ImageView(c);
        art.setImageResource(R.drawable.frieren);
        art.setAlpha(0.42f);
        art.setScaleType(ImageView.ScaleType.CENTER_CROP);
        f.addView(art, new FrameLayout.LayoutParams(-1, -1));

        LinearLayout col = new LinearLayout(c);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setGravity(Gravity.CENTER_HORIZONTAL);
        int pad = Ui.dp(c, 24);
        col.setPadding(pad, pad, pad, pad);

        col.addView(Ui.text(c, "STUDY MODE", 12, Ui.MUTED, false, 0.35f));
        TextView title = Ui.text(c, "WATCHDOG", 40, Ui.TEXT, true, 0.06f);
        title.setPadding(0, Ui.dp(c, 12), 0, 0);
        col.addView(title);
        TextView v1 = Ui.text(c, "V1", 14, Ui.ACCENT, true, 0.2f);
        v1.setPadding(0, Ui.dp(c, 8), 0, 0);
        col.addView(v1);

        TextView active = Ui.text(c, "●  ACTIVE", 34, Ui.ACCENT, true, 0.12f);
        active.setPadding(0, Ui.dp(c, 30), 0, 0);
        active.setShadowLayer(Ui.dp(c, 14), 0, 0, Ui.ACCENT);
        col.addView(active);

        timer = Ui.text(c, "00:00:00", 46, Ui.TEXT, true, 0.03f);
        timer.setPadding(0, Ui.dp(c, 26), 0, 0);
        col.addView(timer);

        TextView note = Ui.mono(c, "This phone is locked until study mode ends on your PC.\nCalls, emergency and alarms still work.", 12, Ui.MUTED);
        note.setGravity(Gravity.CENTER);
        note.setPadding(0, Ui.dp(c, 22), 0, Ui.dp(c, 26));
        col.addView(note);

        LinearLayout buttons = new LinearLayout(c);
        buttons.setGravity(Gravity.CENTER);
        buttons.addView(button("PHONE", Ui.TEXT, () -> launch(new Intent(Intent.ACTION_DIAL))));
        View gap = new View(c);
        buttons.addView(gap, new LinearLayout.LayoutParams(Ui.dp(c, 14), 1));
        buttons.addView(button("EMERGENCY", Ui.RED, () -> {
            Intent em = new Intent("com.android.phone.EmergencyDialer.DIAL");
            if (!launch(em)) launch(new Intent(Intent.ACTION_DIAL, Uri.parse("tel:911")));
        }));
        col.addView(buttons);

        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(-1, -2, Gravity.CENTER);
        f.addView(col, lp);
        return f;
    }

    private TextView button(String label, int color, Runnable action) {
        TextView b = Ui.text(ctx, label, 13, color, true, 0.12f);
        int h = Ui.dp(ctx, 20), v = Ui.dp(ctx, 12);
        b.setPadding(h, v, h, v);
        b.setBackground(Ui.pill(ctx, 0x14FFFFFF, (color & 0x00FFFFFF) | 0x66000000));
        b.setOnClickListener(x -> action.run());
        return b;
    }

    private boolean launch(Intent i) {
        try {
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            ctx.startActivity(i);
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
