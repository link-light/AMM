# AI Money Machine (AMM)

AI驱动的多Agent系统，自动发现商机、评估、执行和交付。

## 🏗️ 架构概览

```
AMM/
├── core/           # 核心基础设施 (配置、数据库、队列、模型)
├── gateway/        # AI Gateway (成本可控、故障容错、供应商路由)
├── orchestrator/   # 中枢调度 (评估器、分发器、审核器)
├── scouts/         # 搜索层 (发现商机)
├── workers/        # 执行层 (任务执行)
├── knowledge/      # 知识库 (预留)
├── api/            # API 层 (FastAPI + WebSocket)
├── dashboard/      # 前端面板 (React + Tailwind)
├── migrations/     # 数据库迁移 (Alembic)
└── scripts/        # 工具脚本
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆仓库
git clone <repo>
cd amm

# 安装依赖
make setup

# 配置环境变量
cp .env.example .env
# 编辑 .env (可选，默认启用 Mock 模式)
```

### 2. 启动服务

```bash
# 方式1: 使用 Make (推荐)
make dev

# 方式2: 手动启动
make up          # 启动 Redis + PostgreSQL
make migrate     # 运行迁移
make seed        # 导入种子数据
python main.py   # 启动所有组件
```

### 3. 访问服务

- **API 文档**: http://localhost:8000/docs
- **Dashboard**: http://localhost:3000
- **Health Check**: http://localhost:8000/health

## 📋 使用指南

### Mock 模式 (开发)

默认启用 Mock 模式，无需真实 API Key:

```bash
# .env
MOCK_AI=true
MOCK_SCOUTS=true
```

在 Mock 模式下:
- AI 调用返回预设响应
- Scout 返回模拟商机数据
- 成本计算使用真实定价

### 生产模式

```bash
# 配置真实 API Keys
ANTHROPIC_API_KEY=your-key
OPENAI_API_KEY=your-key    # 可选

# 关闭 Mock
MOCK_AI=false
MOCK_SCOUTS=false

# 启动
make prod
```

## 🔧 配置说明

关键环境变量:

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | Anthropic API Key | - |
| `DAILY_HARD_LIMIT` | 每日预算硬限制 ($) | 20 |
| `MONTHLY_HARD_LIMIT` | 每月预算硬限制 ($) | 400 |
| `MOCK_AI` | Mock AI 调用 | true |
| `MOCK_SCOUTS` | Mock Scout 数据 | true |
| `JWT_SECRET` | JWT 签名密钥 | change-in-production |

## 🧪 测试

```bash
# 单元测试
make test

# 端到端测试
make test-e2e

# 手动测试 Scout
make dev-scout
```

## 📊 系统特性

### AI Gateway
- ✅ 多供应商路由 (Anthropic/OpenAI/DeepSeek)
- ✅ 成本追踪和预算熔断
- ✅ 令牌桶限流
- ✅ 三态熔断器
- ✅ 响应缓存

### 商机评估
- ✅ 6维度评分系统
- ✅ 利润门槛检查
- ✅ 合规风险检测
- ✅ 自动/人工决策

### 任务执行
- ✅ 代码生成 (Python)
- ✅ 自动测试生成
- ✅ 文档生成
- ✅ Skill 系统预留

### 质量审核
- ✅ 置信度计算
- ✅ 自动/AI/人工三级审核
- ✅ AI 痕迹检测

### Dashboard
- ✅ 实时监控
- ✅ 成本看板
- ✅ 人工任务面板
- ✅ 信号/任务管理

## 🗺️ 路线图

### Phase 1 (当前) ✅
- 基础设施搭建
- AI Gateway 核心
- 基础 Scout + Worker
- Dashboard MVP

### Phase 2 (计划中)
- 向量知识库
- 学习引擎
- 更多 Scout 源
- 更多 Worker 类型
- 真实平台集成

## 🤝 贡献

1. Fork 项目
2. 创建分支 (`git checkout -b feature/xxx`)
3. 提交更改 (`git commit -am 'Add feature'`)
4. 推送分支 (`git push origin feature/xxx`)
5. 创建 Pull Request

## 📝 License

MIT License - 详见 [LICENSE](LICENSE)

## 🙏 致谢

- FastAPI - Web 框架
- SQLAlchemy - ORM
- Celery - 任务队列
- Anthropic - AI 模型
