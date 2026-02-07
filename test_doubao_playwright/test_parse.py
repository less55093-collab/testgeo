import re

# 测试解析逻辑
with open('debug_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 使用正则提取内容区域的文本
# 找到所有包含关键内容的区域
content_parts = []

# 提取md-box中的内容
import re
md_boxes = re.findall(r'class="[^"]*md-box[^"]*"[^>]*>([^<]+)<', html)
print(f"找到 {len(md_boxes)} 个md-box内容")

# 直接提取可见文本
visible_text = re.sub(r'<[^>]+>', '\n', html)
visible_text = re.sub(r'\s+', ' ', visible_text)

# 找到关键段落
keywords = ['恒天奢侈品', '鲸光阁珠宝', '茜豪珠宝', '典客名品汇', '小花中古']
for kw in keywords:
    if kw in visible_text:
        idx = visible_text.find(kw)
        context = visible_text[max(0,idx-50):idx+150]
        print(f"\n✓ {kw}:")
        print(f"  {context}")
        
# 测试解析正则
test_lines = [
    "一、恒天奢侈品（综合实力TOP1）",
    "二、上海鲸光阁珠宝（专业上门回收TOP1）",
    "三、上海茜豪珠宝",
    "四、典客名品汇",
    "五、小花中古",
]

cn_num_map = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
}

print("\n\n测试正则匹配:")
for line in test_lines:
    match = re.match(r'^([一二三四五六七八九十]+)、\s*(.+?)(?:（|【|$)', line)
    if match:
        cn_rank = match.group(1) 
        name = match.group(2).strip()
        rank = 0
        for char in cn_rank:
            rank = rank * 10 + cn_num_map.get(char, 0)
        print(f"  ✓ {rank}. {name}")
    else:
        print(f"  ✗ 未匹配: {line}")
