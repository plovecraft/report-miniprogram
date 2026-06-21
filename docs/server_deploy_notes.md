# 服务器部署说明

## 1. 环境要求

- Python 3.11 或兼容版本
- Linux 服务器建议使用 UTF-8 环境
- 需要可写的数据目录用于：
  - 任务上传
  - 生成 DOCX 输出
  - 本地 SQLite

## 2. 安装依赖

```powershell
cd C:\Users\wuzitian\WeChatProjects\miniprogram-2\backend
pip install -r requirements.txt
```

说明：

- 当前图片识别使用 `opencv-python-headless`
- 不需要额外启动独立图片识别服务
- 不需要额外启动 AI Planner 服务

## 3. .env 配置

建议从模板复制：

```powershell
copy .env.example .env
```

关键项：

```env
STORAGE_DIR=./storage
OUTPUT_DIR=./storage/outputs
MAX_UPLOAD_MB=50
CORS_ORIGINS=https://your-domain.com
PUBLIC_BASE_URL=https://your-backend-domain.com
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
```

说明：

- 不提交真实 `LLM_API_KEY`
- 未配置 `LLM_*` 时，AI Planner 自动降级为 `disabled`
- 不影响主生成链路

## 4. 启动命令

项目根目录：

```powershell
cd C:\Users\wuzitian\WeChatProjects\miniprogram-2
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

或 backend 目录：

```powershell
cd C:\Users\wuzitian\WeChatProjects\miniprogram-2\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 5. 反向代理建议

- 对外只暴露 HTTPS 域名
- 反向代理到本地 `127.0.0.1:8000`
- 为上传接口放宽请求体限制
- 为下载接口保留 `Content-Disposition`

## 6. 小程序合法域名

微信公众平台至少配置：

- request 合法域名
- uploadFile 合法域名
- downloadFile 合法域名

要求：

- 必须 HTTPS
- 不使用裸 IP 作为正式域名

## 7. 存储目录说明

默认结构：

- `storage/tasks/<task_id>/uploads`
- `storage/tasks/<task_id>/outputs`
- `storage/app.sqlite3`

要求：

- 运行用户有写权限
- 定期清理历史任务输出
- 不将 `storage/` 提交到仓库

## 8. 常见问题排查

- 上传 413：检查 `MAX_UPLOAD_MB` 与反向代理 body 限制
- CORS 报错：检查 `CORS_ORIGINS`
- 下载失败：检查反向代理下载头是否保留，检查输出文件是否存在
- AI Planner 无结果：通常是未配置 `LLM_*`，此时应显示 `disabled`
- 图片识别异常：单图失败不应拖垮整个 preview，查看后端日志

## 9. 真机联调清单

1. 上传原始报告 DOCX
2. 上传指导书
3. 上传图片
4. 等待 `preview_ready`
5. 检查 `imagePlan`
6. 检查 `tablePlan`
7. 编辑并保存一张表格
8. 切换一个表格为“不插入”
9. 查看 AI 摘要
10. 采用 AI / 恢复规则
11. 确认生成
12. 下载 DOCX
13. 用 Word/WPS 打开检查
