# 社區出入管理系統（車牌辨識 + 訪客管理）單機版

專為社區日常出入設計的輕量級單機系統，移除大型停車場的收費與計費架構，聚焦在：

- **住戶白名單**（汽車／機車、有效期管理）自動放行
- **訪客管理**（預約／現場登記、授權時段、在場追蹤、逾時未離場警示）
- **黑名單與未登記車輛警示**（未登記車輛彈窗由警衛決定：放行一次／登記為訪客／拒絕）
- **進出紀錄與截圖**（依日期、車牌、車種、類別、車道查詢，匯出 CSV / Excel `.xlsx`）
- **可抽換柵欄控制**（模擬柵欄、HTTP 繼電器、Modbus TCP 繼電器預留）

---

## 系統需求

- Python 3.12（建議透過 `uv` 管理）
- Node.js（僅重新建置前端時需要；`backend/app/static/` 已包含建置後的靜態檔）

---

## 快速安裝與啟動

```bash
cd /Users/vince.huang/.gemini/antigravity/scratch/community-gate

# 1. 安裝後端依賴（含 fast-alpr ONNX Runtime）
uv sync

# 2. 建立第一組管理員／警衛帳號
uv run gate create-admin

# 3. 啟動本機伺服器（預設 http://127.0.0.1:8000）
uv run gate serve
```

> **離線說明**：首次執行車牌辨識時，`fast-alpr` 會自動下載輕量 ONNX 偵測與 OCR 模型（約數十 MB）；下載完成並快取後即可完全離線運作。

### 重新建置前端（如有修改 `frontend/`）

```bash
cd frontend
npm install
npm run build   # 會自動輸出至 backend/app/static/
```

---

## 用手機當攝影機（開發／測試）

### 方式一：掃描 QR Code 即開即用（推薦，免裝任何 App）

系統已內建手機瀏覽器相機推播功能：
1. 啟動伺服器並開啟 HTTPS 與區網監聽：
   ```bash
   uv run gate serve --host 0.0.0.0 --port 8000 --ssl
   ```
   *(系統會自動使用 `cryptography` 在 `data/` 產生自我簽署憑證)*
2. 電腦瀏覽器進入系統（例如 `https://192.168.x.x:8000`）。
3. 在 **「即時監控」** 或 **「系統設定 → 車道與硬體」** 點擊 **「📱 手機鏡頭」** 按鈕，畫面上會彈出 QR Code。
4. 使用手機相機掃描 QR Code 開啟連結：
   - 首次進入若提示「非私人連線 / 不安全」，點選 **「進階」** $\rightarrow$ **「繼續前往」**。
   - 允許相機存取權限。
5. 手機畫面立即變身為該車道的即時車牌辨識攝影機，後台監控畫面同步顯示串流與即時車牌辨識結果！

### 方式二：使用第三方 IP 攝影機 App

讓手機與電腦連線到同一個 Wi‑Fi 後：

- **Android**：安裝 **IP Webcam** → 開啟「Start server」→ 取得串流網址：
  `http://<手機IP>:8080/video`
- **iPhone**：安裝 **DroidCam** 或 **IP Camera Lite** → 取得串流網址，例如：
  `http://<手機IP>:4747/video`

在「系統設定 → 車道與硬體」將上述網址貼入「攝影機來源」即可。

> **機車辨識提醒**：台灣機車車牌較小且位於車尾，建議機車道攝影機低角度、近距離拍攝車尾，以確保辨識穩定度。

---

## 常用 CLI 指令

```bash
uv run gate create-admin                 # 新增操作帳號
uv run gate reset-password <username>    # 重設指定帳號密碼
uv run gate backup                       # 備份 data/app.db 到 data/backup_*.db
uv run gate serve --host 127.0.0.1 --port 8000
uv run gate serve --host 0.0.0.0 --port 8000 --ssl   # 開啟 HTTPS 支援手機掃碼攝影機
```

---

## 執行測試

```bash
uv run pytest -v
cd frontend && npm run type-check
```

---

## 容器化與 GitLab CI / aiBorn 自動部署

完整設定、環境變數列表、MySQL + GCS 磁碟區配置與排解步驟請參閱 [部署指南（docs/deployment.md）](docs/deployment.md)。

摘要：
- **Dockerfile**：兩階段建置（Node 22 編譯 `frontend/` → Python 3.12 執行 `uvicorn`，監聽 `0.0.0.0:${PORT:-8000}`）。
- **資料庫與磁碟區**：本機單機版預設使用 SQLite；雲端（aiBorn）支援透過 `DATABASE_URL` 連接 MySQL 8.4（SSL），並以 `GATE_SNAPSHOT_DIR` 將截圖存至磁碟區（如 `/mnt/gcs/snapshots`）。
- **自動建管理員帳號**：設定 `GATE_ADMIN_USERNAME` 與 `GATE_ADMIN_PASSWORD`（選填 `GATE_ADMIN_DISPLAY_NAME`），首次啟動時會自動建立該帳號。
- **GitLab CI/CD**：推送至預設分支（`main`）會由 [.gitlab-ci.yml](.gitlab-ci.yml) 打包 `HEAD` 並透過 `AIBORN_DEPLOY_TOKEN`（Masked + Protected）觸發 aiBorn 部署。


