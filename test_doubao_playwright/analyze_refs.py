from bs4 import BeautifulSoup
import re

with open('debug_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

# 查找所有外部链接
external_links = soup.find_all('a', href=re.compile(r'^https?://(?!.*doubao\.com)(?!.*bytedance\.com)'))

print(f"找到 {len(external_links)} 个外部链接:\n")

for i, link in enumerate(external_links, 1):
    href = link.get('href', '')
    link_text = link.get_text(strip=True)
    
    print(f"{i}. {link_text[:50]}")
    print(f"   {href[:70]}")
    print()
