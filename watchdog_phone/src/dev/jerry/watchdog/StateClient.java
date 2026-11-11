package dev.jerry.watchdog;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

import org.json.JSONObject;

/** Fetches WATCHDOG's study state: {"studying": bool, "started_at": epoch-seconds|null, ...}. */
final class StateClient {
    static final class State {
        final boolean studying;
        final double startedAt;

        State(boolean studying, double startedAt) {
            this.studying = studying;
            this.startedAt = startedAt;
        }
    }

    /** Blocking; call off the main thread. Throws on network/format errors. */
    static State fetch(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(3000);
        c.setReadTimeout(3000);
        c.setUseCaches(false);
        try {
            int code = c.getResponseCode();
            if (code != 200) throw new Exception("HTTP " + code);
            InputStream in = c.getInputStream();
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            byte[] chunk = new byte[4096];
            int n;
            while ((n = in.read(chunk)) > 0 && buf.size() < 65536) buf.write(chunk, 0, n);
            JSONObject o = new JSONObject(buf.toString("UTF-8"));
            double started = o.isNull("started_at") ? 0 : o.optDouble("started_at", 0);
            return new State(o.optBoolean("studying", false), started);
        } finally {
            c.disconnect();
        }
    }
}
