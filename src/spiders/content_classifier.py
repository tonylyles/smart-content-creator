"""内容类型分类器 - 自动识别内容类型（事件/技术/政策）"""
import re
from typing import List, Dict, Tuple


class ContentClassifier:
    """内容类型分类器"""
    
    # 内容类型定义
    CONTENT_TYPES = {
        "event": {
            "name": "事件",
            "keywords": ["发布会", "展会", "峰会", "论坛", "活动", "大会", 
                        "启动", "开幕", "闭幕", "举办", "召开", "宣布",
                        "战略合作", "签约", "入驻", "上线", "发布", "推出"],
            "patterns": [
                r".*[发布|推出|上线].*[产品|服务|功能]",
                r".*[举办|召开|举行].*[会议|峰会|论坛]",
                r".*[签约|合作|战略].*[协议|伙伴]"
            ]
        },
        "technology": {
            "name": "技术",
            "keywords": ["技术", "研发", "创新", "AI", "人工智能", "大数据",
                        "云计算", "区块链", "算法", "模型", "架构", "框架",
                        "升级", "优化", "突破", "研究", "开发", "专利"],
            "patterns": [
                r".*[技术|研发|创新].*[突破|进展|成果]",
                r".*[AI|人工智能|大模型].*[应用|落地]",
                r".*[算法|架构|框架].*[优化|升级]"
            ]
        },
        "policy": {
            "name": "政策",
            "keywords": ["政策", "法规", "条例", "通知", "公告", "办法",
                        "规定", "指导", "意见", "规划", "方案", "措施",
                        "扶持", "补贴", "优惠", "改革", "监管", "审批"],
            "patterns": [
                r".*[政策|法规|条例].*[发布|出台|实施]",
                r".*[通知|公告|办法].*[印发|公布]",
                r".*[扶持|补贴|优惠].*[政策|措施]"
            ]
        }
    }
    
    def __init__(self):
        self.type_weights = {
            "event": 0,
            "technology": 0,
            "policy": 0
        }
    
    def _match_keywords(self, text: str) -> Dict[str, int]:
        """匹配关键词并计分"""
        scores = {ctype: 0 for ctype in self.CONTENT_TYPES}
        
        for ctype, config in self.CONTENT_TYPES.items():
            for keyword in config["keywords"]:
                if keyword in text:
                    scores[ctype] += 1
        return scores
    
    def _match_patterns(self, text: str) -> Dict[str, int]:
        """匹配正则模式并计分"""
        scores = {ctype: 0 for ctype in self.CONTENT_TYPES}
        
        for ctype, config in self.CONTENT_TYPES.items():
            for pattern in config["patterns"]:
                if re.search(pattern, text, re.IGNORECASE):
                    scores[ctype] += 2  # 模式匹配权重更高
        return scores
    
    def classify(self, title: str, content: str = "") -> Tuple[str, float]:
        """
        分类内容类型
        
        Args:
            title: 标题
            content: 内容摘要
        
        Returns:
            (类型名称, 置信度)
        """
        text = f"{title} {content}"
        text = text.lower()
        
        # 计算关键词得分
        keyword_scores = self._match_keywords(text)
        # 计算模式得分
        pattern_scores = self._match_patterns(text)
        
        # 综合得分
        total_scores = {}
        for ctype in self.CONTENT_TYPES:
            total_scores[ctype] = keyword_scores[ctype] + pattern_scores[ctype]
        
        # 找出最高分
        max_score = max(total_scores.values())
        
        if max_score == 0:
            return ("other", 0.0)
        
        # 确定类型
        matched_type = max(total_scores, key=total_scores.get)
        confidence = max_score / (len(text) // 10 + 1)  # 归一化置信度
        
        return (matched_type, min(confidence, 1.0))
    
    def get_type_name(self, type_code: str) -> str:
        """获取类型中文名称"""
        return self.CONTENT_TYPES.get(type_code, {}).get("name", "其他")