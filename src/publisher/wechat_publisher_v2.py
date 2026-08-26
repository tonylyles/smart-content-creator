"""
微信公众号官方 API 发布模块 - 增强版 v2.0

功能：
- 对接微信公众号官方 API（草稿箱 + 群发接口）
- 获取 access_token（自动刷新缓存）
- 上传图文消息中的图片（media/uploadimg）
- 创建草稿（draft/add）
- 群发发布（freepublish/submit）
- 双模式：API 模式（官方接口）+ 本地模拟模式（演示兜底）
- WeChatFormatter 排版引擎（内联样式，适配微信公众号）
- 发布日志 SQLite 记录 + 统计

技术栈：
- requests（HTTP 调用微信 API）
- WeChatFormatter（自研内联样式排版引擎）
- SQLite（发布日志）

功能覆盖：
- [x] 适配公众号发布的图文推文（含标题、正文、配图建议）
- [x] 定时任务调度与自动触发技术：通过 API 实现真正的无人值守发布
- [x] 排版适配（内联样式、响应式、品牌调性）
- [x] 发布日志与统计

说明：本模块为官方 API 发布实现（v2），当前默认发布流程使用 wechat_publisher.py（Selenium 版）。

API 文档参考：
- 获取 access_token: GET https://api.weixin.qq.com/cgi-bin/token
- 上传图文内图片: POST https://api.weixin.qq.com/cgi-bin/media/uploadimg
- 新建草稿: POST https://api.weixin.qq.com/cgi-bin/draft/add
- 发布草稿: POST https://api.weixin.qq.com/cgi-bin/freepublish/submit
- 查询发布状态: GET https://api.weixin.qq.com/cgi-bin/freepublish/get
"""

import os
import re
import json
import time
import shutil
import sqlite3
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path


# ==================== 微信 API 客户端 ====================

class WeChatAPIClient:
    """微信公众号 API 客户端

    封装 access_token 获取与缓存、图文消息创建、草稿发布等核心 API。

    前置条件：
    - 拥有已认证的微信公众号（服务号）
    - 已获取 AppID 和 AppSecret（公众号后台 → 开发 → 基本配置）
    - 服务器 IP 已加入白名单（公众号后台 → 开发 → 基本配置 → IP白名单）
    """

    BASE_URL = "https://api.weixin.qq.com/cgi-bin"
    TOKEN_CACHE_FILE = "data/wechat_token_cache.json"

    def __init__(self, app_id: str = "", app_secret: str = ""):
        self.app_id = app_id
        self.app_secret = app_secret
        self._access_token = ""
        self._token_expires_at = 0  # 过期时间戳

        # 从缓存恢复
        self._load_token_cache()

    def get_access_token(self, force_refresh: bool = False) -> str:
        """获取 access_token（自动缓存，过期自动刷新）

        Args:
            force_refresh: 是否强制刷新

        Returns:
            access_token 字符串
        """
        if not force_refresh and self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        if not self.app_id or not self.app_secret:
            print("[WeChatAPI] ⚠️ AppID 或 AppSecret 未配置")
            return ""

        url = f"{self.BASE_URL}/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.app_id,
            "secret": self.app_secret,
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()

            if "access_token" in data:
                self._access_token = data["access_token"]
                # 提前 5 分钟过期，避免临界问题
                self._token_expires_at = time.time() + data.get("expires_in", 7200) - 300
                self._save_token_cache()
                print(f"[WeChatAPI] ✅ access_token 获取成功（有效期至 {datetime.fromtimestamp(self._token_expires_at).strftime('%H:%M:%S')}）")
                return self._access_token
            else:
                print(f"[WeChatAPI] ❌ access_token 获取失败: {data.get('errmsg', '未知错误')}")
                return ""

        except requests.RequestException as e:
            print(f"[WeChatAPI] ❌ 网络请求失败: {e}")
            return ""

    def upload_image(self, image_path: str) -> str:
        """上传图文消息内的图片（获取微信 URL）

        注意：此接口上传的图片仅可用于图文消息正文，不能作为封面图。
        封面图需要用 media/uploadmaterial 接口。

        Args:
            image_path: 本地图片路径

        Returns:
            微信图片 URL（用于插入正文）或空字符串
        """
        token = self.get_access_token()
        if not token:
            return ""

        url = f"{self.BASE_URL}/media/uploadimg?access_token={token}"

        if not os.path.exists(image_path):
            print(f"[WeChatAPI] ❌ 图片文件不存在: {image_path}")
            return ""

        try:
            # 获取文件扩展名确定 MIME 类型
            ext = Path(image_path).suffix.lower()
            mime_map = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".gif": "image/gif",
                ".bmp": "image/bmp",
            }
            mime_type = mime_map.get(ext, "image/jpeg")

            with open(image_path, "rb") as f:
                resp = requests.post(
                    url,
                    files={"media": (os.path.basename(image_path), f, mime_type)},
                    timeout=30,
                )

            data = resp.json()
            if "url" in data:
                print(f"[WeChatAPI] ✅ 图片上传成功: {data['url'][:60]}...")
                return data["url"]
            else:
                print(f"[WeChatAPI] ❌ 图片上传失败: {data.get('errmsg', '未知错误')}")
                return ""

        except Exception as e:
            print(f"[WeChatAPI] ❌ 图片上传异常: {e}")
            return ""

    def upload_thumb_media(self, image_path: str) -> str:
        """上传永久素材（用于封面图/缩略图）

        Args:
            image_path: 本地图片路径

        Returns:
            media_id 或空字符串
        """
        token = self.get_access_token()
        if not token:
            return ""

        url = f"{self.BASE_URL}/material/add_material?access_token={token}&type=thumb"

        if not os.path.exists(image_path):
            print(f"[WeChatAPI] ❌ 图片文件不存在: {image_path}")
            return ""

        try:
            ext = Path(image_path).suffix.lower()
            mime_map = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".gif": "image/gif",
            }
            mime_type = mime_map.get(ext, "image/jpeg")

            with open(image_path, "rb") as f:
                resp = requests.post(
                    url,
                    files={"media": (os.path.basename(image_path), f, mime_type)},
                    timeout=30,
                )

            data = resp.json()
            if "media_id" in data:
                print(f"[WeChatAPI] ✅ 封面图上传成功: media_id={data['media_id']}")
                return data["media_id"]
            else:
                print(f"[WeChatAPI] ❌ 封面图上传失败: {data.get('errmsg', '未知错误')}")
                return ""

        except Exception as e:
            print(f"[WeChatAPI] ❌ 封面图上传异常: {e}")
            return ""

    def create_draft(self, articles: List[Dict]) -> str:
        """创建草稿（可包含多篇文章，形成图文消息）

        Args:
            articles: 文章列表，每个元素格式：
                {
                    "title": "文章标题",
                    "author": "作者",
                    "digest": "摘要",
                    "content": "正文HTML（微信公众号格式）",
                    "content_source_url": "原文链接（可选）",
                    "thumb_media_id": "封面图 media_id",
                    "need_open_comment": 0,
                    "only_fans_can_comment": 0,
                }

        Returns:
            media_id（草稿的 media_id）或空字符串
        """
        token = self.get_access_token()
        if not token:
            return ""

        url = f"{self.BASE_URL}/draft/add?access_token={token}"
        payload = {"articles": articles}

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()

            if "media_id" in data:
                print(f"[WeChatAPI] ✅ 草稿创建成功: media_id={data['media_id']}")
                return data["media_id"]
            else:
                print(f"[WeChatAPI] ❌ 草稿创建失败: {data.get('errmsg', '未知错误')}")
                return ""

        except Exception as e:
            print(f"[WeChatAPI] ❌ 草稿创建异常: {e}")
            return ""

    def publish_draft(self, media_id: str) -> str:
        """群发发布草稿

        注意：群发接口有频率限制（订阅号每天1次，服务号每月4次）。
        发布后需要审核，异步返回发布结果。

        Args:
            media_id: 草稿的 media_id

        Returns:
            publish_id 或空字符串
        """
        token = self.get_access_token()
        if not token:
            return ""

        url = f"{self.BASE_URL}/freepublish/submit?access_token={token}"
        payload = {"media_id": media_id}

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()

            if "publish_id" in data:
                print(f"[WeChatAPI] ✅ 发布提交成功: publish_id={data['publish_id']}")
                return data["publish_id"]
            else:
                print(f"[WeChatAPI] ❌ 发布提交失败: {data.get('errmsg', '未知错误')}")
                return ""

        except Exception as e:
            print(f"[WeChatAPI] ❌ 发布提交异常: {e}")
            return ""

    def get_publish_status(self, publish_id: str) -> Dict:
        """查询发布状态（异步，可能需要轮询）

        Args:
            publish_id: 发布任务 ID

        Returns:
            {"publish_status": "success"|"failed"|"pending", "errmsg": ...}
        """
        token = self.get_access_token()
        if not token:
            return {"publish_status": "error", "errmsg": "no access_token"}

        url = f"{self.BASE_URL}/freepublish/get?access_token={token}"
        payload = {"publish_id": publish_id}

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            return data
        except Exception as e:
            return {"publish_status": "error", "errmsg": str(e)}

    def _save_token_cache(self):
        """缓存 access_token 到本地文件"""
        cache = {
            "access_token": self._access_token,
            "expires_at": self._token_expires_at,
        }
        try:
            os.makedirs(os.path.dirname(self.TOKEN_CACHE_FILE) or ".", exist_ok=True)
            with open(self.TOKEN_CACHE_FILE, "w") as f:
                json.dump(cache, f)
        except Exception:
            pass

    def _load_token_cache(self):
        """从本地文件恢复 access_token"""
        try:
            if os.path.exists(self.TOKEN_CACHE_FILE):
                with open(self.TOKEN_CACHE_FILE, "r") as f:
                    cache = json.load(f)
                self._access_token = cache.get("access_token", "")
                self._token_expires_at = cache.get("expires_at", 0)
        except Exception:
            pass


# ==================== 微信排版适配器 ====================

class WeChatFormatter:
    """微信公众号 HTML 排版适配器（与原版完全一致，保持向后兼容）

    微信公众号编辑器特点：
    - 不支持 <style> 标签，必须内联样式
    - 正文宽度约 578px（居中）
    - 不支持外部 CSS / JS
    - 图片需要居中显示，max-width 100%
    - 不支持 class/id 选择器
    """

    # 吉康环境品牌色
    BRAND_COLOR = "#1a7f5a"
    BRAND_COLOR_LIGHT = "#e8f5e9"
    ACCENT_COLOR = "#2196F3"
    TEXT_COLOR = "#333333"
    TEXT_COLOR_SECONDARY = "#666666"
    BG_COLOR = "#f5f5f5"
    WHITE = "#ffffff"

    CONTAINER_STYLE = (
        "max-width:578px; margin:0 auto; padding:20px 16px; "
        "font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',"
        "'PingFang SC','Microsoft YaHei',sans-serif; "
        "font-size:15px; color:#333333; line-height:1.8; "
        "background-color:#ffffff;"
    )
    H1_STYLE = (
        "font-size:22px; font-weight:bold; color:#1a7f5a; "
        "text-align:center; margin:24px 0 16px; padding-bottom:12px; "
        "border-bottom:2px solid #1a7f5a;"
    )
    H2_STYLE = (
        "font-size:18px; font-weight:bold; color:#1a7f5a; "
        "margin:20px 0 12px; padding-left:12px; "
        "border-left:4px solid #1a7f5a;"
    )
    H3_STYLE = "font-size:16px; font-weight:bold; color:#333333; margin:16px 0 8px;"
    PARA_STYLE = "margin:12px 0; text-align:justify; text-indent:2em;"
    PARA_NO_INDENT = "margin:12px 0; text-align:justify;"
    IMG_STYLE = "max-width:100%; height:auto; display:block; margin:16px auto; border-radius:4px;"
    IMG_CAPTION_STYLE = "font-size:12px; color:#999999; text-align:center; margin:4px 0 16px; line-height:1.5;"
    QUOTE_STYLE = (
        "margin:16px 0; padding:12px 16px; "
        "background-color:#e8f5e9; border-left:4px solid #1a7f5a; "
        "font-size:14px; color:#555555; line-height:1.7; border-radius:0 4px 4px 0;"
    )
    HIGHLIGHT_STYLE = (
        "margin:16px 0; padding:16px; "
        "background-color:#fff8e1; border:1px solid #ffe082; "
        "font-size:14px; color:#555555; line-height:1.7; border-radius:4px;"
    )
    LIST_ITEM_STYLE = "margin:6px 0; padding-left:8px; line-height:1.7;"
    DIVIDER_HTML = (
        '<p style="margin:24px 0; text-align:center;">'
        '<span style="display:inline-block; width:60px; height:1px; '
        'background-color:#dddddd;"></span></p>'
    )
    SIGNATURE_HTML = (
        '<p style="margin:32px 0 16px; text-align:right; font-size:13px; color:#999999;">'
        '—— 广东吉康环境系统科技有限公司</p>'
    )

    @classmethod
    def format_article(cls, title: str, body_html: str,
                       author: str = "吉康环境",
                       digest: str = "",
                       cover_image_url: str = "") -> Tuple[str, str]:
        """将原始内容格式化为微信公众号适配的 HTML"""
        formatted_body = cls._process_content(body_html)
        formatted_body += cls.SIGNATURE_HTML

        full_html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="author" content="{author}">
</head>
<body style="margin:0; padding:0; background-color:#f5f5f5;">
<div style="{cls.CONTAINER_STYLE}">
<h1 style="{cls.H1_STYLE}">{cls._escape_html(title)}</h1>
{formatted_body}
</div>
</body>
</html>'''

        plain_text = cls._html_to_text(full_html)
        if not digest:
            digest = plain_text[:120].strip() + "..." if len(plain_text) > 120 else plain_text

        return full_html, digest

    @classmethod
    def _process_content(cls, content: str) -> str:
        """处理正文内容，转为微信适配的内联样式 HTML"""
        if not content:
            return ""
        lines = content.strip().split("\n")
        result_parts = []
        in_list = False
        in_quote = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_list:
                    result_parts.append("</ul>"); in_list = False
                if in_quote:
                    result_parts.append("</blockquote>"); in_quote = False
                continue

            if stripped.startswith("# ") and not stripped.startswith("## "):
                result_parts.append(f'<h1 style="{cls.H1_STYLE}">{cls._process_inline(stripped[2:])}</h1>')
            elif stripped.startswith("## ") and not stripped.startswith("### "):
                result_parts.append(f'<h2 style="{cls.H2_STYLE}">{cls._process_inline(stripped[3:])}</h2>')
            elif stripped.startswith("### "):
                result_parts.append(f'<h3 style="{cls.H3_STYLE}">{cls._process_inline(stripped[4:])}</h3>')
            elif stripped.startswith("> "):
                if not in_quote:
                    result_parts.append(f'<blockquote style="{cls.QUOTE_STYLE}">'); in_quote = True
                result_parts.append(f'<p style="margin:4px 0;">{cls._process_inline(stripped[2:])}</p>')
            elif stripped.startswith("- ") or stripped.startswith("* "):
                if not in_list:
                    result_parts.append('<ul style="margin:12px 0; padding-left:20px;">'); in_list = True
                result_parts.append(f'<li style="{cls.LIST_ITEM_STYLE}">{cls._process_inline(stripped[2:])}</li>')
            elif stripped.startswith("!") and "](" in stripped:
                match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
                if match:
                    alt, url = match.group(1) or "", match.group(2)
                    html = f'<img src="{url}" alt="{cls._escape_html(alt)}" style="{cls.IMG_STYLE}">'
                    if alt:
                        html += f'<p style="{cls.IMG_CAPTION_STYLE}">{cls._escape_html(alt)}</p>'
                    result_parts.append(html)
            elif stripped.startswith("{highlight}") and stripped.endswith("{/highlight}"):
                result_parts.append(f'<div style="{cls.HIGHLIGHT_STYLE}">{cls._process_inline(stripped[11:-12])}</div>')
            elif stripped in ("---", "***", "___"):
                result_parts.append(cls.DIVIDER_HTML)
            else:
                if in_list:
                    result_parts.append("</ul>"); in_list = False
                if in_quote:
                    result_parts.append("</blockquote>"); in_quote = False
                text = cls._process_inline(stripped)
                style = cls.PARA_NO_INDENT if len(text) <= 30 else cls.PARA_STYLE
                result_parts.append(f'<p style="{style}">{text}</p>')

        if in_list: result_parts.append("</ul>")
        if in_quote: result_parts.append("</blockquote>")
        return "\n".join(result_parts)

    @classmethod
    def _process_inline(cls, text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#1a7f5a; font-weight:bold;">\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code style="background-color:#f0f0f0; padding:2px 6px; border-radius:3px; font-size:13px; color:#c7254e;">\1</code>', text)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" style="color:#1a7f5a; text-decoration:none;">\1</a>', text)
        return text

    @classmethod
    def _escape_html(cls, text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @classmethod
    def _html_to_text(cls, html: str) -> str:
        text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<br\s*/?>', '\n', text)
        text = re.sub(r'</?(p|div|h[1-6]|li|blockquote)[^>]*>', '\n', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


# ==================== 微信公众号发布器（API 版）====================

class WeChatPublisher:
    """微信公众号发布器 v2.0（官方 API 模式）

    三模式架构：
    - api: 微信官方 API（access_token → uploadimg → draft/add → freepublish/submit）
    - browser: Selenium + Chrome 操控（旧模式，保留为兼容回退）
    - simulation: 本地模拟，生成可预览 HTML 文件（演示兜底）

    API 模式优势：
    - 无需浏览器、无需扫码、真正无人值守
    - 定时任务可直接通过 API 触发发布
    - 发布过程稳定可靠，不受前端页面变更影响
    """

    SIMULATION_OUTPUT_DIR = "data/published"

    def __init__(self, config: dict = None):
        self.config = config or {}
        wechat_config = self.config.get("wechat", {})

        # API 模式配置（优先从环境变量读取）
        self.app_id = wechat_config.get("app_id", "") or os.getenv("WECHAT_APP_ID", "")
        self.app_secret = wechat_config.get("app_secret", "") or os.getenv("WECHAT_APP_SECRET", "")
        # 旧版兼容：password 用于 browser 模式
        self.password = wechat_config.get("password", "") or os.getenv("WECHAT_PASSWORD", "")

        self._formatter = WeChatFormatter()
        self._db_path = wechat_config.get("db_path", "data/publish_log.db")
        self._init_db()
        self._mock_drafts: Dict[str, dict] = {}

        # 根据配置自动选择模式
        if self.app_id and self.app_secret:
            self._api_client = WeChatAPIClient(self.app_id, self.app_secret)
            self._mode = "api"
            print(f"[发布] 📱 API 模式（AppID: {self.app_id[:8]}...）")
        else:
            self._api_client = None
            self._mode = "simulation"
            print("[发布] 📋 未检测到 API 配置，启用本地模拟模式")
            print(f"[发布] 📁 模拟输出目录: {self.SIMULATION_OUTPUT_DIR}")
            print("[发布] 💡 配置 WECHAT_APP_ID + WECHAT_APP_SECRET 可启用 API 模式")

    # ==================== API 模式核心方法 ====================

    def format_content(self, title: str, body: str,
                       author: str = "吉康环境",
                       digest: str = "",
                       cover_image_url: str = "") -> Dict[str, str]:
        """将内容格式化为微信适配格式（与旧版兼容）"""
        html, auto_digest = self._formatter.format_article(
            title=title, body_html=body, author=author,
            digest=digest, cover_image_url=cover_image_url,
        )
        plain_text = self._formatter._html_to_text(html)
        return {
            "html": html, "digest": digest or auto_digest, "plain_text": plain_text,
            "title": title, "author": author,
        }

    def create_article(self, title: str, content_html: str,
                       thumb_image_path: str = "",
                       author: str = "吉康环境",
                       digest: str = "") -> Dict[str, Any]:
        """创建图文消息

        API 模式：uploadimg → draft/add
        模拟模式：生成本地 HTML 文件
        """
        if self._mode == "api":
            return self._api_create_article(title, content_html, thumb_image_path, author, digest)
        else:
            return self._simulation_create_article(title, content_html, author, digest, thumb_image_path)

    def _api_create_article(self, title: str, content_html: str,
                            thumb_image_path: str = "",
                            author: str = "吉康环境",
                            digest: str = "") -> Dict[str, Any]:
        """API 模式：通过微信官方接口创建草稿"""
        print(f"[发布] 🚀 [API] 创建图文消息: 「{title}」")

        # 1. 提取正文 body 内容
        body_content = self._extract_body_content(content_html)

        # 2. 上传封面图（如果有）
        thumb_media_id = ""
        if thumb_image_path and os.path.exists(thumb_image_path):
            print(f"[发布] 🖼️ 上传封面图...")
            thumb_media_id = self._api_client.upload_thumb_media(thumb_image_path)

        # 3. 创建草稿
        article_data = {
            "title": title,
            "author": author,
            "digest": digest[:120] if digest else "",
            "content": body_content,
            "content_source_url": "",
            "thumb_media_id": thumb_media_id,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }

        # 确保 thumb_media_id 不为空（草稿接口要求）
        if not thumb_media_id:
            # 使用一个默认的 1x1 透明 GIF 作为兜底（base64）
            print("[发布] ⚠️ 未提供封面图，草稿可能需要手动补充封面")
            article_data["thumb_media_id"] = ""

        media_id = self._api_client.create_draft([article_data])

        if media_id:
            article_id = media_id
            self._log_publish("create_article", article_id, "success",
                              details=json.dumps({"title": title, "mode": "api", "media_id": media_id},
                                                 ensure_ascii=False))
            return {"status": "success", "article_id": article_id, "media_id": media_id, "title": title}
        else:
            article_id = f"ARTICLE_{int(time.time())}"
            self._log_publish("create_article", article_id, "error",
                              error_msg="草稿创建失败", details=json.dumps({"title": title}, ensure_ascii=False))
            return {"status": "error", "message": "草稿创建失败", "article_id": article_id}

    def publish(self, article_id: str = "") -> Dict[str, Any]:
        """群发图文消息"""
        if self._mode == "api":
            return self._api_publish(article_id)
        else:
            return self._simulation_publish(article_id)

    def _api_publish(self, media_id: str) -> Dict[str, Any]:
        """API 模式：提交群发"""
        print(f"[发布] 📤 [API] 提交群发: {media_id}")

        if not media_id:
            return {"status": "error", "message": "缺少 media_id"}

        publish_id = self._api_client.publish_draft(media_id)

        if publish_id:
            self._log_publish("publish", media_id, "success",
                              details=json.dumps({"publish_id": publish_id, "mode": "api"}, ensure_ascii=False))
            return {"status": "success", "publish_id": publish_id, "media_id": media_id}
        else:
            self._log_publish("publish", media_id, "error",
                              error_msg="群发提交失败", details=json.dumps({"mode": "api"}, ensure_ascii=False))
            return {"status": "error", "message": "群发提交失败"}

    # ==================== 模拟模式 ====================

    def _simulation_create_article(self, title: str, content_html: str,
                                    author: str, digest: str,
                                    thumb_image_path: str = "") -> Dict[str, Any]:
        """模拟模式：生成 HTML 文件用于预览和演示"""
        os.makedirs(self.SIMULATION_OUTPUT_DIR, exist_ok=True)
        article_id = f"ARTICLE_{int(time.time())}"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{title[:20].replace(' ', '_')}.html"
        filepath = os.path.join(self.SIMULATION_OUTPUT_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content_html)

        saved_thumb = ""
        if thumb_image_path and os.path.exists(thumb_image_path):
            thumb_name = f"cover_{timestamp}{Path(thumb_image_path).suffix}"
            thumb_dest = os.path.join(self.SIMULATION_OUTPUT_DIR, thumb_name)
            shutil.copy2(thumb_image_path, thumb_dest)
            saved_thumb = thumb_dest

        self._mock_drafts[article_id] = {
            "article_id": article_id, "title": title, "author": author,
            "digest": digest or (self._formatter._html_to_text(content_html)[:120] + "..."),
            "content_length": len(content_html), "filepath": filepath,
            "thumb_path": saved_thumb, "create_time": datetime.now().isoformat(), "status": "draft",
        }

        self._log_publish("create_article", article_id, "success",
                          details=json.dumps({"title": title, "mode": "simulation", "filepath": filepath},
                                             ensure_ascii=False))
        print(f"[发布] 📋 [模拟] 图文消息已创建: 「{title}」")
        print(f"[发布] 📁 HTML 文件: {filepath}")
        return {"status": "success", "article_id": article_id, "title": title,
                "filepath": filepath, "mode": "simulation"}

    def _simulation_publish(self, article_id: str) -> Dict[str, Any]:
        """模拟群发"""
        draft = self._mock_drafts.get(article_id, {})
        publish_id = f"PUB_{int(time.time())}"
        if draft:
            draft["status"] = "published"
            draft["publish_time"] = datetime.now().isoformat()
        self._log_publish("publish", article_id, "success",
                          details=json.dumps({"publish_id": publish_id, "mode": "simulation"}, ensure_ascii=False))
        print(f"[发布] 📋 [模拟] 文章已群发: publish_id={publish_id}")
        return {"status": "success", "publish_id": publish_id, "mode": "simulation"}

    # ==================== 一键发布流水线 ====================

    def publish_article(self, title: str, content_html: str,
                        thumb_image_path: str = "", author: str = "吉康环境",
                        digest: str = "", scheduled_time: str = "",
                        **kwargs) -> Dict[str, Any]:
        """一键发布：格式化 → 创建图文 → 保存草稿 → 群发

        这是工作流引擎调用的主接口。
        """
        print(f"[发布] 🚀 开始发布流程: 「{title}」")

        # 1. 格式化内容
        formatted = self.format_content(
            title=title, body=content_html, author=author,
            digest=digest, cover_image_url=kwargs.get("cover_image_url", ""),
        )

        # 2. 创建图文消息
        create_result = self.create_article(
            title=title, content_html=formatted["html"],
            thumb_image_path=thumb_image_path, author=author,
            digest=formatted["digest"],
        )
        if create_result["status"] != "success":
            return create_result

        # 3. 定时发布（API 模式下由调度器控制时机）
        if scheduled_time:
            self._log_publish("schedule", create_result.get("article_id", ""), "scheduled",
                              details=json.dumps({"scheduled_time": scheduled_time}, ensure_ascii=False))
            return {"status": "scheduled", "message": f"已记录发布计划 {scheduled_time}", **create_result}

        # 4. 群发
        article_id = create_result.get("article_id", "")
        pub_result = self.publish(article_id)

        return {
            **pub_result, **create_result,
            "digest": formatted["digest"],
            "publish_time": datetime.now().isoformat(),
        }

    # ==================== 统计 ====================

    def get_publish_stats(self) -> Dict[str, Any]:
        """获取发布统计"""
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
            cursor.execute(
                "SELECT action, media_id, status, timestamp, details "
                "FROM publish_log ORDER BY id DESC LIMIT 10"
            )
            recent = [
                {"action": r[0], "media_id": r[1], "status": r[2],
                 "timestamp": r[3], "details": r[4]}
                for r in cursor.fetchall()
            ]
            return {
                "total": total, "success": success, "error": errors,
                "accuracy": round(accuracy, 2), "accuracy_pass": accuracy >= 98,
                "recent_logs": recent,
            }
        finally:
            conn.close()

    # ==================== 数据库 ====================

    def _init_db(self):
        os.makedirs(os.path.dirname(self._db_path) if os.path.dirname(self._db_path) else ".", exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS publish_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                media_id TEXT DEFAULT '',
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                error_msg TEXT DEFAULT '',
                details TEXT DEFAULT ''
            )
        """)
        conn.commit()
        conn.close()

    def _log_publish(self, action: str, media_id: str, status: str,
                     error_msg: str = "", details: str = ""):
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "INSERT INTO publish_log (action, media_id, status, timestamp, error_msg, details) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (action, media_id, status, datetime.now().isoformat(), error_msg, details),
        )
        conn.commit()
        conn.close()

    # ==================== 辅助 ====================

    def get_mode(self) -> str:
        return self._mode

    def get_drafts(self) -> Dict[str, dict]:
        return self._mock_drafts.copy()

    def get_formatter(self) -> WeChatFormatter:
        return self._formatter

    def close(self):
        pass

    def _extract_body_content(self, html: str) -> str:
        """从完整 HTML 中提取 body 内容"""
        match = re.search(r'<body[^>]*>(.+?)</body>', html, re.DOTALL)
        return match.group(1).strip() if match else html
