"""爬虫管理器 - 协调内容爬取、分类和发布规划"""
from typing import List, Dict, Any
from datetime import datetime

from .content_classifier import ContentClassifier
from .release_planner import ReleasePlanner, PublishFrequency
from .news_crawler import NewsCrawler


class SpiderManager:
    """爬虫管理器"""
    
    def __init__(self):
        self.classifier = ContentClassifier()
        self.planner = ReleasePlanner()
        self.crawler = NewsCrawler()
    
    def crawl_and_classify(self, categories: List[str] = None) -> List[Dict[str, Any]]:
        """
        爬取新闻并自动分类
        
        Args:
            categories: 爬取类别列表
        
        Returns:
            分类后的新闻列表
        """
        # 爬取新闻
        news_list = self.crawler.crawl(categories)
        
        # 对每条新闻进行分类
        for news in news_list:
            title = news.get("title", "")
            content_type, confidence = self.classifier.classify(title)
            news["content_type"] = content_type
            news["confidence"] = confidence
            news["type_name"] = self.classifier.get_type_name(content_type)
        
        return news_list
    
    def plan_release(self, 
                     content_list: List[Dict[str, Any]],
                     frequency: str = "daily",
                     daily_limit: int = 3) -> List[Dict[str, Any]]:
        """
        规划发布节奏
        
        Args:
            content_list: 内容列表
            frequency: 发布频率 (daily/weekly/biweekly/monthly)
            daily_limit: 每日最大发布数量
        
        Returns:
            发布计划列表
        """
        # 转换频率参数
        freq_mapping = {
            "daily": PublishFrequency.DAILY,
            "weekly": PublishFrequency.WEEKLY,
            "biweekly": PublishFrequency.BIWEEKLY,
            "monthly": PublishFrequency.MONTHLY
        }
        
        publish_freq = freq_mapping.get(frequency, PublishFrequency.DAILY)
        
        # 生成发布计划
        plans = self.planner.generate_schedule(
            content_list, 
            frequency=publish_freq, 
            daily_limit=daily_limit
        )
        
        # 转换为字典格式
        return [plan.to_dict() for plan in plans]
    
    def full_workflow(self, 
                      categories: List[str] = None,
                      frequency: str = "daily",
                      daily_limit: int = 3) -> Dict[str, Any]:
        """
        完整工作流：爬取 → 分类 → 规划
        
        Args:
            categories: 爬取类别列表
            frequency: 发布频率
            daily_limit: 每日最大发布数量
        
        Returns:
            包含新闻列表和发布计划的字典
        """
        print("=" * 50)
        print("开始执行爬虫完整工作流")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 50)
        
        # 1. 爬取并分类
        print("\n[Step 1] 爬取新闻并分类...")
        news_list = self.crawl_and_classify(categories)
        print(f"爬取到 {len(news_list)} 条新闻")
        
        # 统计各类别数量
        type_counts = {}
        for news in news_list:
            type_name = news["type_name"]
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        print(f"分类结果: {type_counts}")
        
        # 2. 规划发布
        print("\n[Step 2] 规划发布节奏...")
        plans = self.plan_release(news_list, frequency, daily_limit)
        print(f"生成了 {len(plans)} 个发布计划")
        
        # 统计计划分布
        date_counts = {}
        for plan in plans:
            date_key = plan["date"].split(" ")[0]
            date_counts[date_key] = date_counts.get(date_key, 0) + 1
        print(f"发布日期分布: {date_counts}")
        
        print("\n" + "=" * 50)
        print("工作流执行完成")
        print("=" * 50)
        
        return {
            "news": news_list,
            "plans": plans,
            "summary": {
                "total_news": len(news_list),
                "type_distribution": type_counts,
                "total_plans": len(plans),
                "date_distribution": date_counts
            }
        }
    
    def save_results(self, 
                     news_list: List[Dict[str, Any]], 
                     plans: List[Dict[str, Any]],
                     news_file: str = "news_results.json",
                     plan_file: str = "release_plan.json") -> None:
        """保存结果到文件"""
        self.crawler.save_results(news_list, news_file)
        import json
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plans, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到 {news_file} 和 {plan_file}")


# 示例用法
if __name__ == "__main__":
    manager = SpiderManager()
    
    # 执行完整工作流
    result = manager.full_workflow(
        categories=["tech", "policy", "industry"],
        frequency="daily",
        daily_limit=3
    )
    
    # 保存结果
    manager.save_results(result["news"], result["plans"])