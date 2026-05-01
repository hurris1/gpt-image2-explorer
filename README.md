# GPT Image Prompts Gallery

在线浏览、搜索 AI 图像生成提示词（Prompt）的静态网页应用。聚合了两个开源数据源，共 **3157 条**提示词及对应图片，支持中英文双语。

## 数据来源

本项目聚合了以下开源 Prompt 数据集：

| 来源 | 说明 |
|------|------|
| [EvoLinkAI/awesome-gpt-image-2-prompts](https://github.com/EvoLinkAI/awesome-gpt-image-2-prompts) | EvoLinkAI 社区整理的 GPT Image 2 提示词合集，含分类案例和双语 Prompt |
| [gpt-image2/awesome-gptimage2-prompts](https://github.com/gpt-image2/awesome-gptimage2-prompts) | GPT Image 2 官方社区提示词合集 |

以上数据遵循各自仓库的许可证。本项目的代码部分（HTML/CSS/JS/Python 脚本）采用 MIT 许可证。

## 功能

| 功能 | 说明 |
|------|------|
| 搜索 | 支持中英文搜索提示词、标题、标签 |
| 分类筛选 | 7 个分类：电商产品、广告创意、人像摄影、海报设计、角色设计、UI 界面、对比与趣味 |
| 来源筛选 | EvoLinkAI / GPT Image 2 两个数据源 |
| 中英切换 | 界面文案、Prompt 内容、分类标签均可切换语言 |
| 一键复制 | 卡片和详情弹窗均可复制 Prompt 文本 |
| 无限滚动 | 滚动到底部自动加载更多 |
| 响应式 | 适配桌面和移动端 |

## 本地运行

```bash
# 1. 创建虚拟环境（首次）
python3 -m venv .venv

# 2. 启动服务
bash start.sh
```

浏览器自动打开 `http://localhost:8765`。首次启动自动拉取数据并下载图片（耗时较长）。

局域网内其他设备可通过本机 IP 访问，如 `http://10.10.10.87:8765`。

## 数据更新

本仓库自带一份预构建数据（`data/prompts.json` 和 `images/`），可直接使用。如需更新到最新数据：

```bash
bash update.sh   # 增量更新
```

或全量重建：

```bash
source .venv/bin/activate
python scripts/fetch_data.py --full
```

> **注意：** 全量拉取会重置所有数据，包括手动添加的中文标题。建议提前备份 `data/prompts.json`。

## 添加中文标题/摘要

每个 Prompt 条目有两个可选的中文字段：

| 字段 | 说明 | 默认行为 |
|------|------|----------|
| `title_zh` | 中文标题 | 为空时自动使用英文 `title` |
| `description_zh` | 中文摘要 | 为空时自动使用英文 `description` |

直接编辑 `data/prompts.json`，在对应条目中填写字段即可。例如：

```json
{
  "id": "evo_113",
  "title": "E-commerce Main Image - Luxury Amber Perfume Ad",
  "title_zh": "电商主图 - 琥珀香水广告",
  "description": "A luxurious cinematic product photograph...",
  "description_zh": "一张奢华的琥珀香水电影级产品摄影..."
}
```

填写后刷新页面，切换到中文即可看到中文标题和摘要。

> **注意：** `bash update.sh` 增量更新不会覆盖已有的 `title_zh` / `description_zh`。`--full` 全量拉取会重置，请提前备份。

## 部署到 GitHub Pages

本项目为纯静态站点（HTML + CSS + JS + JSON + 图片），可直接部署到 GitHub Pages：

1. 将仓库推送到 GitHub
2. 在仓库 Settings → Pages 中选择部署分支（如 `master`）和目录（`/ (root)`）
3. 访问 `https://<username>.github.io/<repo>/`

**本地更新数据后部署：**

```bash
bash update.sh           # 更新数据
git add data/ images/
git commit -m "Update prompt data"
git push
```

> **注意：** 数据更新脚本（`fetch_data.py`）不能在 GitHub Pages 上运行，需在本地执行后再推送。

## 项目结构

```
├── index.html          # 主页面
├── server.py           # 本地开发服务器（仅本地使用）
├── start.sh            # 本地启动脚本
├── update.sh           # 数据更新脚本
├── css/style.css       # 样式
├── js/
│   ├── data.js         # 数据加载 & 状态管理
│   ├── search.js       # 搜索、筛选、分页逻辑
│   └── app.js          # UI 渲染、事件绑定
├── scripts/
│   └── fetch_data.py   # 数据抓取（仅本地使用）
├── data/
│   ├── prompts.json    # 提示词数据（12MB）
│   └── sync_state.json # 同步状态
└── images/             # 提示词对应图片（~130MB, 2975 张）
```

## 许可证

代码（HTML/CSS/JS/Python 脚本）采用 [MIT License](https://opensource.org/licenses/MIT)。

Prompt 数据来自 [EvoLinkAI/awesome-gpt-image-2-prompts](https://github.com/EvoLinkAI/awesome-gpt-image-2-prompts) 和 [gpt-image2/awesome-gptimage2-prompts](https://github.com/gpt-image2/awesome-gptimage2-prompts)，遵循各自仓库的许可证。图片版权归原作者所有。
