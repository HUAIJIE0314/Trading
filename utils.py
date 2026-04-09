import requests
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import base64
import os
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
# from utils import get_all_tw_stocks_with_names

# ==========================================
# 🌟 中文自型設定區 (繪圖用)
# ==========================================
def set_zh_font():
    """嘗試設定 matplotlib 的中文自型，依序尋找系統內建字型"""
    # 常見的繁體中文字型名稱 (Windows, Mac, Linux)
    common_zh_fonts = [
        'Microsoft JhengHei', # Windows 微軟正黑體
        'Heiti TC',           # Mac 黑體
        'Arial Unicode MS',   # 通用
        'SimSun',            # Windows 宋體 (備援)
        'Noto Sans CJK TC',  # Linux 通用
    ]
    
    found = False
    for font_name in common_zh_fonts:
        # 檢查字型是否存在於 matplotlib 系統中
        if font_name in [f.name for f in fm.fontManager.ttflist]:
            plt.rcParams['font.sans-serif'] = [font_name]
            found = True
            # print(f"✅ 已設定中文字型為: {font_name}")
            break
            
    if not found:
        print("⚠️ 警告: 找不到內建中文字型，圖表中的中文可能會顯示為方塊。")
        print("建議手動安裝 '微軟正黑體' 或 'Noto Sans CJK'。")
        
    # 解決負號 '-' 顯示為方塊的問題
    plt.rcParams['axes.unicode_minus'] = False

# 初始化時就嘗試設定字型
set_zh_font()


# ==========================================
# 1. 資料抓取與技術指標 (保持原樣)
# ==========================================
def get_all_tw_stocks_with_names():
    """使用政府 Open API 抓取最新股票代號與【中文簡稱】的字典 (中英雙語防呆版)"""
    # print("正在透過政府開放資料下載台股代號與名稱，請稍候...")
    
    def extract_codes_and_names(api_url, suffix):
        try:
            res = requests.get(api_url, timeout=10)
            data = res.json()
            
            if not data:
                return {}
                
            sample_keys = data[0].keys()
            code_key = None
            name_key = None
            
            # 自動偵測代號欄位 (加入政府英文欄位 SecuritiesCompanyCode, Symbol)
            for k in sample_keys:
                if k in ['公司代號', '證券代號', '股票代號', 'Code', 'code', 'SecuritiesCompanyCode', 'Symbol']:
                    code_key = k
                    break
            if not code_key:
                for k in sample_keys:
                    if '代號' in k or 'code' in k.lower(): code_key = k
                    
            # 自動偵測名稱欄位 (加入政府英文欄位 CompanyAbbreviation, CompanyName)
            for k in sample_keys:
                if k in ['公司簡稱', '證券名稱', '公司名稱', 'Name', 'name', 'CompanyAbbreviation', 'CompanyName']:
                    name_key = k
                    break
            if not name_key:
                for k in sample_keys:
                    if '名稱' in k or '簡稱' in k or 'name' in k.lower(): name_key = k
            
            if not code_key or not name_key:
                print(f"⚠️ 找不到代號或名稱欄位！現有欄位: {list(sample_keys)}")
                return {}
                
            # 建立 {代號: 名稱} 的字典
            stock_dict = {}
            for item in data:
                code = str(item.get(code_key, '')).strip()
                name = str(item.get(name_key, '')).strip()
                if code and len(code) == 4: 
                    stock_dict[f"{code}{suffix}"] = name
                    
            return stock_dict
            
        except Exception as e:
            print(f"❌ 請求 {api_url} 時發生錯誤: {e}")
            return {}

    # 分別抓取上市與上櫃字典
    url_twse = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    twse_dict = extract_codes_and_names(url_twse, ".TW")
    
    url_tpex = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
    tpex_dict = extract_codes_and_names(url_tpex, ".TWO")
    
    # 將上市與上櫃字典合併
    full_stock_dict = {**twse_dict, **tpex_dict}
    
    if full_stock_dict:
        # print(f"✅ 下載完成！共取得 {len(full_stock_dict)} 檔普通股。")
        return full_stock_dict
    else:
        print("⚠️ 無法取得清單，啟用備用預設清單...")
        return {'2330.TW': '台積電', '2317.TW': '鴻海', '2454.TW': '聯發科'}
    



def run_backtest(TICKER='2337', BACKTEST_DAYS=100, DayInterval=3):
    # ==========================================
    # 1. 參數設定
    # ==========================================
    INITIAL_CAPITAL = 500000     # 初始資金
    RSI_PERIOD = 14
    KD_K, KD_D, KD_SMOOTH = 60, 3, 3

    bars_per_day = 5             # 台股 60分K 一天約 5 根
    lookback_bars = DayInterval * bars_per_day
    MA_sell = 60
    MA_select = str(MA_sell) + "MA"

    stock_dict = get_all_tw_stocks_with_names() 
    filtered_list = {k: v for k, v in stock_dict.items() if k[:4] == TICKER}
    stock_dict = filtered_list

    keys_list = list(stock_dict.keys())

    if keys_list:
        TICKER = keys_list[0]         # 取出第一個代碼
        stock_name = stock_dict[TICKER] # 透過代碼拿到名稱
    else:
        # 若找不到股票，預設回傳 0
        return 0.0, 0.0

    # ==========================================
    # 2. 獲取資料與計算指標
    # ==========================================
    if BACKTEST_DAYS > 730:
        BACKTEST_DAYS = 730

    df = yf.download(TICKER, period=f"{BACKTEST_DAYS}d", interval="60m", progress=False)

    if df.empty:
        return 0.0, 0.0

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 🌟 核心新增：時區轉換 (將 UTC 轉換為台灣時間)
    try:
        df.index = df.index.tz_convert('Asia/Taipei')
    except TypeError:
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Taipei')
        
    # 計算技術指標
    df['RSI'] = df.ta.rsi(length=RSI_PERIOD)
    df['5MA'] = df.ta.sma(length=5)
    df['60MA'] = df.ta.sma(length=60)

    if MA_select != '60MA':
        df[MA_select] = df.ta.sma(length=MA_sell)
        
    stoch = df.ta.stoch(k=KD_K, d=KD_D, smooth_k=KD_SMOOTH)
    df = pd.concat([df, stoch], axis=1)

    # 🌟 自動抓取 KD 的 K 值與 D 值欄位名稱
    k_col = [col for col in df.columns if 'STOCHk' in col][0]
    d_col = [col for col in df.columns if 'STOCHd' in col][0]

    # --- 產生進出場訊號 ---
    df['KD_Cross'] = (df[k_col] > 50) & (df[k_col].shift(1) <= 50)
    df['MA_Cross'] = (df['5MA'] > df['60MA']) & (df['5MA'].shift(1) <= df['60MA'].shift(1))
    df['KD_Cross_5d'] = df['KD_Cross'].rolling(window=lookback_bars).max()
    df['MA_Cross_5d'] = df['MA_Cross'].rolling(window=lookback_bars).max()

    # 買進：RSI > 60 且 5MA 金叉 60MA
    df['MA_Golden_Cross'] = (df['KD_Cross_5d'] == 1) & (df['MA_Cross_5d'] == 1) 
    df['Buy_Signal'] = (df['RSI'] > 60) & (df['MA_Golden_Cross'])

    # 賣出：5MA 死叉 60MA 且 RSI < 50
    df['MA_Death_Cross'] = (df['5MA'] < df[MA_select]) & (df['5MA'].shift(1) >= df[MA_select].shift(1))
    df['Sell_Signal'] = (df['MA_Death_Cross']) & (df['RSI'] < 50)

    df = df.dropna()

    # ==========================================
    # 3. 執行回測邏輯 (事件驅動)
    # ==========================================
    capital = INITIAL_CAPITAL  
    position = 0               
    entry_price = 0.0          
    entry_date = None
    equity_curve = [INITIAL_CAPITAL] 
    trade_history = []         

    buy_points = []
    sell_points = []

    for date, row in df.iterrows():
        current_price = row['Close']
        
        # 尋找買點
        if position == 0:
            if row['Buy_Signal']:
                shares_to_buy = int(capital / (current_price * 1.001425))
                if shares_to_buy > 0:
                    position = shares_to_buy
                    entry_price = current_price
                    entry_date = date
                    capital = capital - (position * entry_price * 1.001425)
                    buy_points.append((date, entry_price))
                
        # 判斷出場
        elif position > 0:
            if row['Sell_Signal']:
                sell_revenue = position * current_price * (1 - 0.001425 - 0.003)
                capital += sell_revenue
                
                profit = sell_revenue - (position * entry_price * 1.001425)
                profit_pct = (current_price - entry_price) / entry_price * 100
                
                trade_history.append({
                    'Buy_Date': entry_date,     
                    'Sell_Date': date,          
                    'Buy_Price': entry_price,
                    'Sell_Price': current_price,
                    'Profit': profit,
                    'Return(%)': round(profit_pct, 2)
                })
                sell_points.append((date, current_price))
                
                position = 0
                entry_price = 0.0
                entry_date = None

        # 每天記錄最新的總資產
        current_equity = capital + (position * current_price * (1 - 0.001425 - 0.003))
        equity_curve.append(current_equity)

    equity_curve = equity_curve[1:]
    df['Equity_Curve'] = equity_curve

    total_return = (df['Equity_Curve'].iloc[-1] - INITIAL_CAPITAL) / INITIAL_CAPITAL

    total_trades = len(trade_history) 
    winning_trades = sum(1 for t in trade_history if t['Profit'] > 0)
    win_rate = (winning_trades / total_trades) if total_trades > 0 else 0

    return total_return, win_rate


# ==========================================
# 🌟 新增：視覺化繪圖區
# ==========================================
def generate_ranking_chart(data_list, metric_name, title, filename='temp_chart.png'):
    """
    根據排序好的資料列表生成直方圖，並存成圖片。
    metric_name: 'avg_win_rate' 或 'avg_return'
    """
    if not data_list:
        return None
        
    # 只取前 10 名做圖，避免畫面太擁擠 (如果總數小於10就全部取)
    plot_data = data_list[:5]
    
    # 準備繪圖數據
    labels = [f"{item['symbol']}\n{item['name']}" for item in plot_data]
    values = [item[metric_name] * 100 for item in plot_data] # 轉為百分比
    
    # 設定顏色: 勝率用金色調，報酬用藍色調
    bar_color = '#F59E0B' if metric_name == 'avg_win_rate' else '#3B82F6'
    
    # 創建圖表 (設定較高的 DPI 讓圖片清晰，適合手機閱讀)
    plt.figure(figsize=(10, 6), dpi=120)
    
    # 畫直方圖
    bars = plt.bar(labels, values, color=bar_color, edgecolor='black', alpha=0.8)
    
    # 在柱狀圖上方加入數值標籤
    for bar in bars:
        height = bar.get_height()
        # 格式化數值：勝率整數，報酬率開到小數第一位
        label_fmt = f'{height:.0f}%' if metric_name == 'avg_win_rate' else f'{height:.1f}%'
        
        plt.text(bar.get_x() + bar.get_width() / 2, height,
                 label_fmt,
                 ha='center', va='bottom', fontsize=10, fontweight='bold')

    # 設定標題與軸標籤
    plt.title(title, fontsize=16, fontweight='bold', pad=20)
    plt.ylabel('百分比 (%)', fontsize=12)
    plt.xticks(rotation=0, fontsize=10) # X軸標籤不旋轉，直著看
    plt.yticks(fontsize=10)
    
    # 加入網格線
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    
    # 自動調整排版
    plt.tight_layout()
    
    # 存檔
    plt.savefig(filename)
    plt.close() # 關閉 plt 釋放記憶體
    
    return filename


# ==========================================
# 2. LINE 與 ImgBB API 處理區 (保持原樣/整合)
# ==========================================
def send_line_message(message, token, target_id):
    """使用 LINE Messaging API (LINE Bot) 發送推播訊息"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": target_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        print("✅ LINE 訊息推播成功！")
    else:
        print(f"❌ 發送失敗，錯誤碼：{response.status_code}, 訊息：{response.text}")



def upload_to_imgbb(image_path, api_key):
    """將本地圖片轉換為 Base64 並上傳至 ImgBB，回傳公開網址"""
    url = "https://api.imgbb.com/1/upload"
    
    # ImgBB 要求將圖片轉成 Base64 編碼上傳
    with open(image_path, "rb") as file:
        encoded_string = base64.b64encode(file.read())
        
    payload = {
        "key": api_key,
        "image": encoded_string
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            image_url = response.json()['data']['url']
            print(f"✅ 上傳 ImgBB 成功: {image_url}")
            return image_url
        else:
            print(f"❌ 上傳失敗: {response.text}")
            return None
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        return None
    
def send_line_image(image_url, token, target_id):
    """使用 LINE API 推播圖片"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    # 注意：LINE 圖片推播的 type 是 "image"，需要原圖和縮圖網址
    payload = {
        "to": target_id,
        "messages": [
            {
                "type": "image",
                "originalContentUrl": image_url,
                "previewImageUrl": image_url  # 縮圖可以用同一張
            }
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    print("LINE 圖片發送狀態:", response.status_code)
