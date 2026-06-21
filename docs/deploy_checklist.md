# 部署前检查清单

## 1. 后端依赖

安装命令：

```powershell
cd C:\Users\wuzitian\WeChatProjects\miniprogram-2\backend
pip install -r requirements.txt
```

当前运行依赖：

- fastapi
- uvicorn
- python-docx
- python-dotenv
- python-multipart
- requests
- PyMuPDF
- httpx
- opencv-python-headless
- Pillow
- numpy
- pytest

## 2. 启动命令

从项目根目录启动：

```powershell
cd C:\Users\wuzitian\WeChatProjects\miniprogram-2
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

从 `backend` 目录启动：

```powershell
cd C:\Users\wuzitian\WeChatProjects\miniprogram-2\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 3. 环境变量

复制模板：

```powershell
copy .env.example .env
```

建议至少配置：

- `STORAGE_DIR`
- `OUTPUT_DIR`
- `MAX_UPLOAD_MB`
- `CORS_ORIGINS`
- `PUBLIC_BASE_URL`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_TIMEOUT`

说明：

- 未配置 `LLM_*` 时，AI Planner 保持影子禁用，不影响正式生成。
- `STORAGE_DIR` 默认是 `backend/storage`。
- `OUTPUT_DIR` 当前建议与任务目录下的 `outputs` 保持同层语义，主要作为部署占位和后续运维文档约定。
- `CORS_ORIGINS=*` 仅适合开发环境；生产环境应改为明确域名列表。
- `PUBLIC_BASE_URL` 用于部署文档和反向代理约定，不应写成前端密钥或本地地址。

## 4. 存储目录

后端会自动创建：

- `storage/tasks`
- `storage/app.sqlite3`
- 每个任务目录下的：
  - `uploads`
  - `outputs`

部署前确认：

- 运行用户对 `STORAGE_DIR` 有写权限
- 存储目录不提交到 git
- 服务器磁盘空间足够

## 5. 小程序后端地址

统一配置文件：

- `miniprogram/config.ts`

发布前必须替换：

```ts
export const API_BASE_URL = 'https://your-backend-domain'
```

不要在其他前端文件中散落硬编码后端地址。

## 6. 上传与安全

- 单次上传体积由 `MAX_UPLOAD_MB` 控制
- `.env` 不提交
- `backend/storage/` 不提交
- API key 不写入前端
- 小程序只访问统一后端
- 小程序不直接调用图片识别或大模型服务

## 7. 日志与失败状态

当前后端具备：

- 任务失败进入 `failed`
- preview 失败写日志
- 单张图片识别失败不拖垮整个 preview
- DOCX 生成失败进入 `failed`

部署前建议确认：

- 服务日志可持久化或可采集
- 失败日志可检索

## 8. 上线前回归

后端：

```powershell
cd C:\Users\wuzitian\WeChatProjects\miniprogram-2
python -m pytest backend\tests -q --tb=short
python -m compileall backend\app backend\tests -q
```

前端风险语法检查：

```powershell
Get-ChildItem -Path miniprogram -Recurse -Include *.ts,*.js | Select-String -Pattern '\?\.|\?\?'
```

## 9. 当前边界

- AI Planner 仍然只是影子/可采用布局源，不直接写 Word
- legacy fallback 保留，仅用于兼容旧路径
- 正式小程序域名仍需人工切换，不做运行时环境自动识别
