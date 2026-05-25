# Burrow 兔子洞 — 手机 Termux 宝宝级部署指南

本指南教你把 Burrow 装在你的**安卓手机**上，通过 **Streamable HTTP** 协议接入 **Rikkahub**（AI 聊天客户端），让 AI 拥有跨对话长期记忆。

**适用人群**：完全不懂代码也能照着做。
**预计耗时**：30 分钟 ~ 1 小时（看网速和手机性能）。
**一次装好之后日常无需维护**。

---

## 📋 准备工作

### 你需要的东西

- **一台安卓手机**（Android 8 及以上）
- **至少 500MB 可用存储**
- **WiFi**（整个过程下载约 200MB）
- **充电器**（编译时手机会发热，建议插着电）

### 需要申请的 API Key（可选功能，不开也行）

| 用途 | 需要什么 | 是否必须 |
|------|---------|---------|
| 自动打标签 | DeepSeek API Key | ❌ 可选（关了也能用） |
| 语义搜索 | Gemini API Key | ❌ 可选（关了也能用） |

---

## 第一步：安装 Termux

### 1.1 下载 Termux

> ⚠️ **不要**从 Google Play 商店下载 Termux！那个版本太老了。要从 GitHub 官方下载。

打开手机浏览器，访问下面这个网址，下载 Termux 主程序：

**https://github.com/termux/termux-app/releases**

进去后：
1. 找最新的 release（排在最上面的那个）
2. 往下翻，找到 **Assets** 部分
3. 下载文件名带 **arm64-v8a** 的 `.apk` 文件（比如 `termux-app_v0.118.1+github-debug_arm64-v8a.apk`）
4. 下载完成后点击安装

> 如果手机拦截"未知来源安装"，去手机系统设置 → 安全 → 给浏览器开"允许安装未知应用"权限。

### 1.2 装完后打开 Termux

安装完成后，打开 Termux 应用。你会看到一个黑底绿字的界面，提示符是 `~ $`，等你输命令。

> **虚拟键盘**：Termux 底排有一排虚拟按键（`Ctrl` `Alt` 等），屏幕中间区域点一下会弹出键盘。如果你想调出额外按键行，在屏幕上从**顶部边缘往下滑**，点 "Keyboard" 即可。

---

## 第二步：配置 Termux 基础环境

### 2.1 换国内镜像源（不换的话下载会卡）

在 Termux 里输入以下命令，然后回车：

```
termux-change-repo
```

会弹出一个蓝底菜单。操作方式：
- **方向键 ↑↓**：移动光标
- **空格键**：勾选当前项（前面出现 `*`）
- **Tab 键**：切换到 `<OK>` 按钮
- **回车**：确认

**具体步骤：**
1. 第一屏：用方向键选中 **Main repository**，按**空格**勾选它（前面会出现 `*`），按 **Tab** 切换到 `<OK>`，**回车**
2. 第二屏：找带 **China**、**Tsinghua**（清华）、**USTC**（中科大）字样的镜像，选中一个，Tab 到 OK，回车

回到 `~ $` 就成功了。

### 2.2 升级软件包

```
apt update && apt full-upgrade -y
```

这个过程可能需要几分钟。如果中间问 `[Y/n]`，敲 `Y` 回车。如果问 "configuration file" 替换的，按 **Enter** 用默认值。

跑完后验证一下：

```
curl --version
```

看到一长串 `curl 8.x.x` 信息就 OK。

### 2.3 安装 Python 和编译工具

```
pkg install -y python rust cmake ninja
```

这个步骤会安装 Python 和一些编译工具（因为后面装依赖时 `pydantic-core` 需要从 Rust 源码编译）。大概 3-5 分钟。

### 2.4 授权存储空间

```
termux-setup-storage
```

手机会弹一个权限对话框，点 **"允许"**。

### 2.5 防杀后台

```
termux-wake-lock
```

没有任何输出是对的。这行命令告诉系统不要杀掉 Termux 的后台进程。

### 2.6 验证 Python

```
python --version
```

应该看到 `Python 3.12.x` 或更新版本。

---

## 第三步：拉取 Burrow 源码

```
cd ~
git clone https://github.com/你的仓库地址/burrow.git
cd Burrow/Burrow
```

完成后提示符变成 `~/Burrow/Burrow $`。**后面的所有命令都要在这个目录里执行！**

---

## 第四步：安装 Python 依赖（最容易卡的一步）

### 4.1 配置 pip 走国内镜像（避免超时）

```
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 4.2 先装预编译版 numpy（跳过编译）

```
pkg install -y python-numpy python-cryptography
```

这两个包如果让 pip 装，会在手机上编译半小时甚至失败。Termux 直接提供编译好的版本。

### 4.3 设置编译环境变量（规避 Termux 编译 bug）

```
export CARGO_BUILD_JOBS=1
export ANDROID_API_LEVEL=24
```

**解释：**
- `CARGO_BUILD_JOBS=1`：让 Rust 单线程编译，绕过多线程报错
- `ANDROID_API_LEVEL=24`：告诉编译工具用 Android 7.0 的 API

### 4.4 安装所有依赖

```
pip install -r requirements.txt
```

预计 **15 ~ 30 分钟**。期间手机会发热，正常现象。`pydantic-core` 是 Rust 编译的，单线程会慢但稳。

**成功标志**：最后看到一长串 `Successfully installed xxx...`

**如果中途失败了**，重新跑一次上面的 pip install 命令，大多数情况下第二次就能过。

---

## 第五步：配置 API Key（可选）

### 5.1 编辑配置文件

```
nano config.yaml
```

你会看到：

```yaml
tagger:
  enabled: true
  model: "deepseek-chat"
  base_url: "https://api.deepseek.com/v1"
  api_key: "sk-your-deepseek-key"      # ← 改成你的 DeepSeek Key

embedding:
  enabled: true
  model: "text-embedding-004"
  api_key: "your-gemini-api-key"       # ← 改成你的 Gemini Key

server:
  transport: "streamable-http"
  host: "0.0.0.0"
  port: 8000

database:
  path: "./data/burrow.db"
```

### 5.2 获取 API Key

#### DeepSeek Key（自动打标签用）
1. 浏览器访问 https://platform.deepseek.com
2. 注册 → 登录
3. 左侧菜单 "API Keys" → "Create API Key"
4. 复制 `sk-` 开头的 Key，粘贴到 `config.yaml` 的 `api_key` 位置

#### Gemini Key（语义搜索用）
1. 浏览器访问 https://aistudio.google.com/apikey
2. "Create API Key" → 复制
3. 粘贴到 `config.yaml`

### 5.3 不想用这些功能？

把 `enabled: true` 改成 `enabled: false` 就行了：

```yaml
tagger:
  enabled: false
  ...
embedding:
  enabled: false
  ...
```

> **即使不开这些功能，Burrow 的核心功能（记录、搜索、回忆）也完全能用！**

### 5.4 保存退出

在 nano 编辑器中：
1. **保存**：`Ctrl + O`，回车确认
2. **退出**：`Ctrl + X`

---

## 第六步：启动服务

```
python server.py
```

**成功标志：** 看到类似这样的输出：

```
Burrow 启动 | 传输: streamable-http
监听地址: http://0.0.0.0:8000/mcp
请在 Rikkahub 中添加 MCP 服务器：
  类型: streamable-http
  URL:  http://127.0.0.1:8000/mcp
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

光标停在最下面闪烁是正常的，表示它在监听请求。**不要按 Ctrl+C**，让它继续跑。

> **如果看到红字 `Failed to parse config file`** → 说明 config.yaml 有语法错误。最常见的是第一行前面有空格。按 `Ctrl+C` 停掉，重新 `nano config.yaml` 检查修正。

---

## 第七步：Rikkahub 接入

保持 Termux 在后台运行（**不要滑掉它**），切换到 Rikkahub。

在 Rikkahub 中找到 MCP 服务设置，新建一个：

| 字段 | 值 |
|------|-----|
| 名字 | 随便，比如 "Burrow" 或 "兔子洞" |
| 类型 | **streamable-http** |
| URL | **http://127.0.0.1:8000/mcp** |

保存。回到对话界面，丢一句测试：

> 记住这个：今天我装好了 Burrow 记忆库。

如果连通了，AI 会调 `remember` 工具把这条存进去。再问：

> 你记得我提过 Burrow 吗？

AI 会调 `recall` 工具搜索，回忆起刚才那条。两遍都通了说明端到端连上了。🎉

---

## 第八步：配置开机自启（强烈推荐）

不配这个的话，每次手机重启或 Termux 被杀，记忆服务就没了，要重新手动启动。

### 8.1 开新 Termux 窗口

当前的 Termux 窗口被服务器占着，不能输命令了。点屏幕底排虚拟键里左数第二个图标 **≡（三横线）**，打开 sessions 抽屉，点底部 **NEW SESSION**，开一个新窗口。

### 8.2 创建开机启动脚本

```
mkdir -p ~/.termux/boot
nano ~/.termux/boot/start-burrow.sh
```

粘贴以下内容（长按屏幕可以粘贴）：

```bash
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd ~/burrow/burrow
while true; do
    python server.py
    echo "[$(date)] 服务挂了，5 秒后重启..."
    sleep 5
done
```

保存退出：`Ctrl + O` → 回车 → `Ctrl + X`

### 8.3 给脚本执行权限

```
chmod +x ~/.termux/boot/start-burrow.sh
```

### 8.4 安装 Termux:Boot（可选，用于真正开机自启）

如果想让手机重启后自动启动 Burrow：

1. 访问 https://github.com/termux/termux-boot/releases
2. 下载 arm64-v8a 的 APK 安装

### 8.5 加电池白名单（强烈建议）

去手机系统设置 → 应用管理 → Termux → 电池，选 **"无限制"** 或 **"忽略电池优化"**。

> 国产手机（小米、华为、OPPO、vivo）的省电策略很激进，即使挂了 wakelock 也可能会杀 Termux。这一步是兜底。

---

## 第九步：（可选）启动 Web 前端

如果你想像普通 App 一样在浏览器里浏览记忆：

在**新开的 Termux 窗口**里：

```
cd ~/burrow/burrow
python web_server.py
```

然后手机浏览器打开 **http://localhost:8080**

> 注意：Web 前端和 MCP 服务器是两个独立的进程，互不干扰。你可以两个同时跑。

---

## ❓ 故障排查

### Pip install 卡住了 / 报错了

```
# 重试，大多数情况第二次能过
pip install -r requirements.txt

# 如果还不行，单独装出问题的包
pip install mcp[cli] pyyaml httpx uvicorn
```

### pydantic-core 编译报错 "Text file busy"

这是 Termux 多线程编译的 bug。确认设了 `export CARGO_BUILD_JOBS=1` 后重试。

### pydantic-core 编译报错 "Failed to determine Android API level"

设上 `export ANDROID_API_LEVEL=24` 后重试。

### Rikkahub 连不上 8000 端口

1. 确认 `server.py` 还在跑（去 Termux 看日志）
2. 确认 URL 是 `http://127.0.0.1:8000/mcp`，类型是 `streamable-http`
3. 确认 Termux 没被滑掉（最近任务里它还在）
4. 如果改了端口，URL 里的端口号也要同步改

### 服务启动后报 "Failed to parse config file"

YAML 语法错误。最常见的是某一行前面有空格。用 `nano config.yaml` 检查。

### 手机重启后服务不在了

1. 确认装了 Termux:Boot APK
2. 确认 `~/.termux/boot/start-burrow.sh` 存在且有执行权限
3. 确认给了 Termux 自启动权限（手机设置里找）
4. 也可以手动进 Termux，重新跑 `python server.py`

### 不知道怎么关服务

在跑着服务的窗口按 `Ctrl + C` 就能停掉。

### 不知道出了什么错

去跑 server 的那个 Termux 窗口看实时日志。屏幕左边缘往右滑，或点底排 ≡ 图标可以切换窗口。

---

## 📝 日常使用

正常在 Rikkahub 里聊天就行，AI 会自动调用 `remember`（存）和 `recall`（取）。你不需要手动做任何事。

想看记忆库？手机浏览器打开 http://localhost:8080（需要同时跑着 `web_server.py`）。

**对话结束时 AI 会自动检查待办和今天记录**，完全自动化。

---

## 🗑️ 卸载

如果哪天想拆掉：

```
cd ~
rm -rf burrow
rm -f ~/.termux/boot/start-burrow.sh
```

记忆数据在 `~/burrow/burrow/data/burrow.db`，要不要保留你自己定。

Rikkahub 里把 MCP 服务器配置删掉。

---

## 快速参考

```
# 启动 Burrow
cd ~/burrow/burrow
python server.py

# 启动 Web 前端（可选）
python web_server.py

# 查看日志
# → 在跑 server 的窗口看
```

**Rikkahub 配置**：
- 类型：`streamable-http`
- URL：`http://127.0.0.1:8000/mcp`
