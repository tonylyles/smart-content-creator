"""爬虫模块 - 胡圳刚负责

包含以下功能：
1. 内容类型分类器 - 自动识别内容类型（事件/技术/政策）
2. 发布节奏规划器 - 根据企业市场推广计划规划发布节奏
3. 新闻爬虫 - 主动抓取外部最新行业资讯、政策动态及技术进展
4. 爬虫管理器 - 协调内容爬取、分类和发布规划的完整工作流
"""

from .content_classifier import ContentClassifier
from .release_planner import ReleasePlanner, ReleasePlan, PublishFrequency
from .news_crawler import NewsCrawler
from .spider_manager import SpiderManager

__all__ = [
    "ContentClassifier",
    "ReleasePlanner",
    "ReleasePlan",
    "PublishFrequency",
    "NewsCrawler",
    "SpiderManager"
]