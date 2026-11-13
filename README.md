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

## 用手機當 IP 攝影機（開發／測試）

讓手機與電腦連線到同一個 Wi‑Fi 後：

- **Android**：安裝 **IP Webcam** → 開啟「Start server」→ 取得串流網址：
  `http://<手機IP>:8080/video`
- **iPhone**：安裝 **DroidCam** 或 **IP Camera Lite** → 取得串流網址，例如：
  `http://<手機IP>:4747/video`

登入系統後進入 **「系統設定 → 車道與硬體」**，在入口／出口車道的「攝影機來源」填入上述網址（正式環境改填 `rtsp://...`，或填入本機測試影片路徑／USB 攝影機編號 `0`），儲存後立即連線。

> **機車辨識提醒**：台灣機車車牌較小且位於車尾，建議機車道攝影機低角度、近距離拍攝車尾，以確保辨識穩定度。

---

## 常用 CLI 指令

```bash
uv run gate create-admin                 # 新增操作帳號
uv run gate reset-password <username>    # 重設指定帳號密碼
uv run gate backup                       # 備份 data/app.db 到 data/backup_*.db
uv run gate serve --host 127.0.0.1 --port 8000
```

---

## 執行測試

```bash
uv run pytest -v
cd frontend && npm run type-check
```

---

## 容器化與 GitLab CI / aiBorn 自動部署

專案根目錄已附帶 [Dockerfile](Dockerfile) 與 [.gitlab-ci.yml](.gitlab-ci.yml)：

- **Dockerfile**：兩階段建置（Node 22 編譯 `frontend/` → Python 3.12 執行 `uvicorn`，監聽 `0.0.0.0:${PORT:-8000}`）。
- **容器自動建管理員帳號**：可在部署環境設定 `GATE_ADMIN_USERNAME` 與 `GATE_ADMIN_PASSWORD`（選填 `GATE_ADMIN_DISPLAY_NAME`），首次啟動時會自動建立該帳號。
- **GitLab CI/CD**：推送至預設分支（`main`）會打包 `HEAD` 並透過 `AIBORN_DEPLOY_TOKEN`（Masked + Protected）觸發 aiBorn 部署。

