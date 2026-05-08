import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
driver_path = r"C:\Users\ZhuanZ1\chromedriver\chromedriver.exe"

opts = Options()
opts.binary_location = chrome_path
opts.add_argument("--no-first-run")
opts.add_argument("--no-default-browser-check")
opts.add_argument("--remote-allow-origins=*")
opts.add_argument("--disable-gpu")
opts.add_argument("--disable-dev-shm-usage")
opts.add_argument("--window-size=1280,900")
opts.add_experimental_option("excludeSwitches", ["enable-automation"])
opts.add_experimental_option("useAutomationExtension", False)

print("Starting Chrome...")
try:
    svc = Service(driver_path)
    driver = webdriver.Chrome(service=svc, options=opts)
    print("SUCCESS! Chrome started.")
    driver.get("https://www.baidu.com")
    print(f"Page title: {driver.title}")
    input("Press Enter to close...")
    driver.quit()
    print("Closed.")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
