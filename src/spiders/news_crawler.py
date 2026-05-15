"""新闻爬虫 - 主动抓取外部最新行业资讯、政策动态及技术进展"""
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from typing import List, Dict, Any
import time
import random

# Selenium 相关导入（用于 JavaScript 渲染）
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


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
                {"url": "https://www.hbzhan.com/", "parser": "hbzhan"},          # 环保在线 ✅
                {"url": "https://www.chinawater.com.cn/", "parser": "chinawater"},  # 中国水网 ✅
                {"url": "https://huanbao.bjx.com.cn/", "parser": "bjx_huanbao", "requires_js": True},  # 北极星环保网（需要JS渲染）
                {"url": "https://www.cenews.com.cn/", "parser": "cenews", "requires_js": True},       # 中国环境新闻网（需要JS渲染）
                {"url": "https://www.ehwater.com/", "parser": "ehwater"}        # 中国环保设备网 ✅
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
    
    # 配置参数
    TIMEOUT = 30  # 增加超时时间到30秒
    MAX_RETRIES = 3  # 最大重试次数
    
    # 智能延迟配置（根据网站类型设置不同间隔）
    DELAY_CONFIG = {
        "priority": {"min_delay": 1, "max_delay": 2},
        "industry": {"min_delay": 2, "max_delay": 4},
        "policy": {"min_delay": 3, "max_delay": 5},  # 政府网站延迟更长
        "tech": {"min_delay": 2, "max_delay": 3}
    }
    
    def __init__(self):
        self.timeout = self.TIMEOUT
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
            "cenews": self._parse_cenews,            # 中国环境新闻网
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
        """解析北极星环保网 - 专用解析器"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            # 北极星环保网常见结构1：新闻列表
            news_list = soup.find("div", class_="news-list")
            if news_list:
                items = news_list.find_all("li")
                for item in items[:15]:
                    title_tag = item.find("a")
                    if title_tag:
                        title = title_tag.get_text(strip=True)
                        if len(title) >= 5:
                            results.append({
                                "title": title,
                                "url": title_tag.get("href", "#"),
                                "source": "北极星环保网",
                                "category": "industry"
                            })
            
            # 北极星环保网常见结构2：文章列表
            if not results:
                articles = soup.find_all("div", class_="article-item")
                for article in articles[:15]:
                    title_tag = article.find("h3") or article.find("h2")
                    if title_tag and title_tag.a:
                        title = title_tag.a.get_text(strip=True)
                        if len(title) >= 5:
                            results.append({
                                "title": title,
                                "url": title_tag.a.get("href", "#"),
                                "source": "北极星环保网",
                                "category": "industry"
                            })
            
            # 如果专用解析器没找到，回退到通用解析器
            if not results:
                results = self._parse_generic(html, "北极星环保网", "industry")
            
        except Exception as e:
            print(f"北极星环保网解析错误: {e}")
            results = self._parse_generic(html, "北极星环保网", "industry")
        
        return results[:15]

    def _parse_cenews(self, html: str) -> List[Dict[str, Any]]:
        """解析中国环境新闻网 - 专用解析器（替代失效的cn-em.com）"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            # 中国环境新闻网常见结构1：列表容器
            list_container = soup.find("div", id="listContainer") or soup.find("div", class_="list-container")
            if list_container:
                items = list_container.find_all("li")
                for item in items[:15]:
                    title_tag = item.find("a")
                    if title_tag:
                        title = title_tag.get_text(strip=True)
                        if len(title) >= 5:
                            results.append({
                                "title": title,
                                "url": title_tag.get("href", "#"),
                                "source": "中国环境新闻网",
                                "category": "industry"
                            })
            
            # 中国环境新闻网常见结构2：新闻列表
            if not results:
                news_items = soup.find_all("div", class_="news-item")
                for item in news_items[:15]:
                    title_tag = item.find("h3") or item.find("h2")
                    if title_tag and title_tag.a:
                        title = title_tag.a.get_text(strip=True)
                        if len(title) >= 5:
                            results.append({
                                "title": title,
                                "url": title_tag.a.get("href", "#"),
                                "source": "中国环境新闻网",
                                "category": "industry"
                            })
            
            # 如果专用解析器没找到，回退到通用解析器
            if not results:
                results = self._parse_generic(html, "中国环境新闻网", "industry")
            
        except Exception as e:
            print(f"中国环境新闻网解析错误: {e}")
            results = self._parse_generic(html, "中国环境新闻网", "industry")
        
        return results[:15]

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
        """通用解析器 - 增强版，支持多种HTML结构"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            # 扩展选择器列表，覆盖更多网站结构
            selectors = [
                # 常见新闻标题结构
                ("article h2 a", {}),
                ("article h3 a", {}),
                ("article header h2 a", {}),
                ("article header h3 a", {}),
                (".article h2 a", {}),
                (".article h3 a", {}),
                
                # 列表结构
                ("div.news-item h3 a", {}),
                ("div.news-item h2 a", {}),
                ("div.news-list li a", {}),
                ("ul.news-list li a", {}),
                ("div.list-content h3 a", {}),
                ("div.content-list li a", {}),
                ("div.news-content h3 a", {}),
                ("div.news-content h2 a", {}),
                
                # 通用容器
                ("div.main-content h3 a", {}),
                ("div.container li a", {}),
                ("div.list-box li a", {}),
                ("div.list-body li a", {}),
                ("div.main h3 a", {}),
                ("div.main-body h3 a", {}),
                
                # 政府网站结构
                ("div.list h4 a", {}),
                ("ul.list li a", {}),
                ("div.newslist li a", {}),
                ("ul.newslist li a", {}),
                
                # 新闻列表变体
                ("div.news_list li a", {}),
                ("ul.news_list li a", {}),
                ("div.newlist li a", {}),
                ("div.newsList li a", {}),
                
                # 卡片式布局
                ("div.card h3 a", {}),
                ("div.card-title a", {}),
                ("div.news-card h3 a", {}),
                (".card-body h3 a", {}),
                
                # 表格布局
                ("table.news-list a", {}),
                ("tr.news-item a", {}),
                
                # 无序列表变体
                ("ul li.news a", {}),
                ("ul li.article a", {}),
                ("ol li a", {}),
                
                # 通用链接样式
                ("a.news-title", {}),
                ("a.article-title", {}),
                ("a[class*='title']", {}),
                ("a[class*='news']", {}),
                
                # 回退选择器
                ("h1 a", {}),
                ("h2 a", {}),
                ("h3 a", {}),
                ("h4 a", {}),
                ("a.title", {}),
                ("a[title]", {}),
                ("div.title a", {}),
                ("span.title a", {}),
                (".title a", {})
            ]
            
            for selector, attrs in selectors:
                items = soup.select(selector)
                for item in items[:6]:  # 每个选择器最多取6条
                    title = item.get_text(strip=True) if item else ""
                    url = item.get("href", "") if item else ""
                    
                    # 过滤条件：标题长度至少4个字符，URL非空且不为#
                    if title and len(title) >= 4 and url and url != "#":
                        # 处理相对URL
                        if not url.startswith("http"):
                            url = "#"
                        
                        results.append({
                            "title": title,
                            "url": url,
                            "source": source_name,
                            "category": category
                        })
            
            # 去重 - 使用标题作为唯一键
            seen = set()
            unique_results = []
            for item in results:
                key = item["title"]
                if key not in seen:
                    seen.add(key)
                    unique_results.append(item)
            
            return unique_results[:15]  # 最多返回15条
            
        except Exception as e:
            print(f"{source_name}通用解析器错误: {e}")
            return []
    
    def _get_dynamic_html(self, url: str) -> str:
        """使用 Selenium 获取 JavaScript 渲染的页面内容"""
        if not SELENIUM_AVAILABLE:
            print("❌ Selenium 未安装，请安装: pip install selenium webdriver-manager")
            return ""
        
        html = ""
        driver = None
        
        try:
            # 配置 Chrome 选项
            options = Options()
            options.add_argument("--headless=new")  # 无头模式
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            # 创建驱动
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )
            
            # 访问页面
            driver.set_page_load_timeout(self.timeout)
            driver.get(url)
            
            # 等待 JavaScript 渲染（最多等待10秒）
            time.sleep(5)
            
            # 获取渲染后的 HTML
            html = driver.page_source
            print(f"✅ 动态渲染成功: {url}")
            
        except Exception as e:
            print(f"❌ 动态渲染失败 {url}: {e}")
            html = ""
        finally:
            if driver:
                driver.quit()
        
        return html

    def crawl_source(self, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """爬取单个来源（支持 JavaScript 渲染，失败时自动回退）"""
        results = []
        url_info = source_config
        url = url_info["url"]
        requires_js = url_info.get("requires_js", False)
        html = ""
        
        try:
            # 判断是否需要 JavaScript 渲染
            if requires_js and SELENIUM_AVAILABLE:
                # 先尝试使用 Selenium 获取动态内容
                html = self._get_dynamic_html(url)
                
                # 如果动态渲染失败，回退到普通 HTTP 请求
                if not html:
                    print(f"⏱️ 动态渲染失败，尝试普通请求 {url}")
                    requires_js = False  # 标记为普通请求
            
            # 使用普通 HTTP 请求（包括回退情况）
            if not html:
                response = self.session.get(url, timeout=self.timeout)
                response.encoding = response.apparent_encoding
                
                if response.status_code != 200:
                    print(f"❌ 请求失败 {url}: HTTP {response.status_code}")
                    return results
                
                html = response.text
            
            # 解析 HTML
            parser = self._get_parser(url_info["parser"])
            items = parser(html)
            
            for item in items:
                item["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                item["source_url"] = url
                item["dynamic"] = requires_js  # 标记是否为动态渲染
                results.append(item)
            
            print(f"✅ 成功爬取 {url}: {len(results)} 条")
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 爬取失败 {url}: {e}")
        except Exception as e:
            print(f"❌ 爬取异常 {url}: {e}")
        
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