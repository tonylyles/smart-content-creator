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
    
    # 新闻来源配置
    SOURCES = {
        "tech": {
            "name": "科技资讯",
            "urls": [
                {"url": "https://www.techweb.com.cn/", "parser": "techweb"},
                {"url": "https://tech.sina.com.cn/", "parser": "sina_tech"},
                {"url": "https://www.ithome.com/", "parser": "ithome"}
            ]
        },
        "policy": {
            "name": "政策动态",
            "urls": [
                {"url": "http://www.gov.cn/", "parser": "gov"},
                {"url": "https://www.miit.gov.cn/", "parser": "miit"},
                {"url": "https://www.cac.gov.cn/", "parser": "cac"}
            ]
        },
        "industry": {
            "name": "行业资讯",
            "urls": [
                {"url": "https://www.36kr.com/", "parser": "36kr"},
                {"url": "https://www.pinggu.org/", "parser": "pinggu"},
                {"url": "https://www.jrj.com.cn/", "parser": "jrj"}
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
        return parsers.get(parser_name, lambda html: [])
    
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