import selenium
from dotenv import load_dotenv
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.keys import Keys
import os
import subprocess
import tempfile
import time
import requests
load_dotenv()

USERNAME = os.getenv("CWL_USERNAME")
PASSWORD = os.getenv("CWL_PASSWORD")
DUO_WEBHOOK_URL = os.getenv("DISCORD_DUO_WEBHOOK_URL")

# Persistent Chrome profile dir so the CWL/Duo "remember this browser" trust survives across runs
PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".chrome_profile")


def _notify_duo_push():
    """Best-effort Discord notification that a Duo push was just sent -- never blocks or raises."""
    if not DUO_WEBHOOK_URL:
        return
    try:
        requests.post(
            DUO_WEBHOOK_URL,
            json={"content": "A Duo push was just sent for your CWL login. Take your time and approve it on your phone whenever you're ready."},
            timeout=5,
        )
    except Exception:
        pass


def _kill_orphaned_chromedriver():
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/f", "/im", "chromedriver.exe"], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "chromedriver"], capture_output=True)
    except Exception:
        pass


def default_headless():
    """Headless unless SELENIUM_HEADLESS=0. Duo push approval happens on the phone,
    not in the browser window, so hidden is safe by default; the window is shown
    only when a person actually needs to act in it (see relaunch())."""
    return os.getenv("SELENIUM_HEADLESS", "1") != "0"


def get_driver(profile_dir=None, headless=None):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    use_headless = default_headless() if headless is None else headless

    def build(user_data_dir):
        options = Options()
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument("--profile-directory=Default")
        # newer Chrome versions refuse the DevTools handshake without this
        options.add_argument("--remote-allow-origins=*")
        if use_headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
            # without these, headless Chrome reliably hangs on startup in this environment
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
        return webdriver.Chrome(options=options)

    target_dir = profile_dir or PROFILE_DIR
    try:
        driver = build(target_dir)
    except WebDriverException:
        driver = None

    if driver is None:
        # first retry: kill any orphaned chromedriver holding the profile lock (e.g. after a crash)
        _kill_orphaned_chromedriver()
        try:
            driver = build(target_dir)
        except WebDriverException:
            driver = None

    if driver is None:
        # persistent profile still unusable -> fall back to a disposable temp profile (no saved session)
        target_dir = tempfile.mkdtemp(prefix="ubc-mcp-chrome-")
        driver = build(target_dir)

    # remember how/where this driver was launched so CWL_login can relaunch it
    # visibly (same profile) if a manual step like Duo comes up
    driver._mcp_profile_dir = target_dir
    driver._mcp_headless = use_headless
    return driver



# Fields Storage/Network.setCookies accepts (getCookies returns a few extra, e.g.
# "size" and "session", that setCookies rejects).
_COOKIE_FIELDS = {
    "name", "value", "domain", "path", "secure", "httpOnly", "sameSite",
    "expires", "priority", "sourceScheme", "sourcePort", "partitionKey",
}


def _get_all_cookies(driver):
    for cmd in ("Storage.getCookies", "Network.getAllCookies"):
        try:
            return driver.execute_cdp_cmd(cmd, {}).get("cookies", [])
        except Exception:
            continue
    return []


def _set_all_cookies(driver, cookies):
    cleaned = []
    for cookie in cookies:
        c = {k: v for k, v in cookie.items() if k in _COOKIE_FIELDS}
        if cookie.get("session") or c.get("expires", -1) <= 0:
            c.pop("expires", None)
        cleaned.append(c)
    if not cleaned:
        return
    try:
        driver.execute_cdp_cmd("Storage.setCookies", {"cookies": cleaned})
        return
    except Exception:
        pass
    # batch rejected (e.g. one malformed cookie) -- fall back to one at a time
    for c in cleaned:
        try:
            driver.execute_cdp_cmd("Network.setCookie", c)
        except Exception:
            pass


def bring_to_front(driver):
    """Raise a visible Chrome window above other windows so the user notices it
    (minimize + maximize is the reliable way to do that through WebDriver)."""
    try:
        driver.minimize_window()
        driver.maximize_window()
    except Exception:
        pass


def relaunch(driver, headless):
    """Restart the browser in headless or visible mode, carrying over every open
    tab (and which one is active) plus all cookies -- including session-only ones
    like a fresh CWL login, which the profile on disk wouldn't keep. Chrome can't
    switch modes on a running window, so a restart is the only way. Unsaved form
    input and in-page state are lost."""
    profile_dir = getattr(driver, "_mcp_profile_dir", None) or PROFILE_DIR
    urls, active = [], 0
    try:
        current = driver.current_window_handle
        for i, handle in enumerate(driver.window_handles):
            driver.switch_to.window(handle)
            urls.append(driver.current_url)
            if handle == current:
                active = i
    except Exception:
        pass
    cookies = _get_all_cookies(driver)
    try:
        driver.quit()
    except Exception:
        pass

    new_driver = get_driver(profile_dir=profile_dir, headless=headless)
    _set_all_cookies(new_driver, cookies)
    for i, url in enumerate(urls):
        try:
            if i > 0:
                new_driver.switch_to.new_window("tab")
            new_driver.get(url)
        except Exception:
            pass
    try:
        new_driver.switch_to.window(new_driver.window_handles[active])
    except Exception:
        pass
    if not headless:
        bring_to_front(new_driver)
    return new_driver


MANUAL_AUTH_TIMEOUT = int(os.getenv("CWL_MANUAL_AUTH_TIMEOUT", "300"))


def _wait_for_manual_auth(driver, timeout=MANUAL_AUTH_TIMEOUT):
    """Block the caller until the user finishes whatever Duo needs (push approval,
    picking a method, "remember this device", etc.), by waiting for the browser to
    navigate away from duosecurity.com. This makes CWL_login (and so the MCP tool
    call using it) wait for the manual step to actually finish instead of returning
    on stale mid-flow state. Returns True if Duo finished, False on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if "duosecurity.com" not in driver.current_url:
                return True
        except Exception:
            return True
        time.sleep(1)
    return False


def CWL_login(driver, url):
    driver.get(url)

    try:
        username_field = driver.find_element("id", "username")
        password_field = driver.find_element("id", "password")
    except NoSuchElementException:
        # already signed in from a previous session (cookies + Duo trust persisted in the profile)
        return driver

    username_field.send_keys(USERNAME)
    password_field.send_keys(PASSWORD)

    #press enter key
    password_field.send_keys(Keys.RETURN)

    # briefly watch for the Duo redirect so we can notify right away
    for _ in range(10):
        time.sleep(0.5)
        if "duosecurity.com" in driver.current_url:
            _notify_duo_push()
            was_headless = getattr(driver, "_mcp_headless", False)
            if was_headless:
                # Duo may need a manual step (pick a method, "remember this device", etc.) --
                # unhide the browser so the user can finish it themselves
                driver = relaunch(driver, headless=False)
            # block here until the manual step is actually done, so the caller (and
            # any agent waiting on this tool call) doesn't continue on stale state
            finished = _wait_for_manual_auth(driver)
            if was_headless and finished:
                # done with the user -- go back to hidden, keeping the new login
                driver = relaunch(driver, headless=True)
            break

    return driver

if __name__ == "__main__":
    driver = get_driver()
    driver = CWL_login(driver, "https://canvas.ubc.ca")
    time.sleep(1010000)
