"""Playwright-based Doubao crawler provider.

This provider reuses the main JobManager/Analyzer pipeline but fulfils crawling by
automating the public Doubao web client with Playwright. It opens the chat page
with the configured cookies, asks questions for each keyword, captures the AI
answer plus Doubao's own reference list, then leverages an internal LLM to
convert the response into structured rankings that downstream analytics already
understand.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from llm.config_loader import create_random_llm_wrapper
from ...core.types import CallParams, CallResult

logger = logging.getLogger(__name__)

# City → geolocation mapping for virtual location spoofing
CITY_LOCATIONS: dict[str, dict] = {
    "上海": {"latitude": 31.2304, "longitude": 121.4737, "timezone_id": "Asia/Shanghai"},
    "北京": {"latitude": 39.9042, "longitude": 116.4074, "timezone_id": "Asia/Shanghai"},
    "广州": {"latitude": 23.1291, "longitude": 113.2644, "timezone_id": "Asia/Shanghai"},
    "深圳": {"latitude": 22.5431, "longitude": 114.0579, "timezone_id": "Asia/Shanghai"},
    "杭州": {"latitude": 30.2741, "longitude": 120.1551, "timezone_id": "Asia/Shanghai"},
    "成都": {"latitude": 30.5728, "longitude": 104.0668, "timezone_id": "Asia/Shanghai"},
    "武汉": {"latitude": 30.5928, "longitude": 114.3055, "timezone_id": "Asia/Shanghai"},
    "南京": {"latitude": 32.0603, "longitude": 118.7969, "timezone_id": "Asia/Shanghai"},
    "重庆": {"latitude": 29.4316, "longitude": 106.9123, "timezone_id": "Asia/Shanghai"},
    "西安": {"latitude": 34.3416, "longitude": 108.9398, "timezone_id": "Asia/Shanghai"},
    "苏州": {"latitude": 31.2990, "longitude": 120.5853, "timezone_id": "Asia/Shanghai"},
    "天津": {"latitude": 39.3434, "longitude": 117.3616, "timezone_id": "Asia/Shanghai"},
}


DEFAULT_QUESTION_TEMPLATE = (
    "你是资深市场调研顾问。请围绕关键词\u201c{keyword}\u201d分析目标品牌\u201c{target_brand}\u201d及其核心竞品，"
    "给出可信度/口碑/服务能力的综合排名，至少列出5个品牌。"
    "在回答里需要：\n"
    "1. 明确标出每个品牌的排名数字（1、2、3…）；\n"
    "2. 针对排名给出一句话理由或核心优势；\n"
    "3. 引用豆包自动匹配的参考资料；\n"
    "4. 如果目标品牌未出现在该场景，请说明原因。"
)


RANKING_SYSTEM_PROMPT = """你是一个擅长解析排名内容的助手。用户会给你豆包AI的完整回答文本，
以及该回答附带的参考资料列表。请将回答中出现的品牌或平台按原始顺序转换成JSON结构。

JSON格式：
{
  "products": [
    {
      "rank": 1,
      "name": "品牌名称",
      "summary": "一句话概述",
      "is_target": true/false
    }
  ]
}

要求：
1. rank 为正整数，从 1 开始递增或保持原始顺序。
2. name 为品牌或平台名称，去掉多余的空格、emoji、序号。
3. summary 是对该品牌的关键信息或优势的简短说明。
4. 如果发现目标品牌（由用户输入），请将 is_target 设为 true，否则为 false。
5. 不要杜撰排名，如果文本没有出现排名条目，则返回空数组。
6. 只输出 JSON，不要包含任何额外文字。
"""


@dataclass(slots=True)
class DoubaoConfig:
    """Lightweight config container for the Playwright crawler."""

    cookies: str
    chat_url: str
    headless: bool
    reference_pages: int
    question_template: str
    viewport_width: int = 1440
    viewport_height: int = 900
    geolocation: dict | None = None
    timezone_id: str | None = None


class Doubao:
    """Main provider entry – conforms to provider.core.types.CallResult contract."""

    def __init__(self, config_path: str = "config.json", location: str | None = None):
        self.config_path = str(config_path)
        config = self._load_provider_config(config_path)
        # Apply virtual location if specified
        if location and location in CITY_LOCATIONS:
            loc = CITY_LOCATIONS[location]
            config.geolocation = {"latitude": loc["latitude"], "longitude": loc["longitude"]}
            config.timezone_id = loc["timezone_id"]
            logger.info("Virtual location set to %s (%.4f, %.4f)", location, loc["latitude"], loc["longitude"])
        self.config = config
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._session_initialized = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def call(self, params: CallParams) -> CallResult:
        """Execute one keyword query through the Doubao web UI (A→F flow)."""
        keyword = (params.messages or "").strip()
        if not keyword:
            raise ValueError("Keyword prompt cannot be empty")

        target_brand = (params.extra.get("target_brand") or "").strip()
        question = keyword
        logger.info("Doubao query: keyword=%s target=%s", keyword, target_brand)

        page = await self._ensure_session()

        # Step A: New conversation (reset context)
        await self._start_new_conversation(page)

        # Step B: Send question and wait for completion
        await self._send_question(page, question)
        await self._wait_for_response_v2(page)

        # Step C: Extract answer text
        answer_text = await self._extract_latest_answer(page)
        if not answer_text:
            logger.warning("Empty answer from Doubao for keyword=%s", keyword)

        # Step D: Click reference button and extract links from sidebar
        references: list[dict] = []
        ref_clicked = await self._click_reference_button(page)
        if ref_clicked:
            references = await self._extract_sidebar_references(page)
            await self._close_reference_sidebar(page)

        # Fallback 1: extract links from answer area DOM
        if not references:
            references = await self._extract_answer_area_links(page)

        # Fallback 2: extract URLs directly from answer text
        if not references and answer_text:
            references = self._extract_references_from_text(answer_text)

        # Step E: Deep verification
        if references and target_brand:
            references = await self._deep_verify_references(references, target_brand)

        # Step F: LLM ranking extraction + source attachment + return
        rankings = await self._extract_rankings_with_llm(
            keyword=keyword,
            target_brand=target_brand,
            content=answer_text,
            references=references,
        )
        self._attach_sources(rankings, references)

        return CallResult(
            raw_response={
                "keyword": keyword,
                "question": question,
                "answer_length": len(answer_text),
            },
            content=answer_text,
            reasoning=None,
            sources=[
                {
                    "title": ref.get("title", ""),
                    "url": ref.get("url", ""),
                    "snippet": ref.get("summary", ""),
                    "site_name": ref.get("site_name", ""),
                    "index": ref.get("index"),
                    "verified": ref.get("verified"),
                    "brand_mentioned": ref.get("brand_mentioned"),
                }
                for ref in references
            ],
            rankings=rankings,
            metadata={
                "keyword": keyword,
                "target_brand": target_brand,
                "provider": "doubao_playwright",
            },
        )

    # ------------------------------------------------------------------ #
    # Initialization helpers
    # ------------------------------------------------------------------ #
    def _load_provider_config(self, config_path: str | Path) -> DoubaoConfig:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")

        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        provider_config = config.get("providers", {}).get("doubao") or {}
        accounts = provider_config.get("accounts") or []
        account = accounts[0] if accounts else {}
        cookies = (account.get("cookies") or "").strip()

        if not cookies:
            raise ValueError("豆包配置缺少 cookies，请在设置页面粘贴浏览器 Cookie。")

        chat_url = provider_config.get("chat_url") or "https://www.doubao.com/chat/"
        headless = bool(provider_config.get("headless", False))
        reference_pages = int(provider_config.get("reference_pages", 5))
        template = provider_config.get("question_template") or DEFAULT_QUESTION_TEMPLATE

        return DoubaoConfig(
            cookies=cookies,
            chat_url=chat_url,
            headless=headless,
            reference_pages=max(1, reference_pages),
            question_template=template,
        )

    async def _create_context(self, browser: Browser) -> BrowserContext:
        ctx_kwargs: dict[str, Any] = {
            "locale": "zh-CN",
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
        }
        if self.config.geolocation:
            ctx_kwargs["geolocation"] = self.config.geolocation
            ctx_kwargs["permissions"] = ["geolocation"]
        if self.config.timezone_id:
            ctx_kwargs["timezone_id"] = self.config.timezone_id

        context = await browser.new_context(**ctx_kwargs)
        cookies = self._parse_cookies(self.config.cookies)
        if cookies:
            await context.add_cookies(cookies)
        return context

    async def _ensure_session(self) -> Page:
        if self._page and not self._page.is_closed():
            return self._page

        if not self._playwright:
            self._playwright = await async_playwright().start()

        if not self._browser:
            self._browser = await self._playwright.chromium.launch(headless=self.config.headless)

        if not self._context:
            self._context = await self._create_context(self._browser)

        self._page = await self._context.new_page()
        await self._page.goto(self.config.chat_url, wait_until="domcontentloaded", timeout=60000)
        await self._dismiss_modals(self._page)
        self._session_initialized = True
        return self._page

    # ------------------------------------------------------------------ #
    # Browser automation helpers
    # ------------------------------------------------------------------ #
    async def _dismiss_modals(self, page: Page) -> None:
        """Attempt to close any announcement or intro modals."""
        close_selectors = [
            'button:has-text("我知道了")',
            'button:has-text("关闭")',
            '[class*="close"]',
        ]
        for selector in close_selectors:
            try:
                btn = await page.query_selector(selector)
                if btn:
                    await btn.click()
                    await asyncio.sleep(0.3)
            except Exception:
                continue

    # Step A: New conversation
    async def _start_new_conversation(self, page: Page) -> None:
        """Click '新对话' to reset conversation context."""
        # Strategy 1: Playwright text locator
        try:
            new_chat_btn = page.locator('text=新对话').first
            await new_chat_btn.wait_for(state="visible", timeout=3000)
            await new_chat_btn.click()
            await asyncio.sleep(0.8)
            await self._wait_for_chat_clear(page, timeout=3)
            logger.info("New conversation started via text locator")
            return
        except Exception:
            pass

        # Strategy 2: JavaScript fallback
        try:
            clicked = await page.evaluate("""() => {
                const targets = ["新对话", "开启新对话", "New chat"];
                const elements = document.querySelectorAll('button, a, div, span');
                for (const text of targets) {
                    for (const el of elements) {
                        if ((el.innerText || '').trim().startsWith(text)) {
                            el.click();
                            return true;
                        }
                    }
                }
                return false;
            }""")
            if clicked:
                await asyncio.sleep(0.8)
                await self._wait_for_chat_clear(page, timeout=3)
                logger.info("New conversation started via JS fallback")
                return
        except Exception:
            pass

        logger.warning("Could not click '新对话' button, proceeding anyway")

    async def _wait_for_chat_clear(self, page: Page, timeout: int = 3) -> None:
        """Wait for the chat area to clear after clicking '新对话'."""
        for _ in range(timeout):
            has_content = await page.evaluate("""() => {
                const msgs = document.querySelectorAll(
                    '[class*="assistant"], [class*="markdown"], [data-role="assistant"]'
                );
                return msgs.length > 0;
            }""")
            if not has_content:
                return
            await asyncio.sleep(0.3)

    # Step B: Send question
    async def _send_question(self, page: Page, question: str) -> None:
        """Type question into the input box and click send."""
        input_selector = 'textarea, div[contenteditable="true"]'
        editor = await page.wait_for_selector(input_selector, timeout=20000)
        if not editor:
            raise RuntimeError("未找到豆包输入框")

        await editor.click()
        # Clear existing content
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.2)

        # Type character by character to mimic human input
        await page.keyboard.type(question, delay=50)

        await asyncio.sleep(0.3)

        send_button = await page.query_selector(
            'button[type="submit"], button:has-text("发送"), button:has-text("Send")'
        )
        if send_button:
            await send_button.click()
        else:
            await page.keyboard.press("Enter")

        # Allow UI to transition to generating state
        await asyncio.sleep(1)

    # Step B (part 2): Wait for response
    async def _wait_for_response_v2(self, page: Page, timeout: int = 180) -> None:
        """Wait for Doubao to finish generating.

        Detection strategy:
        1. Wait for generation to START: detect "停止生成" button appearing
        2. Wait for generation to END: detect "停止生成" disappearing OR
           "参考 N 篇资料" button appearing at the bottom
        3. Fallback: text length stabilization (3 consecutive stable checks)
        """
        # Phase 1: Wait for generation to start (up to 15s, poll every 0.5s)
        generation_started = False
        for _ in range(30):
            stop_btn = await page.evaluate("""() => {
                const elements = document.querySelectorAll('button, div, span');
                for (const el of elements) {
                    const text = (el.innerText || '').trim();
                    if (text === '停止生成' || text === 'Stop generating') {
                        return true;
                    }
                }
                return false;
            }""")
            if stop_btn:
                generation_started = True
                logger.info("Generation started (detected '停止生成' button)")
                break
            await asyncio.sleep(0.3)

        if not generation_started:
            logger.warning("'停止生成' button not detected within 15s, using fallback")

        # Phase 2: Wait for generation to complete (poll every 0.8s)
        prev_length = 0
        stable_ticks = 0
        REQUIRED_STABLE = 3

        for tick in range(timeout):
            await asyncio.sleep(0.8)

            # Combined check: stop button + reference button in one evaluate
            status = await page.evaluate(r"""() => {
                const elements = document.querySelectorAll('button, div, span');
                let stopVisible = false;
                let refVisible = false;
                for (const el of elements) {
                    const text = (el.innerText || '').trim();
                    if (text === '停止生成' || text === 'Stop generating') {
                        stopVisible = true;
                    }
                    if (/参考\s*\d+\s*篇资料/.test(text)) {
                        refVisible = true;
                    }
                }
                return { stopVisible, refVisible };
            }""")

            if status["refVisible"]:
                logger.info("Response complete (detected '参考 N 篇资料' at tick %d)", tick)
                return

            if generation_started and not status["stopVisible"]:
                logger.info("Response complete ('停止生成' disappeared at tick %d)", tick)
                await asyncio.sleep(0.3)
                return

            # Fallback: text stabilization
            if not status["stopVisible"]:
                latest = await self._extract_latest_answer(page)
                cur_length = len(latest) if latest else 0
                if cur_length > 20 and cur_length == prev_length:
                    stable_ticks += 1
                    if stable_ticks >= REQUIRED_STABLE:
                        logger.info("Response stabilized at %d chars (fallback)", cur_length)
                        return
                else:
                    stable_ticks = 0
                prev_length = cur_length
            else:
                stable_ticks = 0

        logger.warning("Response wait timed out after %d seconds", timeout)

    # Step C: Extract answer text
    async def _extract_latest_answer(self, page: Page) -> str:
        """Extract the latest assistant answer's innerText."""
        script = """() => {
            // Strategy 1: markdown/prose blocks excluding user messages
            const allBlocks = Array.from(document.querySelectorAll(
                '[class*="markdown"], [class*="prose"], [class*="message-content"]'
            ));
            const assistantBlocks = allBlocks.filter(el => {
                const userParent = el.closest('[class*="user"], [data-role="user"]');
                return !userParent;
            });
            if (assistantBlocks.length > 0) {
                const last = assistantBlocks[assistantBlocks.length - 1];
                const text = last.innerText.trim();
                if (text.length > 20) return text;
            }

            // Strategy 2: data-role="assistant"
            const byRole = document.querySelectorAll('[data-role="assistant"]');
            if (byRole.length > 0) {
                const last = byRole[byRole.length - 1];
                const text = last.innerText.trim();
                if (text.length > 20) return text;
            }

            // Strategy 3: broadest fallback
            const byClass = Array.from(document.querySelectorAll('[class*="assistant"]'))
                .map(n => n.innerText.trim())
                .filter(t => t.length > 40);
            if (byClass.length > 0) return byClass[byClass.length - 1];

            return '';
        }"""
        try:
            text = await page.evaluate(script)
            return text or ""
        except Exception as exc:
            logger.warning("Failed to extract answer: %s", exc)
            return ""

    # Step D: Click reference button and extract links
    async def _click_reference_button(self, page: Page) -> bool:
        """Click the '参考 N 篇资料' button at the bottom of the answer.

        Returns True if the button was found and clicked.
        """
        # Primary: Playwright locator with regex text matching
        try:
            ref_btn = page.locator(r'text=/参考\s*\d+\s*篇资料/').first
            await ref_btn.wait_for(state="visible", timeout=3000)
            await ref_btn.click()
            logger.info("Clicked reference button via regex locator")
            await asyncio.sleep(1)
            return True
        except Exception:
            pass

        # Fallback: JavaScript search
        try:
            clicked = await page.evaluate(r"""() => {
                const elements = document.querySelectorAll('button, span, div, a');
                for (const el of elements) {
                    const text = (el.innerText || '').trim();
                    if (/参考\s*\d+\s*篇资料/.test(text) && text.length < 30) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            if clicked:
                logger.info("Clicked reference button via JS fallback")
                await asyncio.sleep(1)
                return True
        except Exception:
            pass

        logger.warning("Could not find '参考 N 篇资料' button")
        return False

    async def _extract_sidebar_references(self, page: Page) -> list[dict]:
        """Extract all reference links from the expanded sidebar."""
        # Wait for sidebar/drawer to appear
        sidebar_appeared = False
        for _ in range(10):
            has_sidebar = await page.evaluate("""() => {
                const candidates = document.querySelectorAll(
                    '[class*="drawer"], [class*="sidebar"], [class*="panel"], ' +
                    '[class*="modal"], [class*="reference"], [class*="citation"]'
                );
                for (const el of candidates) {
                    const links = el.querySelectorAll('a[href^="http"]');
                    const rect = el.getBoundingClientRect();
                    if (links.length >= 1 && rect.width > 100 && rect.height > 100) {
                        return true;
                    }
                }
                return false;
            }""")
            if has_sidebar:
                sidebar_appeared = True
                break
            await asyncio.sleep(0.3)

        if not sidebar_appeared:
            logger.warning("Reference sidebar did not appear within 5 seconds")
            return []

        # Extract all links from the sidebar
        references = await page.evaluate("""() => {
            const containerSelectors = [
                '[class*="drawer"]', '[class*="sidebar"]', '[class*="panel"]',
                '[class*="modal"]', '[class*="reference"]', '[class*="citation"]'
            ];

            let sidebar = null;
            for (const sel of containerSelectors) {
                const candidates = document.querySelectorAll(sel);
                for (const el of candidates) {
                    const links = el.querySelectorAll('a[href^="http"]');
                    const rect = el.getBoundingClientRect();
                    if (links.length >= 1 && rect.width > 100 && rect.height > 100) {
                        if (!sidebar || el.innerHTML.length < sidebar.innerHTML.length) {
                            sidebar = el;
                        }
                    }
                }
            }

            if (!sidebar) return [];

            const seen = new Set();
            const results = [];
            const links = sidebar.querySelectorAll('a[href^="http"]');

            for (const link of links) {
                const href = (link.href || '').trim();
                if (!href || href.includes('doubao.com') || href.includes('bytedance.com')) continue;
                if (seen.has(href)) continue;
                seen.add(href);

                const card = link.closest('li, article, [class*="item"], [class*="card"]') || link;
                const titleNode = card.querySelector('[class*="title"], h3, h4, h5, strong') || link;
                const summaryNode = card.querySelector('[class*="summary"], [class*="desc"], [class*="snippet"], p');

                results.push({
                    title: (titleNode.innerText || '').trim(),
                    url: href,
                    summary: summaryNode ? (summaryNode.innerText || '').trim() : '',
                    index: results.length + 1
                });
            }

            return results;
        }""")

        if not references:
            logger.warning("No references extracted from sidebar")
            return []

        for ref in references:
            ref["site_name"] = self._extract_source_name(ref.get("url", ""))

        logger.info("Extracted %d references from sidebar", len(references))
        return references

    async def _close_reference_sidebar(self, page: Page) -> None:
        """Close the reference sidebar."""
        try:
            closed = await page.evaluate("""() => {
                const closeSelectors = [
                    '[class*="drawer"] [class*="close"]',
                    '[class*="sidebar"] [class*="close"]',
                    '[class*="panel"] [class*="close"]',
                    '[class*="drawer"] button',
                    '[class*="modal"] [class*="close"]',
                ];
                for (const sel of closeSelectors) {
                    const btn = document.querySelector(sel);
                    if (btn) {
                        const text = (btn.innerText || '').trim();
                        const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                        if (text.length < 10 || ariaLabel.includes('close') || ariaLabel.includes('关闭')) {
                            btn.click();
                            return true;
                        }
                    }
                }
                return false;
            }""")
            if closed:
                await asyncio.sleep(0.3)
            else:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
        except Exception:
            logger.debug("Could not close reference sidebar, continuing")

    async def _extract_answer_area_links(self, page: Page) -> list[dict]:
        """Extract <a> links from the assistant answer and search result areas."""
        try:
            references = await page.evaluate("""() => {
                const seen = new Set();
                const results = [];

                // Strategy 1: Doubao search result cards (a.search-*)
                const searchLinks = document.querySelectorAll('a[class*="search-"]');
                for (const link of searchLinks) {
                    const href = (link.href || '').trim();
                    if (!href || !href.startsWith('http')) continue;
                    if (href.includes('doubao.com') || href.includes('bytedance.com')) continue;
                    if (seen.has(href)) continue;
                    seen.add(href);

                    const titleEl = link.querySelector('[class*="title"]');
                    const summaryEl = link.querySelector('[class*="summary"]');
                    results.push({
                        title: titleEl ? titleEl.innerText.trim() : (link.innerText || '').trim().substring(0, 100),
                        url: href,
                        summary: summaryEl ? summaryEl.innerText.trim() : '',
                        index: results.length + 1
                    });
                }

                // Strategy 2: any <a> in assistant answer blocks
                const allBlocks = Array.from(document.querySelectorAll(
                    '[class*="markdown"], [class*="prose"], [class*="message-content"]'
                ));
                const assistantBlocks = allBlocks.filter(el => {
                    const userParent = el.closest('[class*="user"], [data-role="user"]');
                    return !userParent;
                });
                if (assistantBlocks.length > 0) {
                    const lastBlock = assistantBlocks[assistantBlocks.length - 1];
                    const links = lastBlock.querySelectorAll('a[href^="http"]');
                    for (const link of links) {
                        const href = (link.href || '').trim();
                        if (!href || href.includes('doubao.com') || href.includes('bytedance.com')) continue;
                        if (seen.has(href)) continue;
                        seen.add(href);
                        results.push({
                            title: (link.innerText || '').trim() || href,
                            url: href,
                            summary: '',
                            index: results.length + 1
                        });
                    }
                }

                return results;
            }""")

            if references:
                for ref in references:
                    ref["site_name"] = self._extract_source_name(ref.get("url", ""))
                logger.info("Extracted %d references from answer area links", len(references))
            return references or []
        except Exception as exc:
            logger.warning("Failed to extract answer area links: %s", exc)
            return []

    # Step E: Deep verification
    async def _deep_verify_references(
        self, references: list[dict], target_brand: str
    ) -> list[dict]:
        """Open each reference URL in a new tab and check for target_brand mention."""
        if not target_brand or not self._context:
            return references

        logger.info("Deep verifying %d references for brand '%s'", len(references), target_brand)

        for ref in references:
            url = ref.get("url", "")
            if not url:
                ref["verified"] = False
                ref["brand_mentioned"] = False
                continue

            mentioned = await self._verify_single_url(url, target_brand)
            ref["verified"] = True
            ref["brand_mentioned"] = mentioned
            if mentioned:
                logger.info("  Brand found in: %s", url[:80])

        return references

    async def _verify_single_url(self, url: str, target_brand: str) -> bool:
        """Open a URL in a new tab and check if the page mentions target_brand."""
        if not self._context:
            return False

        try:
            verify_page = await self._context.new_page()
            try:
                # Wait for network idle so JS-rendered content is loaded
                await verify_page.goto(url, wait_until="networkidle", timeout=15000)
                # Extra wait for late JS rendering
                await asyncio.sleep(0.3)

                content = await verify_page.evaluate("""() => {
                    const mainSelectors = ['article', '[class*="content"]', 'main', '#content'];
                    for (const sel of mainSelectors) {
                        const elem = document.querySelector(sel);
                        if (elem && elem.innerText.length > 100) {
                            return elem.innerText.substring(0, 5000);
                        }
                    }
                    return (document.body.innerText || '').substring(0, 5000);
                }""")

                return target_brand in (content or "")
            finally:
                await verify_page.close()
        except Exception as exc:
            logger.debug("Failed to verify URL %s: %s", url[:60], exc)
            return False

    # ------------------------------------------------------------------ #
    # Ranking + source parsing helpers
    # ------------------------------------------------------------------ #
    async def _extract_rankings_with_llm(
        self,
        keyword: str,
        target_brand: str,
        content: str,
        references: list[dict],
    ) -> list[dict]:
        if not content:
            logger.warning("No content returned from Doubao for keyword=%s", keyword)
            return []

        llm_wrapper = create_random_llm_wrapper(self.config_path)
        if not llm_wrapper:
            logger.error("LLM wrapper not configured; skip ranking extraction")
            return []

        refs_context = []
        for idx, ref in enumerate(references[:8], start=1):
            refs_context.append(
                f"[{idx}] {ref.get('title', '')}\nURL: {ref.get('url', '')}\n总结: {ref.get('summary', '')[:200]}"
            )

        prompt = (
            f"关键词：{keyword}\n"
            f"目标品牌：{target_brand or '未指定'}\n"
            f"豆包回答：\n{content[:6000]}\n\n"
            f"参考资料：\n{chr(10).join(refs_context) if refs_context else '无'}"
        )

        try:
            response = await llm_wrapper.call(prompt, system_prompt=RANKING_SYSTEM_PROMPT)
        finally:
            try:
                await llm_wrapper.close()
            except Exception:
                pass

        data = self._parse_llm_json(response)
        products = data.get("products") if isinstance(data, dict) else data
        if not isinstance(products, list):
            logger.warning("LLM ranking response malformed for keyword=%s", keyword)
            return []

        rankings: list[dict] = []
        for item in products:
            name = (item.get("name") or "").strip()
            if not name:
                continue
            rank = self._safe_int(item.get("rank"))
            if rank <= 0:
                continue

            rankings.append(
                {
                    "rank": rank,
                    "name": name,
                    "summary": (item.get("summary") or item.get("features") or "").strip(),
                    "is_target": bool(item.get("is_target")),
                    "sources": [],
                }
            )

        rankings.sort(key=lambda r: r["rank"])
        return rankings

    def _attach_sources(self, rankings: list[dict], references: list[dict]) -> None:
        if not rankings or not references:
            return

        normalized_refs = []
        for ref in references:
            normalized_refs.append(
                {
                    "title": ref.get("title", ""),
                    "url": ref.get("url", ""),
                    "summary": ref.get("summary", ""),
                    "site_name": ref.get("site_name", ""),
                    "index": ref.get("index"),
                    "text": self._normalize_text(
                        " ".join(
                            filter(
                                None,
                                [
                                    ref.get("title", ""),
                                    ref.get("summary", ""),
                                    ref.get("site_name", ""),
                                ],
                            )
                        )
                    ),
                }
            )

        for ranking in rankings:
            normalized_name = self._normalize_text(ranking.get("name"))
            if not normalized_name:
                continue
            attached = []
            for ref in normalized_refs:
                if normalized_name in ref["text"]:
                    attached.append(
                        {
                            "title": ref["title"],
                            "url": ref["url"],
                            "site_name": ref["site_name"],
                            "index": ref.get("index"),
                        }
                    )
            ranking["sources"] = sorted(attached, key=lambda item: item.get("index") or 0)

    # ------------------------------------------------------------------ #
    # Utility methods
    # ------------------------------------------------------------------ #
    def _build_question(self, keyword: str, target_brand: str, all_keywords: list[str]) -> str:
        placeholder_data = {
            "keyword": keyword,
            "target_brand": target_brand or "（未指定）",
            "all_keywords": "、".join(all_keywords) if all_keywords else keyword,
        }
        try:
            return self.config.question_template.format(**placeholder_data)
        except Exception:
            return DEFAULT_QUESTION_TEMPLATE.format(**placeholder_data)

    async def close(self):
        """Close browser resources."""
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
        except Exception:
            pass
        finally:
            self._page = None
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        finally:
            self._context = None
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        finally:
            self._browser = None
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        finally:
            self._playwright = None
            self._session_initialized = False

    def _parse_llm_json(self, response: str) -> Any:
        try:
            response = response.strip()
            if response.startswith("{") or response.startswith("["):
                return json.loads(response)
            match = re.search(r"(\{.*\})", response, re.S)
            if match:
                return json.loads(match.group(1))
        except Exception as exc:
            logger.warning("Failed to parse LLM JSON response: %s", exc)
        return {"products": []}

    def _parse_cookies(self, cookie_string: str) -> list[dict]:
        cookies = []
        for chunk in cookie_string.split(";"):
            if "=" not in chunk:
                continue
            name, value = chunk.split("=", 1)
            cookies.append(
                {
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".doubao.com",
                    "path": "/",
                }
            )
        return cookies

    def _extract_references_from_text(self, text: str) -> list[dict]:
        """Extract reference URLs directly from the answer text."""
        urls = re.findall(r'https?://[^\s;；，,、）)》\]]+', text)
        seen: set[str] = set()
        references: list[dict] = []
        for url in urls:
            url = url.rstrip('/')
            if url in seen:
                continue
            if 'doubao.com' in url or 'bytedance.com' in url:
                continue
            seen.add(url)
            references.append({
                "title": url.split('/')[-1][:60] or url,
                "url": url,
                "summary": "",
                "site_name": self._extract_source_name(url),
                "index": len(references) + 1,
            })
        logger.info("Extracted %d references from answer text (fallback)", len(references))
        return references

    def _extract_source_name(self, url: str) -> str:
        if not url:
            return "未知来源"
        mapping = {
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
            "wandoujia.com": "豌豆荚",
            "toutiao.com": "今日头条",
            "csdn.net": "CSDN",
        }
        for domain, name in mapping.items():
            if domain in url:
                return name
        domain_match = re.search(r"https?://([^/]+)/?", url)
        if domain_match:
            host = domain_match.group(1)
            return host.replace("www.", "")
        return "未知来源"

    def _normalize_text(self, text: str | None) -> str:
        if not text:
            return ""
        return re.sub(r"[\s·•，,。、\u201c\u201d\"'()（）【】\[\]《》<>—\-]", "", text).lower()

    def _safe_int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
