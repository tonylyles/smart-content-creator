"""新闻爬虫 - 主动抓取外部最新行业资讯、政策动态及技术进展"""
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from typing import List, Dict, Any
import time
import random


class NewsCrawler:
    """新闻爬虫"""
    
    # 新闻来源配置 - 专注于低温除湿干化领域
    # 优先级说明：列表顺序即为爬取优先级，越靠前优先级越高
    SOURCES = {
        "priority": {
            "name": "核心目标网站",
            "urls": [
                {"url": "https://gdjikang.com/", "parser": "jikang", "priority": 1}  # 最高优先级
            ]
        },
        "industry": {
            "name": "行业资讯",
            "urls": [
                {"url": "https://www.hbzhan.com/", "parser": "hbzhan"},          # 环保在线
                {"url": "https://www.china-water.com.cn/", "parser": "chinawater"},  # 中国水网
                {"url": "https://huanbao.bjx.com.cn/", "parser": "bjx_huanbao"},  # 北极星环保网
                {"url": "https://www.cn-em.com/", "parser": "cnem"},            # 中国环境网
                {"url": "https://www.ehwater.com/", "parser": "ehwater"}        # 中国环保设备网
            ]
        },
        "policy": {
            "name": "政策动态",
            "urls": [
                {"url": "http://www.mee.gov.cn/", "parser": "mee"},              # 生态环境部
                {"url": "http://www.gov.cn/", "parser": "gov"},                  # 中国政府网
                {"url": "https://www.mepc.gov.cn/", "parser": "mepc"}            # 广东省生态环境厅
            ]
        },
        "tech": {
            "name": "技术资讯",
            "urls": [
                {"url": "https://www.cnhubei.com/", "parser": "cnhubei"},        # 湖北日报（环保科技）
                {"url": "https://tech.sina.com.cn/", "parser": "sina_tech"}      # 新浪科技
            ]
        }
    }
    
    # 请求头
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive"
    }
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
    
    def _parse_techweb(self, html: str) -> List[Dict[str, Any]]:
        """解析 TechWeb"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            articles = soup.find_all("article", class_="article-item")
            for article in articles:
                title_tag = article.find("h2", class_="article-title")
                if title_tag and title_tag.a:
                    results.append({
                        "title": title_tag.a.get_text(strip=True),
                        "url": title_tag.a["href"],
                        "source": "TechWeb",
                        "category": "technology"
                    })
        except Exception as e:
            print(f"TechWeb解析错误: {e}")
        return results
    
    def _parse_sina_tech(self, html: str) -> List[Dict[str, Any]]:
        """解析新浪科技"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            articles = soup.find_all("div", class_="news-item")
            for article in articles:
                title_tag = article.find("h2")
                if title_tag and title_tag.a:
                    results.append({
                        "title": title_tag.a.get_text(strip=True),
                        "url": title_tag.a["href"],
                        "source": "新浪科技",
                        "category": "technology"
                    })
        except Exception as e:
            print(f"新浪科技解析错误: {e}")
        return results
    
    def _parse_ithome(self, html: str) -> List[Dict[str, Any]]:
        """解析IT之家"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            articles = soup.find_all("div", class_="news-list")
            for article in articles:
                title_tag = article.find("h2")
                if title_tag and title_tag.a:
                    results.append({
                        "title": title_tag.a.get_text(strip=True),
                        "url": "https://www.ithome.com" + title_tag.a["href"],
                        "source": "IT之家",
                        "category": "technology"
                    })
        except Exception as e:
            print(f"IT之家解析错误: {e}")
        return results
    
    def _parse_gov(self, html: str) -> List[Dict[str, Any]]:
        """解析中国政府网"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            articles = soup.find_all("div", class_="list_item")
            for article in articles:
                title_tag = article.find("a")
                if title_tag:
                    results.append({
                        "title": title_tag.get_text(strip=True),
                        "url": title_tag["href"],
                        "source": "中国政府网",
                        "category": "policy"
                    })
        except Exception as e:
            print(f"中国政府网解析错误: {e}")
        return results
    
    def _parse_miit(self, html: str) -> List[Dict[str, Any]]:
        """解析工信部"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            articles = soup.find_all("li", class_="list-item")
            for article in articles:
                title_tag = article.find("a")
                if title_tag:
                    results.append({
                        "title": title_tag.get_text(strip=True),
                        "url": "https://www.miit.gov.cn" + title_tag["href"],
                        "source": "工信部",
                        "category": "policy"
                    })
        except Exception as e:
            print(f"工信部解析错误: {e}")
        return results
    
    def _parse_cac(self, html: str) -> List[Dict[str, Any]]:
        """解析网信办"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            articles = soup.find_all("div", class_="news-item")
            for article in articles:
                title_tag = article.find("h3")
                if title_tag and title_tag.a:
                    results.append({
                        "title": title_tag.a.get_text(strip=True),
                        "url": "https://www.cac.gov.cn" + title_tag.a["href"],
                        "source": "网信办",
                        "category": "policy"
                    })
        except Exception as e:
            print(f"网信办解析错误: {e}")
        return results
    
    def _parse_36kr(self, html: str) -> List[Dict[str, Any]]:
        """解析36氪"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            articles = soup.find_all("article", class_="article-item")
            for article in articles:
                title_tag = article.find("h3")
                if title_tag and title_tag.a:
                    results.append({
                        "title": title_tag.a.get_text(strip=True),
                        "url": "https://www.36kr.com" + title_tag.a["href"],
                        "source": "36氪",
                        "category": "industry"
                    })
        except Exception as e:
            print(f"36氪解析错误: {e}")
        return results
    
    def _parse_pinggu(self, html: str) -> List[Dict[str, Any]]:
        """解析人大经济论坛"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            articles = soup.find_all("tr", class_="forumRow")
            for article in articles:
                title_tag = article.find("a", class_="title")
                if title_tag:
                    results.append({
                        "title": title_tag.get_text(strip=True),
                        "url": title_tag["href"],
                        "source": "人大经济论坛",
                        "category": "industry"
                    })
        except Exception as e:
            print(f"人大经济论坛解析错误: {e}")
        return results
    
    def _parse_jrj(self, html: str) -> List[Dict[str, Any]]:
        """解析金融界"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            articles = soup.find_all("div", class_="news-item")
            for article in articles:
                title_tag = article.find("h2")
                if title_tag and title_tag.a:
                    results.append({
                        "title": title_tag.a.get_text(strip=True),
                        "url": title_tag.a["href"],
                        "source": "金融界",
                        "category": "industry"
                    })
        except Exception as e:
            print(f"金融界解析错误: {e}")
        return results
    
    def _get_parser(self, parser_name: str):
        """获取解析器函数"""
        parsers = {
            "jikang": self._parse_jikang,            # 广东吉康环境
            "hbzhan": self._parse_hbzhan,            # 环保在线
            "chinawater": self._parse_chinawater,     # 中国水网
            "bjx_huanbao": self._parse_bjx_huanbao,   # 北极星环保网
            "cnem": self._parse_cnem,                # 中国环境网
            "ehwater": self._parse_ehwater,          # 中国环保设备网
            "mee": self._parse_mee,                  # 生态环境部
            "mepc": self._parse_mepc,                # 广东省生态环境厅
            "cnhubei": self._parse_cnhubei,          # 湖北日报
            "techweb": self._parse_techweb,
            "sina_tech": self._parse_sina_tech,
            "ithome": self._parse_ithome,
            "gov": self._parse_gov,
            "miit": self._parse_miit,
            "cac": self._parse_cac,
            "36kr": self._parse_36kr,
            "pinggu": self._parse_pinggu,
            "jrj": self._parse_jrj
        }
        return parsers.get(parser_name, self._parse_generic)

    def _parse_jikang(self, html: str) -> List[Dict[str, Any]]:
        """解析广东吉康环境官网 - 低温除湿干化核心网站"""
        return self._parse_generic(html, "吉康环境", "priority")

    def _parse_hbzhan(self, html: str) -> List[Dict[str, Any]]:
        """解析环保在线"""
        return self._parse_generic(html, "环保在线", "industry")

    def _parse_chinawater(self, html: str) -> List[Dict[str, Any]]:
        """解析中国水网"""
        return self._parse_generic(html, "中国水网", "industry")

    def _parse_bjx_huanbao(self, html: str) -> List[Dict[str, Any]]:
        """解析北极星环保网"""
        return self._parse_generic(html, "北极星环保网", "industry")

    def _parse_cnem(self, html: str) -> List[Dict[str, Any]]:
        """解析中国环境网"""
        return self._parse_generic(html, "中国环境网", "industry")

    def _parse_ehwater(self, html: str) -> List[Dict[str, Any]]:
        """解析中国环保设备网"""
        return self._parse_generic(html, "中国环保设备网", "industry")

    def _parse_mee(self, html: str) -> List[Dict[str, Any]]:
        """解析生态环境部"""
        return self._parse_generic(html, "生态环境部", "policy")

    def _parse_mepc(self, html: str) -> List[Dict[str, Any]]:
        """解析广东省生态环境厅"""
        return self._parse_generic(html, "广东省生态环境厅", "policy")

    def _parse_cnhubei(self, html: str) -> List[Dict[str, Any]]:
        """解析湖北日报"""
        return self._parse_generic(html, "湖北日报", "tech")

    def _parse_generic(self, html: str, source_name: str, category: str) -> List[Dict[str, Any]]:
        """通用解析器 - 尝试多种常见HTML结构"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            # 尝试多种常见的标题选择器
            selectors = [
                ("h1 a", {}),
                ("h2 a", {}),
                ("h3 a", {}),
                ("article a", {}),
                ("div.news a", {}),
                ("div.list a", {}),
                ("ul li a", {}),
                ("div.content a", {}),
                ("a.title", {}),
                ("a[title]", {})
            ]
            
            for selector, attrs in selectors:
                items = soup.select(selector)
                for item in items[:10]:  # 每个选择器最多取10条
                    title = item.get_text(strip=True) if item else ""
                    url = item.get("href", "") if item else ""
                    
                    if title and url:
                        # 处理相对URL
                        if not url.startswith("http"):
                            url = "#"
                        
                        results.append({
                            "title": title,
                            "url": url,
                            "source": source_name,
                            "category": category
                        })
            
            # 去重
            seen = set()
            unique_results = []
            for item in results:
                key = (item["title"], item["url"])
                if key not in seen:
                    seen.add(key)
                    unique_results.append(item)
            
            return unique_results[:15]  # 最多返回15条
            
        except Exception as e:
            print(f"{source_name}解析错误: {e}")
            return []
    
    def crawl_source(self, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """爬取单个来源"""
        results = []
        url_info = source_config
        
        try:
            response = self.session.get(url_info["url"], timeout=self.timeout)
            response.encoding = response.apparent_encoding
            
            if response.status_code == 200:
                parser = self._get_parser(url_info["parser"])
                items = parser(response.text)
                
                for item in items:
                    item["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    results.append(item)
            else:
                print(f"请求失败 {url_info['url']}: {response.status_code}")
                
        except requests.RequestException as e:
            print(f"爬取失败 {url_info['url']}: {e}")
        
        # 随机延迟，避免被封禁
        time.sleep(random.uniform(1, 3))
        return results
    
    def crawl(self, categories: List[str] = None) -> List[Dict[str, Any]]:
        """
        爬取新闻
        
        Args:
            categories: 爬取类别列表，可选值: tech, policy, industry
        
        Returns:
            新闻列表
        """
        if categories is None:
            categories = list(self.SOURCES.keys())
        
        all_results = []
        
        for category in categories:
            if category in self.SOURCES:
                print(f"开始爬取 {self.SOURCES[category]['name']}...")
                for url_info in self.SOURCES[category]["urls"]:
                    results = self.crawl_source(url_info)
                    all_results.extend(results)
        
        print(f"爬取完成，共获取 {len(all_results)} 条新闻")
        return all_results
    
    def save_results(self, results: List[Dict[str, Any]], filename: str) -> None:
        """保存爬取结果到文件"""
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    
    def load_results(self, filename: str) -> List[Dict[str, Any]]:
        """从文件加载爬取结果"""
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)