# GPT Image Prompts Gallery

一个在局域网内浏览、搜索 AI 图像生成提示词（Prompt）的网页应用。聚合了 [EvoLinkAI](https://github.com/EvoLinkAI/awesome-gpt-image-2-prompts) 和 [GPT Image 2](https://github.com/gpt-image2/awesome-gptimage2-prompts) 两个来源的数据，共 **3157 条**提示词和对应图片。

## 快速开始

```bash
# 1. 创建虚拟环境（首次）
python3 -m venv .venv

# 2. 启动服务
bash start.sh
```

浏览器会自动打开 `http://localhost:8765`，局域网内其他设备可访问 `http://10.10.10.87:8765`。

首次启动会自动拉取数据并下载图片（耗时较长）。

## 功能

| 功能 | 说明 |
|------|------|
| 搜索 | 支持中英文搜索提示词、标题、标签 |
| 分类筛选 | 7 个分类：电商产品、广告创意、人像摄影、海报设计、角色设计、UI 界面、对比与趣味 |
| 来源筛选 | EvoLinkAI / GPT Image 2 两个数据源 |
| 中英切换 | 界面和提示词内容均可切换语言 |
| 图片懒加载 | 滚动到可见区域才加载，带失败重试 |
| 一键复制 | 卡片和详情弹窗均可复制 Prompt |
| 无限滚动 | 滚动到底部自动加载更多 |
| 响应式 | 适配桌面和移动端 |

## 项目结构

```
├── index.html          # 主页面
├── server.py           # HTTP 服务器（ThreadingTCPServer, 端口 8765）
├── start.sh            # 启动脚本（自动激活 venv + 拉取数据）
├── update.sh           # 增量更新脚本
├── css/style.css       # 样式
├── js/
│   ├── data.js         # 数据加载 & 状态管理
│   ├── search.js       # 搜索、筛选、分页逻辑
│   └── app.js          # UI 渲染、事件绑定、图片重试
├── scripts/
│   └── fetch_data.py   # 数据抓取脚本
├── data/
│   ├── prompts.json    # 合并后的提示词数据
│   └── sync_state.json # 同步状态（用于增量更新）
├── images/             # 本地图片缓存（已 gitignore）
└── .cache/             # 源数据缓存（已 gitignore）
```

## 数据更新

```bash
bash update.sh   # 增量更新，只拉取变化的数据
```

首次使用或数据损坏时进行全量拉取：

```bash
source .venv/bin/activate
python scripts/fetch_data.py --full
```

## 开发说明

- Python 仅需标准库，无外部依赖
- 服务端使用 `ThreadingTCPServer` 支持浏览器并发连接
- 前端图片加载失败会自动重试 3 次（间隔递增）
- 虚拟环境 `.venv/`、缓存 `.cache/`、图片 `images/` 已在 gitignore 中

## 许可证

数据来自 [EvoLinkAI/awesome-gpt-image-2-prompts](https://github.com/EvoLinkAI/awesome-gpt-image-2-prompts) 和 [gpt-image2/awesome-gptimage2-prompts](https://github.com/gpt-image2/awesome-gptimage2-prompts)，遵循各自的许可证。
