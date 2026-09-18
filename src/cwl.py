import selenium
from dotenv import load_dotenv
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.keys import Keys
import os
import subprocess
import tempfile
import time
load_dotenv()

USERNAME = os.getenv("CWL_USERNAME")
PASSWORD = os.getenv("CWL_PASSWORD")

# Persistent Chrome profile dir so the CWL/Duo "remember this browser" trust survives across runs
PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".chrome_profile")


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

    def build(user_data_dir):
        options = Options()
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument("--profile-directory=Default")
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

if __name__ == "__main__":
    driver = get_driver()
    CWL_login(driver, "https://canvas.ubc.ca")
    time.sleep(1010000)
