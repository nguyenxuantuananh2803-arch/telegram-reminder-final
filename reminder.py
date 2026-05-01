import requests
from datetime import datetime, timedelta
import os
import re

# ==================== CẤU HÌNH ====================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SHEET_ID = os.getenv('SHEET_ID')

# URL sheet (gid=0 là sheet đầu tiên)
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"

# Số ngày báo trước
REMIND_DAYS_3MONTH = 10   # Sim 3 tháng: báo trước 10 ngày
REMIND_DAYS_2MONTH = 30   # Sim 2 tháng: báo trước 30 ngày

def send_telegram_message(message):
    """Gửi tin nhắn Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Lỗi gửi tin nhắn: {e}")
        return False

def parse_date(date_str):
    """Chuyển đổi định dạng ngày tháng"""
    if not date_str or date_str.strip() == '':
        return None
    try:
        if ' ' in date_str:
            date_str = date_str.split(' ')[0]
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        return None

def extract_phone(phone_str):
    """Trích xuất số điện thoại (lấy 8 số cuối)"""
    if not phone_str or phone_str.strip() == '':
        return "Khong co SDT"
    phone = re.sub(r'[^\d]', '', str(phone_str))
    if len(phone) >= 8:
        return phone[-8:]
    return str(phone_str)

def parse_package(package_str):
    """Phân tích gói cước: 363*3, 363x2, 360*3..."""
    if not package_str or package_str.strip() == '':
        return None, None
    package_str = str(package_str).strip().upper()
    match = re.search(r'(\d+)[\*x](\d+)', package_str, re.IGNORECASE)
    if match:
        price = int(match.group(1))
        months = int(match.group(2))
        return price, months
    return None, None

def is_recent_record(ngay_lam):
    """Kiểm tra xem bản ghi có phải là gần đây không (trong vòng 60 ngày trở lại)"""
    if not ngay_lam:
        return True
    today = datetime.now().date()
    days_diff = (today - ngay_lam).days
    # Chỉ lấy các bản ghi trong vòng 60 ngày (không lấy dữ liệu quá cũ)
    return days_diff <= 60

def calculate_due_date(ngay_lam, months):
    """Tính ngày hết hạn dựa trên ngày làm và số tháng"""
    if not ngay_lam or not months:
        return None
    if months == 2:
        return ngay_lam + timedelta(days=60)
    else:
        return ngay_lam + timedelta(days=90)

def check_reminders():
    """Kiểm tra và gửi thông báo"""
    try:
        print("🔄 Đang đọc dữ liệu từ Google Sheets...")
        response = requests.get(SHEET_URL, timeout=30)
        
        if response.status_code != 200:
            send_telegram_message(f"❌ Lỗi: Không đọc được sheet (Mã: {response.status_code})")
            return
        
        lines = response.text.strip().split('\n')
        if len(lines) < 2:
            send_telegram_message("⚠️ Không có dữ liệu trong sheet")
            return
        
        # Đọc header để xác định vị trí các cột
        headers = lines[0].split(',')
        print(f"📋 Header: {headers[:13]}...")
        
        today = datetime.now().date()
        current_month = today.month
        current_year = today.year
        
        print(f"📅 Hôm nay: {today} - Tháng {current_month}/{current_year}")
        
        # Danh sách phân loại
        urgent_overdue = []      # Quá hạn > 7 ngày
        normal_overdue = []      # Quá hạn 1-7 ngày
        upcoming = []            # Sắp đến hạn (trong vòng REMIND_DAYS_3MONTH ngày)
        
        # Bỏ qua dòng header
        data_rows = lines[1:]
        
        for idx, row in enumerate(data_rows, start=2):
            if not row.strip():
                continue
            
            cols = row.split(',')
            if len(cols) < 13:
                continue
            
            try:
                # Lấy dữ liệu theo index (dựa trên cấu trúc chuẩn)
                ten_kh = cols[7].strip() if len(cols) > 7 else ''
                ngay_89_str = cols[2].strip() if len(cols) > 2 else ''
                sdt_raw = cols[11].strip() if len(cols) > 11 else ''
                goi_cuoc_raw = cols[12].strip() if len(cols) > 12 else ''
                ngay_sinh_str = cols[8].strip() if len(cols) > 8 else ''
                ngay_lam_str = cols[1].strip() if len(cols) > 1 else ''
                
                if not ten_kh:
                    continue
                
                # Parse ngày làm
                ngay_lam = parse_date(ngay_lam_str)
                
                # === LỌC DỮ LIỆU CŨ ===
                # Chỉ xử lý các bản ghi có NGAY LAM trong vòng 60 ngày trở lại
                if ngay_lam:
                    days_since_lam = (today - ngay_lam).days
                    if days_since_lam > 60:
                        print(f"⏭️ Bỏ qua dòng {idx}: {ten_kh} - NGAY LAM {ngay_lam} (quá {days_since_lam} ngày, dữ liệu cũ)")
                        continue
                else:
                    # Nếu không có NGAY LAM, bỏ qua (tránh dữ liệu rác)
                    print(f"⏭️ Bỏ qua dòng {idx}: {ten_kh} - Không có NGAY LAM")
                    continue
                
                # Parse gói cước
                price, months = parse_package(goi_cuoc_raw)
                
                # Tính ngày hết hạn dựa trên NGAY LAM và số tháng
                due_date = calculate_due_date(ngay_lam, months)
                if not due_date:
                    print(f"⚠️ Dòng {idx}: Không tính được ngày hết hạn cho {ten_kh} (gói: {goi_cuoc_raw})")
                    continue
                
                phone = extract_phone(sdt_raw)
                
                # Xác định số ngày báo trước
                if months == 2:
                    remind_days = REMIND_DAYS_2MONTH
                    sim_type = "SIM 2 THANG (60 ngay)"
                elif months == 3:
                    remind_days = REMIND_DAYS_3MONTH
                    sim_type = "SIM 3 THANG (90 ngay)"
                else:
                    # Nếu không xác định được, bỏ qua
                    print(f"⚠️ Dòng {idx}: Không xác định được số tháng cho {ten_kh} (gói: {goi_cuoc_raw})")
                    continue
                
                remind_date = due_date - timedelta(days=remind_days)
                days_until_due = (due_date - today).days
                
                print(f"📌 Dòng {idx}: {ten_kh} - NGAY LAM: {ngay_lam} - Due: {due_date} - Con {days_until_due} ngay - {sim_type}")
                
                # === PHÂN LOẠI ===
                # 1. QUÁ HẠN (due_date < today)
                if days_until_due < 0:
                    days_overdue = abs(days_until_due)
                    item = {
                        'name': ten_kh.upper(),
                        'phone': phone,
                        'due_date': due_date,
                        'days': days_overdue,
                        'package': goi_cuoc_raw,
                        'sim_type': sim_type,
                        'ngay_lam': ngay_lam
                    }
                    if days_overdue >= 14:
                        urgent_overdue.append(item)
                        print(f"   🔥🔥 QUA HAN {days_overdue} ngay (KHAN CAP)")
                    else:
                        normal_overdue.append(item)
                        print(f"   🔥 QUA HAN {days_overdue} ngay")
                
                # 2. SẮP ĐẾN HẠN (trong vòng remind_days ngày tới)
                elif 0 <= days_until_due <= remind_days:
                    if days_until_due == 0:
                        status = "HOM NAY"
                    else:
                        status = f"Con {days_until_due} ngay"
                    
                    upcoming.append({
                        'name': ten_kh.upper(),
                        'phone': phone,
                        'due_date': due_date,
                        'days_left': days_until_due,
                        'status': status,
                        'package': goi_cuoc_raw,
                        'sim_type': sim_type,
                        'ngay_lam': ngay_lam
                    })
                    print(f"   ⏰ SAP DEN HAN: {status}")
                
            except Exception as e:
                print(f"⚠️ Lỗi dòng {idx}: {e}")
                continue
        
        # ==================== TẠO TIN NHẮN ====================
        message = "🔔 <b>BÁO CÁO CÔNG VIỆC SIM</b> 🔔\n"
        message += f"📅 {today.strftime('%d/%m/%Y')}\n"
        message += f"⏰ Báo trước: {REMIND_DAYS_3MONTH} ngay (sim 3 thang) | 30 ngay (sim 2 thang)\n"
        message += "━" * 35 + "\n\n"
        
        # 1. QUÁ HẠN NGHIÊM TRỌNG (>=14 ngày)
        if urgent_overdue:
            message += "🚨🚨 <b>KHAN CAP - QUA HAN TREN 14 NGAY</b> 🚨🚨\n\n"
            for item in urgent_overdue:
                message += f"🔥🔥 <b>{item['name']}</b>\n"
                message += f"   📱 {item['phone']}\n"
                message += f"   📅 Ngay lam: {item['ngay_lam']}\n"
                message += f"   📅 Het han: {item['due_date']}\n"
                message += f"   ⚠️ QUA HAN {item['days']} NGAY\n"
                message += f"   📦 {item['package']} - {item['sim_type']}\n"
                message += "\n"
        
        # 2. QUÁ HẠN THÔNG THƯỜNG (1-13 ngày)
        if normal_overdue:
            message += "🚨 <b>QUA HAN (CAN XU LY NGAY)</b> 🚨\n\n"
            for item in normal_overdue:
                message += f"🔥 <b>{item['name']}</b>\n"
                message += f"   📱 {item['phone']}\n"
                message += f"   📅 Ngay lam: {item['ngay_lam']}\n"
                message += f"   📅 Het han: {item['due_date']}\n"
                message += f"   ⚠️ QUA HAN {item['days']} NGAY\n"
                message += f"   📦 {item['package']} - {item['sim_type']}\n"
                message += "\n"
        
        # 3. SẮP ĐẾN HẠN
        if upcoming:
            message += f"⏰ <b>SAP DEN HAN (TRONG {REMIND_DAYS_3MONTH} NGAY TOI)</b> ⏰\n\n"
            for item in upcoming:
                if item['days_left'] == 0:
                    message += f"📅 <b>{item['name']}</b> - HOM NAY\n"
                else:
                    message += f"📌 <b>{item['name']}</b> - Con {item['days_left']} ngay\n"
                message += f"   📱 {item['phone']}\n"
                message += f"   📅 Ngay lam: {item['ngay_lam']}\n"
                message += f"   📅 Den han: {item['due_date']}\n"
                message += f"   📦 {item['package']} - {item['sim_type']}\n\n"
        
        # 4. KHÔNG CÓ VIỆC
        if not urgent_overdue and not normal_overdue and not upcoming:
            message += "✅ Hôm nay không có công việc cần xử lý.\n"
            message += "\n💡 Lưu ý:\n"
            message += f"   - Sim 2 thang (363*2): bao truoc {REMIND_DAYS_2MONTH} ngay\n"
            message += f"   - Sim 3 thang (363*3, 360*3): bao truoc {REMIND_DAYS_3MONTH} ngay\n"
            message += "   - Chi hien thi du lieu trong vong 60 ngay gan day\n"
        
        # Gửi tin nhắn
        send_telegram_message(message)
        
        print(f"\n📊 KET QUA XU LY:")
        print(f"   - Qua han nghiem trong (>=14 ngay): {len(urgent_overdue)}")
        print(f"   - Qua han thuong (1-13 ngay): {len(normal_overdue)}")
        print(f"   - Sap den han ({REMIND_DAYS_3MONTH} ngay): {len(upcoming)}")
        
    except Exception as e:
        error_msg = f"❌ Lỗi hệ thống: {str(e)}"
        print(error_msg)
        send_telegram_message(error_msg)

# ==================== CHẠY CHÍNH ====================
if __name__ == "__main__":
    print("🚀 Bot nhac viec khoi dong...")
    check_reminders()
    print("🏁 Ket thuc")
