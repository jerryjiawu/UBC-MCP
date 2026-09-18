import selenium
from dotenv import load_dotenv
import os

load_dotenv()

USERNAME = os.getenv("CWL_USERNAME")
PASSWORD = os.getenv("CWL_PASSWORD")

URL = "https://cwl.ubc.ca/login"

def CWL_login(driver):
    driver.get(URL)
    username_field = driver.find_element("id", "username")
    password_field = driver.find_element("id", "password")
    login_button = driver.find_element("id", "login-button")

    username_field.send_keys(USERNAME)
    password_field.send_keys(PASSWORD)
    login_button.click()

if __name__ == "__main__":
    from selenium import webdriver
    driver = webdriver.Chrome()
    CWL_login(driver)
