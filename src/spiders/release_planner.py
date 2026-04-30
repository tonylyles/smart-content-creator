"""发布节奏规划器 - 根据企业市场推广计划规划发布节奏"""
from datetime import datetime, timedelta
from typing import List, Dict, Any
from enum import Enum


class PublishFrequency(Enum):
    """发布频率枚举"""
    DAILY = "每日"
    WEEKLY = "每周"
    BIWEEKLY = "双周"
    MONTHLY = "每月"


class ReleasePlan:
    """发布计划"""
    
    def __init__(self, date: datetime, content_type: str, title: str, priority: int = 3):
        self.date = date
        self.content_type = content_type
        self.title = title
        self.priority = priority  # 1-5，1最高
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.strftime("%Y-%m-%d %H:%M"),
            "content_type": self.content_type,
            "title": self.title,
            "priority": self.priority
        }


class ReleasePlanner:
    """发布节奏规划器"""
    
    # 内容类型最佳发布时间
    TYPE_TIME_PREFERENCE = {
        "event": ["09:00", "14:00", "15:30"],      # 事件类适合工作时间早中段
        "technology": ["10:00", "16:00", "19:30"],  # 技术类适合深度阅读时间
        "policy": ["09:30", "15:00", "17:00"],      # 政策类适合官方发布时间
        "other": ["11:00", "14:30", "20:00"]        # 其他内容灵活安排
    }
    
    # 每周各天适合的内容类型分布
    WEEKDAY_PREFERENCE = {
        0: ["policy", "technology"],   # 周一：政策、技术
        1: ["technology", "event"],    # 周二：技术、事件
        2: ["event", "technology"],    # 周三：事件、技术
        3: ["policy", "event"],        # 周四：政策、事件
        4: ["technology", "other"],    # 周五：技术、其他
        5: ["event", "other"],         # 周六：事件、其他
        6: ["other", "policy"]         # 周日：其他、政策
    }
    
    def __init__(self, start_date: datetime = None):
        self.start_date = start_date or datetime.now()
        self.plan = []
    
    def generate_schedule(self, 
                          content_list: List[Dict[str, Any]],
                          frequency: PublishFrequency = PublishFrequency.DAILY,
                          daily_limit: int = 3) -> List[ReleasePlan]:
        """
        生成发布计划
        
        Args:
            content_list: 内容列表，每个元素包含 title, content_type, priority
            frequency: 发布频率
            daily_limit: 每日最大发布数量
        
        Returns:
            发布计划列表
        """
        self.plan = []
        
        # 按优先级排序
        sorted_content = sorted(content_list, 
                               key=lambda x: x.get("priority", 3), 
                               reverse=False)
        
        # 计算发布间隔
        if frequency == PublishFrequency.DAILY:
            interval_days = 1
        elif frequency == PublishFrequency.WEEKLY:
            interval_days = 7
        elif frequency == PublishFrequency.BIWEEKLY:
            interval_days = 14
        else:
            interval_days = 30
        
        current_date = self.start_date
        content_index = 0
        day_count = 0
        
        while content_index < len(sorted_content):
            # 获取当天适合的内容类型
            weekday = current_date.weekday()
            preferred_types = self.WEEKDAY_PREFERENCE.get(weekday, [])
            
            # 在当天分配内容
            daily_count = 0
            temp_index = content_index
            
            while temp_index < len(sorted_content) and daily_count < daily_limit:
                content = sorted_content[temp_index]
                content_type = content.get("content_type", "other")
                
                # 优先安排当天偏好类型的内容
                if content_type in preferred_types or daily_count == 0:
                    # 选择合适的发布时间
                    time_options = self.TYPE_TIME_PREFERENCE.get(content_type, ["10:00"])
                    time_str = time_options[day_count % len(time_options)]
                    
                    # 创建发布计划
                    plan_date = datetime.strptime(
                        f"{current_date.strftime('%Y-%m-%d')} {time_str}",
                        "%Y-%m-%d %H:%M"
                    )
                    
                    self.plan.append(ReleasePlan(
                        date=plan_date,
                        content_type=content_type,
                        title=content.get("title", ""),
                        priority=content.get("priority", 3)
                    ))
                    
                    daily_count += 1
                    content_index += 1
                
                temp_index += 1
            
            # 推进到下一个发布日
            current_date += timedelta(days=interval_days)
            day_count += 1
        
        return self.plan
    
    def get_plan_by_date(self, date: datetime) -> List[ReleasePlan]:
        """获取指定日期的发布计划"""
        return [p for p in self.plan if p.date.date() == date.date()]
    
    def export_plan(self, filename: str) -> None:
        """导出发布计划到文件"""
        import json
        
        plan_data = [p.to_dict() for p in self.plan]
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(plan_data, f, ensure_ascii=False, indent=2)