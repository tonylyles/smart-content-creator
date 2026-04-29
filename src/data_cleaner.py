"""数据清洗模块 - 胡圳刚负责"""


class DataCleaner:
    """数据清洗器"""

    def clean(self, raw_data):
        """清洗原始数据"""
        cleaned = self._remove_duplicates(raw_data)
        cleaned = self._normalize_text(cleaned)
        cleaned = self._filter_invalid(cleaned)
        return cleaned

    def _remove_duplicates(self, data):
        """去重"""
        pass

    def _normalize_text(self, data):
        """文本标准化"""
        pass

    def _filter_invalid(self, data):
        """过滤无效数据"""
        pass
