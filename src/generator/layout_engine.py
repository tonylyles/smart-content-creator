"""排版权式引擎 - 刘凯睿负责

功能：
- Markdown内容结构化解析
- 微信公众号排版样式渲染
- 图文混排布局
- 多种排版模板（专业/简约/科技）
- 图片占位与配图建议
- 自适应排版（PC/移动端）
- 内容分段与视觉层次生成
"""
import re
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime


# ==================== 排版模板 ====================

LAYOUT_TEMPLATES = {
    "professional": {
        "name": "专业商务",
        "description": "适合政策解读、技术分析类内容",
        "h1_style": "font-size:22px;color:#1a5c2a;border-left:4px solid #2d8c4e;padding-left:12px;margin:24px 0 16px;font-weight:bold",
        "h2_style": "font-size:18px;color:#2d8c4e;border-bottom:1px solid #e8f5e9;padding-bottom:8px;margin:20px 0 12px;font-weight:bold",
        "h3_style": "font-size:16px;color:#3a7d3a;margin:16px 0 8px;font-weight:bold",
        "body_style": "font-size:15px;line-height:2;color:#333;margin:8px 0;text-align:justify",
        "quote_style": "background:#f5faf5;border-left:4px solid #2d8c4e;padding:12px 16px;margin:12px 0;color:#555;font-size:14px",
        "highlight_style": "background:linear-gradient(to right,#e8f5e9,#fff);padding:12px 16px;border-radius:8px;margin:12px 0",
        "brand_color": "#2d8c4e",
    },
    "minimal": {
        "name": "简约清新",
        "description": "适合资讯摘要、短篇快读",
        "h1_style": "font-size:20px;color:#333;text-align:center;margin:24px 0 16px;font-weight:bold",
        "h2_style": "font-size:17px;color:#555;margin:16px 0 10px;font-weight:bold",
        "h3_style": "font-size:15px;color:#666;margin:12px 0 6px;font-weight:bold",
        "body_style": "font-size:15px;line-height:1.8;color:#444;margin:6px 0",
        "quote_style": "background:#fafafa;border-left:3px solid #ccc;padding:10px 14px;margin:10px 0;color:#666;font-size:14px",
        "highlight_style": "background:#f9f9f9;padding:10px 14px;border-radius:6px;margin:10px 0",
        "brand_color": "#666",
    },
    "tech": {
        "name": "科技感",
        "description": "适合技术趋势、数据报告",
        "h1_style": "font-size:22px;color:#0d47a1;background:linear-gradient(to right,#e3f2fd,#fff);padding:12px 16px;border-radius:6px;margin:24px 0 16px;font-weight:bold",
        "h2_style": "font-size:18px;color:#1565c0;border-bottom:2px solid #1565c0;padding-bottom:6px;margin:20px 0 12px;font-weight:bold",
        "h3_style": "font-size:16px;color:#1976d2;margin:16px 0 8px;font-weight:bold",
        "body_style": "font-size:15px;line-height:2;color:#333;margin:8px 0;text-align:justify",
        "quote_style": "background:#e3f2fd;border-left:4px solid #1565c0;padding:12px 16px;margin:12px 0;color:#333;font-size:14px",
        "highlight_style": "background:linear-gradient(135deg,#e3f2fd,#f3e5f5);padding:12px 16px;border-radius:8px;margin:12px 0",
        "brand_color": "#1565c0",
    },
}

# 图片占位配置
IMAGE_PLACEHOLDERS = {
    "header": {
        "label": "封面图",
        "width": 900,
        "height": 383,
        "description": "文章封面配图，建议尺寸900×383",
    },
    "section": {
        "label": "章节配图",
        "width": 900,
        "height": 500,
        "description": "章节间配图，建议尺寸900×500",
    },
    "inline": {
        "label": "文中插图",
        "width": 400,
        "height": 300,
        "description": "文中说明性插图",
    },
}

# 品牌水印
BRAND_WATERMARK = "吉康环境 · AuraScribe"


class LayoutEngine:
    """排版权式引擎.

    将Markdown内容转换为排版精美的HTML，支持：
    - 多种排版模板
    - 图文混排布局
    - 配图建议与占位
    - 微信公众号兼容输出
    - 品牌元素注入

    Attributes:
        template_name: 当前使用的排版模板名称.
    """

    def __init__(self, template_name: str = "professional"):
        """初始化排版权式引擎.

        Args:
            template_name: 排版模板名称，可选值：professional/minimal/tech.
        """
        self.template_name = template_name
        self.template = LAYOUT_TEMPLATES.get(template_name, LAYOUT_TEMPLATES["professional"])

    def render(self, markdown_content: str, title: str = "",
               scene_type: str = "municipal",
               images: Optional[List[dict]] = None,
               include_watermark: bool = True) -> dict:
        """将Markdown渲染为排版HTML.

        Args:
            markdown_content: Markdown格式内容.
            title: 文章标题.
            scene_type: 场景类型.
            images: 配图列表，格式为 [{"type": "header|section|inline", "url": str, "alt": str}].
            include_watermark: 是否包含品牌水印.

        Returns:
            dict: {
                "html": str,
                "wechat_html": str,
                "image_suggestions": list[dict],
                "word_count": int,
                "reading_time_minutes": float
            }
        """
        images = images or []

        # 解析Markdown结构
        blocks = self._parse_markdown(markdown_content)

        # 注入图片
        blocks = self._inject_images(blocks, images)

        # 渲染为通用HTML
        html = self._render_html(blocks, title)

        # 渲染微信兼容HTML（内联样式）
        wechat_html = self._render_wechat_html(blocks, title)

        # 生成配图建议
        image_suggestions = self._suggest_images(blocks, scene_type)

        # 统计信息
        plain_text = re.sub(r'[#*`\[\]|>\-]', '', markdown_content)
        word_count = len(plain_text.replace("\n", "").replace(" ", ""))
        reading_time = round(word_count / 400, 1)

        # 品牌水印
        if include_watermark:
            watermark = self._build_watermark()
            html = html.replace("</body>", f"{watermark}</body>")
            wechat_html = wechat_html.replace("</section>", f"{watermark}</section>")

        return {
            "html": html,
            "wechat_html": wechat_html,
            "image_suggestions": image_suggestions,
            "word_count": word_count,
            "reading_time_minutes": reading_time,
        }

    def list_templates(self) -> dict:
        """列出所有可用排版模板.

        Returns:
            dict: {模板key: {"name": str, "description": str}}.
        """
        return {k: {"name": v["name"], "description": v["description"]}
                for k, v in LAYOUT_TEMPLATES.items()}

    def set_template(self, template_name: str) -> bool:
        """切换排版模板.

        Args:
            template_name: 模板名称.

        Returns:
            bool: 是否切换成功.
        """
        if template_name in LAYOUT_TEMPLATES:
            self.template_name = template_name
            self.template = LAYOUT_TEMPLATES[template_name]
            return True
        return False

    # ==================== Markdown 解析 ====================

    def _parse_markdown(self, content: str) -> List[dict]:
        """将Markdown解析为结构化块列表.

        Args:
            content: Markdown内容.

        Returns:
            list[dict]: [{"type": str, "content": str, "level": int, ...}]
        """
        blocks = []
        lines = content.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 标题
            heading_match = re.match(r'^(#{1,4})\s+(.+)', stripped)
            if heading_match:
                level = len(heading_match.group(1))
                blocks.append({
                    "type": "heading",
                    "level": level,
                    "content": heading_match.group(2),
                })
                i += 1
                continue

            # 引用
            if stripped.startswith(">"):
                quote_lines = []
                while i < len(lines) and lines[i].strip().startswith(">"):
                    quote_lines.append(lines[i].strip().lstrip("> "))
                    i += 1
                blocks.append({
                    "type": "quote",
                    "content": "\n".join(quote_lines),
                })
                continue

            # 表格
            if "|" in stripped and i + 1 < len(lines) and "---" in lines[i + 1]:
                table_lines = []
                while i < len(lines) and "|" in lines[i]:
                    table_lines.append(lines[i])
                    i += 1
                blocks.append({
                    "type": "table",
                    "content": "\n".join(table_lines),
                })
                continue

            # 代码块
            if stripped.startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # skip closing ```
                blocks.append({
                    "type": "code",
                    "content": "\n".join(code_lines),
                })
                continue

            # 列表
            if re.match(r'^[\-\*]\s', stripped) or re.match(r'^\d+\.\s', stripped):
                list_lines = []
                while i < len(lines) and (re.match(r'^[\-\*]\s', lines[i].strip()) or re.match(r'^\d+\.\s', lines[i].strip())):
                    list_lines.append(lines[i].strip())
                    i += 1
                blocks.append({
                    "type": "list",
                    "content": list_lines,
                })
                continue

            # 水平线
            if stripped in ["---", "***", "___"]:
                blocks.append({"type": "hr"})
                i += 1
                continue

            # 普通段落
            para_lines = []
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("#"):
                if re.match(r'^[\-\*]\s', lines[i].strip()) or re.match(r'^\d+\.\s', lines[i].strip()):
                    break
                if lines[i].strip().startswith(">") or lines[i].strip().startswith("```"):
                    break
                if "|" in lines[i] and i + 1 < len(lines) and "---" in lines.get(i + 1, ""):
                    break
                para_lines.append(lines[i])
                i += 1

            if para_lines:
                text = " ".join(para_lines).strip()
                if text:
                    blocks.append({
                        "type": "paragraph",
                        "content": text,
                    })
            else:
                i += 1

        return blocks

    # ==================== 图片注入 ====================

    def _inject_images(self, blocks: List[dict], images: List[dict]) -> List[dict]:
        """在内容块中注入图片.

        Args:
            blocks: 内容块列表.
            images: 图片列表.

        Returns:
            list[dict]: 注入图片后的块列表.
        """
        if not images:
            return blocks

        result = list(blocks)

        # 封面图插入最前面
        header_imgs = [img for img in images if img.get("type") == "header"]
        if header_imgs:
            img = header_imgs[0]
            result.insert(0, {
                "type": "image",
                "url": img.get("url", ""),
                "alt": img.get("alt", "封面图"),
                "width": IMAGE_PLACEHOLDERS["header"]["width"],
                "height": IMAGE_PLACEHOLDERS["header"]["height"],
            })

        # 章节配图：在每个h2后插入
        section_imgs = [img for img in images if img.get("type") == "section"]
        img_idx = 0
        inserted = 0
        for i, block in enumerate(list(result)):
            if block["type"] == "heading" and block["level"] == 2 and img_idx < len(section_imgs):
                img = section_imgs[img_idx]
                result.insert(i + 1 + inserted, {
                    "type": "image",
                    "url": img.get("url", ""),
                    "alt": img.get("alt", ""),
                    "width": IMAGE_PLACEHOLDERS["section"]["width"],
                    "height": IMAGE_PLACEHOLDERS["section"]["height"],
                })
                img_idx += 1
                inserted += 1

        # 文中插图：保持原位
        inline_imgs = [img for img in images if img.get("type") == "inline"]
        for img in inline_imgs:
            result.append({
                "type": "image",
                "url": img.get("url", ""),
                "alt": img.get("alt", ""),
                "width": IMAGE_PLACEHOLDERS["inline"]["width"],
                "height": IMAGE_PLACEHOLDERS["inline"]["height"],
            })

        return result

    def _suggest_images(self, blocks: List[dict], scene_type: str) -> List[dict]:
        """根据内容结构生成配图建议.

        Args:
            blocks: 内容块列表.
            scene_type: 场景类型.

        Returns:
            list[dict]: [{"position": str, "type": str, "suggestion": str}]
        """
        suggestions = []

        # 封面图
        suggestions.append({
            "position": "文章顶部",
            "type": "header",
            "suggestion": f"建议添加{SCENE_TYPE_LABELS.get(scene_type, '环保')}主题封面图",
        })

        # 每个h2后建议配图
        h2_count = sum(1 for b in blocks if b["type"] == "heading" and b.get("level") == 2)
        for i in range(min(h2_count, 3)):
            suggestions.append({
                "position": f"第{i+1}个章节标题后",
                "type": "section",
                "suggestion": "建议添加工艺流程图或项目实景图",
            })

        # 有表格的地方建议数据可视化
        table_count = sum(1 for b in blocks if b["type"] == "table")
        for i in range(min(table_count, 2)):
            suggestions.append({
                "position": "数据表格处",
                "type": "inline",
                "suggestion": "建议将表格数据制作成图表",
            })

        return suggestions

    # ==================== HTML 渲染 ====================

    def _render_html(self, blocks: List[dict], title: str) -> str:
        """渲染为通用HTML.

        Args:
            blocks: 内容块列表.
            title: 文章标题.

        Returns:
            str: HTML字符串.
        """
        tmpl = self.template
        parts = []

        parts.append(f'<html lang="zh-CN"><head><meta charset="UTF-8">')
        parts.append(f'<meta name="viewport" content="width=device-width,initial-scale=1.0">')
        parts.append(f'<title>{self._escape(title or "文章")}</title>')
        parts.append(f'<style>')
        parts.append(f'body{{max-width:680px;margin:0 auto;padding:20px;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}}')
        parts.append(f'</style></head><body>')

        for block in blocks:
            parts.append(self._render_block(block, tmpl, inline=False))

        parts.append('</body></html>')
        return "\n".join(parts)

    def _render_wechat_html(self, blocks: List[dict], title: str) -> str:
        """渲染为微信公众号兼容HTML（内联样式）.

        Args:
            blocks: 内容块列表.
            title: 文章标题.

        Returns:
            str: 微信兼容HTML字符串.
        """
        tmpl = self.template
        parts = []

        parts.append(f'<section style="max-width:680px;margin:0 auto;padding:16px;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif">')

        for block in blocks:
            parts.append(self._render_block(block, tmpl, inline=True))

        parts.append('</section>')
        return "\n".join(parts)

    def _render_block(self, block: dict, tmpl: dict, inline: bool = False) -> str:
        """渲染单个内容块.

        Args:
            block: 内容块.
            tmpl: 模板配置.
            inline: 是否内联样式（微信兼容）.

        Returns:
            str: HTML字符串.
        """
        block_type = block.get("type", "paragraph")

        if block_type == "heading":
            level = block.get("level", 2)
            content = self._render_inline_markdown(block["content"])
            if level == 1:
                style = tmpl["h1_style"]
            elif level == 2:
                style = tmpl["h2_style"]
            else:
                style = tmpl["h3_style"]
            tag = f"h{min(level, 3)}"
            return f'<{tag} style="{style}">{content}</{tag}>'

        elif block_type == "paragraph":
            content = self._render_inline_markdown(block["content"])
            style = tmpl["body_style"]
            return f'<p style="{style}">{content}</p>'

        elif block_type == "quote":
            content = self._render_inline_markdown(block["content"])
            style = tmpl["quote_style"]
            return f'<blockquote style="{style}">{content}</blockquote>'

        elif block_type == "list":
            items = block["content"]
            style = tmpl["body_style"]
            html_items = []
            for item in items:
                item_text = self._render_inline_markdown(item.lstrip("- *").strip())
                html_items.append(f'<li style="{style}">{item_text}</li>')
            return f'<ul style="padding-left:20px">{"".join(html_items)}</ul>'

        elif block_type == "table":
            return self._render_table(block["content"], tmpl)

        elif block_type == "code":
            content = self._escape(block["content"])
            return f'<pre style="background:#1a2a1a;color:#e0e0e0;padding:16px;border-radius:6px;overflow-x:auto;font-size:13px"><code>{content}</code></pre>'

        elif block_type == "image":
            url = block.get("url", "")
            alt = self._escape(block.get("alt", ""))
            width = block.get("width", 900)
            if url:
                return f'<figure style="text-align:center;margin:16px 0"><img src="{url}" alt="{alt}" style="max-width:100%;border-radius:6px" /><figcaption style="font-size:12px;color:#999;margin-top:4px">{alt}</figcaption></figure>'
            else:
                return f'<div style="background:#f0f0f0;height:200px;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#999;margin:16px 0">📷 {alt or "图片占位"}</div>'

        elif block_type == "hr":
            return f'<hr style="border:none;border-top:1px solid #e0e0e0;margin:24px 0" />'

        return ""

    def _render_table(self, content: str, tmpl: dict) -> str:
        """渲染表格.

        Args:
            content: Markdown表格文本.
            tmpl: 模板配置.

        Returns:
            str: HTML表格.
        """
        lines = [l.strip() for l in content.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            return ""

        header_cells = [c.strip() for c in lines[0].split("|") if c.strip()]
        rows = []
        for line in lines[2:]:  # skip separator
            cells = [c.strip() for c in line.split("|") if c.strip()]
            rows.append(cells)

        brand_color = tmpl["brand_color"]
        parts = [f'<table style="border-collapse:collapse;width:100%;margin:12px 0;font-size:14px">']

        # Header
        parts.append(f'<tr>')
        for cell in header_cells:
            parts.append(f'<th style="background:{brand_color};color:#fff;padding:8px 12px;border:1px solid #ddd;text-align:left">{self._render_inline_markdown(cell)}</th>')
        parts.append('</tr>')

        # Rows
        for row in rows:
            parts.append('<tr>')
            for cell in row:
                parts.append(f'<td style="padding:8px 12px;border:1px solid #ddd">{self._render_inline_markdown(cell)}</td>')
            parts.append('</tr>')

        parts.append('</table>')
        return "".join(parts)

    def _render_inline_markdown(self, text: str) -> str:
        """渲染行内Markdown（加粗、链接等）.

        Args:
            text: 包含行内Markdown的文本.

        Returns:
            str: HTML字符串.
        """
        # 加粗
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # 链接
        text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2" style="color:#2d8c4e">\1</a>', text)
        # 行内代码
        text = re.sub(r'`(.+?)`', r'<code style="background:#f0f5f0;padding:2px 6px;border-radius:3px;font-size:13px">\1</code>', text)
        return text

    def _build_watermark(self) -> str:
        """构建品牌水印.

        Returns:
            str: 水印HTML.
        """
        now = datetime.now().strftime("%Y年%m月")
        return f'<div style="text-align:center;padding:20px 0;margin-top:24px;border-top:1px solid #e8f5e9;color:#999;font-size:12px">{BRAND_WATERMARK} | {now}</div>'

    @staticmethod
    def _escape(text: str) -> str:
        """HTML转义.

        Args:
            text: 待转义文本.

        Returns:
            str: 转义后的文本.
        """
        return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


# 场景类型中文标签
SCENE_TYPE_LABELS = {
    "municipal": "市政环保",
    "industrial": "工业环保",
}
