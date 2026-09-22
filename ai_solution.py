```python
```python
```

```md
---
title: "Zhuang语言代理快速入门指南"
date: 2023-10-11
---

在这个示例中，展示了如何快速开始使用Zhuang语言的代理。

### 代理友好型合同
确保你的代理符合以下条件：
- 稳定的JSON输出
- 稳定的退出码
- 在无头环境中没有交互式提示
- 对重试友好的行为

### 一次性人机对话授权
确保只进行一次人机对话授权。

### 五个最常见的代理操作
1. **获取知识库**
2. **获取信息**
3. **思考**
4. **记忆**
5. **总结**

### 桌面版API工作流
- 包含结构化截图失败处理

### 示例Python代理循环
```python
while True:
    user_input = input("用户：").strip()
    if user_input == "退出":
        break
    response = agent_response(user_input)
    print("助手：", response)
```

### 率限处理
在你的代码中加入：
```python
if __name__ == "__main__":
    while True:
        try:
            # 你的代理逻辑
        except Exception as e:
            print(f"发生错误：{e}")
```

### 运行小贴士
- 确保你的代理支持中文
- 在无头模式下运行时，避免使用input输出

```