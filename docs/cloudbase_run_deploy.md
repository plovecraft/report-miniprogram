# CloudBase Run 部署说明

## 目标

将当前 FastAPI 后端部署到微信云托管，获得可用于小程序发布的 HTTPS 后端地址。当前阶段推荐使用云托管 HTTPS 访问域名，保留现有 `wx.uploadFile` / `wx.downloadFile` 流程。

## 已准备的文件

- `Dockerfile`：云托管容器入口，监听 `PORT` 环境变量。
- `.dockerignore`：排除 `.env`、运行数据、密钥和缓存。
- `cloudbase.json`：CloudBase Framework 部署模板，需替换 `envId`。
- `miniprogram/config.ts`：支持在 ECS 开发地址和 CloudBase HTTPS 地址之间切换。

## CloudBase 控制台配置

1. 开通云开发环境。
2. 进入云托管，创建或更新服务 `flask-5pvg`。
3. 构建方式选择 Dockerfile。
4. 容器端口使用 `8000`。
5. 配置环境变量：

```env
STORAGE_DIR=/app/backend/storage
OUTPUT_DIR=/app/backend/storage/outputs
CORS_ORIGINS=*
MAX_UPLOAD_MB=100
LLM_BASE_URL=https://node-hk.sssaicodeapi.com/api/v1
LLM_API_KEY=填入真实 key
LLM_MODEL=gpt-5.4-mini
LLM_TIMEOUT=180
LLM_TEMPERATURE=0.2
LLM_RESPONSE_LOG_CHARS=8000
LLM_STREAM=0
LLM_SEND_TEMPERATURE=0
VISION_RECOGNITION_ENABLED=1
VISION_RECOGNITION_TIMEOUT=60
VISION_RECOGNITION_TEMPERATURE=0
VISION_RECOGNITION_REVIEW_THRESHOLD=0.55
DOC_EXTRACTION_TIMEOUT=20
TABLE_FEATURE_ENABLED=0
```

不要把真实 `LLM_API_KEY` 写入仓库。

## 小程序配置

当前云托管环境：

```text
envId: prod-d3gn7yz2311f3f9ce
serviceName: flask-5pvg
publicUrl: https://flask-5pvg-278832-6-1445646635.sh.run.tcloudbase.com
```

当前控制台显示的 Flask 模板只提供 `/api/count`，还不是本项目后端。部署本项目 Dockerfile 后，必须确认 `/health` 返回正常。

部署成功后，复制云托管提供的 HTTPS 访问地址，更新：

```ts
export const CLOUDBASE_HTTP_BASE_URL = 'https://flask-5pvg-278832-6-1445646635.sh.run.tcloudbase.com'
export const USE_CLOUDBASE_HTTP = true
```

开发阶段可继续保持：

```ts
export const USE_CLOUDBASE_HTTP = false
export const API_BASE_URL = 'http://47.99.57.73'
```

## 验证

部署后访问：

```text
https://你的云托管访问域名/health
```

期望返回：

```json
{"status":"ok","llmConfigured":true}
```

然后在微信开发者工具中重新编译小程序，完整测试：

1. 微信登录。
2. 上传材料。
3. 预览图片识别结果。
4. 采用或恢复 AI 布局。
5. 确认生成 DOCX。
6. 下载并打开 DOCX。

## 当前限制

当前版本仍将任务文件写入容器本地存储。云托管容器重启或扩缩容时，历史任务可能丢失。发布初期建议：

- `minNum=1`
- `maxNum=1` 或小流量阶段保持单实例
- 避免长时间依赖历史任务

后续稳定版应将上传材料和输出 DOCX 迁移到 CloudBase 云存储，并将任务元数据迁移到 CloudBase 数据库。
