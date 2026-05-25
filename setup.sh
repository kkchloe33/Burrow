#!/data/data/com.termux/files/usr/bin/bash
# Burrow 兔子洞 —— Termux 一键安装脚本
# 使用方法: bash setup.sh

echo "========================================="
echo "  Burrow 兔子洞 记忆库 - 安装中..."
echo "========================================="
echo ""

# 1. 更新包管理器
echo "[1/5] 更新 Termux 包管理器..."
pkg update -y && pkg full-upgrade -y

# 2. 安装 Python 和编译工具（pydantic-core 需要 Rust 编译）
echo "[2/5] 安装 Python 和编译工具..."
pkg install -y python rust cmake ninja

# 3. 设置 Rust 编译环境变量（规避 Termux 多线程编译 bug）
export CARGO_BUILD_JOBS=1
export ANDROID_API_LEVEL=24

# 4. 安装 Python 依赖
echo "[3/5] 安装 Python 依赖（可能需要 15-30 分钟）..."
pip install -r requirements.txt

# 5. 创建数据目录
echo "[4/5] 初始化数据目录..."
mkdir -p data

echo ""
echo "========================================="
echo "  安装完成！"
echo "========================================="
echo ""
echo "接下来要做的事:"
echo ""
echo "1. 编辑 config.yaml，填入你的 API Key:"
echo "   nano config.yaml"
echo ""
echo "2. 启动 MCP 服务器（Streamable HTTP 模式）:"
echo "   python server.py"
echo ""
echo "3. 在 Rikkahub 中添加 MCP 配置:"
echo "   类型: streamable-http"
echo "   URL:  http://127.0.0.1:8000/mcp"
echo ""
echo "4. (可选) 启动 Web 前端:"
echo "   python web_server.py"
echo "   然后手机浏览器打开 http://localhost:8080"
echo ""
echo "5. (可选) 配置开机自启:"
echo "   mkdir -p ~/.termux/boot"
echo "   nano ~/.termux/boot/start-burrow.sh"
echo "   参考 DEPLOY.md 中的开机自启脚本"
echo ""
echo "========================================="
