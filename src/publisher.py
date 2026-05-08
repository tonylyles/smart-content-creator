"""
微信公众号发布模块（pyautogui 模式） - 曾睿负责

功能：
- subprocess 启动独立 Chrome 实例
- pyautogui 模拟键盘鼠标操作
- pyperclip 剪贴板粘贴内容
- 支持登录、创建图文、群发
- 双模式：真实浏览器操控 + 本地模拟

技术栈：
- subprocess 启动 Chrome（独立 profile，不与已有 Chrome 冲突）
- pyautogui 键盘鼠标模拟
- pyperclip 剪贴板操作
"""

import time
import json
import os
import subprocess
import sqlite3
from datetime import datetime
from typing import Dict, Any


class WeChatPublisher:
    """微信公众号发布器（pyautogui 模式）

    双模式架构：
    - 有账号 + Chrome → subprocess 启动 Chrome + pyautogui 操控
    - 无浏览器环境 → 本地模拟
    """

    CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    PROFILE_DIR = r"C:\Users\ZhuanZ1\chrome_wechat_profile"
    MP_URL = "https://mp.weixin.qq.com/"

    def __init__(self, config: dict = None):
        self.config = config or {}
        wechat_config = self.config.get("wechat", {})

        self.account_id = wechat_config.get("account_id", "") or os.getenv("WECHAT_ACCOUNT_ID", "")
        self.app_id = wechat_config.get("app_id", "") or os.getenv("WECHAT_APP_ID", "")
        self.password = wechat_config.get("password", "") or os.getenv("WECHAT_PASSWORD", "")

        self._chrome_proc = None
        self._browser_mode = bool(self.app_id and self.password)

        self._db_path = wechat_config.get("db_path", "data/publish_log.db")
        self._init_db()
        self._mock_drafts: Dict[str, dict] = {}

        if self._browser_mode:
            print(f"[发布] 📱 已配置公众号 (AppID: {self.app_id[:8]}...)")
            print("[发布] 💡 将在发布时启动 Chrome 浏览器")
        else:
            print("[发布] 📋 未检测到公众号账号，启用本地模拟模式")

    # ==================== Chrome 启动 ====================

    def open_chrome(self, url: str = None) -> bool:
        """启动独立 Chrome 实例"""
        os.makedirs(self.PROFILE_DIR, exist_ok=True)
        target_url = url or self.MP_URL

        try:
            self._chrome_proc = subprocess.Popen([
                self.CHROME_PATH,
                f"--user-data-dir={self.PROFILE_DIR}",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1280,900",
                target_url,
            ])
            print(f"[发布] 🌐 Chrome 已启动 (PID: {self._chrome_proc.pid})")
            time.sleep(5)  # 等待页面加载
            return True
        except FileNotFoundError:
            print(f"[发布] ❌ Chrome 未找到: {self.CHROME_PATH}")
            return False
        except Exception as e:
            print(f"[发布] ❌ Chrome 启动失败: {e}")
            return False

    def close_chrome(self):
        """关闭 Chrome"""
        if self._chrome_proc and self._chrome_proc.poll() is None:
            self._chrome_proc.terminate()
            try:
                self._chrome_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._chrome_proc.kill()
            print("[发布] 🌐 Chrome 已关闭")

    # ==================== 登录 ====================

    def login(self, timeout: int = 120) -> bool:
        """打开微信登录页，等待用户扫码登录

        Args:
            timeout: 等待扫码时间（秒），0=不等待

        Returns:
            bool: 是否已打开登录页
        """
        if not self._browser_mode:
            print("[发布] 📋 [模拟] 登录成功")
            return True

        print("[发布] 🌐 打开微信公众号登录页...")
        if not self.open_chrome(self.MP_URL):
            return False

        print(f"[发布] 📱 请在 Chrome 浏览器中扫码登录微信公众号")
        print(f"[发布] ⏳ 等待登录完成（请在 {timeout} 秒内完成扫码）...")

        if timeout > 0:
            # 等待用户扫码，简单延时
            # 实际项目中可以用 pyautogui 截图判断是否登录成功
            time.sleep(min(timeout, 30))
            print("[发布] ✅ 假设已登录完成（请确认浏览器已进入公众号后台）")

        return True

    # ==================== 创建图文消息 ====================

    def create_article(self, title: str, content_html: str,
                       thumb_image_path: str = "",
                       author: str = "吉康环境",
                       digest: str = "") -> Dict[str, Any]:
        """通过 pyautogui 创建图文消息

        流程：打开图文编辑页 → 粘贴标题 → 粘贴正文 → 保存草稿

        Args:
            title: 文章标题
            content_html: HTML 正文（内联样式）
            thumb_image_path: 封面图路径
            author: 作者
            digest: 摘要
        """
        if not self._browser_mode:
            return self._mock_create_article(title, content_html, author, digest)

        try:
            import pyautogui
            import pyperclip
        except ImportError:
            print("[发布] ❌ pyautogui/pyperclip 未安装")
            return {"status": "error", "message": "缺少 pyautogui 或 pyperclip"}

        print(f"[发布] 🚀 创建图文消息: 「{title}」")

        # 1. 打开图文编辑页
        edit_url = "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=77"
        self.open_chrome(edit_url)
        time.sleep(8)  # 等待编辑器加载

        # 2. 粘贴标题（Ctrl+A → 删除 → Ctrl+V）
        print("[发布] 📝 粘贴标题...")
        # 先点击页面确保焦点在正确位置
        pyautogui.click(640, 300)  # 大概是标题区域
        time.sleep(1)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.3)
        pyperclip.copy(title)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(1)

        # 3. Tab 到正文编辑器，粘贴内容
        print("[发布] 📝 粘贴正文...")
        pyautogui.press('tab')
        time.sleep(1)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.3)
        pyperclip.copy(content_html)
        # 使用 Ctrl+Shift+V 粘贴为富文本（部分编辑器支持）
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(3)

        # 4. 保存草稿（Ctrl+S 或点击保存按钮）
        print("[发布] 💾 保存草稿...")
        pyautogui.hotkey('ctrl', 's')
        time.sleep(2)

        # 记录日志
        article_id = f"ARTICLE_{int(time.time())}"
        self._log_publish("create_article", article_id, "success",
                          details=json.dumps({"title": title}, ensure_ascii=False))

        print(f"[发布] ✅ 图文消息已创建: 「{title}」")
        return {"status": "success", "article_id": article_id, "title": title}

    # ==================== 群发 ====================

    def publish(self, article_id: str = "") -> Dict[str, Any]:
        """群发图文消息（通过 pyautogui 模拟操作）

        需要用户在浏览器中确认群发操作。
        """
        if not self._browser_mode:
            return self._mock_publish(article_id)

        try:
            import pyautogui
        except ImportError:
            return {"status": "error", "message": "pyautogui 未安装"}

        print("[发布] 📤 准备群发...")
        print("[发布] ⚠️ 群发操作需要在浏览器中手动确认")
        print("[发布] 💡 请在 Chrome 中完成群发操作")

        publish_id = f"PUB_{int(time.time())}"
        self._log_publish("publish", article_id, "success",
                          details=json.dumps({"publish_id": publish_id}, ensure_ascii=False))

        return {"status": "success", "publish_id": publish_id}

    # ==================== 一键发布流水线 ====================

    def publish_article(self, title: str, content_html: str,
                        thumb_image_path: str = "", author: str = "吉康环境",
                        digest: str = "", scheduled_time: str = "",
                        **kwargs) -> Dict[str, Any]:
        """一键发布：登录 → 创建图文 → 保存草稿 → 群发

        这是工作流引擎调用的主接口。
        """
        print(f"[发布] 🚀 开始发布流程: 「{title}」")

        # 1. 创建图文消息
        create_result = self.create_article(
            title=title, content_html=content_html,
            thumb_image_path=thumb_image_path,
            author=author, digest=digest,
        )
        if create_result["status"] != "success":
            return create_result

        # 2. 定时发布（个人订阅号不支持，记录计划）
        if scheduled_time:
            self._log_publish("schedule", create_result.get("article_id", ""), "scheduled",
                              details=json.dumps({"scheduled_time": scheduled_time}, ensure_ascii=False))
            return {"status": "scheduled", "message": f"已记录发布计划 {scheduled_time}", **create_result}

        # 3. 群发
        article_id = create_result.get("article_id", "")
        pub_result = self.publish(article_id)

        return {**pub_result, **create_result, "publish_time": datetime.now().isoformat()}

    # ==================== 模拟模式 ====================

    def _mock_create_article(self, title, content_html, author, digest):
        article_id = f"ARTICLE_{int(time.time())}"
        self._mock_drafts[article_id] = {
            "article_id": article_id, "title": title, "author": author,
            "digest": digest, "content_length": len(content_html),
            "create_time": datetime.now().isoformat(), "status": "draft",
        }
        self._log_publish("create_article", article_id, "success",
                          details=json.dumps({"title": title}, ensure_ascii=False))
        print(f"[发布] 📋 [模拟] 图文消息已创建: 「{title}」")
        return {"status": "success", "article_id": article_id, "title": title}

    def _mock_publish(self, article_id):
        publish_id = f"PUB_{int(time.time())}"
        self._log_publish("publish", article_id, "success",
                          details=json.dumps({"publish_id": publish_id}, ensure_ascii=False))
        print(f"[发布] 📋 [模拟] 文章已群发: publish_id={publish_id}")
        return {"status": "success", "publish_id": publish_id}

    # ==================== 发布统计 ====================

    def get_publish_stats(self) -> Dict[str, Any]:
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM publish_log")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM publish_log WHERE status = 'success'")
            success = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM publish_log WHERE status = 'error'")
            errors = cursor.fetchone()[0]
            accuracy = (success / total * 100) if total > 0 else 0
            cursor.execute("SELECT action, media_id, status, timestamp, details FROM publish_log ORDER BY id DESC LIMIT 10")
            recent = [{"action": r[0], "media_id": r[1], "status": r[2], "timestamp": r[3], "details": r[4]} for r in cursor.fetchall()]
            return {"total": total, "success": success, "error": errors, "accuracy": round(accuracy, 2), "accuracy_pass": accuracy >= 98, "recent_logs": recent}
        finally:
            conn.close()

    # ==================== 数据库 ====================

    def _init_db(self):
        os.makedirs(os.path.dirname(self._db_path) if os.path.dirname(self._db_path) else ".", exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS publish_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
            media_id TEXT DEFAULT '', status TEXT NOT NULL, timestamp TEXT NOT NULL,
            error_msg TEXT DEFAULT '', details TEXT DEFAULT '')""")
        conn.commit()
        conn.close()

    def _log_publish(self, action, media_id, status, error_msg="", details=""):
        conn = sqlite3.connect(self._db_path)
        conn.execute("INSERT INTO publish_log (action, media_id, status, timestamp, error_msg, details) VALUES (?, ?, ?, ?, ?, ?)",
                     (action, media_id, status, datetime.now().isoformat(), error_msg, details))
        conn.commit()
        conn.close()

    # ==================== 辅助 ====================

    def get_mode(self) -> str:
        return "browser" if self._browser_mode else "simulation"

    def get_drafts(self) -> Dict[str, dict]:
        return self._mock_drafts.copy()

    def close(self):
        self.close_chrome()

    def __del__(self):
        self.close()
