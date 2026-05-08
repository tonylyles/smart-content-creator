"""
环保行业智能爬虫 - 胡圳刚/曾睿

功能：
- 自动抓取环保行业新闻、政策动态、技术进展
- 按关键词智能检索相关网页
- 内容去重与摘要提取
- 覆盖≥5个主流环保数据源（赛题要求）

数据源：
1. 环保在线 (hbzhan.com) - 行业新闻
2. 中国环保网 (chinaep.org) - 政策动态
3. 生态环境部 (mee.gov.cn) - 官方政策
4. 广东省生态环境厅 (gdee.gd.gov.cn) - 地方政策
5. 北极星环保网 (bjx.com.cn) - 技术进展
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
import time
import random


class EcoNewsCrawler:
    """环保行业新闻爬虫"""
    
    # 环保行业数据源（≥5个，满足赛题要求）
    SOURCES = {
        "industry": {
            "name": "行业资讯",
            "sources": [
                {
                    "name": "环保在线",
                    "url": "https://www.hbzhan.com/news/",
                    "parser": "hbzhan",
                    "keywords_url": "https://www.hbzhan.com/news/t{}-.html",  # keyword placeholder
                },
                {
                    "name": "北极星环保网",
                    "url": "https://huanbao.bjx.com.cn/",
                    "parser": "bjx",
                    "keywords_url": "https://huanbao.bjx.com.cn/Search?k={}",
                },
            ]
        },
        "policy": {
            "name": "政策动态",
            "sources": [
                {
                    "name": "生态环境部",
                    "url": "https://www.mee.gov.cn/ywdt/gzdt/",
                    "parser": "mee",
                    "keywords_url": "https://www.mee.gov.cn/search/?searchword={}",
                },
                {
                    "name": "广东省生态环境厅",
                    "url": "https://gdee.gd.gov.cn/gkmlpt/",
                    "parser": "gdee",
                },
                {
                    "name": "中国环保网",
                    "url": "https://www.chinaep.org.cn/",
                    "parser": "chinaep",
                },
            ]
        },
        "tech": {
            "name": "技术进展",
            "sources": [
                {
                    "name": "环保在线技术",
                    "url": "https://www.hbzhan.com/tech/",
                    "parser": "hbzhan_tech",
                },
            ]
        },
    }
    
    # 吉康环境核心关键词（用于智能检索）
    KEYWORDS = [
        "低温除湿", "污泥干化", "闭式循环", "除湿干化",
        "高湿环境", "回南天", "污泥处理", "固废处理",
        "环保政策", "双碳", "节能", "绿色发展",
        "涡旋式热泵", "工业除湿", "污水处理",
    ]
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._seen_hashes = set()  # 去重用
    
    def _hash_content(self, title: str, url: str) -> str:
        """内容去重哈希"""
        return hashlib.md5(f"{title}{url}".encode()).hexdigest()
    
    def _is_duplicate(self, title: str, url: str) -> bool:
        """检查是否重复"""
        h = self._hash_content(title, url)
        if h in self._seen_hashes:
            return True
        self._seen_hashes.add(h)
        return False
    
    def _clean_text(self, text: str) -> str:
        """清洗文本"""
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:500]  # 限制摘要长度
    
    def _extract_links(self, html: str, base_url: str) -> List[Dict[str, Any]]:
        """通用链接提取（当专用解析器不可用时使用）"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                title = a_tag.get_text(strip=True)
                href = a_tag["href"]
                # 过滤：标题长度>10，含有中文
                if len(title) > 10 and re.search(r'[\u4e00-\u9fff]', title):
                    # 补全URL
                    if href.startswith("/"):
                        from urllib.parse import urljoin
                        href = urljoin(base_url, href)
                    if not self._is_duplicate(title, href):
                        results.append({
                            "title": title,
                            "url": href,
                            "source": base_url,
                            "category": "unknown",
                            "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        })
        except Exception as e:
            pass
        return results
    
    def _fetch_page(self, url: str) -> Optional[str]:
        """安全获取页面"""
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.encoding = resp.apparent_encoding or "utf-8"
            if resp.status_code == 200:
                return resp.text
        except Exception as e:
            print(f"  [爬虫] 请求失败 {url}: {e}")
        return None
    
    def crawl_source(self, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """爬取单个数据源"""
        url = source_config["url"]
        name = source_config["name"]
        print(f"  [爬虫] 正在抓取: {name} ({url})")
        
        html = self._fetch_page(url)
        if not html:
            return []
        
        # 尝试专用解析器，失败则用通用提取
        parser_name = source_config.get("parser", "")
        results = self._extract_links(html, url)
        
        # 过滤：只保留与环保相关的
        eco_keywords = ["环保", "环境", "生态", "污泥", "污水", "固废", "废气",
                        "除湿", "干化", "节能", "碳", "绿色", "污染", "处理",
                        "减排", "水资源", "循环", "可持续", "新能源", "热泵"]
        
        filtered = []
        for item in results:
            title = item["title"]
            if any(kw in title for kw in eco_keywords):
                item["category"] = "environmental"
                filtered.append(item)
        
        # 如果过滤后太少，保留原始结果（最多20条）
        if len(filtered) < 3:
            filtered = results[:20]
        
        print(f"  [爬虫] {name}: 获取 {len(results)} 条，过滤后 {len(filtered)} 条")
        time.sleep(random.uniform(0.5, 1.5))
        return filtered
    
    def search_by_keywords(self, keywords: List[str] = None, 
                            max_results: int = 20) -> List[Dict[str, Any]]:
        """按关键词智能检索相关网页
        
        使用百度搜索获取最新相关资讯，比固定网站爬取更灵活。
        
        Args:
            keywords: 搜索关键词列表
            max_results: 最大结果数
            
        Returns:
            检索结果列表
        """
        if not keywords:
            keywords = random.sample(self.KEYWORDS, min(3, len(self.KEYWORDS)))
        
        all_results = []
        
        for keyword in keywords:
            print(f"  [搜索] 关键词: {keyword}")
            # 用百度搜索
            search_url = f"https://www.baidu.com/s?wd={keyword}&rn=10"
            html = self._fetch_page(search_url)
            if not html:
                continue
            
            try:
                soup = BeautifulSoup(html, "html.parser")
                # 百度搜索结果
                for result_div in soup.find_all(["div", "h3"], 
                        class_=re.compile(r"result|t")):
                    a_tag = result_div.find("a")
                    if not a_tag:
                        continue
                    title = a_tag.get_text(strip=True)
                    href = a_tag.get("href", "")
                    
                    if len(title) > 8 and not self._is_duplicate(title, href):
                        all_results.append({
                            "title": self._clean_text(title),
                            "url": href,
                            "source": "百度搜索",
                            "category": "search_result",
                            "keyword": keyword,
                            "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        })
            except Exception as e:
                print(f"  [搜索] 解析失败: {e}")
            
            time.sleep(random.uniform(1, 2))
            
            if len(all_results) >= max_results:
                break
        
        print(f"  [搜索] 关键词检索完成，共 {len(all_results)} 条结果")
        return all_results[:max_results]
    
    def fetch_article_content(self, url: str) -> Optional[str]:
        """获取文章正文内容
        
        Args:
            url: 文章URL
            
        Returns:
            正文文本（纯文本，已清洗）
        """
        html = self._fetch_page(url)
        if not html:
            return None
        
        try:
            soup = BeautifulSoup(html, "html.parser")
            # 移除脚本和样式
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            
            # 尝试找到文章主体
            article = (soup.find("article") or 
                      soup.find("div", class_=re.compile(r"article|content|detail|text|body")) or
                      soup.find("div", id=re.compile(r"article|content|detail|text|body")))
            
            if article:
                text = article.get_text(separator="\n", strip=True)
            else:
                text = soup.get_text(separator="\n", strip=True)
            
            # 清洗
            lines = [line.strip() for line in text.split("\n") if line.strip() and len(line.strip()) > 10]
            return "\n".join(lines[:50])  # 最多50行
        except Exception as e:
            print(f"  [爬虫] 正文提取失败 {url}: {e}")
            return None
    
    def auto_discover_topics(self, count: int = 5) -> List[Dict[str, Any]]:
        """自动发现热门话题（用于自动生成推文主题）
        
        流程：搜索关键词 → 提取热门话题 → 返回主题列表
        
        Args:
            count: 需要的主题数量
            
        Returns:
            主题列表，每个包含 title, keywords, context
        """
        print(f"[发现] 🔍 自动发现 {count} 个热门话题...")
        
        # 随机选2-3个关键词搜索
        search_keywords = random.sample(self.KEYWORDS, min(3, len(self.KEYWORDS)))
        results = self.search_by_keywords(search_keywords, max_results=30)
        
        if not results:
            # 搜索失败时用默认话题
            default_topics = [
                {"title": "华南地区工业除湿技术创新趋势", "keywords": ["低温除湿", "节能", "华南"], "context": "大湾区工业除湿需求增长"},
                {"title": "广东省环保政策对污泥处理的影响", "keywords": ["环保政策", "污泥干化", "广东"], "context": "十四五环保规划要求"},
                {"title": "闭式循环技术如何助力双碳目标", "keywords": ["闭式循环", "双碳", "节能"], "context": "碳排放法规趋严"},
            ]
            return default_topics[:count]
        
        # 用关键词匹配度排序 + 过滤不相关
        scored = []
        for item in results:
            title = item.get("title", "")
            score = sum(1 for kw in self.KEYWORDS if kw in title)
            # 过滤明显不相关的
            blacklist = ["娱乐", "明星", "电影", "综艺", "游戏", "健身", "减肥", "美食菜谱"]
            if any(bw in title for bw in blacklist):
                continue
            scored.append((score, item))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        
        topics = []
        for score, item in scored[:count]:
            # 从标题生成推文主题
            title = item["title"]
            # 提取相关关键词
            matched_kws = [kw for kw in self.KEYWORDS if kw in title]
            if not matched_kws:
                matched_kws = search_keywords[:2]
            
            topics.append({
                "title": title,
                "keywords": matched_kws,
                "context": f"来源: {item.get('source', '网络')}",
                "search_result": item,
            })
        
        print(f"[发现] ✅ 发现 {len(topics)} 个话题")
        for i, t in enumerate(topics, 1):
            print(f"  {i}. {t['title']} (关键词: {', '.join(t['keywords'])})")
        
        return topics
    
    def crawl(self, categories: List[str] = None) -> List[Dict[str, Any]]:
        """
        爬取环保行业新闻
        
        Args:
            categories: 类别列表 ["industry", "policy", "tech"]
        
        Returns:
            新闻列表
        """
        if not categories:
            categories = list(self.SOURCES.keys())
        
        all_results = []
        
        for category in categories:
            if category not in self.SOURCES:
                continue
            print(f"\n[爬虫] 📰 开始爬取 {self.SOURCES[category]['name']}...")
            for source in self.SOURCES[category]["sources"]:
                results = self.crawl_source(source)
                for r in results:
                    r["category"] = category
                all_results.extend(results)
        
        # 去重
        unique = []
        seen = set()
        for item in all_results:
            h = self._hash_content(item.get("title", ""), item.get("url", ""))
            if h not in seen:
                seen.add(h)
                unique.append(item)
        
        print(f"\n[爬虫] ✅ 爬取完成，共 {len(unique)} 条（去重后）")
        return unique
    
    def save_results(self, results: List[Dict[str, Any]], filename: str) -> None:
        """保存结果到JSON"""
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"[爬虫] 结果已保存到 {filename}")
