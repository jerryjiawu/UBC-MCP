"""Build WATCHDOG.apk without Gradle: aapt2 -> javac -> d8 -> zipalign -> apksigner.

    python watchdog_phone/build.py

Needs JDK 17+ and the Android SDK (platform android-36 + build-tools 37.0.0) at
%LOCALAPPDATA%\\Android\\Sdk (override with ANDROID_HOME / JAVA_HOME).
Output: watchdog_phone/dist/WATCHDOG.apk

Signing key: watchdog_phone/keystore/watchdog.jks, created on first build and kept
out of git. Keep it -- Android only installs updates signed with the same key.
"""
import glob
import os
import secrets
import shutil
import subprocess
import sys
import time
import zipfile

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "watchdog_app"))
from artsplit import load_srgb, split  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.environ.get("ANDROID_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
BT = os.path.join(SDK, "build-tools", "37.0.0")
ANDROID_JAR = os.path.join(SDK, "platforms", "android-36", "android.jar")
JAVA_HOME = os.environ.get("JAVA_HOME") or max(glob.glob(r"C:\Program Files\Java\jdk-*"), default="")
EXE = ".exe" if os.name == "nt" else ""
BAT = ".bat" if os.name == "nt" else ""

BUILD = os.path.join(HERE, "build")
DIST = os.path.join(HERE, "dist")
KEYDIR = os.path.join(HERE, "keystore")
KEYSTORE = os.path.join(KEYDIR, "watchdog.jks")
KEYPASS_FILE = os.path.join(KEYDIR, "password.txt")

VERSION_NAME = "1.0"
MIN_SDK, TARGET_SDK = "26", "36"



ART_SRC = os.path.join(os.path.dirname(HERE), "watchdog_app", "ui", "img", "frieren-mask.png")
ART_OUT = os.path.join(HERE, "res", "drawable-nodpi", "frieren.png")
ART_TINT = (160, 205, 255)


def make_art():
    """Phone lock-screen art from the PC app's mask: line work tinted blue, coloured
    parts (eyes) in their own sRGB colour, baked into one PNG (see artsplit.py)."""
    src = load_srgb(ART_SRC)
    src = src.resize((1000, round(src.height * 1000 / src.width)), Image.LANCZOS)
    lines, colour, has_colour = split(src)
    out = Image.new("RGBA", src.size, ART_TINT + (0,))
    out.putalpha(lines)
    if has_colour:
        out.alpha_composite(colour)
    out.save(ART_OUT, optimize=True)

def run(*cmd):
    env = dict(os.environ, JAVA_HOME=JAVA_HOME, SKIP_JDK_VERSION_CHECK="1")
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.exit(f"FAILED: {' '.join(map(str, cmd[:2]))}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def keystore_password():
    os.makedirs(KEYDIR, exist_ok=True)
    if not os.path.exists(KEYPASS_FILE):
        with open(KEYPASS_FILE, "w") as fh:
            fh.write(secrets.token_urlsafe(18))
    return open(KEYPASS_FILE).read().strip()


def main():
    for p in (BT, ANDROID_JAR, JAVA_HOME):
        if not os.path.exists(p):
            sys.exit(f"missing: {p}")
    shutil.rmtree(BUILD, ignore_errors=True)
    for d in ("gen", "classes", "dex"):
        os.makedirs(os.path.join(BUILD, d))
    os.makedirs(DIST, exist_ok=True)

    print("[1/6] resources")
    if os.path.exists(ART_SRC):
        make_art()
    res_zip = os.path.join(BUILD, "res.zip")
    run(os.path.join(BT, "aapt2" + EXE), "compile", "--dir", os.path.join(HERE, "res"), "-o", res_zip)
    base = os.path.join(BUILD, "base.apk")
    version_code = str(int(time.time() // 60))  # always increases, so updates install over
    run(os.path.join(BT, "aapt2" + EXE), "link", "-o", base, "-I", ANDROID_JAR,
        "--manifest", os.path.join(HERE, "AndroidManifest.xml"), "-A", os.path.join(HERE, "assets"),
        "--java", os.path.join(BUILD, "gen"), "--min-sdk-version", MIN_SDK, "--target-sdk-version", TARGET_SDK,
        "--version-code", version_code, "--version-name", VERSION_NAME, res_zip)

    print("[2/6] javac")
    sources = glob.glob(os.path.join(HERE, "src", "**", "*.java"), recursive=True) + \
        glob.glob(os.path.join(BUILD, "gen", "**", "*.java"), recursive=True)
    run(os.path.join(JAVA_HOME, "bin", "javac" + EXE), "--release", "17", "-nowarn", "-encoding", "UTF-8",
        "-classpath", ANDROID_JAR, "-d", os.path.join(BUILD, "classes"), *sources)

    print("[3/6] d8")
    classes = glob.glob(os.path.join(BUILD, "classes", "**", "*.class"), recursive=True)
    run(os.path.join(BT, "d8" + BAT), "--release", "--min-api", MIN_SDK, "--lib", ANDROID_JAR,
        "--output", os.path.join(BUILD, "dex"), *classes)

    print("[4/6] package")
    with zipfile.ZipFile(base, "a", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(BUILD, "dex", "classes.dex"), "classes.dex")
    aligned = os.path.join(BUILD, "aligned.apk")
    run(os.path.join(BT, "zipalign" + EXE), "-p", "-f", "4", base, aligned)

    print("[5/6] sign")
    pw = keystore_password()
    if not os.path.exists(KEYSTORE):
        run(os.path.join(JAVA_HOME, "bin", "keytool" + EXE), "-genkeypair", "-keystore", KEYSTORE,
            "-alias", "watchdog", "-keyalg", "RSA", "-keysize", "3072", "-validity", "10000",
            "-storepass", pw, "-keypass", pw, "-dname", "CN=WATCHDOG, O=jerry")
    out = os.path.join(DIST, "WATCHDOG.apk")
    run(os.path.join(BT, "apksigner" + BAT), "sign", "--ks", KEYSTORE, "--ks-key-alias", "watchdog",
        "--ks-pass", "pass:" + pw, "--key-pass", "pass:" + pw, "--out", out, aligned)

    print("[6/6] verify")
    print(run(os.path.join(BT, "apksigner" + BAT), "verify", "--print-certs", out).splitlines()[0])
    print(f"built {out} ({os.path.getsize(out) // 1024} KB, versionCode {version_code})")


if __name__ == "__main__":
    main()
