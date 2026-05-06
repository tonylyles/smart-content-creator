"""数据清洗模块 - 胡圳刚负责"""
import re
from typing import List, Dict, Any


class DataCleaner:
    """数据清洗器 - 提供文本去重、标准化和过滤功能"""

    def __init__(self):
        # 常见停用词
        self.stopwords = {
            "的", "了", "是", "在", "和", "与", "或", "等", "及", "有", "也", "都",
            "不", "人", "很", "会", "就", "可", "以", "说", "要", "去", "你", "我",
            "他", "她", "它", "这", "那", "此", "其", "某", "各", "每", "所", "个",
            "如何", "怎么", "什么", "哪些", "可以", "能够", "应该", "必须", "需要"
        }
        
        # 敏感词模式
        self.sensitive_patterns = [
            r"[^\u4e00-\u9fff0-9a-zA-Z，。！？、；：""''（）\\s]",  # 非法字符
            r"\s{2,}",  # 多个连续空格
            r"[\u3000]",  # 全角空格
        ]

    def clean(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """清洗原始数据 - 执行完整清洗流程"""
        if not raw_data:
            return []
        
        # 步骤1: 去重
        cleaned = self._remove_duplicates(raw_data)
        print(f"去重后: {len(cleaned)} 条")
        
        # 步骤2: 文本标准化
        cleaned = self._normalize_text(cleaned)
        print(f"标准化完成")
        
        # 步骤3: 过滤无效数据
        cleaned = self._filter_invalid(cleaned)
        print(f"过滤后: {len(cleaned)} 条")
        
        return cleaned

    def _remove_duplicates(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """去重 - 基于标题和内容判断重复"""
        seen = set()
        unique_data = []
        
        for item in data:
            # 使用标题和内容的组合作为去重键
            title = item.get("title", "").strip()
            content = item.get("content", "").strip()[:200]  # 取前200字作为特征
            
            key = f"{title}|{content}"
            key_hash = hash(key)
            
            if key_hash not in seen:
                seen.add(key_hash)
                unique_data.append(item)
        
        return unique_data

    def _normalize_text(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """文本标准化 - 统一格式、去除噪声"""
        for item in data:
            # 处理标题
            if "title" in item:
                item["title"] = self._normalize_string(item["title"])
            
            # 处理内容
            if "content" in item:
                item["content"] = self._normalize_string(item["content"])
            
            # 处理其他文本字段
            for key in ["description", "summary", "source"]:
                if key in item:
                    item[key] = self._normalize_string(item[key])
        
        return data

    def _normalize_string(self, text: str) -> str:
        """标准化单个字符串"""
        if not text:
            return ""
        
        # 转换为字符串
        text = str(text)
        
        # 去除前后空格
        text = text.strip()
        
        # 替换全角字符为半角
        text = self._full_to_half(text)
        
        # 移除非法字符
        for pattern in self.sensitive_patterns:
            text = re.sub(pattern, "", text)
        
        # 替换多个连续空格为单个空格
        text = re.sub(r"\s+", " ", text)
        
        # 移除控制字符
        text = "".join([c for c in text if ord(c) >= 32 or c in "\n\r\t"])
        
        return text.strip()

    def _full_to_half(self, text: str) -> str:
        """全角转半角"""
        result = []
        for char in text:
            code = ord(char)
            if 0xFF01 <= code <= 0xFF5E:  # 全角字符范围
                result.append(chr(code - 0xFEE0))
            else:
                result.append(char)
        return "".join(result)

    def _filter_invalid(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤无效数据 - 移除空内容、过短内容、低质量数据"""
        valid_data = []
        
        for item in data:
            title = item.get("title", "").strip()
            content = item.get("content", "").strip()
            
            # 检查标题和内容是否存在
            if not title and not content:
                continue
            
            # 检查内容长度（至少10个字符）
            total_length = len(title) + len(content)
            if total_length < 10:
                continue
            
            # 检查是否为有效内容（不是纯空白或特殊字符）
            if self._is_valid_content(title, content):
                valid_data.append(item)
        
        return valid_data

    def _is_valid_content(self, title: str, content: str) -> bool:
        """判断内容是否有效"""
        combined = title + content
        
        # 检查中文字符比例（至少30%是中文）
        chinese_chars = sum(1 for c in combined if "\u4e00" <= c <= "\u9fff")
        if len(combined) > 0 and chinese_chars / len(combined) < 0.3:
            return False
        
        # 检查是否包含有意义的内容
        meaningful_words = ["政策", "技术", "环保", "发展", "创新", "产业", 
                           "科技", "发布", "研究", "应用", "系统", "解决方案"]
        if any(word in combined for word in meaningful_words):
            return True
        
        # 如果标题或内容足够长，也认为有效
        if len(title) >= 10 or len(content) >= 50:
            return True
        
        return False

    def extract_keywords(self, text: str, top_n: int = 10) -> List[str]:
        """提取关键词"""
        if not text:
            return []
        
        # 分词（简单实现）
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]+', text)
        
        # 过滤停用词
        words = [w for w in words if w not in self.stopwords]
        
        # 统计词频
        word_counts = {}
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1
        
        # 返回频率最高的词
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in sorted_words[:top_n]]
