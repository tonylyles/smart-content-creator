"""多模态处理模块 - 刘凯睿负责

功能：
- 图片生成提示词构建
- 配图策略推荐
- 图文混排内容组装
- 图片占位符管理
- 场景化视觉元素推荐
- 与layout_engine集成

注意：实际的图片生成依赖外部服务（如DALL-E/MidJourney），
本模块负责构建请求参数和配图策略，不直接调用图片生成API。
"""
import re
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from src.generator.layout_engine import LayoutEngine, SCENE_TYPE_LABELS


# ==================== 配图策略 ====================

SCENE_IMAGE_STRATEGY = {
    "municipal": {
        "cover_style": "环保蓝绿色调，城市天际线与水处理设施融合，专业商务风格",
        "section_styles": [
            "污水处理厂鸟瞰图，蓝绿主色调",
            "智能监控大屏实时数据，科技蓝风格",
            "再生水管道系统示意图，简洁线条",
            "绿植环绕的环保设施，自然清新风格",
        ],
        "color_palette": ["#1a5c2a", "#2d8c4e", "#e8f5e9", "#f5faf5"],
    },
    "industrial": {
        "cover_style": "工业科技风，厂房与净化设备，深蓝灰调",
        "section_styles": [
            "VOCs催化燃烧设备特写，金属质感",
            "废水零排放系统流程图，工业风",
            "危废处置车间实景，专业严肃",
            "清洁生产审核报告封面，简约科技",
        ],
        "color_palette": ["#0d47a1", "#1565c0", "#e3f2fd", "#f5f5f5"],
    },
}

# 内容类型配图建议
CONTENT_TYPE_IMAGES = {
    "article": {
        "min_images": 2,
        "max_images": 4,
        "positions": ["cover", "after_h2_1", "after_h2_2"],
    },
    "battle_report": {
        "min_images": 3,
        "max_images": 6,
        "positions": ["cover", "after_h2_1", "after_h2_2", "data_section"],
    },
    "policy_analysis": {
        "min_images": 1,
        "max_images": 3,
        "positions": ["cover", "after_h2_1"],
    },
    "tech_trend": {
        "min_images": 2,
        "max_images": 5,
        "positions": ["cover", "after_h2_1", "after_h2_2", "after_h2_3"],
    },
    "news_digest": {
        "min_images": 1,
        "max_images": 2,
        "positions": ["cover"],
    },
}


class MultimodalProcessor:
    """多模态处理器.

    功能：
    - 图片生成提示词构建
    - 配图策略推荐
    - 图文混排内容组装
    - 与LayoutEngine集成

    Attributes:
        layout_engine: 排版引擎实例.
        scene_type: 场景类型.
    """

    def __init__(self, scene_type: str = "municipal",
                 template_name: str = "professional"):
        """初始化多模态处理器.

        Args:
            scene_type: 场景类型.
            template_name: 排版模板名称.
        """
        self.scene_type = scene_type
        self.layout_engine = LayoutEngine(template_name)

    def generate_image_prompts(self, title: str, content_type: str = "article",
                                keywords: Optional[List[str]] = None) -> List[dict]:
        """生成图片创作提示词列表.

        根据文章标题、内容类型和场景，生成适合AI图片生成服务的提示词.

        Args:
            title: 文章标题.
            content_type: 内容类型.
            keywords: 关键词列表.

        Returns:
            list[dict]: [{"position": str, "prompt": str, "negative_prompt": str,
                          "width": int, "height": int, "alt": str}]
        """
        strategy = SCENE_IMAGE_STRATEGY.get(self.scene_type, SCENE_IMAGE_STRATEGY["municipal"])
        img_config = CONTENT_TYPE_IMAGES.get(content_type, CONTENT_TYPE_IMAGES["article"])
        kw = "、".join(keywords) if keywords else "环保"
        scene_label = SCENE_TYPE_LABELS.get(self.scene_type, "环保")

        prompts = []
        positions = img_config["positions"]
        section_styles = strategy["section_styles"]

        for i, pos in enumerate(positions):
            if pos == "cover":
                prompt = (
                    f"{strategy['cover_style']}，"
                    f"主题：{title}，"
                    f"关键词：{kw}，{scene_label}行业，"
                    f"高质量专业配图，4K，无文字"
                )
                alt = f"{scene_label}行业封面配图"
                width, height = 900, 383
            else:
                style_idx = min(i - 1, len(section_styles) - 1)
                style = section_styles[style_idx] if style_idx >= 0 else section_styles[0]
                prompt = (
                    f"{style}，"
                    f"与'{title}'相关，"
                    f"{kw}，"
                    f"高质量技术配图，4K，无文字"
                )
                alt = f"{scene_label}章节配图"
                width, height = 900, 500

            prompts.append({
                "position": pos,
                "prompt": prompt,
                "negative_prompt": "低质量, 模糊, 文字, 水印, 变形, 不自然",
                "width": width,
                "height": height,
                "alt": alt,
            })

        return prompts

    def suggest_layout_with_images(self, markdown_content: str, title: str = "",
                                   content_type: str = "article",
                                   existing_images: Optional[List[dict]] = None) -> dict:
        """生成图文混排布局建议.

        Args:
            markdown_content: Markdown内容.
            title: 文章标题.
            content_type: 内容类型.
            existing_images: 已有图片列表.

        Returns:
            dict: {
                "layout": dict,
                "image_prompts": list[dict],
                "rendered_html": str,
                "wechat_html": str,
                "word_count": int,
                "reading_time_minutes": float
            }
        """
        existing_images = existing_images or []

        # 生成图片提示词
        image_prompts = self.generate_image_prompts(title, content_type)

        # 使用排版引擎渲染
        # 如果有现有图片就用，没有就用占位符
        images_for_layout = []
        if existing_images:
            images_for_layout = existing_images
        else:
            # 用占位符
            for prompt in image_prompts:
                images_for_layout.append({
                    "type": "header" if prompt["position"] == "cover" else "section",
                    "url": "",
                    "alt": prompt["alt"],
                })

        result = self.layout_engine.render(
            markdown_content,
            title=title,
            scene_type=self.scene_type,
            images=images_for_layout,
        )

        return {
            "layout": {
                "template": self.layout_engine.template_name,
                "image_count": len(images_for_layout),
                "image_positions": [img.get("type", "unknown") for img in images_for_layout],
            },
            "image_prompts": image_prompts,
            "rendered_html": result["html"],
            "wechat_html": result["wechat_html"],
            "word_count": result["word_count"],
            "reading_time_minutes": result["reading_time_minutes"],
        }

    def assemble_content(self, markdown_content: str, title: str = "",
                         content_type: str = "article",
                         images: Optional[List[dict]] = None,
                         template_name: Optional[str] = None) -> dict:
        """组装最终的图文混排内容.

        Args:
            markdown_content: Markdown内容.
            title: 文章标题.
            content_type: 内容类型.
            images: 图片列表 [{"url": str, "alt": str, "type": str}].
            template_name: 排版模板名称（可选，覆盖默认）.

        Returns:
            dict: {
                "html": str,
                "wechat_html": str,
                "image_suggestions": list[dict],
                "image_prompts": list[dict],
                "word_count": int,
                "reading_time_minutes": float
            }
        """
        images = images or []

        if template_name and template_name != self.layout_engine.template_name:
            self.layout_engine.set_template(template_name)

        # 渲染排版
        render_result = self.layout_engine.render(
            markdown_content,
            title=title,
            scene_type=self.scene_type,
            images=images,
        )

        # 生成图片提示词（供后续图片生成）
        image_prompts = self.generate_image_prompts(title, content_type)

        return {
            "html": render_result["html"],
            "wechat_html": render_result["wechat_html"],
            "image_suggestions": render_result["image_suggestions"],
            "image_prompts": image_prompts,
            "word_count": render_result["word_count"],
            "reading_time_minutes": render_result["reading_time_minutes"],
        }

    def get_scene_colors(self) -> List[str]:
        """获取当前场景推荐色板.

        Returns:
            list[str]: 颜色代码列表.
        """
        strategy = SCENE_IMAGE_STRATEGY.get(self.scene_type, SCENE_IMAGE_STRATEGY["municipal"])
        return strategy["color_palette"]

    def list_templates(self) -> dict:
        """列出可用排版模板.

        Returns:
            dict: 模板信息字典.
        """
        return self.layout_engine.list_templates()
