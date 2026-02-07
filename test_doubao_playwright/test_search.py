
import asyncio
import os
import sys
from doubao_crawler import DoubaoCrawler

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_search():
    crawler = DoubaoCrawler(headless=False, cookies="")  # 提供空cookie即可由于不需要登录豆包
    await crawler.start()
    
    print("测试在线搜索功能...")
    # 保存截图以便调试
    crawler.page = await crawler.context.new_page()
    try:
        results = await crawler.search_online_for_product("妃鱼・高奢之家", "二手奢侈品上门回收")
    except Exception as e:
        print(f"Error: {e}")
        results = []
    
    # 手动截图
    # await crawler.page.screenshot(path="debug_search.png")
    
    print(f"\n搜索结果 ({len(results)}个):")
    for res in results:
        print(f"- {res['title']}")
        print(f"  Url: {res['url']}")
        print(f"  Source: {res['source']}")
        
    await crawler.close()

if __name__ == "__main__":
    asyncio.run(test_search())
