package dev.jerry.watchdog;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.view.accessibility.AccessibilityEvent;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/**
 * The lockdown engine. Runs as an accessibility service so Android keeps it alive and
 * tells it which app is in front. While WATCHDOG study mode is on (polled from the
 * server every few seconds), every app except the allowlist is covered by LockOverlay.
 */
public class LockService extends AccessibilityService {
    /** Apps that stay usable during lockdown: calls, emergency, alarms. */
    static final Set<String> ALLOWED = new HashSet<>(Arrays.asList(
            // Samsung
            "com.samsung.android.dialer", "com.samsung.android.incallui",
            "com.samsung.android.app.telephonyui", "com.samsung.android.emergency",
            "com.sec.android.app.clockpackage",
            // AOSP / Google
            "com.android.dialer", "com.google.android.dialer", "com.android.phone",
            "com.android.server.telecom", "com.android.emergency",
            "com.google.android.deskclock", "com.android.deskclock"));

    /** Windows from these don't change "which app is in front" (shade, dialogs, keyboards). */
    static final Set<String> TRANSIENT = new HashSet<>(Arrays.asList(
            "com.android.systemui", "android"));

    private static final long POLL_AWAKE_MS = 4000;
    private static final long POLL_ASLEEP_MS = 30000;

    private Prefs prefs;
    private LockOverlay overlay;
    private Handler main;
    private Handler net;
    private HandlerThread netThread;
    private String frontPkg = "";
    private String frontClass = "";

    private final Runnable poll = new Runnable() {
        @Override public void run() {
            long now = System.currentTimeMillis();
            try {
                StateClient.State s = StateClient.fetch(prefs.url());
                prefs.recordOk(s.studying, s.startedAt, now);
            } catch (Exception e) {
                String msg = e.getMessage();
                prefs.recordError(e.getClass().getSimpleName() + (msg == null ? "" : ": " + msg), now);
            }
            prefs.beat(now);
            main.post(LockService.this::refresh);
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            net.postDelayed(this, pm != null && pm.isInteractive() ? POLL_AWAKE_MS : POLL_ASLEEP_MS);
        }
    };

    @Override
    protected void onServiceConnected() {
        prefs = new Prefs(this);
        main = new Handler(Looper.getMainLooper());
        overlay = new LockOverlay(this, prefs);
        netThread = new HandlerThread("watchdog-poll");
        netThread.start();
        net = new Handler(netThread.getLooper());
        net.post(poll);
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null || event.getEventType() != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return;
        CharSequence p = event.getPackageName();
        if (p == null) return;
        String pkg = p.toString();
        CharSequence cls = event.getClassName();
        if (TRANSIENT.contains(pkg) || pkg.equals(currentKeyboard())) return;
        if (pkg.equals(getPackageName()) && (cls == null || !cls.toString().endsWith(".MainActivity"))) {
            return; // our own overlay window, not a real app switch
        }
        frontPkg = pkg;
        frontClass = cls == null ? "" : cls.toString();
        refresh();
    }

    private String currentKeyboard() {
        String ime = Settings.Secure.getString(getContentResolver(), Settings.Secure.DEFAULT_INPUT_METHOD);
        if (ime == null) return "";
        int slash = ime.indexOf('/');
        return slash > 0 ? ime.substring(0, slash) : ime;
    }

    private boolean allowed() {
        if (ALLOWED.contains(frontPkg)) return true;
        // our own setup screen stays reachable (it's read-only while locked)
        return frontPkg.equals(getPackageName()) && frontClass.endsWith(".MainActivity");
    }

    private void refresh() {
        if (overlay == null) return;
        if (prefs.locked() && !allowed()) overlay.show();
        else overlay.hide();
    }

    @Override
    public void onInterrupt() { }

    @Override
    public void onDestroy() {
        if (net != null) net.removeCallbacksAndMessages(null);
        if (netThread != null) netThread.quitSafely();
        if (overlay != null) overlay.hide();
        super.onDestroy();
    }
}
