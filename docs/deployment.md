# 部署指南（單機版 / Docker / GitLab CI + aiBorn）

本系統支援兩種執行方式，共用同一份程式碼：

| 部署方式 | 資料庫 | 截圖儲存 | 攝影機來源 | 適用情境 |
|---|---|---|---|---|
| **警衛室單機版**（`uv run gate serve`） | 本機 SQLite（`data/app.db`） | 本機 `data/snapshots/` | RTSP / USB / 第三方 IP Cam / 手機掃碼推流 | 社區現場離線運作、連接實體柵欄繼電器 |
| **aiBorn 雲端容器**（Docker + GitLab CI） | aiBorn 代管 MySQL 8.4（SSL） | GCS 磁碟區（`/mnt/gcs/snapshots`） | 手機掃碼推流（HTTPS）、上傳圖片、模擬辨識 | 遠端測試、手機/電腦展示、無實體柵欄環境 |

---

## 一、環境變數完整說明

後端透過 [config.py](../backend/app/config.py) 讀取環境變數（本機也可放在專案根目錄 `.env` 檔，切勿將含真實密碼的 `.env` 提交進 Git）：

| 變數名稱 | 必填 | 預設值 | 說明 |
|---|---|---|---|
| `DATABASE_URL`（或 `GATE_DATABASE_URL`） | 雲端必填 | 本機 `sqlite:///data/app.db` | 資料庫連線字串。支援 `mysql://user:pass@host:3306/db?sslaccept=accept_invalid_certs`，[db.py](../backend/app/db.py) 會自動轉成 `mysql+pymysql://` 並啟用 TLS |
| `GATE_DATA_DIR` | 否 | `./data`（Docker 內 `/app/data`） | 本機 SQLite、金鑰、SSL 自簽憑證等資料目錄 |
| `GATE_SNAPSHOT_DIR`（或 `SNAPSHOT_DIR`） | 雲端建議 | `<GATE_DATA_DIR>/snapshots` | 截圖儲存路徑。使用 aiBorn 預設 GCS 掛載點 `/mnt/gcs` 時，請設為 `/mnt/gcs/snapshots` |
| `GATE_ADMIN_USERNAME` | 容器必填 | 無 | 啟動時若此帳號不存在，自動建立此管理員帳號 |
| `GATE_ADMIN_PASSWORD` | 容器必填 | 無 | 上述自動建立帳號的密碼（至少 6 碼） |
| `GATE_ADMIN_DISPLAY_NAME` | 否 | `管理員` | 自動建立帳號的顯示名稱 |
| `GATE_SECRET_KEY` | 雲端建議 | 自動產生於 `data/secret.key` | Session Cookie 簽章金鑰。雲端未設定時每次重啟會重產金鑰導致使用者被登出 |
| `GATE_SESSION_MAX_AGE_SEC` | 否 | `43200`（12 小時） | 登入 Session 有效秒數 |
| `GATE_HOST` / `GATE_PORT` / `PORT` | 否 | `127.0.0.1:8000`（Docker `0.0.0.0:${PORT:-8000}`） | 服務監聽位址與埠號 |
| `GATE_ENABLE_WORKERS` | 否 | `true` | 是否啟動背景攝影機擷取與排程（測試環境設 `false`） |
| `GATE_ALPR_DETECTOR_MODEL` | 否 | `yolo-v9-t-384-license-plate-end2end` | 車牌偵測 ONNX 模型名稱 |
| `GATE_ALPR_OCR_MODEL` | 否 | `cct-xs-v2-global-model` | 車牌 OCR ONNX 模型名稱 |

---

## 二、aiBorn 平台部署設定

### 1. 建立與設定資料庫（MySQL 8.4）

1. 在 aiBorn 專案設定頁點擊 **「建立資料庫」**。
2. 取得平台提供的 `DATABASE_URL` 範例與「資料庫密碼」（點眼睛圖示複製），將 `<密碼>` 替換成真實密碼。

> [!IMPORTANT]
> aiBorn 的「磁碟區」是透過 GCS FUSE 掛載的 Cloud Storage Bucket，不支援 SQLite `WAL` 模式的檔案鎖定與記憶體映射，因此雲端部署**必須使用 MySQL**，不可把 SQLite 放在 `/mnt/gcs`。

### 2. 建立與設定磁碟區（截圖儲存）

1. 在 aiBorn 點擊建立 **「磁碟區」**。
2. 容器掛載路徑維持預設 **`/mnt/gcs`**（配合環境變數 `GATE_SNAPSHOT_DIR=/mnt/gcs/snapshots`），或改為 `/app/data/snapshots`（此時可省略 `GATE_SNAPSHOT_DIR`）。
3. 按 **「儲存掛載路徑」**。

### 3. 設定環境變數（`.env` 範本）

在 aiBorn **「環境變數」** 區點擊 **「貼上 .env」**，填入以下內容（將 `<資料庫密碼>`、`<登入密碼>`、`<隨機金鑰>` 換成實際值）：

```env
DATABASE_URL=mysql://<資料庫帳號>:<資料庫密碼>@<DB_HOST>:3306/<資料庫名稱>?sslaccept=accept_invalid_certs
GATE_SNAPSHOT_DIR=/mnt/gcs/snapshots
GATE_ADMIN_USERNAME=admin
GATE_ADMIN_PASSWORD=<登入密碼至少6碼>
GATE_ADMIN_DISPLAY_NAME=管理員
GATE_SECRET_KEY=<任意32字元以上隨機字串>
```

儲存後再進行部署；首次登入後建議從側邊欄左下角 **「改密碼」** 更換管理員密碼。

---

## 三、GitLab CI/CD 自動部署設定

GitLab 專案：`https://gitlab1.program.com.tw/appinfo/community-gate`

### 1. GitLab 變數與保護分支

到 GitLab 專案 **Settings → CI/CD → Variables** 新增：

| 欄位 | 設定值 |
|---|---|
| Key | `AIBORN_DEPLOY_TOKEN` |
| Value | 由 aiBorn「部署權杖」產生的 `abn_...` 權杖 |
| Visibility | **Masked** |
| Flags | **Protect variable**（已勾選，預設分支 `main` 必須為 Protected branch） |

### 2. Pipeline 流程（[.gitlab-ci.yml](../.gitlab-ci.yml)）

每次推送（push）到預設分支 `main` 時自動觸發 `deploy_aiborn` job：

1. 使用 `git archive --format=zip -o src.zip HEAD` 將已提交程式碼打包為 `src.zip`。
2. 以 `Authorization: Bearer $AIBORN_DEPLOY_TOKEN` 上傳至 `https://aiborn.program.com.tw/api/ci/v1/deploy`。
3. 以 `grep -q "AIBORN_STATUS=success" aiborn-deploy.log` 檢查部署結果。

> 若只修改文件且不想觸發重新部署，可在 commit message 加上 `[ci skip]`。

---

## 四、Dockerfile 與本機容器驗證

[Dockerfile](../Dockerfile) 採用兩階段建置：

1. **Stage 1（`node:22-slim`）**：執行 `npm ci` 與 `npm run build`，將 Vue 3 前端編譯輸出至 `backend/app/static/`。
2. **Stage 2（`python:3.12-slim`）**：安裝 OpenCV / ONNX Runtime 所需的 `libglib2.0-0` 與 `libgomp1`，安裝專案套件後以 `uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}` 啟動。

### 本機試跑 Docker 容器

```bash
# 建置映像
docker build -t community-gate:local .

# 啟動（使用本機資料夾保存 SQLite 與截圖）
docker run --rm -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -e GATE_ADMIN_USERNAME=admin \
  -e GATE_ADMIN_PASSWORD=change-me-123 \
  community-gate:local
```

啟動後開啟 `http://127.0.0.1:8000` 即可使用。

---

## 五、攝影機與常見問題排解

1. **雲端環境如何用手機測試車牌辨識？**
   - 推薦使用 **「📱 手機鏡頭」QR Code**（在即時監控或車道設定點開，手機掃碼後由手機瀏覽器直接將影格推流到後端，aiBorn 自帶 HTTPS 即可直接授權相機），或在即時監控使用 **「上傳圖片辨識」／「模擬辨識」**。
   - 第三方 App（如 IP Webcam `http://手機IP:8080/video`）是由後端主動連線拉取，僅適用於「後端跑在與手機同一個區網（本機單機版）」時。
2. **為什麼部署上線失敗或啟動後找不到帳號？**
   - 確認 aiBorn 已設定 `DATABASE_URL`、`GATE_ADMIN_USERNAME` 與 `GATE_ADMIN_PASSWORD`，且設定完環境變數後有觸發重新部署。
3. **首次辨識車牌速度較慢？**
   - 為加快容器啟動，[main.py](../backend/app/main.py) 僅在車道已有設定 `source_url` 時才於啟動時預載 ONNX 模型；若無設定串流來源，首次執行圖片辨識或手機掃碼推流時才會自動下載並載入模型（約數十 MB）。
4. **單機版與雲端版的實體柵欄差異**
   - 實體 HTTP 繼電器（ESP32 / Shelly）與 Modbus TCP 繼電器多半位於社區內網，正式社區現場請以警衛室單機版（`uv run gate serve`）運作；雲端版預設使用「模擬柵欄」。
