# omi-cli 快速上手（上海闲话）

迭份指南用上海闲话讲解头一趟使用 omi-cli 个命令。命令名字搭程序消息侪保持英文。搿搭个例子查询勿会改动侬个 memories、conversations、action items 或者 goals。

## 安装

要求：Python 3.10 或者更新个版本，外加一只 Omi 账号。

假使侬装仔 pipx 个话：

```sh
pipx install omi-cli
omi --help
```

或者装辣激活个 Python virtual environment 里向：

```sh
python -m pip install omi-cli
omi --help
```

注意：`omi` 命令可能一开头还勿辣侬个 PATH 里向 — 要确定 virtual environment 激活仔，或者 pipx 个文件夹辣 `$PATH` 里向。

## 登录

用 CLI 之前先登录：

```sh
omi auth login
```

侬可以用浏览器登录，也可以用 Omi 开发者 API key。Key 是贴进去个 — 勿会留辣终端历史里向。

辣搿台电脑浪用浏览器登录：

```sh
omi auth login --browser
```

假使是只有终端个机器：授权会辣本地地址浪完成。跟牢屏幕浪个提示做就可以。

检查目前个配置搭 API key：

```sh
omi auth status
omi auth whoami
```

`status` 会得显示本地信息，还会得拿 secrets 囥起来，勿会去问服务器。`whoami` 会得发一只认证过个请求；成功个话，就证明侬个 credentials 可以用。

配置存辣 `~/.omi/config.toml` 里向。覅手动改迭只文件 — 里向有 key 个秘密。

## 列 memories 搭 conversations

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

假使列表是空个，只能说明里向还呒没内容。想晓得每条命令支持啥个 filter，可以看：

```sh
omi memory list --help
omi action-item list --help
```

## JSON 搭导出

全局个 `--json` 选项要摆辣 command group **之前**：

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

头一条命令拿头 25 个 memories；第二条拿接下来个 25 个。JSON 输出有完整个 identifier，表格显示会拿伊截短。

存到文件里向：

```sh
omi --json memory list --limit 25 --offset 0 > memories-第1页.json
```

迭个重定向会新建或者覆盖本地文件。先检查命令个输出再讲。错误会到 stderr；空文件勿代表呒没数据。导出个文件可能有个人信息 — 要拿伊保护好。

## 退出登录

```sh
omi auth logout
```

迭条命令会拿本地个 credentials 删脱。服务器浪个 key 要辣 developer key management 里向管理。

想晓得更多命令搭选项：[英文文档](../README.md) 搭 `omi --help`。
