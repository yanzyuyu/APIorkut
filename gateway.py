import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

def calculate_crc16(payload: str) -> str:
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"

def build_dynamic_qris(deposit_id: int, amount: int, date_obj: datetime | None = None) -> str:
    if date_obj is None:
        date_obj = datetime.now()
    
    date_str = date_obj.strftime("%Y%m%d")

    def tlv(tag: str, val: str) -> str:
        return f"{tag}{len(val):02d}{val}"

    sub62 = (
        tlv("01", "MBA036LV")
        + tlv("06", str(deposit_id))
        + tlv("07", "A01")
        + tlv("08", "POSP")
        + tlv("99", f"0002000108{date_str}")
    )

    amount_str = f"{amount}.00"
    payload = (
        tlv("00", "01")
        + tlv("01", "12")
        + tlv("26", "0016COM.NOBUBANK.WWW01189360050300000879140214013276229442080303UBE")
        + tlv("51", "0014ID.CO.QRIS.WWW0303UBE0215ID2024320684408")
        + tlv("52", "4812")
        + tlv("53", "360")
        + tlv("54", amount_str)
        + tlv("58", "ID")
        + tlv("59", "TOPUP ORDERKUOTA")
        + tlv("60", "MOJOKERTO")
        + tlv("61", "61352")
        + tlv("62", sub62)
        + "6304"
    )

    return payload + calculate_crc16(payload)

class OrderKuotaGateway:
    def __init__(self, config_path: str | Path | None = None) -> None:
        if config_path is None:
            config_path = Path(__file__).resolve().parent / "config.json"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.base_api_url = "https://app.orderkuota.com/api/v2/get"
        self.base_web_url = "https://app.orderkuota.com"

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}. Copy config.example.json to config.json and fill your credentials.")
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_config(self) -> None:
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

    def _get_cookie_header(self) -> str:
        parts = [
            f"PHPSESSID={self.config['phpsessid']}",
            f"csrf_cookie={self.config['csrf_token']}",
            f"user_id={self.config['user_id']}",
            f"user_key={self.config['user_key']}"
        ]
        return "; ".join(parts)

    def _get_api_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "okhttp/4.12.0",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "X-Safe-Device": "TRUE"
        }

    def _get_web_headers(self) -> dict[str, str]:
        headers = self._get_api_headers()
        headers["Cookie"] = self._get_cookie_header()
        return headers

    def sync_session_from_device(self) -> bool:
        device_id = self.config.get("device_id")
        adb_prefix = ["adb", "-s", device_id] if device_id else ["adb"]
        
        check_cmd = adb_prefix + ["get-state"]
        res = subprocess.run(check_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return False

        extract_cmd = adb_prefix + ["shell", "su", "-c", "cat /data/data/com.orderkuota.app/app_webview/Default/Cookies"]
        res = subprocess.run(extract_cmd, capture_output=True)
        if res.returncode != 0 or len(res.stdout) < 512:
            return False

        tmp_file = tempfile.NamedTemporaryFile(delete=False)
        tmp_name = tmp_file.name
        try:
            tmp_file.write(res.stdout)
            tmp_file.close()

            conn = sqlite3.connect(tmp_name)
            cursor = conn.cursor()
            rows = cursor.execute(
                "SELECT host_key, name, value FROM cookies WHERE host_key LIKE '%orderkuota.com%'"
            ).fetchall()
            conn.close()
        except Exception:
            return False
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

        updated = False
        for host, name, val in rows:
            if host == "app.orderkuota.com":
                if name == "PHPSESSID" and self.config.get("phpsessid") != val:
                    self.config["phpsessid"] = val
                    updated = True
                elif name == "csrf_cookie" and self.config.get("csrf_token") != val:
                    self.config["csrf_token"] = val
                    updated = True
                elif name == "user_key" and self.config.get("user_key") != val:
                    self.config["user_key"] = val
                    updated = True

        if updated:
            self._save_config()
        return True

    def create_deposit(self, amount: int) -> dict:
        if amount < 10000:
            raise ValueError("Minimal deposit adalah Rp 10.000")

        post_data = urllib.parse.urlencode({
            "csrf_token": self.config["csrf_token"],
            "amount": str(amount),
            "payment": "sinarmas",
            "submit": "deposit"
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_web_url}/akun/deposit",
            data=post_data,
            headers=self._get_web_headers()
        )

        deposit_id = None

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(req, timeout=15)
        except urllib.error.HTTPError as err:
            loc = err.headers.get("Location", "")
            match = re.search(r"/deposit/view/(\d+)", loc)
            if match:
                deposit_id = int(match.group(1))
        except Exception:
            pass

        if not deposit_id:
            history = self.get_history(1)
            if history and history[0].get("status") == "WP":
                deposit_id = history[0]["id"]
            else:
                raise RuntimeError("Gagal membuat deposit tiket")

        qr_trigger_req = urllib.request.Request(
            f"{self.base_web_url}/payment/sinarmas/get_qr/{deposit_id}",
            headers=self._get_web_headers()
        )
        try:
            with urllib.request.urlopen(qr_trigger_req, timeout=10) as resp:
                resp.read()
        except Exception:
            pass

        details = self.check_status(deposit_id)
        total_amount = details.get("amount", amount)

        date_str = details.get("date", "")
        parsed_date = None
        if date_str:
            try:
                parsed_date = datetime.strptime(date_str, "%d/%m/%Y %H:%M:%S")
            except ValueError:
                pass

        qris_string = build_dynamic_qris(deposit_id, total_amount, parsed_date)

        return {
            "deposit_id": deposit_id,
            "invoice_id": details.get("invoice_id", ""),
            "requested_amount": amount,
            "total_amount": total_amount,
            "fee": total_amount - amount,
            "qris_string": qris_string,
            "status": details.get("status", "WP"),
            "expired_time": details.get("expired_time", ""),
            "date": details.get("date", "")
        }

    def check_status(self, deposit_id: int) -> dict:
        payload = {
            "auth_username": self.config["auth_username"],
            "auth_token": self.config["auth_token"],
            "app_version_code": self.config["app_version_code"],
            "app_version_name": self.config["app_version_name"],
            "app_reg_id": "",
            "phone_model": self.config["phone_model"],
            "ui_mode": "light",
            "phone_android_version": self.config["phone_android_version"],
            "phone_uuid": self.config["phone_uuid"],
            "requests[1]": "payments",
            "requests[deposit_details][id]": str(deposit_id)
        }

        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(self.base_api_url, data=data, headers=self._get_api_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            results = body.get("deposit_details", {}).get("results", {})
            status = results.get("status", "UNKNOWN")
            return {
                "id": results.get("id", deposit_id),
                "invoice_id": results.get("invoice_id", ""),
                "amount": results.get("amount", 0),
                "amount_str": results.get("amount_str", ""),
                "status": status,
                "is_paid": status == "OK",
                "is_waiting_payment": status == "WP",
                "expired_time": results.get("expired_time", ""),
                "date": results.get("date", "")
            }

    def cancel_deposit(self, deposit_id: int) -> bool:
        post_data = urllib.parse.urlencode({
            "confirm": "1",
            "csrf_token": self.config["csrf_token"]
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_web_url}/akun/deposit/cancel/{deposit_id}",
            data=post_data,
            headers=self._get_web_headers()
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_history(self, page: int = 1) -> list[dict]:
        payload = {
            "auth_username": self.config["auth_username"],
            "auth_token": self.config["auth_token"],
            "app_version_code": self.config["app_version_code"],
            "app_version_name": self.config["app_version_name"],
            "app_reg_id": "",
            "phone_model": self.config["phone_model"],
            "ui_mode": "light",
            "phone_android_version": self.config["phone_android_version"],
            "phone_uuid": self.config["phone_uuid"],
            "requests[1]": "payments",
            "requests[deposit_history][page]": str(page)
        }

        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(self.base_api_url, data=data, headers=self._get_api_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("deposit_history", {}).get("results", [])

    def wait_for_payment(self, deposit_id: int, timeout_sec: int = 300, poll_interval: int = 5) -> dict:
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            res = self.check_status(deposit_id)
            if res.get("is_paid"):
                return res
            if res.get("status") in ("RM", "EXPIRED", "REFUND"):
                return res
            time.sleep(poll_interval)
        return self.check_status(deposit_id)

def main() -> None:
    parser = argparse.ArgumentParser(description="OrderKuota Automated QRIS Payment Gateway")
    parser.add_argument("--create", type=int, help="Buat tiket deposit QRIS dengan nominal tertentu")
    parser.add_argument("--status", type=int, help="Cek status deposit berdasarkan ID")
    parser.add_argument("--cancel", type=int, help="Batalkan deposit berdasarkan ID")
    parser.add_argument("--wait", type=int, help="Tunggu status deposit sampai terbayar (deposit ID)")
    parser.add_argument("--history", action="store_true", help="Lihat riwayat transaksi deposit")
    parser.add_argument("--sync", action="store_true", help="Sinkronisasi token & cookies dari perangkat Android via ADB")
    args = parser.parse_args()

    gateway = OrderKuotaGateway()

    if args.sync:
        ok = gateway.sync_session_from_device()
        print(f"[{'OK' if ok else 'FAIL'}] Sinkronisasi session dari device via ADB")
        return

    if args.create:
        res = gateway.create_deposit(args.create)
        print(json.dumps(res, indent=2))
        return

    if args.status:
        res = gateway.check_status(args.status)
        print(json.dumps(res, indent=2))
        return

    if args.cancel:
        ok = gateway.cancel_deposit(args.cancel)
        print(f"[{'OK' if ok else 'FAIL'}] Pembatalan deposit #{args.cancel}")
        return

    if args.wait:
        print(f"Menunggu pembayaran deposit #{args.wait}...")
        res = gateway.wait_for_payment(args.wait)
        print(json.dumps(res, indent=2))
        return

    if args.history:
        history = gateway.get_history(1)
        for h in history[:10]:
            print(f"#{h.get('id')} | {h.get('payment')} | Rp {h.get('amount_str')} | Status: {h.get('status')} | {h.get('date')}")
        return

    parser.print_help()

if __name__ == "__main__":
    main()
