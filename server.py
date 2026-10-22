import json
import os
import re
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from gateway import OrderKuotaGateway

BASE_DIR = Path(__file__).resolve().parent
config_path = BASE_DIR / "config.json"
if not config_path.exists() and (BASE_DIR / "config.example.json").exists():
    config_path = BASE_DIR / "config.example.json"
gateway = OrderKuotaGateway(config_path)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Payment Gateway - OrderKuota Dynamic QRIS</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #090d16;
      color: #f1f5f9;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .container {
      max-width: 440px;
      width: 100%;
    }
    .card {
      background: #131b2e;
      border: 1px solid #1e293b;
      border-radius: 20px;
      padding: 28px;
      text-align: center;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
      position: relative;
      overflow: hidden;
    }
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      padding: 6px 14px;
      border-radius: 9999px;
      margin-bottom: 16px;
      transition: all 0.3s ease;
    }
    .status-badge.wp {
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.3);
    }
    .status-badge.ok {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .status-badge.rm {
      background: rgba(239, 68, 68, 0.15);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.3);
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
    }
    .status-badge.wp .status-dot {
      background: #fbbf24;
      box-shadow: 0 0 10px #fbbf24;
      animation: pulse 1.5s infinite;
    }
    .status-badge.ok .status-dot {
      background: #34d399;
      box-shadow: 0 0 10px #34d399;
    }
    .status-badge.rm .status-dot {
      background: #f87171;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(1.2); }
    }
    .title {
      font-size: 22px;
      font-weight: 700;
      color: #ffffff;
    }
    .subtitle {
      font-size: 13px;
      color: #94a3b8;
      margin-top: 4px;
      margin-bottom: 20px;
    }
    .amount-box {
      background: #0a0f1d;
      border: 1px solid #1e293b;
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 20px;
    }
    .amount-label {
      font-size: 12px;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .amount-val {
      font-size: 32px;
      font-weight: 800;
      color: #10b981;
      margin-top: 4px;
    }
    .amount-note {
      font-size: 11px;
      color: #ef4444;
      margin-top: 4px;
      font-weight: 500;
    }
    .qr-frame {
      position: relative;
      background: #ffffff;
      border-radius: 14px;
      padding: 14px;
      display: inline-block;
      margin-bottom: 20px;
      transition: all 0.3s ease;
    }
    .qr-frame svg, .qr-frame img {
      display: block;
      width: 250px;
      height: 250px;
    }
    .qr-frame.dimmed {
      filter: grayscale(1) opacity(0.2);
    }
    .qr-overlay {
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      display: none;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 20px;
      border-radius: 14px;
    }
    .qr-overlay.visible {
      display: flex;
    }
    .qr-overlay.ok-state {
      background: rgba(16, 185, 129, 0.95);
      color: #ffffff;
    }
    .qr-overlay.rm-state {
      background: rgba(239, 68, 68, 0.92);
      color: #ffffff;
    }
    .qr-overlay-icon {
      font-size: 48px;
      margin-bottom: 8px;
    }
    .qr-overlay-text {
      font-weight: 700;
      font-size: 16px;
    }
    .meta-box {
      background: #0a0f1d;
      border: 1px solid #1e293b;
      border-radius: 12px;
      padding: 14px 16px;
      font-size: 12px;
      color: #94a3b8;
      text-align: left;
      line-height: 1.9;
      margin-bottom: 20px;
    }
    .meta-row {
      display: flex;
      justify-content: space-between;
    }
    .meta-row span.val {
      color: #f1f5f9;
      font-weight: 600;
    }
    .btn-group {
      display: flex;
      gap: 10px;
    }
    button {
      flex: 1;
      padding: 12px;
      border-radius: 10px;
      border: none;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.2s;
    }
    button:hover { opacity: 0.9; }
    .btn-primary { background: #3b82f6; color: #fff; }
    .btn-danger { background: #ef4444; color: #fff; }
    .btn-secondary { background: #334155; color: #f1f5f9; }
    .new-tx-box {
      margin-top: 16px;
      background: #131b2e;
      border: 1px solid #1e293b;
      border-radius: 14px;
      padding: 16px;
      display: flex;
      gap: 10px;
    }
    .new-tx-box input {
      flex: 1;
      background: #0a0f1d;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 10px 14px;
      color: #fff;
      font-size: 14px;
      outline: none;
    }
    .new-tx-box input:focus { border-color: #3b82f6; }
    .poll-indicator {
      font-size: 11px;
      color: #64748b;
      margin-top: 12px;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div id="statusBadge" class="status-badge wp">
        <span class="status-dot"></span>
        <span id="statusLabel">Memeriksa Status...</span>
      </div>

      <h1 class="title">TOPUP ORDERKUOTA</h1>
      <p class="subtitle">Scan QRIS menggunakan BCA, Mandiri, Dana, GoPay, OVO, dll</p>

      <div class="amount-box">
        <div class="amount-label">Total Tagihan (Termasuk Kode Unik)</div>
        <div id="amountDisplay" class="amount-val">Rp ...</div>
        <div class="amount-note">Bayar persis sesuai nominal agar otomatis diverifikasi</div>
      </div>

      <div class="qr-frame" id="qrFrame">
        <div id="qrContent"></div>
        <div class="qr-overlay" id="qrOverlay">
          <div class="qr-overlay-icon" id="overlayIcon"></div>
          <div class="qr-overlay-text" id="overlayText"></div>
        </div>
      </div>

      <div class="meta-box">
        <div class="meta-row"><span>ID Deposit</span><span class="val" id="metaId">-</span></div>
        <div class="meta-row"><span>Invoice ID</span><span class="val" id="metaInvoice">-</span></div>
        <div class="meta-row"><span>Metode</span><span class="val">Via Scan QRIS</span></div>
        <div class="meta-row"><span>Kedaluwarsa</span><span class="val" id="metaExpired">-</span></div>
      </div>

      <div class="btn-group">
        <button id="btnCancel" class="btn-danger" onclick="cancelCurrentDeposit()">Batalkan Tiket</button>
        <button class="btn-secondary" onclick="checkStatusManual()">Perbarui Status</button>
      </div>

      <div class="poll-indicator" id="pollIndicator">Sinkronisasi status realtime aktif (setiap 3 detik)</div>
    </div>

    <div class="new-tx-box">
      <input type="number" id="newAmount" placeholder="Nominal baru (misal: 10000)" min="10000" step="1000" value="10000">
      <button class="btn-primary" style="flex: initial; width: 140px;" onclick="createNewDeposit()">Buat QRIS Baru</button>
    </div>
  </div>

  <script>
    let currentDepositId = new URLSearchParams(window.location.search).get("id") || "__INITIAL_ID__";
    let pollInterval = null;

    function applyStatus(data) {
      document.getElementById("metaId").innerText = "#" + data.id;
      document.getElementById("metaInvoice").innerText = data.invoice_id || "-";
      document.getElementById("amountDisplay").innerText = "Rp " + (data.amount_str || Number(data.amount).toLocaleString("id-ID"));
      document.getElementById("metaExpired").innerText = data.expired_time || "-";

      const badge = document.getElementById("statusBadge");
      const label = document.getElementById("statusLabel");
      const frame = document.getElementById("qrFrame");
      const overlay = document.getElementById("qrOverlay");
      const overlayIcon = document.getElementById("overlayIcon");
      const overlayText = document.getElementById("overlayText");
      const btnCancel = document.getElementById("btnCancel");

      badge.className = "status-badge";
      overlay.className = "qr-overlay";
      frame.classList.remove("dimmed");

      if (data.status === "OK" || data.is_paid) {
        badge.classList.add("ok");
        label.innerText = "Pembayaran Berhasil / Lunas";
        frame.classList.add("dimmed");
        overlay.classList.add("visible", "ok-state");
        overlayIcon.innerText = "✓";
        overlayText.innerText = "Pembayaran Diterima!";
        btnCancel.style.display = "none";
        stopPolling("Pembayaran terverifikasi.");
      } else if (data.status === "RM") {
        badge.classList.add("rm");
        label.innerText = "Dibatalkan / Kadaluwarsa";
        frame.classList.add("dimmed");
        overlay.classList.add("visible", "rm-state");
        overlayIcon.innerText = "✕";
        overlayText.innerText = "Tiket Telah Dibatalkan";
        btnCancel.style.display = "none";
        stopPolling("Tiket dibatalkan.");
      } else if (data.status === "WP") {
        badge.classList.add("wp");
        label.innerText = "Menunggu Pembayaran";
        btnCancel.style.display = "block";
      } else {
        badge.classList.add("rm");
        label.innerText = "Status: " + data.status;
      }
    }

    async function fetchStatus() {
      if (!currentDepositId || currentDepositId === "0" || currentDepositId === "__INITIAL_ID__") return;
      try {
        const res = await fetch("/api/status/" + currentDepositId);
        if (!res.ok) return;
        const data = await res.json();
        applyStatus(data);
      } catch (err) {
        console.error(err);
      }
    }

    async function loadQrGraphic() {
      if (!currentDepositId || currentDepositId === "0" || currentDepositId === "__INITIAL_ID__") return;
      try {
        const res = await fetch("/api/qr/" + currentDepositId);
        if (res.ok) {
          const svgText = await res.text();
          document.getElementById("qrContent").innerHTML = svgText;
        }
      } catch (err) {
        console.error(err);
      }
    }

    function startPolling() {
      stopPolling();
      document.getElementById("pollIndicator").innerText = "Sinkronisasi status realtime aktif (setiap 3 detik)";
      fetchStatus();
      loadQrGraphic();
      pollInterval = setInterval(fetchStatus, 3000);
    }

    function stopPolling(reason) {
      if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
      }
      if (reason) {
        document.getElementById("pollIndicator").innerText = reason;
      }
    }

    function checkStatusManual() {
      fetchStatus();
    }

    async function cancelCurrentDeposit() {
      if (!confirm("Yakin ingin membatalkan tiket deposit #" + currentDepositId + "?")) return;
      try {
        const res = await fetch("/api/cancel/" + currentDepositId, { method: "POST" });
        const data = await res.json();
        if (data.success) {
          fetchStatus();
        } else {
          alert("Gagal membatalkan tiket.");
        }
      } catch (err) {
        alert("Kesalahan koneksi.");
      }
    }

    async function createNewDeposit() {
      const amount = parseInt(document.getElementById("newAmount").value, 10);
      if (!amount || amount < 10000) {
        alert("Minimal nominal adalah Rp 10.000");
        return;
      }
      try {
        document.getElementById("pollIndicator").innerText = "Membuat tiket deposit baru...";
        const res = await fetch("/api/create", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ amount })
        });
        const data = await res.json();
        if (data.deposit_id) {
          currentDepositId = data.deposit_id;
          window.history.pushState({}, "", "/?id=" + currentDepositId);
          startPolling();
        } else {
          alert("Gagal membuat deposit: " + (data.error || "Unknown"));
        }
      } catch (err) {
        alert("Gagal menghubungi server gateway.");
      }
    }

    window.onload = startPolling;
  </script>
</body>
</html>
"""

def generate_svg_qr(qris_string: str, out_path: Path) -> bool:
    try:
        cmd = ["npx", "--yes", "qrcode", "-t", "svg", "-o", str(out_path), qris_string]
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except Exception:
        return False

class GatewayRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict, status: int = 200) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, html: str, status: int = 200) -> None:
        raw = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_svg(self, svg_content: str, status: int = 200) -> None:
        raw = svg_content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            deposit_id = query.get("id", ["94047657"])[0]
            rendered_html = HTML_TEMPLATE.replace("__INITIAL_ID__", deposit_id)
            self._send_html(rendered_html)
            return

        status_match = re.match(r"^/api/status/(\d+)$", path)
        if status_match:
            dep_id = int(status_match.group(1))
            try:
                data = gateway.check_status(dep_id)
                self._send_json(data)
            except Exception as err:
                self._send_json({"error": "Gagal memeriksa status deposit", "detail": str(err)}, 500)
            return

        qr_match = re.match(r"^/api/qr/(\d+)$", path)
        if qr_match:
            dep_id = int(qr_match.group(1))
            svg_file = BASE_DIR / f"qris_{dep_id}.svg"
            if not svg_file.exists():
                status_info = gateway.check_status(dep_id)
                amount = status_info.get("amount", 10000)
                from gateway import build_dynamic_qris
                qris_str = build_dynamic_qris(dep_id, amount)
                generate_svg_qr(qris_str, svg_file)

            if svg_file.exists():
                with open(svg_file, "r", encoding="utf-8") as f:
                    self._send_svg(f.read())
            else:
                self._send_json({"error": "QR SVG tidak ditemukan"}, 404)
            return

        self._send_json({"error": "Endpoint tidak ditemukan"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/create":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                payload = json.loads(body)
                amount = int(payload.get("amount", 10000))
                created = gateway.create_deposit(amount)
                dep_id = created["deposit_id"]
                svg_file = BASE_DIR / f"qris_{dep_id}.svg"
                generate_svg_qr(created["qris_string"], svg_file)
                self._send_json(created, 201)
            except Exception as err:
                self._send_json({"error": "Gagal membuat deposit", "detail": str(err)}, 500)
            return

        cancel_match = re.match(r"^/api/cancel/(\d+)$", path)
        if cancel_match:
            dep_id = int(cancel_match.group(1))
            try:
                ok = gateway.cancel_deposit(dep_id)
                self._send_json({"success": ok, "deposit_id": dep_id})
            except Exception as err:
                self._send_json({"error": "Gagal membatalkan deposit", "detail": str(err)}, 500)
            return

        self._send_json({"error": "Endpoint tidak ditemukan"}, 404)

def run_server(port: int = 8000) -> None:
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, GatewayRequestHandler)
    print(f"Gateway Server running at http://127.0.0.1:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == "__main__":
    run_server(8000)
