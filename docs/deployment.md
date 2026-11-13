# 部署指南（單機版 / Docker / 雲端容器）

本系統支援兩種執行方式，共用同一份程式碼：

| 部署方式 | 資料庫 | 截圖儲存 | 攝影機來源 | 適用情境 |
|---|---|---|---|---|
| **警衛室單機版**（`uv run gate serve`） | 本機 SQLite（`data/app.db`） | 本機 `data/snapshots/` | RTSP / USB / 第三方 IP Cam / 手機掃碼推流 | 社區現場離線運作、連接實體柵欄繼電器 |
| **雲端容器版**（Docker / Cloud Run / VPS） | 外部 MySQL 8.4（SSL） | 外部掛載磁碟區 / 儲存桶 | 手機掃碼推流（HTTPS）、上傳圖片、模擬辨識 | 遠端測試、手機/電腦展示、無實體柵欄環境 |

---

## 一、環境變數完整說明

後端透過 [config.py](../backend/app/config.py) 讀取環境變數（本機也可放在專案根目錄 `.env` 檔，切勿將含真實密碼的 `.env` 提交進 Git）：

| 變數名稱 | 必填 | 預設值 | 說明 |
|---|---|---|---|
| `DATABASE_URL`（或 `GATE_DATABASE_URL`） | 雲端建議 | 本機 `sqlite:///data/app.db` | 資料庫連線字串。支援 `mysql://user:pass@host:3306/db?sslaccept=accept_invalid_certs`，[db.py](../backend/app/db.py) 會自動轉成 `mysql+pymysql://` 並啟用 TLS |
| `GATE_DATA_DIR` | 否 | `./data`（Docker 內 `/app/data`） | 本機 SQLite、金鑰、SSL 自簽憑證等資料目錄 |
| `GATE_SNAPSHOT_DIR`（或 `SNAPSHOT_DIR`） | 雲端建議 | `<GATE_DATA_DIR>/snapshots` | 截圖儲存路徑。可指定為外部掛載之磁碟目錄 |
| `GATE_ADMIN_USERNAME` | 容器建議 | 無 | 啟動時若此帳號不存在，自動建立此管理員帳號 |
| `GATE_ADMIN_PASSWORD` | 容器建議 | 無 | 上述自動建立帳號的密碼（至少 6 碼） |
| `GATE_ADMIN_DISPLAY_NAME` | 否 | `管理員` | 自動建立帳號的顯示名稱 |
| `GATE_SECRET_KEY` | 雲端建議 | 自動產生於 `data/secret.key` | Session Cookie 簽章金鑰。雲端未設定時每次重啟會重產金鑰導致使用者被登出 |
| `GATE_SESSION_MAX_AGE_SEC` | 否 | `43200`（12 小時） | 登入 Session 有效秒數 |
| `GATE_HOST` / `GATE_PORT` / `PORT` | 否 | `127.0.0.1:8000`（Docker `0.0.0.0:${PORT:-8000}`） | 服務監聽位址與埠號 |
| `GATE_ENABLE_WORKERS` | 否 | `true` | 是否啟動背景攝影機擷取與排程（測試環境設 `false`） |
| `GATE_ALPR_DETECTOR_MODEL` | 否 | `yolo-v9-t-384-license-plate-end2end` | 車牌偵測 ONNX 模型名稱 |
| `GATE_ALPR_OCR_MODEL` | 否 | `cct-xs-v2-global-model` | 車牌 OCR ONNX 模型名稱 |

---

## 二、雲端容器與外部資料庫設定 (MySQL 8.4)

若將系統部署至雲端容器（如 Google Cloud Run、AWS ECS、個人 VPS 等）：

### 1. 資料庫設定

1. 準備一組 MySQL 8.4 資料庫。
2. 設定 `DATABASE_URL` 環境變數：
   ```env
   DATABASE_URL=mysql://<資料庫帳號>:<資料庫密碼>@<DB_HOST>:3306/<資料庫名稱>?sslaccept=accept_invalid_certs
   ```

### 2. 環境變數（`.env` 範本）

在容器執行環境中設定以下環境變數：

```env
DATABASE_URL=mysql://<資料庫帳號>:<資料庫密碼>@<DB_HOST>:3306/<資料庫名稱>?sslaccept=accept_invalid_certs
GATE_SNAPSHOT_DIR=/app/data/snapshots
GATE_ADMIN_USERNAME=admin
GATE_ADMIN_PASSWORD=<登入密碼至少6碼>
GATE_ADMIN_DISPLAY_NAME=管理員
GATE_SECRET_KEY=<任意32字元以上隨機字串>
```

---

## 三、Dockerfile 與本機容器驗證

[Dockerfile](../Dockerfile) 採用兩階段建置：

1. **Stage 1（`node:22-slim`）**：執行 `npm ci` 與 `npm run build`，將 Vue 3 前端編譯輸出至 `backend/app/static/`。
2. **Stage 2（`python:3.12-slim`）**：安裝 OpenCV / ONNX Runtime 所需的 `libglib2.0-0` 與 `libgomp1`，安裝專案套件後以 `uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}` 啟動。

### 本機建置與試跑 Docker 容器

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

## 四、攝影機與常見問題排解

1. **雲端環境如何用手機測試車牌辨識？**
   - 推薦使用 **「📱 手機鏡頭」QR Code**（在即時監控或車道設定點開，手機掃碼後由手機瀏覽器直接將影格推流到後端；雲端環境若具備 HTTPS 即可直接授權相機），或在即時監控使用 **「上傳圖片辨識」／「模擬辨識」**。
   - 第三方 App（如 IP Webcam `http://手機IP:8080/video`）是由後端主動連線拉取，僅適用於「後端跑在與手機同一個區網（本機單機版）」時。
2. **首次辨識車牌速度較慢？**
   - 為加快容器啟動，[main.py](../backend/app/main.py) 僅在車道已有設定 `source_url` 時才於啟動時預載 ONNX 模型；若無設定串流來源，首次執行圖片辨識或手機掃碼推流時才會自動下載並載入模型（約數十 MB）。
3. **單機版與雲端版的實體柵欄差異**
   - 實體 HTTP 繼電器（ESP32 / Shelly）與 Modbus TCP 繼電器多半位於社區內網，正式社區現場請以警衛室單機版（`uv run gate serve`）運作；雲端版預設使用「模擬柵欄」。
