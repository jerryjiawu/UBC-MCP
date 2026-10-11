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


def get_driver(profile_dir=None, headless=None):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    # Duo push approval happens on the phone, not in the browser window, and the
    # webhook notification + screenshot()/execute_script() tools cover visibility,
    # so headless is safe by default. Set SELENIUM_HEADLESS=0 to watch it run, or
    # pass headless=False explicitly (CWL_login does this automatically when a
    # manual Duo step is detected).
    use_headless = (os.getenv("SELENIUM_HEADLESS", "1") != "0") if headless is None else headless

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



def _switch_to_visible(driver):
    """Quit a headless session and relaunch a visible one at the same URL/profile,
    so the user can complete a manual step (e.g. Duo) themselves."""
    profile_dir = getattr(driver, "_mcp_profile_dir", None) or PROFILE_DIR
    pending_url = driver.current_url
    try:
        driver.quit()
    except Exception:
        pass
    visible = get_driver(profile_dir=profile_dir, headless=False)
    visible.get(pending_url)
    return visible


MANUAL_AUTH_TIMEOUT = int(os.getenv("CWL_MANUAL_AUTH_TIMEOUT", "300"))


def _wait_for_manual_auth(driver, timeout=MANUAL_AUTH_TIMEOUT):
    """Block the caller until the user finishes whatever Duo needs (push approval,
    picking a method, "remember this device", etc.), by waiting for the browser to
    navigate away from duosecurity.com. This makes CWL_login (and so the MCP tool
    call using it) wait for the manual step to actually finish instead of returning
    on stale mid-flow state."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if "duosecurity.com" not in driver.current_url:
                return
        except Exception:
            return
        time.sleep(1)


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
            if getattr(driver, "_mcp_headless", False):
                # Duo may need a manual step (pick a method, "remember this device", etc.) --
                # unhide the browser so the user can finish it themselves
                driver = _switch_to_visible(driver)
            # block here until the manual step is actually done, so the caller (and
            # any agent waiting on this tool call) doesn't continue on stale state
            _wait_for_manual_auth(driver)
            break

    return driver

if __name__ == "__main__":
    driver = get_driver()
    driver = CWL_login(driver, "https://canvas.ubc.ca")
    time.sleep(1010000)
