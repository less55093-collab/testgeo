"""
豆包(Doubao)页面爬虫
使用Playwright爬取豆包聊天页面，提取并记录：
1. 提问的关键词
2. 产品名称和排名
3. 产品来源
"""

import asyncio
import json
import re
import os
import sys
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional
from playwright.async_api import async_playwright, Page, Browser

# 添加父目录到路径以导入llm模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm.config_loader import create_random_llm_wrapper


@dataclass
class ProductInfo:
    """产品信息"""
    rank: int
    name: str
    sources: list = field(default_factory=list)  # 多个来源列表 [{"title": "", "url": "", "source": ""}]


@dataclass
class CrawlResult:
    """爬取结果"""
    keyword: str
    crawl_time: str
    products: list[ProductInfo] = field(default_factory=list)
    raw_content: str = ""
    references: list[dict] = field(default_factory=list)


class DoubaoCrawler:
    """豆包页面爬虫"""
    
    CN_NUM_MAP = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    }
    
    def __init__(self, headless: bool = False, cookies: str = "", use_llm: bool = False):
        """
        初始化爬虫
        
        Args:
            headless: 是否使用无头模式
            cookies: Cookie字符串（从浏览器复制）
            use_llm: 是否在解析阶段调用LLM
        """
        self.headless = headless
        self.cookies = cookies
        self.use_llm = use_llm
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.context = None
        
    def _parse_cookies(self, cookie_string: str, domain: str = ".doubao.com") -> list[dict]:
        """将cookie字符串解析为Playwright格式的cookie列表"""
        cookies = []
        if not cookie_string:
            return cookies
            
        for item in cookie_string.split(';'):
            item = item.strip()
            if not item or '=' not in item:
                continue
            name, value = item.split('=', 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": domain,
                "path": "/",
            })
        return cookies
        
    async def start(self):
        """启动浏览器"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN"
        )
        
        # 注入cookie
        if self.cookies:
            parsed_cookies = self._parse_cookies(self.cookies)
            if parsed_cookies:
                await self.context.add_cookies(parsed_cookies)
                print(f"✓ 已注入 {len(parsed_cookies)} 个cookie")
        
        self.page = await self.context.new_page()
        
    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
            
    async def navigate_to_chat(self, url: str):
        """
        导航到豆包聊天页面
        
        Args:
            url: 豆包聊天页面URL
        """
        try:
            # 增加超时时间到60秒，使用domcontentloaded加快加载
            await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"⚠ 首次加载超时，尝试等待页面稳定: {e}")
            # 如果超时，尝试等待页面稳定
            await asyncio.sleep(5)
        
        # 等待React内容渲染完成
        print("⏳ 等待页面内容渲染...")
        await asyncio.sleep(8)
        
        # 尝试点击"参考资料"展开参考面板
        try:
            # 查找包含"参考"文字的元素
            ref_button = await self.page.query_selector('text=参考')
            if ref_button:
                print("📚 找到参考资料按钮，点击展开...")
                await ref_button.click()
                # 等待参考面板渲染
                await asyncio.sleep(5)
            else:
                # 尝试其他可能的选择器
                ref_selectors = [
                    '[class*="reference"]',
                    '[class*="source"]', 
                    'button:has-text("参考")',
                    'span:has-text("篇资料")',
                ]
                for sel in ref_selectors:
                    try:
                        elem = await self.page.query_selector(sel)
                        if elem:
                            print(f"📚 找到参考元素 '{sel}'，点击展开...")
                            await elem.click()
                            await asyncio.sleep(5)
                            break
                    except:
                        continue
        except Exception as e:
            print(f"⚠ 无法展开参考资料: {e}")
        
    async def send_question(self, question: str):
        """
        在豆包中发送问题
        
        Args:
            question: 要发送的问题
        """
        # 查找输入框并输入问题
        input_selector = 'textarea[placeholder*="输入"], textarea[class*="input"], div[contenteditable="true"]'
        await self.page.wait_for_selector(input_selector, timeout=10000)
        input_element = await self.page.query_selector(input_selector)
        
        if input_element:
            await input_element.fill(question)
            await asyncio.sleep(0.5)
            
            # 点击发送按钮或按回车
            send_btn = await self.page.query_selector('button[type="submit"], button[class*="send"]')
            if send_btn:
                await send_btn.click()
            else:
                await input_element.press("Enter")
                
            # 等待回答生成完成
            await self._wait_for_response()
            
    async def _wait_for_response(self, timeout: int = 60):
        """等待豆包回答生成完成"""
        # 等待加载指示器消失
        await asyncio.sleep(2)
        
        for _ in range(timeout):
            # 检查是否还在生成中
            loading = await self.page.query_selector('[class*="loading"], [class*="typing"]')
            if not loading:
                break
            await asyncio.sleep(1)
            
        # 额外等待确保内容完全加载
        await asyncio.sleep(2)
        
    async def extract_content(self) -> dict:
        """
        提取页面内容
        
        Returns:
            包含主要内容和参考资料的字典
        """
        result = {
            "main_content": "",
            "references": []
        }
        
        # 保存页面截图用于调试
        output_dir = os.path.dirname(os.path.abspath(__file__))
        screenshot_path = os.path.join(output_dir, "debug_screenshot.png")
        try:
            await self.page.screenshot(path=screenshot_path, full_page=True)
            print(f"📷 已保存页面截图: {screenshot_path}")
        except Exception as e:
            print(f"⚠ 截图保存失败: {e}")
        
        # 保存页面HTML用于调试
        html_path = os.path.join(output_dir, "debug_page.html")
        try:
            html_content = await self.page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"📄 已保存页面HTML: {html_path}")
        except Exception as e:
            print(f"⚠ HTML保存失败: {e}")
        
        # 豆包页面特定的内容选择器（更新版）
        content_selectors = [
            # 豆包聊天消息
            '[class*="chat-message"]',
            '[class*="message-item"]',
            '[class*="message-content"]',
            '[class*="bot-message"]',
            '[class*="assistant"]',
            # Markdown内容
            '[class*="markdown"]',
            '[class*="prose"]',
            # 通用回复区域
            '[class*="answer"]',
            '[class*="response"]',
            '[class*="reply"]',
            '[class*="content"]',
            # 文章/正文
            'article',
            'main',
            '[role="main"]',
        ]
        
        # 使用JavaScript直接获取页面内容（更可靠的方法）
        print("\n🔍 正在提取页面内容...")
        
        try:
            # 使用JavaScript获取聊天内容区域的文本
            main_content = await self.page.evaluate('''() => {
                let content = '';
                
                // 方法1: 查找h3标签（产品标题通常在h3中）
                const headings = document.querySelectorAll('h3, h2, h4');
                let foundProducts = [];
                for (const h of headings) {
                    const text = h.innerText.trim();
                    // 检查是否是产品标题（包含中文序号）
                    if (text && /^[一二三四五六七八九十]+、/.test(text)) {
                        foundProducts.push(text);
                        content += text + '\\n';
                    }
                }
                
                // 方法2: 查找ul/li元素获取详细信息
                const listItems = document.querySelectorAll('li');
                for (const li of listItems) {
                    const text = li.innerText.trim();
                    if (text && (
                        text.includes('核心优势') || 
                        text.includes('特色服务') ||
                        text.includes('适合人群')
                    )) {
                        content += text + '\\n';
                    }
                }
                
                // 方法3: 如果上面方法失败，尝试从visible文本中提取
                if (!content || foundProducts.length === 0) {
                    // 查找主要聊天区域
                    const chatAreas = document.querySelectorAll('[class*="message"], [class*="chat"], [class*="content"]');
                    for (const area of chatAreas) {
                        const text = area.innerText;
                        if (text && text.length > 200 && (
                            text.includes('恒天') || 
                            text.includes('核心优势')
                        )) {
                            content = text;
                            break;
                        }
                    }
                }
                
                // 方法4: 最后手段 - 获取整个body文本
                if (!content || content.length < 100) {
                    // 找到最大的内容区域
                    const main = document.querySelector('main') || document.body;
                    content = main.innerText;
                }
                
                return content;
            }''')
            
            if main_content:
                result["main_content"] = main_content
                print(f"📝 通过JavaScript获取到内容: {len(result['main_content'])} 字符")
        except Exception as e:
            print(f"⚠ JavaScript提取失败: {e}")
        
        print(f"\n📝 提取到的内容长度: {len(result['main_content'])} 字符")
        
        # 使用JavaScript提取真正的参考资料（外部链接）
        print("\n🔍 正在提取参考资料...")
        references = await self._collect_panel_references(max_pages=5)
        result["references"] = references
        print(f"📚 提取到的参考资料数: {len(result['references'])}")
                        
        return result
    
    async def extract_rank_table(self) -> list[ProductInfo]:
        """
        直接解析页面上的表格，提取【排名-产品/平台-引用来源】结构
        """
        if not self.page:
            return []
        
        print("\n🔍 尝试从页面表格直接提取数据...")
        try:
            table_rows = await self.page.evaluate("""() => {
                const normalize = (text) => (text || '').replace(/\\s+/g, '').toLowerCase();
                const tables = Array.from(document.querySelectorAll('table'));
                
                for (const table of tables) {
                    const headerRow = table.querySelector('thead tr') || table.querySelector('tr');
                    if (!headerRow) continue;
                    const headerCells = Array.from(headerRow.querySelectorAll('th, td'));
                    const map = {rank: -1, name: -1, source: -1};
                    
                    headerCells.forEach((cell, index) => {
                        const text = cell.innerText || '';
                        const n = normalize(text);
                        if (map.rank === -1 && (n.includes('排名') || n.includes('序号'))) {
                            map.rank = index;
                        }
                        if (map.name === -1 && (n.includes('产品') || n.includes('平台') || n.includes('店') || n.includes('机构'))) {
                            map.name = index;
                        }
                        if (map.source === -1 && (n.includes('引用') || n.includes('来源') || n.includes('参考'))) {
                            map.source = index;
                        }
                    });
                    
                    if (map.rank === -1 || map.name === -1 || map.source === -1) {
                        continue;
                    }
                    
                    const bodyRows = table.querySelectorAll('tbody tr');
                    const dataRows = bodyRows.length ? Array.from(bodyRows) : Array.from(table.querySelectorAll('tr')).slice(1);
                    const rows = [];
                    
                    for (const row of dataRows) {
                        const cells = row.querySelectorAll('td');
                        if (!cells.length) continue;
                        
                        const rankCell = cells[map.rank] || cells[0];
                        const nameCell = cells[map.name] || cells[Math.min(map.name, cells.length - 1)];
                        const sourceCell = cells[map.source] || cells[Math.min(map.source, cells.length - 1)];
                        const nameText = nameCell ? nameCell.innerText.trim() : '';
                        
                        if (!nameText) {
                            continue;
                        }
                        
                        rows.push({
                            rankText: rankCell ? rankCell.innerText.trim() : '',
                            name: nameText,
                            sourceText: sourceCell ? sourceCell.innerText.trim() : '',
                            links: Array.from(sourceCell ? sourceCell.querySelectorAll('a[href]') : []).map(link => ({
                                title: (link.innerText || '').trim(),
                                url: link.href
                            }))
                        });
                    }
                    
                    if (rows.length >= 2) {
                        return rows;
                    }
                }
                
                return [];
            }""")
        except Exception as exc:
            print(f"⚠ 表格提取失败: {exc}")
            return []
        
        if not table_rows:
            print("⚠ 表格结构未检测到，继续使用其他解析策略")
            return []
        
        products = []
        for idx, row in enumerate(table_rows, start=1):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            
            rank = self._parse_rank_value(row.get("rankText"), fallback=idx)
            raw_source_text = (row.get("sourceText") or "").strip()
            products.append(ProductInfo(rank=rank, name=name, sources=[]))
            if raw_source_text:
                print(f"  ✓ 表格数据: {rank}. {name} | 来源提示: {raw_source_text[:60]}")
            else:
                print(f"  ✓ 表格数据: {rank}. {name}")
        
        products.sort(key=lambda p: p.rank)
        if products:
            print(f"📊 从表格提取到 {len(products)} 条记录")
        else:
            print("⚠ 未找到符合要求的表格")
        return products
    
    async def _collect_panel_references(self, max_pages: int = 5) -> list[dict]:
        """抓取豆包参考资料面板的所有链接"""
        if not self.page:
            return []
        
        references: list[dict] = []
        seen_urls: set[str] = set()
        
        for page_idx in range(max_pages):
            page_refs = await self._extract_reference_links_once()
            new_count = 0
            for ref in page_refs:
                url = ref.get("url", "")
                title = ref.get("title", "").strip()
                summary = ref.get("summary", "").strip()
                
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                
                ref["title"] = title
                ref["summary"] = summary
                ref["source"] = self._extract_source_name(url) if url else (ref.get("source_hint") or "未知来源")
                references.append(ref)
                new_count += 1
            
            if new_count == 0:
                # 没有新增内容，停止翻页
                break
            
            has_next = await self._goto_next_reference_page()
            if not has_next:
                break
        
        print(f"📚 参考资料面板共提取 {len(references)} 条")
        return references
    
    async def _extract_reference_links_once(self) -> list[dict]:
        """在当前参考资料面板中提取链接"""
        if not self.page:
            return []
        
        try:
            refs = await self.page.evaluate("""() => {
                const selectors = [
                    '[data-testid*=\"reference\"]',
                    '[class*=\"reference\"]',
                    '[class*=\"references\"]',
                    '[class*=\"citation\"]',
                    '[class*=\"source-list\"]'
                ];
                
                const containers = [];
                for (const sel of selectors) {
                    document.querySelectorAll(sel).forEach(elem => containers.push(elem));
                }
                
                if (!containers.length) {
                    const fallback = Array.from(document.querySelectorAll('section,div'))
                        .filter(elem => {
                            const text = (elem.innerText || '').trim();
                            return text.includes('参考') && elem.querySelectorAll('a[href^=\"http\"]').length >= 1;
                        });
                    containers.push(...fallback);
                }
                
                const seen = new Set();
                const results = [];
                
                for (const container of containers) {
                    const cards = container.querySelectorAll('[data-testid*=\"reference\"], [class*=\"reference-item\"], li, article, [class*=\"item\"], [class*=\"card\"]');
                    for (const card of cards) {
                        const link = card.querySelector('a[href^=\"http\"]');
                        if (!link) continue;
                        
                        const href = link.href;
                        if (!href || href.includes('doubao.com') || href.includes('bytedance.com')) {
                            continue;
                        }
                        if (seen.has(href)) continue;
                        seen.add(href);
                        
                        const titleElem = card.querySelector('[class*=\"title\"], h3, h4, h5, strong') || link;
                        const summaryElem = card.querySelector('[class*=\"summary\"], [class*=\"desc\"], p');
                        const sourceElem = card.querySelector('[class*=\"site\"], [class*=\"source\"], span');
                        
                        const title = titleElem && titleElem.innerText ? titleElem.innerText.trim() : (link.innerText || '').trim();
                        const summary = summaryElem && summaryElem.innerText ? summaryElem.innerText.trim() : '';
                        const source = sourceElem && sourceElem.innerText ? sourceElem.innerText.trim() : '';
                        
                        results.push({
                            title,
                            url: href,
                            summary,
                            source_hint: source
                        });
                    }
                    
                    if (results.length >= 3) {
                        // 当前容器已经有结果，避免继续遍历其它容器导致重复
                        break;
                    }
                }
                
                if (!results.length) {
                    const allLinks = document.querySelectorAll('a[href^=\"http\"]');
                    for (const link of allLinks) {
                        const href = link.href;
                        if (!href || href.includes('doubao.com') || href.includes('bytedance.com')) continue;
                        const parentText = (link.closest('div,li,article')?.innerText || '').trim();
                        if (parentText.includes('参考') || parentText.includes('引用')) {
                            results.push({
                                title: (link.innerText || '').trim(),
                                url: href,
                                summary: parentText.substring(0, 120),
                                source_hint: ''
                            });
                        }
                    }
                }
                
                return results;
            }""")
            return refs or []
        except Exception as exc:
            print(f"⚠ 参考资料提取失败: {exc}")
            return []
    
    async def _goto_next_reference_page(self) -> bool:
        """翻页或滚动以加载更多参考资料"""
        if not self.page:
            return False
        
        try:
            clicked = await self.page.evaluate("""() => {
                const clickSelectors = ['button', 'a', 'div'];
                for (const tag of clickSelectors) {
                    const candidates = Array.from(document.querySelectorAll(tag)).filter(elem => {
                        const text = (elem.innerText || '').trim();
                        return /下一页|查看更多|更多参考|展开更多/.test(text);
                    });
                    for (const btn of candidates) {
                        if (btn.disabled || btn.getAttribute('aria-disabled') === 'true') {
                            continue;
                        }
                        btn.click();
                        return true;
                    }
                }
                
                const panelSelectors = [
                    '[data-testid*=\"reference\"]',
                    '[class*=\"reference-list\"]',
                    '[class*=\"reference-panel\"]'
                ];
                for (const sel of panelSelectors) {
                    const panel = document.querySelector(sel);
                    if (panel && panel.scrollHeight - panel.clientHeight > 20) {
                        const before = panel.scrollTop;
                        panel.scrollTop = panel.scrollHeight;
                        return panel.scrollTop !== before;
                    }
                }
                return false;
            }""")
            if clicked:
                await asyncio.sleep(1.5)
            return clicked
        except Exception as exc:
            print(f"⚠ 参考资料翻页失败: {exc}")
            return False
    
    async def search_online_for_product(self, product_name: str, keyword: str = "") -> list:
        """
        兼容旧接口：根据最新策略禁用外部搜索
        """
        print(f"⚠ 搜索工具已禁用，跳过对 '{product_name}' 的在线搜索请求")
        return []
    
    def _parse_rank_value(self, value, fallback: int) -> int:
        """将表格中的排名字段转换为整数"""
        if isinstance(value, (int, float)):
            ivalue = int(value)
            if ivalue > 0:
                return ivalue
        text = str(value or "").strip()
        if not text:
            return fallback
        digit_match = re.search(r'\d+', text)
        if digit_match:
            return int(digit_match.group())
        total = 0
        for char in text:
            total += self.CN_NUM_MAP.get(char, 0)
        return total or fallback
    
    def _extract_source_name(self, url: str) -> str:
        """从URL提取来源名称"""
        if not url:
            return "未知来源"
            
        # 常见网站映射
        source_map = {
            "zhihu.com": "知乎",
            "xiaohongshu.com": "小红书",
            "baidu.com": "百度",
            "sohu.com": "搜狐",
            "sina.com": "新浪",
            "163.com": "网易",
            "qq.com": "腾讯",
            "weibo.com": "微博",
            "bilibili.com": "B站",
            "douban.com": "豆瓣",
            "taobao.com": "淘宝",
            "jd.com": "京东",
            "xnnews.com.cn": "咸宁网",
            "wandoujia.com": "豌豆荚",
            "toutiao.com": "今日头条",
            "csdn.net": "CSDN",
        }
        
        for domain, name in source_map.items():
            if domain in url:
                return name
        
        domain_match = re.search(r'https?://([^/]+)/?', url)
        if domain_match:
            host = domain_match.group(1)
            return host.replace("www.", "")
        return "未知来源"
    
    def _normalize_text(self, text: str) -> str:
        """统一文本格式用于匹配"""
        if not text:
            return ""
        normalized = re.sub(r'[\s·•，,。、“”\"\'()（）【】\\[\\]《》<>—-]', '', text)
        return normalized.lower()
    
    def _match_references_to_products(self, products: list[ProductInfo], references: list[dict]):
        """根据参考资料匹配引用来源"""
        if not products or not references:
            return
        
        normalized_refs = []
        for ref in references:
            title = ref.get("title", "")
            url = ref.get("url", "")
            summary_blob = " ".join(filter(None, [
                ref.get("summary", ""),
                ref.get("content", ""),
                ref.get("source_hint", ""),
            ]))
            normalized_refs.append({
                "raw": ref,
                "normalized_title": self._normalize_text(title),
                "normalized_content": self._normalize_text(summary_blob),
                "title": title or ref.get("source", "参考资料"),
                "url": url,
                "source": ref.get("source") or self._extract_source_name(url)
            })
        
        for product in products:
            normalized_name = self._normalize_text(product.name)
            if not normalized_name:
                continue
            
            if not hasattr(product, "sources") or not isinstance(product.sources, list):
                product.sources = []
            
            existing = set()
            for src in product.sources:
                key = src.get("url") or src.get("title")
                if key:
                    existing.add(key)
            
            new_added = 0
            for ref in normalized_refs:
                if not ref["normalized_title"] and not ref["normalized_content"]:
                    continue
                if normalized_name not in ref["normalized_title"] and normalized_name not in ref["normalized_content"]:
                    continue
                
                key = ref["url"] or ref["title"]
                if key in existing:
                    continue
                existing.add(key)
                
                product.sources.append({
                    "title": ref["title"],
                    "url": ref["url"],
                    "source": ref["source"]
                })
                new_added += 1
            
            if new_added:
                print(f"    ✓ 引用匹配: {product.name} (新增{new_added}条)")
            
    async def fetch_reference_contents(self, references: list, max_refs: int = 5) -> list:
        """
        获取参考资料网页的正文内容
        
        Args:
            references: 参考资料列表
            max_refs: 最多获取多少个参考资料的内容
            
        Returns:
            更新后的参考资料列表，包含正文内容
        """
        print(f"\n📖 正在获取参考资料网页内容 (最多{max_refs}个)...")
        
        for i, ref in enumerate(references[:max_refs]):
            url = ref.get("url", "")
            if not url:
                continue
                
            try:
                print(f"  [{i+1}/{min(len(references), max_refs)}] 访问: {url[:50]}...")
                
                # 在新标签页中打开参考链接
                page = await self.context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)  # 等待内容渲染
                
                # 提取页面正文
                content = await page.evaluate('''() => {
                    // 移除脚本、样式等无用元素
                    const removeElements = document.querySelectorAll('script, style, noscript, iframe, nav, header, footer, aside');
                    
                    // 尝试获取主要内容区域
                    const mainSelectors = [
                        'article',
                        '[class*="content"]',
                        '[class*="article"]',
                        '[class*="post"]',
                        'main',
                        '.main',
                        '#content',
                        '#main'
                    ];
                    
                    let content = '';
                    for (const sel of mainSelectors) {
                        const elem = document.querySelector(sel);
                        if (elem && elem.innerText.length > 200) {
                            content = elem.innerText;
                            break;
                        }
                    }
                    
                    // 如果没找到主要内容，使用body
                    if (!content || content.length < 200) {
                        content = document.body.innerText;
                    }
                    
                    // 清理空白字符
                    return content.replace(/\\s+/g, ' ').substring(0, 3000);
                }''')
                
                await page.close()
                
                if content and len(content) > 100:
                    ref["content"] = content
                    print(f"    ✓ 获取到 {len(content)} 字符")
                else:
                    ref["content"] = ""
                    print(f"    ⚠ 内容太少或获取失败")
                    
            except Exception as e:
                print(f"    ⚠ 获取失败: {e}")
                ref["content"] = ""
        
        return references

    async def parse_products_with_llm(self, content: str, references: list) -> list[ProductInfo]:
        """
        使用LLM智能解析内容中的产品信息
        
        Args:
            content: 主要内容文本
            references: 参考资料列表（可能包含content字段）
            
        Returns:
            产品信息列表
        """
        print("\n🤖 正在使用LLM解析内容...")
        
        # 获取配置文件路径
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
        
        # 创建LLM wrapper
        llm = create_random_llm_wrapper(config_path)
        if not llm:
            print("⚠ 无法创建LLM wrapper，将使用正则解析")
            return await self._parse_products_regex(content, references)
        
        # 准备引用来源信息，包含正文内容
        refs_text = ""
        if references:
            refs_parts = []
            for i, ref in enumerate(references[:10], 1):
                title = ref.get('title', '未知')
                url = ref.get('url', '')
                ref_content = ref.get('content', '')
                
                if ref_content:
                    # 包含正文内容的参考资料
                    refs_parts.append(f"""参考资料{i}:
标题: {title}
URL: {url}
正文摘要: {ref_content[:1500]}
---""")
                else:
                    refs_parts.append(f"参考资料{i}: {title} ({url})")
            
            refs_text = "\n".join(refs_parts)
        
        # 构建提示词
        system_prompt = """你是一个专业的内容解析助手。你需要从豆包AI的回答中提取产品/商家的排名列表，并从参考资料中匹配所有提到该商家的来源。

请严格按照以下JSON格式返回结果，不要添加任何其他文字：
{
    "products": [
        {
            "rank": 1,
            "name": "产品/商家名称",
            "features": "核心特点和优势的简要描述",
            "sources": [
                {"title": "来源标题1", "url": "来源URL1"},
                {"title": "来源标题2", "url": "来源URL2"}
            ]
        }
    ]
}

匹配规则：
1. rank是排名顺序，从1开始
2. name是产品或商家的名称，去掉emoji（🔰💎等）、序号（一、二、1.等）等前缀
3. features是产品的核心特点描述，简洁明了
4. 重要：sources是一个数组，包含所有提到该商家的参考资料
5. 仔细阅读每个参考资料的标题和正文摘要，只要正文中提到了该商家/产品名称，就添加到sources中
6. 一个商家可能被多个参考资料提到，全部添加到sources数组
7. 如果没有找到匹配的来源，sources为空数组[]
8. 只返回JSON，不要有其他任何文字"""

        user_prompt = f"""请从以下豆包AI的回答中提取产品/商家排名列表：

=== 回答内容 ===
{content[:6000]}

=== 参考资料详情 ===
{refs_text if refs_text else "无参考资料"}

任务：
1. 提取所有提到的产品/商家名称和排名
2. 仔细阅读每个参考资料的标题和正文，查找是否包含这些商家名称
3. 如果多个参考资料的正文中都提到了某个商家，将所有这些参考资料都添加到该商家的sources数组中
4. 返回JSON格式的结果"""

        try:
            response = await llm.call(user_prompt, system_prompt)
            await llm.close()
            
            # 解析JSON响应
            # 尝试提取JSON部分
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                
                products = []
                for item in result.get("products", []):
                    product = ProductInfo(
                        rank=item.get("rank", 0),
                        name=item.get("name", ""),
                        sources=[]
                    )
                    products.append(product)
                    print(f"  ✓ LLM解析: {item.get('rank')}. {item.get('name')}")
                
                self._match_references_to_products(products, references)
                
                print(f"📦 LLM共解析到 {len(products)} 个产品，并完成参考资料匹配")
                return products
            else:
                print(f"⚠ LLM响应格式错误: {response[:200]}")
                return await self._parse_products_regex(content, references)
                
        except Exception as e:
            print(f"⚠ LLM解析失败: {e}")
            await llm.close()
            return await self._parse_products_regex(content, references)
    
    async def _parse_products_regex(self, content: str, references: list) -> list[ProductInfo]:
        """
        使用正则表达式解析产品信息（备选方法）
        """
        products = []
        
        print(f"\n🔍 正在使用正则解析内容... (长度: {len(content)})")
        
        # 解析产品名称和排名
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 模式1：中文序号格式 "一、恒天奢侈品"
            match = re.match(r'^([一二三四五六七八九十]+)、\s*(.+?)(?:（|【|$)', line)
            if match:
                cn_rank = match.group(1)
                name = match.group(2).strip()
                rank = sum(self.CN_NUM_MAP.get(char, 0) for char in cn_rank)
                
                if name and len(name) < 100:
                    products.append(ProductInfo(rank=rank, name=name, sources=[]))
                    print(f"  ✓ 正则找到: {rank}. {name}")
                continue
            
            # 模式2：数字序号格式 "1. 产品名"
            match = re.match(r'^(\d+)[\.、）\)]\s*(.+)', line)
            if match:
                rank = int(match.group(1))
                name = re.sub(r'\[citation:\d+\]|【\d+】', '', match.group(2)).strip()
                
                if name and len(name) < 100:
                    products.append(ProductInfo(rank=rank, name=name, sources=[]))
                    print(f"  ✓ 正则找到: {rank}. {name}")
                continue
            
            # 模式3：emoji前缀格式 "🔰 恒天奢侈品"
            match = re.match(r'^[^\w\u4e00-\u9fff]*\s*(.+?)(?:（|\(|$)', line)
            if match:
                name = match.group(1).strip()
                # 过滤掉太短或太长的名称
                if name and 2 < len(name) < 50 and any(c in name for c in ['店', '品', '宝', '行', '家', '馆']):
                    rank = len(products) + 1
                    products.append(ProductInfo(rank=rank, name=name, sources=[]))
                    print(f"  ✓ 正则找到: {rank}. {name}")
        
        self._match_references_to_products(products, references)
        print(f"📦 正则共解析到 {len(products)} 个产品")
        return products
    
    async def parse_products(self, content: str, references: list, use_llm: Optional[bool] = None) -> list[ProductInfo]:
        """
        解析内容中的产品信息
        
        Args:
            content: 主要内容文本
            references: 参考资料列表
            use_llm: 是否使用LLM解析（默认True）
            
        Returns:
            产品信息列表
        """
        use_llm = self.use_llm if use_llm is None else use_llm
        
        if use_llm and content:
            return await self.parse_products_with_llm(content, references)
        else:
            return await self._parse_products_regex(content, references)
    
    async def crawl(self, url: str, keyword: str = "") -> CrawlResult:
        """
        爬取豆包页面
        
        Args:
            url: 豆包聊天页面URL
            keyword: 关键词（如果为空，将尝试从页面提取）
            
        Returns:
            爬取结果
        """
        await self.navigate_to_chat(url)
        
        table_products = await self.extract_rank_table()
        
        # 提取内容
        content_data = await self.extract_content()
        
        # 如果没有提供关键词，尝试从URL或页面提取
        if not keyword:
            # 尝试从页面标题或输入框提取
            title = await self.page.title()
            keyword = title.replace("豆包", "").replace("-", "").strip()
        
        # 1. 第一轮解析：使用现有参考资料（仅标题/URL）
        references = content_data["references"]
        
        fetched_refs = False
        
        if table_products:
            products = table_products
            print("✅ 已通过表格完成结构化提取，跳过LLM解析")
            self._match_references_to_products(products, references)
        else:
            products = await self.parse_products(
                content_data["main_content"], 
                references,
                use_llm=self.use_llm
            )
            
        products_without_source = [p for p in products if not p.sources]
        if products_without_source and references:
            print(f"\n⚡ 发现 {len(products_without_source)} 个产品缺少来源，尝试使用参考资料正文匹配...")
            references = await self.fetch_reference_contents(references, max_refs=5)
            fetched_refs = True
            self._match_references_to_products(products, references)
            products_without_source = [p for p in products if not p.sources]
            if products_without_source:
                for p in products_without_source:
                    print(f"  ⚠ 仍未为 {p.name} 找到引用，保留为空")
        
        if fetched_refs:
            content_data["references"] = references
        
        return CrawlResult(
            keyword=keyword,
            crawl_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            products=products,
            raw_content=content_data["main_content"],
            references=content_data["references"]
        )


def generate_html_report(results: list[CrawlResult], output_path: str):
    """
    生成HTML格式的报告
    
    Args:
        results: 爬取结果列表
        output_path: 输出文件路径
    """
    html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>豆包爬取结果报告</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            color: white;
            text-align: center;
            margin-bottom: 30px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        .result-card {
            background: white;
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15);
        }
        .keyword-header {
            background: linear-gradient(90deg, #4CAF50, #45a049);
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 18px;
            font-weight: bold;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }
        th {
            background: linear-gradient(90deg, #4CAF50, #45a049);
            color: white;
            padding: 14px 16px;
            text-align: left;
            font-weight: 600;
        }
        th:first-child {
            border-radius: 8px 0 0 0;
            width: 80px;
        }
        th:last-child {
            border-radius: 0 8px 0 0;
        }
        td {
            padding: 14px 16px;
            border-bottom: 1px solid #eee;
        }
        tr:nth-child(even) {
            background-color: #f8f9fa;
        }
        tr:hover {
            background-color: #e8f5e9;
        }
        .rank-cell {
            font-weight: bold;
            color: #4CAF50;
            font-size: 18px;
        }
        .product-name {
            color: #1976D2;
            font-weight: 500;
        }
        .source-link {
            color: #666;
        }
        .source-link a {
            color: #1976D2;
            text-decoration: none;
        }
        .source-link a:hover {
            text-decoration: underline;
        }
        .meta-info {
            color: #888;
            font-size: 14px;
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid #eee;
        }
        .no-data {
            text-align: center;
            color: #999;
            padding: 40px;
            font-style: italic;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 豆包爬取结果报告</h1>
        {content}
    </div>
</body>
</html>
"""
    
    content_html = ""
    
    for result in results:
        card_html = f"""
        <div class="result-card">
            <div class="keyword-header">关键词：{result.keyword}</div>
            <table>
                <thead>
                    <tr>
                        <th>排名</th>
                        <th>产品/平台</th>
                        <th>引用来源</th>
                    </tr>
                </thead>
                <tbody>
"""
        
        if result.products:
            for product in result.products:
                # 处理多个来源
                source_display = "-"
                if hasattr(product, 'sources') and product.sources:
                    links = []
                    for src in product.sources:
                        if isinstance(src, dict):
                            title = src.get('title', '未知来源')
                            url = src.get('url', '')
                            if url:
                                links.append(f'<div style="margin-bottom: 5px;"><a href="{url}" target="_blank">{title}</a></div>')
                            else:
                                links.append(f'<div>{title}</div>')
                    if links:
                        source_display = "".join(links)
                # 兼容旧字段
                elif hasattr(product, 'source') and product.source and product.source_url:
                     source_display = f'<a href="{product.source_url}" target="_blank">{product.source} ({product.source_url})</a>'
                elif hasattr(product, 'source') and product.source:
                     source_display = product.source
                    
                card_html += f"""
                    <tr>
                        <td class="rank-cell">{product.rank}</td>
                        <td class="product-name">{product.name}</td>
                        <td class="source-link">{source_display}</td>
                    </tr>
"""
        else:
            card_html += """
                    <tr>
                        <td colspan="3" class="no-data">暂无产品数据</td>
                    </tr>
"""
            
        card_html += f"""
                </tbody>
            </table>
            <div class="meta-info">
                爬取时间：{result.crawl_time} | 
                参考资料数量：{len(result.references)}
            </div>
        </div>
"""
        content_html += card_html
        
    html_content = html_template.replace("{content}", content_html)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"报告已生成：{output_path}")


def save_json_result(results: list[CrawlResult], output_path: str):
    """保存JSON格式的结果"""
    data = []
    for result in results:
        data.append({
            "keyword": result.keyword,
            "crawl_time": result.crawl_time,
            "products": [asdict(p) for p in result.products],
            "references": result.references
        })
        
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"JSON结果已保存：{output_path}")


async def main():
    """主函数示例"""
    # 示例URL（需要替换为实际的豆包聊天页面URL）
    test_url = "https://doubao.com/chat/3841056122567454"
    keyword = "二手奢侈品上门回收"
    
    crawler = DoubaoCrawler(headless=False)
    
    try:
        await crawler.start()
        
        # 爬取页面
        result = await crawler.crawl(test_url, keyword)
        
        # 保存结果
        results = [result]
        
        # 生成HTML报告
        output_dir = os.path.dirname(os.path.abspath(__file__))
        generate_html_report(results, os.path.join(output_dir, "report.html"))
        
        # 保存JSON结果
        save_json_result(results, os.path.join(output_dir, "results.json"))
        
        # 打印结果摘要
        print(f"\n{'='*50}")
        print(f"关键词: {result.keyword}")
        print(f"爬取时间: {result.crawl_time}")
        print(f"产品数量: {len(result.products)}")
        print(f"参考资料数量: {len(result.references)}")
        print(f"{'='*50}")
        
        for product in result.products:
            print(f"{product.rank}. {product.name} - {product.source}")
            
    finally:
        await crawler.close()


if __name__ == "__main__":
    asyncio.run(main())
