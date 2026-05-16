"""新闻爬虫 - 主动抓取外部最新行业资讯、政策动态及技术进展"""
import re
import hashlib
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
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
                {"url": "https://gdjikang.com/", "parser": "jikang", "priority": 1},         # 最高优先级：吉康官网
                {"url": "https://aiqicha.baidu.com/company_detail_10987115296786?pd=ee", "parser": "aiqicha", "priority": 1},  # 爱企查-吉康环境
                {"url": "https://rdjk2018.b2b168.com/home.aspx", "parser": "b2b168", "priority": 1},  # 1688-吉康环境店铺
                {"url": "https://creategz-test.oss-cn-shenzhen.aliyuncs.com/mpb/assets/%E5%90%89%E5%BA%B7%E7%8E%AF%E5%A2%83%E7%94%B5%E5%AD%90%E6%A0%B7%E5%86%8C(%E6%89%8B%E6%9C%BA%E7%89%88%EF%BC%89.pdf", "parser": "jikang_pdf", "priority": 1},  # 吉康环境电子样册
            ]
        },
        "industry": {
            "name": "行业资讯",
            "urls": [
                {"url": "https://www.hbzhan.com/", "parser": "hbzhan"},          # 环保在线 ✅
                {"url": "https://www.chinawater.com.cn/", "parser": "chinawater"},  # 中国水网 ✅
                {"url": "https://huanbao.bjx.com.cn/", "parser": "bjx_huanbao", "requires_js": True},  # 北极星环保网（需要JS渲染）
                {"url": "https://www.cenews.com.cn/", "parser": "cenews", "requires_js": True},       # 中国环境新闻网（需要JS渲染）
                {"url": "https://www.ehwater.com/", "parser": "ehwater"},        # 中国环保设备网 ✅
                {"url": "https://www.chpa.org.cn/", "parser": "chpa"},           # 中国节能协会热泵专业委员会
                {"url": "http://www.gdepi.com/", "parser": "gdepi"},             # 广东环保产业网
            ]
        },
        "policy": {
            "name": "政策动态",
            "urls": [
                {"url": "https://www.mee.gov.cn/", "parser": "mee"},                   # 生态环境部 ✅
                {"url": "https://www.ndrc.gov.cn/xxgk/zcfb/ghwb/", "parser": "ndrc"},   # 国家发改委-规划（资源环境相关政策）
                {"url": "https://www.mohurd.gov.cn/zcfg/index.html", "parser": "mohurd"},  # 住建部-政策法规（污水/环保设施）
            ]
        },
        "tech": {
            "name": "技术资讯",
            "urls": [
                {"url": "https://www.cnhubei.com/", "parser": "cnhubei"},              # 湖北日报（环保科技）✅
                {"url": "https://huanbao.bjx.com.cn/tech/", "parser": "bjx_tech"},     # 北极星环保网-技术频道
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

    # 吉康环境核心关键词（用于智能检索和话题发现）
    KEYWORDS = [
        "低温除湿", "污泥干化", "闭式循环", "除湿干化",
        "高湿环境", "回南天", "污泥处理", "固废处理",
        "环保政策", "双碳", "节能", "绿色发展",
        "涡旋式热泵", "工业除湿", "污水处理",
    ]
    
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
            "jikang_pdf": self._parse_jikang_pdf,    # 吉康环境电子样册（PDF）
            "aiqicha": self._parse_aiqicha,          # 爱企查-吉康环境
            "b2b168": self._parse_b2b168,            # 1688-吉康环境店铺
            "hbzhan": self._parse_hbzhan,            # 环保在线
            "chinawater": self._parse_chinawater,     # 中国水网
            "bjx_huanbao": self._parse_bjx_huanbao,   # 北极星环保网
            "bjx_tech": self._parse_bjx_tech,         # 北极星环保网-技术频道
            "cenews": self._parse_cenews,            # 中国环境新闻网
            "chpa": self._parse_chpa,                # 中国节能协会热泵专业委员会
            "gdepi": self._parse_gdepi,              # 广东环保产业网
            "ehwater": self._parse_ehwater,          # 中国环保设备网
            "mee": self._parse_mee,                  # 生态环境部
            "ndrc": self._parse_ndrc,                # 国家发改委
            "mohurd": self._parse_mohurd,            # 住建部
            "cnhubei": self._parse_cnhubei,          # 湖北日报
            "techweb": self._parse_techweb,
            "sina_tech": self._parse_sina_tech,
            "ithome": self._parse_ithome,
            "gov": self._parse_gov,
            "miit": self._parse_miit,
            "cac": self._parse_cac,
            "36kr": self._parse_36kr,
            "pinggu": self._parse_pinggu,
            "jrj": self._parse_jrj,
            "mepc": self._parse_mepc,                # 广东省生态环境厅（兼容旧配置）
        }
        return parsers.get(parser_name, self._parse_generic)

    def _parse_jikang(self, html: str) -> List[Dict[str, Any]]:
        """解析广东吉康环境官网 - 低温除湿干化核心网站"""
        return self._parse_generic(html, "吉康环境", "priority")

    def _parse_aiqicha(self, html: str) -> List[Dict[str, Any]]:
        """解析爱企查-吉康环境公司信息页面
        
        爱企查提供公司基本信息、工商登记、风险信息等，
        用于获取吉康环境的企业资质、经营范围、法律风险等。
        """
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            # 爱企查结构：公司基本信息
            company_name = ""
            name_tag = soup.find("span", class_=re.compile(r"company-name|title|zx-title"))
            if name_tag:
                company_name = name_tag.get_text(strip=True)
            
            # 提取公司描述/经营范围等信息
            info_blocks = soup.find_all("div", class_=re.compile(r"info|detail|desc|row|item"))
            for block in info_blocks:
                text = block.get_text(strip=True)
                if len(text) >= 10 and any(kw in text for kw in
                    ["环保", "环境", "除湿", "干化", "污泥", "节能", "技术", "设备", 
                     "注册", "经营", "许可", "认证", "专利"]):
                    results.append({
                        "title": text[:100],
                        "url": "https://aiqicha.baidu.com/company_detail_10987115296786?pd=ee",
                        "source": "爱企查-吉康环境",
                        "category": "priority"
                    })
            
            # 如果专用解析失败，回退到通用解析
            if not results:
                results = self._parse_generic(html, "爱企查-吉康环境", "priority")
            
            # 限制返回数量（公司信息通常较少）
            return results[:10]
            
        except Exception as e:
            print(f"爱企查解析错误: {e}")
            return self._parse_generic(html, "爱企查-吉康环境", "priority")

    def _parse_b2b168(self, html: str) -> List[Dict[str, Any]]:
        """解析1688-吉康环境店铺页面
        
        1688店铺页面提供产品信息、企业动态、联系方式等，
        用于获取吉康环境的产品报价、服务范围等商业信息。
        """
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            # 1688店铺结构：产品列表 / 公司介绍
            # 尝试提取产品信息
            product_items = soup.find_all("div", class_=re.compile(r"product|item|goods|offer"))
            for item in product_items[:10]:
                title_tag = (item.find("h3") or item.find("h2") or 
                           item.find("a", class_=re.compile(r"title|name")))
                if title_tag:
                    title = title_tag.get_text(strip=True)
                    if len(title) >= 5 and any(kw in title for kw in
                        ["除湿", "干化", "污泥", "热泵", "设备", "环保", "节能"]):
                        results.append({
                            "title": title,
                            "url": "https://rdjk2018.b2b168.com/home.aspx",
                            "source": "1688-吉康环境",
                            "category": "priority"
                        })
            
            # 尝试提取公司简介
            intro_tag = (soup.find("div", class_=re.compile(r"intro|about|desc|company")) or
                        soup.find("div", id=re.compile(r"intro|about|desc")))
            if intro_tag:
                text = intro_tag.get_text(strip=True)
                if len(text) >= 20:
                    results.append({
                        "title": f"吉康环境公司介绍: {text[:80]}",
                        "url": "https://rdjk2018.b2b168.com/home.aspx",
                        "source": "1688-吉康环境",
                        "category": "priority"
                    })
            
            # 如果专用解析失败，回退到通用解析
            if not results:
                results = self._parse_generic(html, "1688-吉康环境", "priority")
            
            return results[:10]
            
        except Exception as e:
            print(f"1688店铺解析错误: {e}")
            return self._parse_generic(html, "1688-吉康环境", "priority")

    def _parse_jikang_pdf(self, html: str) -> List[Dict[str, Any]]:
        """解析吉康环境电子样册（PDF 在线预览页）

        OSS 直链 PDF 无法直接解析 HTML，但可以提取 PDF 中的产品参数、技术规格等。
        如果无法提取内容，返回样册的基本描述信息。
        """
        results = []
        # PDF 直链无法通过 HTML 解析，返回样册元数据
        results.append({
            "title": "吉康环境电子样册（手机版）- 低温除湿干化设备产品手册",
            "url": "https://creategz-test.oss-cn-shenzhen.aliyuncs.com/mpb/assets/%E5%90%89%E5%BA%B7%E7%8E%AF%E5%A2%83%E7%94%B5%E5%AD%90%E6%A0%B7%E5%86%8C(%E6%89%8B%E6%9C%BA%E7%89%88%EF%BC%89.pdf",
            "source": "吉康环境电子样册",
            "category": "priority",
        })

        # 尝试用 pdf 工具提取内容（如果可用）
        try:
            import tempfile, os
            pdf_url = "https://creategz-test.oss-cn-shenzhen.aliyuncs.com/mpb/assets/%E5%90%89%E5%BA%B7%E7%8E%AF%E5%A2%83%E7%94%B5%E5%AD%90%E6%A0%B7%E5%86%8C(%E6%89%8B%E6%9C%BA%E7%89%88%EF%BC%89.pdf"
            resp = self.session.get(pdf_url, timeout=30)
            if resp.status_code == 200 and len(resp.content) > 1000:
                # 保存临时 PDF
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp.write(resp.content)
                tmp.close()
                # 尝试提取文字
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(tmp.name)
                    text = ""
                    for page in doc:
                        text += page.get_text()
                    doc.close()
                    if text.strip():
                        # 按段落拆分
                        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 20]
                        for p in paragraphs[:10]:
                            results.append({
                                "title": p[:100],
                                "url": pdf_url,
                                "source": "吉康环境电子样册",
                                "category": "priority",
                            })
                except ImportError:
                    pass  # PyMuPDF 未安装，仅返回元数据
                finally:
                    os.unlink(tmp.name)
        except Exception:
            pass

        return results[:15]

    def _parse_chpa(self, html: str) -> List[Dict[str, Any]]:
        """解析中国节能协会热泵专业委员会

        提供热泵行业政策、技术标准、行业动态等资讯，
        与吉康环境的核心技术（涡旋式热泵）直接相关。
        """
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")

            # 常见结构：新闻列表
            items = (soup.find_all("div", class_=re.compile(r"news|article|list-item|item"))
                     or soup.find_all("li", class_=re.compile(r"news|article|item")))

            for item in items[:15]:
                title_tag = item.find("a")
                if title_tag:
                    title = title_tag.get_text(strip=True)
                    href = title_tag.get("href", "")
                    if len(title) >= 8:
                        if href and not href.startswith("http"):
                            href = "https://www.chpa.org.cn" + href
                        results.append({
                            "title": title,
                            "url": href,
                            "source": "中国节能协会热泵专委会",
                            "category": "industry",
                        })

            if not results:
                results = self._parse_generic(html, "中国节能协会热泵专委会", "industry")

        except Exception as e:
            print(f"热泵专委会解析错误: {e}")
            results = self._parse_generic(html, "中国节能协会热泵专委会", "industry")

        return results[:15]

    def _parse_gdepi(self, html: str) -> List[Dict[str, Any]]:
        """解析广东环保产业网

        广东省环保产业协会官网，提供本地政策、产业动态、
        会员企业资讯等，与吉康环境（广东企业）高度相关。
        """
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")

            # 常见结构
            items = (soup.find_all("div", class_=re.compile(r"news|article|list-item|item"))
                     or soup.find_all("li", class_=re.compile(r"news|article|item")))

            for item in items[:15]:
                title_tag = item.find("a")
                if title_tag:
                    title = title_tag.get_text(strip=True)
                    href = title_tag.get("href", "")
                    if len(title) >= 8:
                        if href and not href.startswith("http"):
                            href = "http://www.gdepi.com" + href
                        results.append({
                            "title": title,
                            "url": href,
                            "source": "广东环保产业网",
                            "category": "industry",
                        })

            if not results:
                results = self._parse_generic(html, "广东环保产业网", "industry")

        except Exception as e:
            print(f"广东环保产业网解析错误: {e}")
            results = self._parse_generic(html, "广东环保产业网", "industry")

        return results[:15]

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

    def _parse_bjx_tech(self, html: str) -> List[Dict[str, Any]]:
        """解析北极星环保网-技术频道
        
        与 bjx_huanbao 共享基础解析逻辑，但聚焦技术文章。
        """
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            # 北极星技术频道常见结构
            tech_list = (soup.find("div", class_="news-list") or 
                        soup.find("div", class_="list-content") or
                        soup.find("div", class_="tech-list"))
            if tech_list:
                items = tech_list.find_all("li")
                for item in items[:15]:
                    title_tag = item.find("a")
                    if title_tag:
                        title = title_tag.get_text(strip=True)
                        if len(title) >= 5:
                            results.append({
                                "title": title,
                                "url": title_tag.get("href", "#"),
                                "source": "北极星环保网-技术",
                                "category": "tech"
                            })
            
            if not results:
                results = self._parse_generic(html, "北极星环保网-技术", "tech")
            
        except Exception as e:
            print(f"北极星环保网技术频道解析错误: {e}")
            results = self._parse_generic(html, "北极星环保网-技术", "tech")
        
        return results[:15]

    def _parse_ndrc(self, html: str) -> List[Dict[str, Any]]:
        """解析国家发改委-规划发布页面
        
        发改委发布国民经济和社会发展规划、资源环境相关政策，
        与环保行业密切相关（如双碳、循环经济、绿色发展规划）。
        """
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            # 发改委规划页面结构
            # 结构1：列表项
            items = soup.find_all("li", class_=re.compile(r"list-item|clearfix"))
            for item in items[:15]:
                title_tag = item.find("a")
                if title_tag:
                    title = title_tag.get_text(strip=True)
                    if len(title) >= 8:
                        href = title_tag.get("href", "")
                        if href and not href.startswith("http"):
                            href = "https://www.ndrc.gov.cn" + href
                        results.append({
                            "title": title,
                            "url": href,
                            "source": "国家发改委",
                            "category": "policy"
                        })
            
            # 结构2：表格行
            if not results:
                rows = soup.find_all("tr")
                for row in rows[:15]:
                    title_tag = row.find("a")
                    if title_tag:
                        title = title_tag.get_text(strip=True)
                        if len(title) >= 8:
                            href = title_tag.get("href", "")
                            if href and not href.startswith("http"):
                                href = "https://www.ndrc.gov.cn" + href
                            results.append({
                                "title": title,
                                "url": href,
                                "source": "国家发改委",
                                "category": "policy"
                            })
            
            # 回退
            if not results:
                results = self._parse_generic(html, "国家发改委", "policy")
            
        except Exception as e:
            print(f"国家发改委解析错误: {e}")
            results = self._parse_generic(html, "国家发改委", "policy")
        
        return results[:15]

    def _parse_mohurd(self, html: str) -> List[Dict[str, Any]]:
        """解析住建部-政策法规页面
        
        住建部负责污水处理设施建设、城镇污泥处置等政策，
        与吉康环境的核心业务（污泥干化）直接相关。
        """
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            # 住建部政策页面结构
            # 结构1：政策列表
            list_div = (soup.find("div", class_="list") or 
                       soup.find("ul", class_="list") or
                       soup.find("div", class_="policy-list") or
                       soup.find("div", class_="news-list"))
            if list_div:
                items = list_div.find_all("li")
                for item in items[:15]:
                    title_tag = item.find("a")
                    if title_tag:
                        title = title_tag.get_text(strip=True)
                        if len(title) >= 8:
                            href = title_tag.get("href", "")
                            if href and not href.startswith("http"):
                                href = "https://www.mohurd.gov.cn" + href
                            results.append({
                                "title": title,
                                "url": href,
                                "source": "住建部",
                                "category": "policy"
                            })
            
            # 结构2：通用链接列表
            if not results:
                links = soup.find_all("a", href=True)
                for link in links[:20]:
                    title = link.get_text(strip=True)
                    href = link.get("href", "")
                    if (len(title) >= 8 and href and 
                        any(kw in title for kw in ["污水", "污泥", "环保", "城镇", 
                            "排水", "环境", "节能", "绿色", "建设", "标准"])):
                        if not href.startswith("http"):
                            href = "https://www.mohurd.gov.cn" + href
                        results.append({
                            "title": title,
                            "url": href,
                            "source": "住建部",
                            "category": "policy"
                        })
            
            # 回退
            if not results:
                results = self._parse_generic(html, "住建部", "policy")
            
        except Exception as e:
            print(f"住建部解析错误: {e}")
            results = self._parse_generic(html, "住建部", "policy")
        
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

    # ==================== 话题发现与关键词搜索 ====================

    def _fetch_page(self, url: str) -> Optional[str]:
        """安全获取页面（通用 HTTP 请求）"""
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.encoding = resp.apparent_encoding or "utf-8"
            if resp.status_code == 200:
                return resp.text
        except Exception as e:
            print(f"  [爬虫] 请求失败 {url}: {e}")
        return None

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
            search_url = f"https://www.baidu.com/s?wd={keyword}&rn=10"
            html = self._fetch_page(search_url)
            if not html:
                continue

            try:
                soup = BeautifulSoup(html, "html.parser")
                for result_div in soup.find_all(["div", "h3"],
                        class_=re.compile(r"result|t")):
                    a_tag = result_div.find("a")
                    if not a_tag:
                        continue
                    title = a_tag.get_text(strip=True)
                    href = a_tag.get("href", "")

                    if len(title) > 8:
                        all_results.append({
                            "title": title.strip()[:500],
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
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()

            article = (soup.find("article") or
                      soup.find("div", class_=re.compile(r"article|content|detail|text|body")) or
                      soup.find("div", id=re.compile(r"article|content|detail|text|body")))

            if article:
                text = article.get_text(separator="\n", strip=True)
            else:
                text = soup.get_text(separator="\n", strip=True)

            lines = [line.strip() for line in text.split("\n")
                     if line.strip() and len(line.strip()) > 10]
            return "\n".join(lines[:50])
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
        print(f"[发现] 自动发现 {count} 个热门话题...")

        search_keywords = random.sample(self.KEYWORDS, min(3, len(self.KEYWORDS)))
        results = self.search_by_keywords(search_keywords, max_results=30)

        if not results:
            default_topics = [
                {"title": "华南地区工业除湿技术创新趋势", "keywords": ["低温除湿", "节能", "华南"], "context": "大湾区工业除湿需求增长"},
                {"title": "广东省环保政策对污泥处理的影响", "keywords": ["环保政策", "污泥干化", "广东"], "context": "十四五环保规划要求"},
                {"title": "闭式循环技术如何助力双碳目标", "keywords": ["闭式循环", "双碳", "节能"], "context": "碳排放法规趋严"},
            ]
            return default_topics[:count]

        scored = []
        blacklist = ["娱乐", "明星", "电影", "综艺", "游戏", "健身", "减肥", "美食菜谱"]
        for item in results:
            title = item.get("title", "")
            score = sum(1 for kw in self.KEYWORDS if kw in title)
            if any(bw in title for bw in blacklist):
                continue
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)

        topics = []
        for score, item in scored[:count]:
            title = item["title"]
            matched_kws = [kw for kw in self.KEYWORDS if kw in title]
            if not matched_kws:
                matched_kws = search_keywords[:2]

            topics.append({
                "title": title,
                "keywords": matched_kws,
                "context": f"来源: {item.get('source', '网络')}",
                "search_result": item,
            })

        print(f"[发现] 发现 {len(topics)} 个话题")
        for i, t in enumerate(topics, 1):
            print(f"  {i}. {t['title']} (关键词: {', '.join(t['keywords'])})")

        return topics