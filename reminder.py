import requests
from datetime import datetime, timedelta
import os
import re

# ==================== CẤU HÌNH ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SHEET_ID = os.getenv('SHEET_ID')

SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    try:
        requests.post(url, json=payload, timeout=10)
        return True
    except Exception as e:
        print(f"Lỗi gửi tin nhắn: {e}")
        return False

def parse_date(date_str):
    if not date_str or date_str.strip() == '':
        return None
    try:
        if ' ' in date_str:
            date_str = date_str.split(' ')[0]
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        return None

def extract_phone(phone_str):
    if not phone_str or phone_str.strip() == '':
        return "Không có SDT"
    phone = re.sub(r'[^\d]', '', str(phone_str))
    if len(phone) >= 8:
        return phone[-8:]
    return str(phone_str)

def parse_package(package_str):
    if not package_str or package_str.strip() == '':
        return None, None
    package_str = str(package_str).strip().upper()
    match = re.search(r'(\d+)[\*x](\d+)', package_str, re.IGNORECASE)
    if match:
        price = int(match.group(1))
        months = int(match.group(2))
        return price, months
    return None, None

def calculate_due_date(original_date, months):
    """Tính lại Due Date dựa vào số tháng của gói cước"""
    if months == 2:
        # Sim 2 tháng: chỉ dùng 60 ngày, không phải 90 ngày
        # Giả sử original_date là ngày bắt đầu (cột NGAY)
        # Cần trừ đi 30 ngày so với cột 89
        new_due_date = original_date - timedelta(days=30)
        return new_due_date
    else:
        # Sim 3 tháng: giữ nguyên
        return original_date

def check_reminders():
    try:
        print("🔄 Đang đọc dữ liệu từ Google Sheets...")
        response = requests.get(SHEET_URL, timeout=30)
        
        if response.status_code != 200:
            send_telegram_message(f"❌ Lỗi: Không đọc được sheet")
            return
        
        lines = response.text.strip().split('\n')
        if len(lines) < 2:
            send_telegram_message("⚠️ Không có dữ liệu")
            return
        
        today = datetime.now().date()
        print(f"📅 Hôm nay: {today}")
        
        # Danh sách phân loại
        overdue = []        # QUÁ HẠN
        today_due = []      # HÔM NAY ĐẾN HẠN
        upcoming_7days = [] # SẮP ĐẾN HẠN (1-7 ngày)
        
        data_rows = lines[1:]
        
        for idx, row in enumerate(data_rows, start=2):
            if not row.strip():
                continue
            
            cols = row.split(',')
            if len(cols) < 13:
                continue
            
            try:
                ten_kh = cols[7].strip() if len(cols) > 7 else ''
                ngay_89_str = cols[2].strip() if len(cols) > 2 else ''
                ngay_str = cols[1].strip() if len(cols) > 1 else ''  # Cột NGAY để tính lại cho sim 2 tháng
                sdt_raw = cols[11].strip() if len(cols) > 11 else ''
                goi_cuoc_raw = cols[12].strip() if len(cols) > 12 else ''
                
                if not ten_kh or not ngay_89_str:
                    continue
                
                original_due_date = parse_date(ngay_89_str)
                if not original_due_date:
                    continue
                
                start_date = parse_date(ngay_str) if ngay_str else None
                phone = extract_phone(sdt_raw)
                price, months = parse_package(goi_cuoc_raw)
                
                # === XỬ LÝ ĐẶC BIỆT CHO SIM 2 THÁNG ===
                if months == 2 and start_date:
                    # Sim 2 tháng: tính lại due_date = start_date + 60 ngày
                    due_date = start_date + timedelta(days=60)
                    sim_type = "SIM 2 THÁNG (60 NGÀY)"
                    print(f"📌 {ten_kh}: Đã điều chỉnh ngày từ {original_due_date} -> {due_date} (sim 2 tháng)")
                else:
                    # Sim 3 tháng: giữ nguyên cột 89
                    due_date = original_due_date
                    sim_type = "SIM 3 THÁNG (90 NGÀY)"
                
                # Tính số ngày đến hạn
                days_until_due = (due_date - today).days
                
                # === PHÂN LOẠI ===
                if days_until_due < 0:
                    overdue.append({
                        'name': ten_kh.upper(),
                        'phone': phone,
                        'due_date': due_date,
                        'days_overdue': abs(days_until_due),
                        'package': goi_cuoc_raw,
                        'sim_type': sim_type,
                        'original_date': original_due_date
                    })
                    print(f"❌ QUÁ HẠN: {ten_kh} - {abs(days_until_due)} ngày (due: {due_date})")
                
                elif days_until_due == 0:
                    today_due.append({
                        'name': ten_kh.upper(),
                        'phone': phone,
                        'due_date': due_date,
                        'package': goi_cuoc_raw,
                        'sim_type': sim_type
                    })
                    print(f"📅 HÔM NAY: {ten_kh} (due: {due_date})")
                
                elif 1 <= days_until_due <= 7:
                    upcoming_7days.append({
                        'name': ten_kh.upper(),
                        'phone': phone,
                        'due_date': due_date,
                        'days_left': days_until_due,
                        'package': goi_cuoc_raw,
                        'sim_type': sim_type
                    })
                    print(f"⏰ Sắp đến hạn: {ten_kh} - còn {days_until_due} ngày (due: {due_date})")
                
            except Exception as e:
                print(f"⚠️ Lỗi dòng {idx}: {e}")
                continue
        
        # ==================== TẠO TIN NHẮN ====================
        message = "🔔 <b>BÁO CÁO CÔNG VIỆC SIM</b> 🔔\n"
        message += f"📅 {today.strftime('%d/%m/%Y')}\n"
        message += "━" * 35 + "\n\n"
        
        # 1. QUÁ HẠN
        if overdue:
            message += "🚨 <b>QUÁ HẠN - CẦN XỬ LÝ NGAY</b> 🚨\n\n"
            for item in overdue:
                message += f"🔥 <b>{item['name']}</b>\n"
                message += f"   📱 {item['phone']}\n"
                message += f"   📅 Hết hạn: {item['due_date']}\n"
                message += f"   ⚠️ QUÁ HẠN {item['days_overdue']} NGÀY\n"
                message += f"   📦 {item['package']} - {item['sim_type']}\n"
                if 'original_date' in item and item['original_date'] != item['due_date']:
                    message += f"   📍 (Đã điều chỉnh từ {item['original_date']})\n"
                message += "\n"
        
        # 2. HÔM NAY ĐẾN HẠN
        if today_due:
            message += "📅 <b>HÔM NAY ĐẾN HẠN</b> 📅\n\n"
            for item in today_due:
                message += f"📌 <b>{item['name']}</b>\n"
                message += f"   📱 {item['phone']}\n"
                message += f"   📅 Đến hạn: {item['due_date']} - HÔM NAY\n"
                message += f"   📦 {item['package']} - {item['sim_type']}\n\n"
        
        # 3. SẮP ĐẾN HẠN
        if upcoming_7days:
            message += "⏰ <b>CÔNG VIỆC SẮP ĐẾN HẠN (TRONG 7 NGÀY TỚI)</b> ⏰\n\n"
            for item in upcoming_7days:
                message += f"📋 <b>{item['name']}</b>\n"
                message += f"   📱 {item['phone']}\n"
                message += f"   📅 Đến hạn: {item['due_date']}\n"
                message += f"   ⏰ Còn {item['days_left']} ngày\n"
                message += f"   📦 {item['package']} - {item['sim_type']}\n\n"
        
        # 4. KHÔNG CÓ VIỆC
        if not overdue and not today_due and not upcoming_7days:
            message += "✅ Hôm nay không có công việc cần xử lý.\n"
            message += "\n💡 Lưu ý:\n"
            message += "   - Sim 2 tháng (363*2): thời gian sử dụng 60 ngày (đã điều chỉnh)\n"
            message += "   - Sim 3 tháng (363*3, 360*3): thời gian sử dụng 90 ngày\n"
        
        send_telegram_message(message)
        
        print(f"\n📊 KẾT QUẢ XỬ LÝ:")
        print(f"   - Quá hạn: {len(overdue)}")
        print(f"   - Hôm nay đến hạn: {len(today_due)}")
        print(f"   - Sắp đến hạn (7 ngày): {len(upcoming_7days)}")
        
    except Exception as e:
        error_msg = f"❌ Lỗi hệ thống: {str(e)}"
        print(error_msg)
        send_telegram_message(error_msg)

if __name__ == "__main__":
    print("🚀 Bot nhắc việc khởi động...")
    check_reminders()
    print("🏁 Kết thúc")
