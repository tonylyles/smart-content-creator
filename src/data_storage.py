"""数据存储接口 - 胡圳刚负责"""


class DataStorage:
    """数据存储抽象层"""

    def __init__(self, config):
        self.config = config

    def save(self, collection, data):
        """保存数据"""
        pass

    def query(self, collection, filters=None):
        """查询数据"""
        pass

    def delete(self, collection, doc_id):
        """删除数据"""
        pass
