package dev.jerry.watchdog;

import android.content.Context;
import android.content.SharedPreferences;

/** Settings + last known lockdown state, shared by the service and the setup screen. */
final class Prefs {
    static final String DEFAULT_URL = "http://10.200.118.212:8787/state.json";
    /** If study mode is on but the PC/NUC can't be reached for this long, unlock (so a dead
     *  server or leaving home can never trap the phone). */
    static final long FAILSAFE_MS = 30 * 60 * 1000L;

    private final SharedPreferences p;

    Prefs(Context c) {
        p = c.getSharedPreferences("watchdog", Context.MODE_PRIVATE);
    }

    String url() { return p.getString("url", DEFAULT_URL); }
    void setUrl(String url) { p.edit().putString("url", url).apply(); }

    /** Study mode as last reported by the server. */
    boolean studying() { return p.getBoolean("studying", false); }
    /** Epoch seconds (PC clock) when the session started; 0 if unknown. */
    double startedAt() { return Double.longBitsToDouble(p.getLong("started_at", 0)); }
    /** Phone time (ms) of the last successful poll; 0 = never. */
    long lastOk() { return p.getLong("last_ok", 0); }
    String lastError() { return p.getString("last_error", ""); }

    /** Whether the phone is actually locked right now: studying, and not released by the failsafe. */
    boolean locked() { return p.getBoolean("locked", false); }

    void recordOk(boolean studying, double startedAt, long now) {
        p.edit().putBoolean("studying", studying)
                .putLong("started_at", Double.doubleToRawLongBits(startedAt))
                .putLong("last_ok", now).putString("last_error", "")
                .putBoolean("locked", studying).apply();
    }

    void recordError(String error, long now) {
        SharedPreferences.Editor e = p.edit().putString("last_error", error);
        if (locked() && lastOk() > 0 && now - lastOk() > FAILSAFE_MS) {
            e.putBoolean("locked", false); // failsafe release
        }
        e.apply();
    }

    /** Heartbeat from the service so the setup screen can tell it's alive. */
    void beat(long now) { p.edit().putLong("beat", now).apply(); }
    long lastBeat() { return p.getLong("beat", 0); }
}
