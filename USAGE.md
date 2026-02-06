# AI Backend Framework - Usage Guide

## 简化后的使用方式

### 快速开始

```python
from ai_backend.providers.deepseek import DeepSeek
from ai_backend.core.types import CallParams

# 1. 初始化provider（同步）
deepseek = DeepSeek("config.json")

# 2. 调用API（异步）
result = await deepseek.call(CallParams(
    messages=[{"role": "user", "content": "Hello!"}],
    enable_thinking=False,
    enable_search=True,
))

print(result.content)
```

就这么简单！

## 配置文件

`config.json`:

```json
{
  "providers": {
    "deepseek": {
      "accounts": [
        {
          "email": "your-email@example.com",
          "password": "your-password"
        }
      ],
      "rate_limit": {
        "max_requests_per_period": 10,
        "period_seconds": 60.0,
        "min_delay_between_requests": 1.0
      },
      "token_storage_path": "data/deepseek_tokens.json",
      "wasm_path": "sha3_wasm_bg.7b9ca65ddd.wasm",
      "max_retries": 3
    }
  }
}
```

## 完整示例

```python
import asyncio
from ai_backend.providers.deepseek import DeepSeek
from ai_backend.core.types import CallParams

async def main():
    # 初始化
    deepseek = DeepSeek("config.json")

    # 准备参数
    params = CallParams(
        messages=[
            {"role": "user", "content": "推荐最好的无线耳机"}
        ],
        enable_thinking=False,  # 是否启用思考链
        enable_search=True,     # 是否启用联网搜索
    )

    # 调用
    result = await deepseek.call(params)

    # 使用结果
    print(f"回答: {result.content}")
    print(f"原始响应: {result.raw_response}")

asyncio.run(main())
```

## 添加新的Provider

创建新provider只需3步：

### 1. 实现组件

在 `ai_backend/providers/your_platform/` 创建：

- `auth.py` - 认证逻辑
- `session.py` - 会话管理（可选）
- `client.py` - API调用
- `provider.py` - Provider类

### 2. Provider类

```python
# ai_backend/providers/your_platform/provider.py
import json
from pathlib import Path
from ai_backend.core.types import CallParams, CallResult
# ... 导入你的组件

class YourPlatform:
    def __init__(self, config_path: str = "config.json"):
        # 读取配置
        with open(config_path) as f:
            config = json.load(f)

        platform_config = config["providers"]["your_platform"]

        # 初始化组件
        # self.authenticator = ...
        # self.client = ...
        # self._provider = Provider(...)

    async def call(self, params: CallParams) -> CallResult:
        return await self._provider.call(params)
```

### 3. 导出

```python
# ai_backend/providers/your_platform/__init__.py
from ai_backend.providers.your_platform.provider import YourPlatform

__all__ = ["YourPlatform"]
```

完成！现在可以这样使用：

```python
from ai_backend.providers.your_platform import YourPlatform

provider = YourPlatform("config.json")
result = await provider.call(params)
```

## 架构优势

### 简洁性
- ✅ 直接实例化：`DeepSeek("config.json")`
- ✅ 无需工厂函数
- ✅ 无需provider_name参数
- ✅ 每个provider自己管理自己

### 灵活性
- ✅ 每个provider独立实现
- ✅ 不同provider可以有不同的配置结构
- ✅ 易于测试和调试

### 可扩展性
- ✅ 添加新provider无需修改核心代码
- ✅ 每个provider是独立模块
- ✅ 可以单独发布不同的provider包

## 与旧版本的区别

### 旧版本（过度设计）

```python
from ai_backend.core.config import Config

config = Config("config.json")
provider = await config.create_provider("deepseek", max_retries=3)
result = await provider.call(params)
```

问题：
- 需要Config类作为中介
- create_provider是async的
- 需要传provider_name字符串
- Config需要知道所有provider的细节

### 新版本（简洁）

```python
from ai_backend.providers.deepseek import DeepSeek

deepseek = DeepSeek("config.json")
result = await deepseek.call(params)
```

优势：
- 直接导入使用
- 初始化是同步的
- 类型安全（导入的是具体类）
- Provider自己负责自己的逻辑

## 测试

运行测试：

```bash
PYTHONPATH=src python test_deepseek.py
```

确保：
1. `config.json` 已配置正确的账号密码
2. `sha3_wasm_bg.7b9ca65ddd.wasm` 在项目根目录
3. 已安装依赖：`curl-cffi`, `wasmtime`

## 错误处理

```python
from ai_backend.core.exceptions import (
    TokenExpired,
    AccountBanned,
    NoAccountAvailable,
    AllRetriesFailed,
)

try:
    result = await deepseek.call(params)
except TokenExpired:
    print("Token过期，正在重新登录...")
except AccountBanned:
    print("账号被封禁")
except NoAccountAvailable:
    print("没有可用账号")
except AllRetriesFailed as e:
    print(f"所有重试都失败了: {e}")
```

## 高级用法

### 多账号自动轮换

框架会自动：
- 轮换使用多个账号
- 遵守每个账号的速率限制
- 在账号失败时自动切换
- 保存token避免重复登录

### 自定义解析器

```python
from ai_backend.parser.base import ResponseParser
from ai_backend.core.types import CallResult

class MyParser(ResponseParser):
    def parse(self, raw_response) -> CallResult:
        # 自定义解析逻辑
        return CallResult(
            raw_response=raw_response,
            content=...,
            rankings=[...],  # 提取产品排名
            sources=[...],   # 提取来源
        )

# 在provider初始化时使用
# self.parser = MyParser()
```

## 最佳实践

1. **环境变量存储密码**
   ```python
   import os
   # 在config.json中不直接写密码
   # 使用环境变量: os.getenv("DEEPSEEK_PASSWORD")
   ```

2. **日志监控**
   ```python
   import logging
   logging.basicConfig(level=logging.INFO)
   ```

3. **错误重试**
   ```python
   # 在config.json中设置
   "max_retries": 3  # 最多重试3次
   ```

4. **速率限制**
   ```python
   # 根据平台限制调整
   "rate_limit": {
     "max_requests_per_period": 20,
     "period_seconds": 60
   }
   ```
