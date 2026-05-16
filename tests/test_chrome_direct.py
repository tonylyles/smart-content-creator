import sys, os, subprocess, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 直接用 subprocess 启动 Chrome，不走 Selenium
chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
user_data_dir = r"C:\Users\ZhuanZ1\chrome_selenium_profile"
url = "https://mp.weixin.qq.com/"

print(f"Launching Chrome directly...")
print(f"URL: {url}")

proc = subprocess.Popen([
    chrome_path,
    f"--user-data-dir={user_data_dir}",
    "--no-first-run",
    "--no-default-browser-check",
    "--window-size=1280,900",
    url
])

print(f"Chrome PID: {proc.pid}")
print("If Chrome opened, you can log in manually.")
print("This confirms Chrome CAN be launched from this environment.")
input("Press Enter to continue...")
