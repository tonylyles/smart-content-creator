import subprocess, sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(chrome_path):
    chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
print(f"Chrome path exists: {os.path.exists(chrome_path)}")
print(f"Chrome path: {chrome_path}")

# Try direct chromedriver with verbose logging
result = subprocess.run(
    [r"C:\Users\ZhuanZ1\chromedriver\chromedriver.exe", "--verbose", "--port=9515"],
    capture_output=True, text=True, timeout=5,
    encoding='utf-8', errors='replace'
)
print(f"STDOUT: {result.stdout[:500]}")
print(f"STDERR: {result.stderr[:500]}")

# Try using selenium with explicit binary location
print("\n--- Trying with explicit binary_location ---")
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.binary_location = chrome_path
opts.add_argument("--no-first-run")
opts.add_argument("--no-default-browser-check")
opts.add_argument("--remote-allow-origins=*")
opts.add_argument("--disable-gpu")
opts.add_experimental_option("excludeSwitches", ["enable-automation"])

try:
    svc = Service(r"C:\Users\ZhuanZ1\chromedriver\chromedriver.exe")
    driver = webdriver.Chrome(service=svc, options=opts)
    print("SUCCESS! Chrome started!")
    driver.get("https://www.baidu.com")
    print(f"Title: {driver.title}")
    driver.quit()
except Exception as e:
    print(f"FAILED: {e}")
