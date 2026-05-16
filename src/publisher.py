# 兼容包装 - 保留旧导入路径
# 新代码请使用: from src.publisher import WeChatPublisher
# 或: from src.publisher.wechat_publisher import WeChatPublisher

from src.publisher.wechat_publisher import WeChatPublisher, WeChatFormatter

__all__ = ["WeChatPublisher", "WeChatFormatter"]
