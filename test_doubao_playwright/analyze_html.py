import re

with open('debug_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 查找可能的类名
patterns = [
    r'class="[^"]*content[^"]*"',
    r'class="[^"]*chat[^"]*"',
    r'class="[^"]*answer[^"]*"',
    r'class="[^"]*markdown[^"]*"',
]

for pattern in patterns:
    matches = re.findall(pattern, html[:200000])
    if matches:
        print(f"\nPattern: {pattern}")
        unique = set(matches[:20])
        for m in unique:
            print(f"  {m}")

# 检查是否有"恒天"等关键词
keywords = ['恒天', '鲸光阁', '茜豪', '典客', '小花中古']
for kw in keywords:
    if kw in html:
        print(f"\n✓ 找到关键词: {kw}")
        idx = html.find(kw)
        # 打印周围的HTML
        context = html[max(0,idx-200):idx+200]
        print(f"  上下文: {context[:100]}...")
    else:
        print(f"\n✗ 未找到关键词: {kw}")
