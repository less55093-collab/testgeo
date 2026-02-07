"""
豆包爬虫测试运行脚本
用于测试爬取豆包页面并提取产品排名信息
"""

import asyncio
import os
from doubao_crawler import DoubaoCrawler, CrawlResult, ProductInfo, generate_html_report, save_json_result


# 测试配置
TEST_CONFIG = {
    # 豆包聊天页面URL（需要替换为实际URL）
    "url": "https://www.doubao.com/chat/38410450003441410",
    
    # 搜索关键词
    "keyword": "二手奢侈品上门回收",
    
    # 是否使用无头模式
    "headless": False,
    
    # 登录Cookie（从浏览器复制）
    "cookies": "i18next=zh; ttcid=fc0ad34415d44e90aadab2c3ea89f11d12; s_v_web_id=verify_ml98lplo_GKNuBTpY_7lWD_41hf_A2bG_N73AorIIxZ23; passport_csrf_token=efaf11b84a596a539ecd2c01ef848aee; passport_csrf_token_default=efaf11b84a596a539ecd2c01ef848aee; msToken=o_Ghk25bbso1QSl00AhLEsPm-Ohqxcf30G7Ggfa22BWhBXAvPOCPr4etD6SSoYjsLSserNPSQXkny4F4otd2NdTqRWrkfDqJOX7WJjob-gW1F0-6mEx-plVQroIV0SHQ5t4=; tt_scid=tA-cAjyURCB7hH988csLTfcFhIxScHJtgAZt9ATh8m.sAOyfmchtlqfGCFIxNapR0b94; odin_tt=6b928476d72e814433b57e54321cc0c3f84e3dda5ac5107bad469244168fcf62b245c20b67b3053cb3c0f66ec3dbb3907903d437170ddcd1c69e69aeb9c6813d; n_mh=psgKgwLb3DxNPyFVxbNiHWwcACBkFKsTUQH9tCCkg7A; sid_guard=b72e44d602ce18208d5e0248fea27507%7C1770294878%7C2592000%7CSat%2C+07-Mar-2026+12%3A34%3A38+GMT; uid_tt=001fe8323cbec3c2ca609556bdb45f21; uid_tt_ss=001fe8323cbec3c2ca609556bdb45f21; sid_tt=b72e44d602ce18208d5e0248fea27507; sessionid=b72e44d602ce18208d5e0248fea27507; sessionid_ss=b72e44d602ce18208d5e0248fea27507; session_tlb_tag=sttt%7C2%7Cty5E1gLOGCCNXgJI_qJ1B__________WOJyvm6fEjMvULqNtZiOYl0THn8Yb6k2eH7TJCxa0Fls%3D; is_staff_user=false; sid_ucp_v1=1.0.0-KGE1NTE1MzlmMTBhYjA2OGM3YmRlYjM4MGJlYjJlY2Q3NDk4ZDUzNjkKHwi7gaCxm8wREN6ckswGGMKxHiAMMOnE7bAGOAdA9AcaAmxmIiBiNzJlNDRkNjAyY2UxODIwOGQ1ZTAyNDhmZWEyNzUwNw; ssid_ucp_v1=1.0.0-KGE1NTE1MzlmMTBhYjA2OGM3YmRlYjM4MGJlYjJlY2Q3NDk4ZDUzNjkKHwi7gaCxm8wREN6ckswGGMKxHiAMMOnE7bAGOAdA9AcaAmxmIiBiNzJlNDRkNjAyY2UxODIwOGQ1ZTAyNDhmZWEyNzUwNw; flow_ssr_sidebar_expand=1; ttwid=1%7CrW_-4EBXAk-CGyQUOzBulFv1pW6XNM2d8HpEAyt_9M8%7C1770428057%7C6c480d7cef872888df44120acdab1a4556ca0c38a8da146385e725347315b33d; passport_fe_beating_status=true",
}


async def run_test():
    """运行爬虫测试"""
    print("=" * 60)
    print("豆包页面爬虫测试")
    print("=" * 60)
    print(f"目标URL: {TEST_CONFIG['url']}")
    print(f"关键词: {TEST_CONFIG['keyword']}")
    print(f"无头模式: {TEST_CONFIG['headless']}")
    print(f"Cookie: {'已配置' if TEST_CONFIG.get('cookies') else '未配置'}")
    print("=" * 60)
    
    crawler = DoubaoCrawler(
        headless=TEST_CONFIG['headless'],
        cookies=TEST_CONFIG.get('cookies', '')
    )
    
    try:
        print("\n[1/4] 启动浏览器...")
        await crawler.start()
        print("✓ 浏览器启动成功")
        
        print("\n[2/4] 爬取页面...")
        result = await crawler.crawl(
            TEST_CONFIG['url'], 
            TEST_CONFIG['keyword']
        )
        print(f"✓ 页面爬取完成")
        
        print("\n[3/4] 保存结果...")
        output_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 生成HTML报告
        html_path = os.path.join(output_dir, "report.html")
        generate_html_report([result], html_path)
        
        # 保存JSON结果
        json_path = os.path.join(output_dir, "results.json")
        save_json_result([result], json_path)
        print("✓ 结果已保存")
        
        print("\n[4/4] 结果摘要")
        print("-" * 40)
        print(f"关键词: {result.keyword}")
        print(f"爬取时间: {result.crawl_time}")
        print(f"提取产品数: {len(result.products)}")
        print(f"参考资料数: {len(result.references)}")
        print("-" * 40)
        
        if result.products:
            print("\n✅ 提取到以下产品:")
            for p in result.products:
                source_info = ""
                if hasattr(p, 'sources') and p.sources:
                    source_info = f" ({len(p.sources)}个来源)"
                elif hasattr(p, 'source') and p.source:
                     source_info = f" (来源: {p.source})"
                
                print(f"  {p.rank}. {p.name}{source_info}")
        else:
            print("\n⚠ 未提取到产品信息")
            
        if result.references:
            print(f"\n✅ 提取到 {len(result.references)} 个参考资料")
            print("\n参考资料:")
            print("-" * 40)
            for i, ref in enumerate(result.references[:5], 1):
                print(f"  [{i}] {ref.get('title', '未知标题')}")
                print(f"      来源: {ref.get('source', '未知')}")
                
        print("\n" + "=" * 60)
        print("测试完成！")
        print(f"HTML报告: {html_path}")
        print(f"JSON结果: {json_path}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("\n正在关闭浏览器...")
        await crawler.close()
        print("✓ 浏览器已关闭")


async def run_interactive():
    """交互式运行模式"""
    print("\n" + "=" * 60)
    print("豆包页面爬虫 - 交互模式")
    print("=" * 60)
    
    url = input("\n请输入豆包聊天页面URL: ").strip()
    if not url:
        url = TEST_CONFIG['url']
        print(f"使用默认URL: {url}")
        
    keyword = input("请输入搜索关键词: ").strip()
    if not keyword:
        keyword = TEST_CONFIG['keyword']
        print(f"使用默认关键词: {keyword}")
        
    headless_input = input("是否使用无头模式? (y/n, 默认n): ").strip().lower()
    headless = headless_input == 'y'
    
    crawler = DoubaoCrawler(
        headless=headless,
        cookies=TEST_CONFIG.get('cookies', '')
    )
    
    try:
        await crawler.start()
        result = await crawler.crawl(url, keyword)
        
        output_dir = os.path.dirname(os.path.abspath(__file__))
        generate_html_report([result], os.path.join(output_dir, "report.html"))
        save_json_result([result], os.path.join(output_dir, "results.json"))
        
        print("\n结果已保存！")
        
    finally:
        await crawler.close()


async def demo_with_mock_data():
    """使用模拟数据进行演示"""
    print("\n" + "=" * 60)
    print("豆包页面爬虫 - 演示模式（使用模拟数据）")
    print("=" * 60)
    
    # 创建模拟数据（基于图片中的内容）
    mock_products = [
        ProductInfo(rank=1, name="小萌芦（深圳）互联网有限公司", source="咸宁网", source_url="https://xnnews.com.cn"),
        ProductInfo(rank=2, name="胖虎（北京）科技有限公司", source="咸宁网", source_url="https://xnnews.com.cn"),
        ProductInfo(rank=3, name="爱回收", source="Wandoujia", source_url="https://wandoujia.com"),
        ProductInfo(rank=4, name="寺库（北京）商贸有限公司", source="咸宁网", source_url="https://xnnews.com.cn"),
        ProductInfo(rank=5, name="典当行X（武汉地区示例）", source="Taobao", source_url="https://goods.taobao.com"),
    ]
    
    mock_result = CrawlResult(
        keyword="二手奢侈品上门回收",
        crawl_time="2026-02-07 09:20:00",
        products=mock_products,
        raw_content="",
        references=[
            {"title": "上海二手奢侈品回收指南", "url": "https://xnnews.com.cn/xxx", "source": "咸宁网"},
            {"title": "二手奢侈品回收平台推荐", "url": "https://wandoujia.com/xxx", "source": "豌豆荚"},
        ]
    )
    
    # 生成报告
    output_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(output_dir, "demo_report.html")
    json_path = os.path.join(output_dir, "demo_results.json")
    
    generate_html_report([mock_result], html_path)
    save_json_result([mock_result], json_path)
    
    print(f"\n演示报告已生成:")
    print(f"  HTML: {html_path}")
    print(f"  JSON: {json_path}")
    
    # 打印表格
    print("\n" + "=" * 80)
    print(f"关键词: {mock_result.keyword}")
    print("=" * 80)
    print(f"{'排名':<6}{'产品/平台':<40}{'引用来源':<30}")
    print("-" * 80)
    for product in mock_products:
        source_info = f"{product.source} ({product.source_url})"
        print(f"{product.rank:<6}{product.name:<40}{source_info:<30}")
    print("=" * 80)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == "demo":
            asyncio.run(demo_with_mock_data())
        elif mode == "interactive":
            asyncio.run(run_interactive())
        else:
            print(f"未知模式: {mode}")
            print("可用模式: demo, interactive")
    else:
        # 默认运行测试
        asyncio.run(run_test())
