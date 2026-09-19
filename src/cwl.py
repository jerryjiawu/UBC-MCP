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


def get_driver(profile_dir=None):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    # Duo push approval happens on the phone, not in the browser window, and the
    # webhook notification + screenshot()/execute_script() tools cover visibility,
    # so headless is safe by default. Set SELENIUM_HEADLESS=0 to watch it run.
    headless = os.getenv("SELENIUM_HEADLESS", "1") != "0"

    def build(user_data_dir):
        options = Options()
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument("--profile-directory=Default")
        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
            # without these, headless Chrome reliably hangs on startup in this environment
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
        return webdriver.Chrome(options=options)

    target_dir = profile_dir or PROFILE_DIR
    try:
        return build(target_dir)
    except WebDriverException:
        pass

    # first retry: kill any orphaned chromedriver holding the profile lock (e.g. after a crash)
    _kill_orphaned_chromedriver()
    try:
        return build(target_dir)
    except WebDriverException:
        pass

    # persistent profile still unusable -> fall back to a disposable temp profile (no saved session)
    fallback_dir = tempfile.mkdtemp(prefix="ubc-mcp-chrome-")
    return build(fallback_dir)



def CWL_login(driver, url):
    driver.get(url)

    try:
        username_field = driver.find_element("id", "username")
        password_field = driver.find_element("id", "password")
    except NoSuchElementException:
        # already signed in from a previous session (cookies + Duo trust persisted in the profile)
        return

    username_field.send_keys(USERNAME)
    password_field.send_keys(PASSWORD)

    #press enter key
    password_field.send_keys(Keys.RETURN)

    # briefly watch for the Duo redirect so we can notify without blocking on the actual approval
    for _ in range(10):
        time.sleep(0.5)
        if "duosecurity.com" in driver.current_url:
            _notify_duo_push()
            break

if __name__ == "__main__":
    driver = get_driver()
    CWL_login(driver, "https://canvas.ubc.ca")
    time.sleep(1010000)
