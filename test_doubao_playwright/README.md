# 豆包(Doubao)页面爬虫测试

使用 Playwright 爬取豆包聊天页面，提取并记录产品排名信息。

## 功能特点

- 🔍 **关键词记录** - 自动提取或手动指定搜索关键词
- 📊 **产品排名** - 解析页面内容，提取产品名称和排名
- 🔗 **来源追踪** - 关联参考资料，记录引用来源
- 📄 **报告生成** - 自动生成美观的HTML报告和JSON数据

## 文件结构

```
test_doubao_playwright/
├── doubao_crawler.py    # 主爬虫类
├── run_test.py          # 测试运行脚本
├── README.md            # 本说明文件
├── report.html          # 生成的HTML报告（运行后生成）
└── results.json         # 生成的JSON结果（运行后生成）
```

## 安装依赖

```bash
# 安装 Playwright
pip install playwright

# 安装浏览器
playwright install chromium
```

## 使用方法

### 1. 演示模式（使用模拟数据）

```bash
python run_test.py demo
```

这将使用预设的模拟数据生成报告，无需实际访问网页。

### 2. 正常测试模式

```bash
python run_test.py
```

需要先修改 `run_test.py` 中的 `TEST_CONFIG` 配置：

```python
TEST_CONFIG = {
    "url": "https://doubao.com/chat/你的会话ID",
    "keyword": "你的搜索关键词",
    "headless": False,  # 是否使用无头模式
}
```

### 3. 交互模式

```bash
python run_test.py interactive
```

将提示输入URL和关键词。

## 输出格式

### HTML报告示例

生成的报告格式如下：

| 排名 | 产品/平台 | 引用来源 |
|------|-----------|----------|
| 1 | 小萌芦（深圳）互联网有限公司 | 咸宁网 (xnnews.com.cn) |
| 2 | 胖虎（北京）科技有限公司 | 咸宁网 (xnnews.com.cn) |
| 3 | 爱回收 | Wandoujia (wandoujia.com) |
| 4 | 寺库（北京）商贸有限公司 | 咸宁网 (xnnews.com.cn) |
| 5 | 典当行X（武汉地区示例） | Taobao (goods.taobao.com) |

### JSON结果格式

```json
[
  {
    "keyword": "二手奢侈品上门回收",
    "crawl_time": "2026-02-07 09:20:00",
    "products": [
      {
        "rank": 1,
        "name": "小萌芦（深圳）互联网有限公司",
        "source": "咸宁网",
        "source_url": "https://xnnews.com.cn"
      }
    ],
    "references": [...]
  }
]
```

## 注意事项

1. **登录状态** - 爬取某些页面可能需要先登录豆包账号
2. **页面加载** - 确保页面完全加载后再提取内容
3. **反爬虫** - 频繁访问可能触发反爬虫机制，建议添加适当延时
4. **页面结构** - 如果豆包更新了页面结构，可能需要调整选择器

## 扩展开发

### 自定义选择器

如果默认选择器无法正确提取内容，可以修改 `doubao_crawler.py` 中的选择器：

```python
content_selectors = [
    'div[class*="message-content"]',
    'div[class*="answer"]',
    # 添加更多选择器...
]
```

### 添加新的来源映射

在 `_extract_source_name` 方法中添加新的域名映射：

```python
source_map = {
    "zhihu.com": "知乎",
    "your-domain.com": "自定义名称",
    # ...
}
```
