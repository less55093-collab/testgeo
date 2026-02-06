import os
from openai import OpenAI

# 请确保您已将 API Key 存储在环境变量 ARK_API_KEY 中
# 初始化Openai客户端，从环境变量中读取您的API Key
client = OpenAI(
    # 此为默认路径，您可根据业务所在地域进行配置
    base_url="https://ark.cn-beijing.volces.com/api/v3/bots",
    # 从环境变量中获取您的 API Key
    api_key="",
)


# Streaming:
print("----- streaming request -----")
stream = client.chat.completions.create(
    model="bot-20260206203351-hknwt",  # bot-20260206203351-hknwt 为您当前的智能体的ID，注意此处与Chat API存在差异。差异对比详见 SDK使用指南
    messages=[
        {"role": "system", "content": "你是豆包，是由字节跳动开发的 AI 人工智能助手"},
        {"role": "user", "content": "徐汇区黄金回收哪家好"},
    ],
    stream=True,
)
for chunk in stream:
    if hasattr(chunk, "references"):
        print(chunk.references)
    if not chunk.choices:
        continue
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
print()
