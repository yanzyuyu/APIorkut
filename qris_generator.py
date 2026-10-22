import argparse
import json
import sys
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

def parse_tlv(raw_qris: str) -> list[tuple[str, str]]:
    elements = []
    idx = 0
    clean = raw_qris.strip()
    while idx + 4 <= len(clean):
        tag = clean[idx:idx + 2]
        len_str = clean[idx + 2:idx + 4]
        if not len_str.isdigit():
            break
        length = int(len_str)
        val = clean[idx + 4:idx + 4 + length]
        elements.append((tag, val))
        idx += 4 + length
    return elements

def extract_merchant_info(raw_qris: str) -> dict[str, str]:
    tlvs = parse_tlv(raw_qris)
    mapping = {
        "01": "initiation_point",
        "51": "merchant_account_51",
        "52": "merchant_category_code",
        "53": "currency_code",
        "54": "amount",
        "58": "country_code",
        "59": "merchant_name",
        "60": "merchant_city",
        "61": "postal_code"
    }
    info = {}
    for tag, val in tlvs:
        if tag in mapping:
            info[mapping[tag]] = val
            if tag == "51":
                sub_tlvs = parse_tlv(val)
                for s_tag, s_val in sub_tlvs:
                    if s_tag == "02":
                        info["nmid"] = s_val
    return info

def generate_dynamic_qris(static_qris: str, amount: int) -> str:
    if amount <= 0:
        raise ValueError("Nominal pembayaran harus lebih besar dari 0")
    
    clean = static_qris.strip()
    if not clean:
        raise ValueError("String QRIS tidak boleh kosong")
        
    crc_marker = "6304"
    if crc_marker in clean:
        clean = clean[:clean.rfind(crc_marker)]
        
    clean = clean.replace("010211", "010212")
    
    amount_str = str(int(amount))
    tag_54 = f"54{len(amount_str):02d}{amount_str}"
    
    country_marker = "5802ID"
    if country_marker in clean:
        idx_country = clean.find(country_marker)
        before_country = clean[:idx_country]
        if "54" in before_country:
            tag_idx = before_country.find("54")
            len_part = before_country[tag_idx + 2:tag_idx + 4]
            if len_part.isdigit():
                t_len = int(len_part)
                before_country = before_country[:tag_idx] + before_country[tag_idx + 4 + t_len:]
        payload = before_country + tag_54 + clean[idx_country:]
    else:
        payload = clean + tag_54
        
    payload_with_crc_tag = payload + crc_marker
    crc = calculate_crc16(payload_with_crc_tag)
    return payload_with_crc_tag + crc

def render_html_viewer(qris_string: str, merchant_info: dict[str, str], amount: int, output_path: Path):
    merchant_name = merchant_info.get("merchant_name", "QRIS Merchant")
    nmid = merchant_info.get("nmid", "ID0000000000000")
    formatted_amount = f"Rp {amount:,.0f}".replace(",", ".")
    
    html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QRIS Payment - {merchant_name}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background-color: #0f172a;
  color: #f8fafc;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  padding: 16px;
}}
.card {{
  background-color: #ffffff;
  color: #0f172a;
  border-radius: 20px;
  max-width: 420px;
  width: 100%;
  padding: 24px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
  text-align: center;
}}
.header-badge {{
  display: inline-block;
  background-color: #fee2e2;
  color: #b91c1c;
  font-weight: 700;
  font-size: 13px;
  padding: 4px 12px;
  border-radius: 9999px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin-bottom: 12px;
}}
.merchant-title {{
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 4px;
}}
.nmid-tag {{
  font-size: 13px;
  color: #64748b;
  margin-bottom: 16px;
}}
.qr-frame {{
  background-color: #ffffff;
  border: 2px solid #e2e8f0;
  border-radius: 16px;
  padding: 16px;
  display: flex;
  justify-content: center;
  align-items: center;
  margin-bottom: 16px;
}}
#qrcode {{
  width: 250px;
  height: 250px;
}}
.amount-box {{
  background-color: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px;
  margin-bottom: 16px;
}}
.amount-label {{
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
  margin-bottom: 2px;
}}
.amount-value {{
  font-size: 24px;
  font-weight: 800;
  color: #0f172a;
}}
.payload-box {{
  word-break: break-all;
  font-family: monospace;
  font-size: 11px;
  background-color: #f1f5f9;
  padding: 10px;
  border-radius: 8px;
  color: #475569;
  text-align: left;
  max-height: 80px;
  overflow-y: auto;
  border: 1px dashed #cbd5e1;
}}
.copy-btn {{
  margin-top: 12px;
  width: 100%;
  background-color: #0f172a;
  color: #ffffff;
  border: none;
  border-radius: 10px;
  padding: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s;
}}
.copy-btn:hover {{
  background-color: #334155;
}}
</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
</head>
<body>
<div class="card">
  <div class="header-badge">QRIS STANDAR PEMBAYARAN NASIONAL</div>
  <h1 class="merchant-title">{merchant_name}</h1>
  <div class="nmid-tag">NMID: {nmid}</div>
  <div class="qr-frame">
    <div id="qrcode"></div>
  </div>
  <div class="amount-box">
    <div class="amount-label">TOTAL PEMBAYARAN</div>
    <div class="amount-value">{formatted_amount}</div>
  </div>
  <div class="payload-box" id="rawPayload">{qris_string}</div>
  <button class="copy-btn" onclick="navigator.clipboard.writeText('{qris_string}').then(() => alert('String QRIS berhasil disalin!'))">Salin String QRIS</button>
</div>
<script>
  new QRCode(document.getElementById("qrcode"), {{
    text: "{qris_string}",
    width: 250,
    height: 250,
    correctLevel: QRCode.CorrectLevel.M
  }});
</script>
</body>
</html>"""
    output_path.write_text(html_content, encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description="Generator QRIS Dinamis (EMVCo QRCPS Standar BI)")
    parser.add_argument("-q", "--qris", help="String QRIS Statis atau path file teks berisi QRIS")
    parser.add_argument("-a", "--amount", type=int, help="Nominal pembayaran (contoh: 15000)")
    parser.add_argument("-o", "--output", help="Simpan string QRIS dinamis ke file teks")
    parser.add_argument("--html", help="Render halaman visual QR Code ke file HTML (contoh: payment.html)")
    parser.add_argument("--info", action="store_true", help="Tampilkan metadata merchant QRIS")
    
    args = parser.parse_args()
    
    qris_input = args.qris
    if not qris_input:
        if not sys.stdin.isatty():
            qris_input = sys.stdin.read().strip()
        else:
            print("Masukkan string QRIS Statis:")
            qris_input = input().strip()
            
    if Path(qris_input).is_file():
        qris_input = Path(qris_input).read_text(encoding="utf-8").strip()
        
    merchant_info = extract_merchant_info(qris_input)
    
    if args.info:
        print("\n=== METADATA MERCHANT QRIS ===")
        print(json.dumps(merchant_info, indent=2))
        if not args.amount:
            return
            
    if not args.amount:
        print("Masukkan nominal pembayaran (contoh: 10000):")
        amount = int(input().strip())
    else:
        amount = args.amount
        
    dynamic_qris = generate_dynamic_qris(qris_input, amount)
    
    print("\n=== QRIS DINAMIS BERHASIL DIBUAT ===")
    print(f"Merchant : {merchant_info.get('merchant_name', 'Unknown')}")
    print(f"Nominal  : Rp {amount:,.0f}".replace(",", "."))
    print(f"String   : {dynamic_qris}\n")
    
    if args.output:
        out_file = Path(args.output)
        out_file.write_text(dynamic_qris, encoding="utf-8")
        print(f"Disimpan ke: {out_file.resolve()}")
        
    if args.html:
        html_file = Path(args.html)
        render_html_viewer(dynamic_qris, merchant_info, amount, html_file)
        print(f"Halaman visual QR dibuat di: {html_file.resolve()}")

if __name__ == "__main__":
    main()
