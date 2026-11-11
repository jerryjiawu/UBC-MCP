package dev.jerry.watchdog;

import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Setup + status screen. Settings are locked (read-only) while a lockdown is active. */
public class MainActivity extends Activity {
    private final Handler h = new Handler(Looper.getMainLooper());
    private Prefs prefs;
    private TextView status, signal, service, timer, testResult;
    private EditText url;
    private TextView save, stepRestricted, stepAccess, stepBattery;

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            update();
            h.postDelayed(this, 1000);
        }
    };

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        prefs = new Prefs(this);
        getWindow().setStatusBarColor(Ui.BG);
        getWindow().setNavigationBarColor(Ui.BG);

        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Ui.BG);
        scroll.setFillViewport(true);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        int pad = Ui.dp(this, 24);
        col.setPadding(pad, Ui.dp(this, 40), pad, pad);
        scroll.addView(col);

        LinearLayout brand = new LinearLayout(this);
        brand.setGravity(Gravity.BOTTOM);
        brand.addView(Ui.text(this, "WATCHDOG", 32, Ui.TEXT, true, 0.06f));
        TextView v1 = Ui.text(this, "  V1", 13, Ui.ACCENT, true, 0.2f);
        brand.addView(v1);
        col.addView(brand);
        TextView tag = Ui.text(this, "PHONE LOCKDOWN", 11, Ui.MUTED, false, 0.3f);
        tag.setPadding(0, Ui.dp(this, 10), 0, Ui.dp(this, 28));
        col.addView(tag);

        status = Ui.text(this, "", 22, Ui.TEXT, true, 0.08f);
        col.addView(status);
        timer = Ui.text(this, "", 40, Ui.TEXT, true, 0.03f);
        timer.setPadding(0, Ui.dp(this, 8), 0, Ui.dp(this, 16));
        col.addView(timer);
        signal = Ui.mono(this, "", 13, Ui.MUTED);
        col.addView(signal);
        service = Ui.mono(this, "", 13, Ui.MUTED);
        service.setPadding(0, Ui.dp(this, 4), 0, Ui.dp(this, 28));
        col.addView(service);

        col.addView(section("SETUP"));
        stepRestricted = step("1. Allow restricted settings",
                "Samsung blocks accessibility for apps installed from a file. Tap here, then the ⋮ menu (top right) → Allow restricted settings.",
                v -> startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getPackageName()))));
        col.addView(stepRestricted);
        stepAccess = step("2. Turn on WATCHDOG lockdown",
                "Accessibility → Installed apps → WATCHDOG lockdown → On.",
                v -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        col.addView(stepAccess);
        stepBattery = step("3. Never put WATCHDOG to sleep",
                "Lets it keep checking for study mode in the background.",
                v -> startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + getPackageName()))));
        col.addView(stepBattery);

        col.addView(section("SIGNAL SERVER"));
        url = new EditText(this);
        url.setText(prefs.url());
        url.setTextColor(Ui.TEXT);
        url.setTypeface(android.graphics.Typeface.MONOSPACE);
        url.setTextSize(13);
        url.setSingleLine(true);
        url.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        col.addView(url);
        save = Ui.text(this, "SAVE & TEST", 13, Ui.ACCENT, true, 0.12f);
        int hp = Ui.dp(this, 18), vp = Ui.dp(this, 12);
        save.setPadding(hp, vp, hp, vp);
        save.setBackground(Ui.pill(this, 0x0F4FA8FF, 0x664FA8FF));
        LinearLayout.LayoutParams slp = new LinearLayout.LayoutParams(-2, -2);
        slp.topMargin = Ui.dp(this, 10);
        col.addView(save, slp);
        save.setOnClickListener(v -> saveAndTest());
        testResult = Ui.mono(this, "", 12, Ui.MUTED);
        testResult.setPadding(0, Ui.dp(this, 8), 0, 0);
        col.addView(testResult);

        TextView foot = Ui.mono(this, "\nWhile study mode is on, every app except calls, emergency and alarms is covered. "
                + "If the server can't be reached for 30 minutes during a session, the phone unlocks itself.", 11, Ui.MUTED);
        col.addView(foot);

        setContentView(scroll);
    }

    private TextView section(String s) {
        TextView t = Ui.text(this, s, 11, Ui.MUTED, false, 0.3f);
        t.setPadding(0, Ui.dp(this, 8), 0, Ui.dp(this, 12));
        return t;
    }

    private TextView step(String title, String detail, View.OnClickListener click) {
        TextView t = Ui.mono(this, title + "\n" + detail, 13, Ui.TEXT);
        int p = Ui.dp(this, 14);
        t.setPadding(p, p, p, p);
        t.setBackground(Ui.pill(this, 0x0AFFFFFF, 0x22FFFFFF));
        t.setOnClickListener(click);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.bottomMargin = Ui.dp(this, 10);
        t.setLayoutParams(lp);
        return t;
    }

    private void saveAndTest() {
        if (prefs.locked()) return;
        String u = url.getText().toString().trim();
        prefs.setUrl(u);
        testResult.setTextColor(Ui.MUTED);
        testResult.setText("testing " + u + " ...");
        new Thread(() -> {
            String msg;
            int color;
            try {
                StateClient.State s = StateClient.fetch(u);
                msg = "OK · study mode is " + (s.studying ? "ON" : "off");
                color = Ui.ACCENT;
            } catch (Exception e) {
                msg = "Can't reach it: " + e.getClass().getSimpleName() + (e.getMessage() == null ? "" : " " + e.getMessage());
                color = Ui.RED;
            }
            final String m = msg;
            final int c = color;
            h.post(() -> { testResult.setText(m); testResult.setTextColor(c); });
        }).start();
    }

    private boolean serviceEnabled() {
        String list = Settings.Secure.getString(getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        String me = new ComponentName(this, LockService.class).flattenToString();
        return list != null && list.toLowerCase().contains(me.toLowerCase());
    }

    private void update() {
        long now = System.currentTimeMillis();
        boolean locked = prefs.locked();
        boolean on = serviceEnabled();

        status.setText(locked ? "●  LOCKDOWN ACTIVE" : prefs.studying() ? "○  UNLOCKED (FAILSAFE)" : "○  STANDING BY");
        status.setTextColor(locked ? Ui.ACCENT : Ui.MUTED);
        double start = prefs.startedAt();
        timer.setText(prefs.studying() && start > 0 ? Ui.hms((long) (now / 1000.0 - start)) : "");
        timer.setVisibility(prefs.studying() && start > 0 ? View.VISIBLE : View.GONE);

        long ok = prefs.lastOk();
        if (!on) signal.setText("signal: service off");
        else if (ok == 0) signal.setText("signal: waiting " + (prefs.lastError().isEmpty() ? "" : "· " + prefs.lastError()));
        else if (prefs.lastError().isEmpty()) signal.setText("signal: ok · " + ((now - ok) / 1000) + "s ago");
        else signal.setText("signal: lost " + ((now - ok) / 1000) + "s ago · " + prefs.lastError());
        signal.setTextColor(on && ok > 0 && prefs.lastError().isEmpty() ? Ui.MUTED : Ui.RED);

        service.setText("lockdown service: " + (on ? "on" : "OFF — finish setup below"));
        service.setTextColor(on ? Ui.MUTED : Ui.RED);

        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        boolean battery = pm != null && pm.isIgnoringBatteryOptimizations(getPackageName());
        stepAccess.setAlpha(on ? 0.45f : 1f);
        stepRestricted.setAlpha(on ? 0.45f : 1f);
        stepBattery.setAlpha(battery ? 0.45f : 1f);

        // no changing where the lock comes from mid-session
        url.setEnabled(!locked);
        save.setEnabled(!locked);
        save.setAlpha(locked ? 0.35f : 1f);
        stepAccess.setEnabled(!locked);
        stepRestricted.setEnabled(!locked);
        stepBattery.setEnabled(!locked);
    }

    @Override protected void onResume() { super.onResume(); h.post(tick); }
    @Override protected void onPause() { super.onPause(); h.removeCallbacks(tick); }
}
