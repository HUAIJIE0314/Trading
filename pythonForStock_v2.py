import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import time
from tqdm import tqdm
import random

# enableRSI = True
DayInterval = 3 # 3 days
filterFlag = False # True / False



import os
# LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
# TARGET_ID = os.environ.get('TARGET_ID')

# --- 參數設定區 ---
# 1. 請填入你在 LINE Developers 申請的 Channel Access Token
LINE_CHANNEL_ACCESS_TOKEN = "gbWfkE+jnMW8L9OB4agKPulEeKwzBP95WQ4Non4I6Q5lVCnNdik/l6cJ6PhV/krB7ss5mtjtr66K06m2VU1njN9sbUtfv1HftPlHyrwYCeKCOCqKMdz05lWboSg9FX0G3Wtocisn8hZ2IFFT50WrgwdB04t89/1O/w1cDnyilFU=" # "你的_CHANNEL_ACCESS_TOKEN_請填這"
# 2. 請填入你的 User ID 或 Group ID (通常是 U 開頭或 C 開頭的一串亂碼)
# TARGET_ID = "Ue64e679cfb6307bbe458a1490037f648" # "你的_USER_ID_或_GROUP_ID_請填這" 

# TARGET_ID = "C404155e7f01a3fd4dbb8fdf425f90991"

TARGET_ID_LIST = ["Ue64e679cfb6307bbe458a1490037f648", "C404155e7f01a3fd4dbb8fdf425f90991", "C904d5fa59a1fdf3afc8cf95ae41c1b9d"]


RSI_PERIOD = 14
KD_K, KD_D, KD_SMOOTH = 60, 3, 3 # KD 指標的參數：60期、平滑3、D值3

# stock_list = ['2330.TW', '2317.TW', '2454.TW', '2603.TW', '2382.TW', '2337.TW']
interest_list = ['2330', '2317', '2454', '2603', '2382', '2337']

# stock_list = ['2330.TW']
import requests

def get_all_tw_stocks_with_names():
    """使用政府 Open API 抓取最新股票代號與【中文簡稱】的字典 (中英雙語防呆版)"""
    print("正在透過政府開放資料下載台股代號與名稱，請稍候...")
    
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
        print(f"✅ 下載完成！共取得 {len(full_stock_dict)} 檔普通股。")
        return full_stock_dict
    else:
        print("⚠️ 無法取得清單，啟用備用預設清單...")
        return {'2330.TW': '台積電', '2317.TW': '鴻海', '2454.TW': '聯發科'}
    

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


def check_stock_strategy(ticker):
    """檢查單一股票是否符合進階策略條件 (60分K線版本)"""
    try:
        # df = yf.download(ticker, period="150d", progress=False)
        # df = yf.download(ticker, period="1mo", interval="60m", progress=False)
        
        # 修改 1：將 period 拉長到 3個月，確保 60MA 與 KD(60) 有足夠的前置數據平滑
        # 去 Yahoo 下載這檔股票過去 3 個月的資料，並且每一根 K 棒代表 60 分鐘。
        df = yf.download(ticker, period="3mo", interval="60m", progress=False)
        
        # 解決 yfinance 新版 MultiIndex 格式問題
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 如果這檔股票剛上市，資料太少 (不到 65 根 K 棒)，根本算不出 60MA，就直接淘汰回傳 False。
        if df.empty or len(df) < 65:
            return False
        
        
        # 🌟 新增：成交量濾網 (Volume)
        # yfinance 的 Volume 欄位預設是「股數」，所以 1000 張 = 1,000,000 股
        today_volume = df['Volume'].iloc[-1]
        
        # 如果今天成交量小於 1000 張 (1百萬股)，直接淘汰，不用算後面的技術指標了！
        if today_volume < 1000000:
            return False
        
        # 1. 計算技術指標
        df['RSI'] = df.ta.rsi(length=RSI_PERIOD)
        df['5MA'] = df.ta.sma(length=5)
        df['60MA'] = df.ta.sma(length=60)
        
        stoch = df.ta.stoch(k=KD_K, d=KD_D, smooth_k=KD_SMOOTH)
        df = pd.concat([df, stoch], axis=1)
        k_col_name = [col for col in df.columns if 'STOCHk' in col][0]
        
        # --- 核心邏輯改寫：計算穿越訊號 (全時段) ---
        # 產生一個布林值(True/False)的欄位：今天 K > 50 且 昨天 K <= 50
        kd_cross_signal = (df[k_col_name] > 50) & (df[k_col_name].shift(1) <= 50)
        
        # 產生一個布林值的欄位：今天 5MA > 60MA 且 昨天 5MA <= 60MA
        ma_cross_signal = (df['5MA'] > df['60MA']) & (df['5MA'].shift(1) <= df['60MA'].shift(1))
        
        # --- 判斷最近 5 天的狀態 ---
        # 條件 A: 「今天」的 RSI > 60
        cond_rsi = df['RSI'].iloc[-1] > 60
        
        # 條件 B: 過去 5 天內 (包含今天)，是否有任何一天 kd_cross_signal 為 True
        cond_k_cross_5d = kd_cross_signal.tail(5*DayInterval).any()
        
        # 條件 C: 過去 5 天內 (包含今天)，是否有任何一天 ma_cross_signal 為 True
        cond_ma_cross_5d = ma_cross_signal.tail(5*DayInterval).any()
        
        # 綜合判斷 (三個條件同時滿足)
        if cond_rsi and cond_k_cross_5d and cond_ma_cross_5d:
            print(f"⭐ 發現符合標的：{ticker} (近{DayInterval}日內觸發雙金叉，且今日 RSI>60)")
            return True
            
    except Exception as e:
        print(f"處理 {ticker} 時發生錯誤: {e}")
        
    return False



# =============================================================================
# def main():
#     print("啟動進階選股程式，開始掃描...")
#     matched_stocks = []
#     
#     #for stock in stock_list:
#     for stock in tqdm(stock_list, desc="掃描台股進度"):
#         print(f"正在檢查 {stock} ...")
#         if check_stock_strategy(stock):
#             matched_stocks.append(stock)
#         time.sleep(1) # 避免 yfinance 阻擋
#         
#     # 彙整結果並發送 LINE
#     if matched_stocks:
#         message = "📈 【動能突破選股結果出爐】\n\n滿足以下條件：\n1. RSI > 60\n2. KD(60) K值向上突破 50\n3. 5MA 向上突破 60MA\n\n符合標的：\n"
#         for s in matched_stocks:
#             message += f"• {s}\n"
#         send_line_message(message, LINE_CHANNEL_ACCESS_TOKEN, TARGET_ID)
#     else:
#         print("今日無符合條件的股票。")
#         send_line_message("今日無符合「動能突破與雙重金叉」條件的股票。", LINE_CHANNEL_ACCESS_TOKEN, TARGET_ID)
# =============================================================================

# =============================================================================
# if __name__ == "__main__":
#     main()
# =============================================================================
def main():
    print("啟動進階選股程式，開始掃描...")
    matched_stocks = []
    
    # 取得 {代號: 中文名} 的字典
    stock_dict = get_all_tw_stocks_with_names() 
    # stock_dict = stock_dict[:5]
    
    
    # n = 10
    # stock_dict = dict(list(stock_dict.items())[:n])
    
    if filterFlag == True:
        # 3. 核心修改：只過濾出符合 interest_list 的標的
        # 我們檢查全台股代號（如 2330.TW）的前 4 碼是否在你的清單中
        filtered_list = {k: v for k, v in stock_dict.items() if k[:4] in interest_list}
        print(f"過濾完成，準備掃描：{list(filtered_list.values())}")
        stock_dict = filtered_list
    
    # 只取出代號來跑迴圈，加上 tqdm 進度條
    for stock_symbol in tqdm(stock_dict.keys(), desc="掃描台股進度"):
        
        # 取得對應的中文公司名稱
        stock_name = stock_dict[stock_symbol] 
        
        
        # 把代號丟進策略裡去檢查
        if check_stock_strategy(stock_symbol):
            # 如果符合條件，把「代號 + 中文名」整包存進清單裡！
            matched_stocks.append(f"{stock_symbol} ({stock_name})")
            
        # time.sleep(0.6) # 避免 yfinance 阻擋
        time.sleep(random.uniform(0.5, 0.7))
        
    # 彙整結果並發送 LINE
    if matched_stocks:
        
        # --- 修改這裡：對 List 裡的每一個 ID 輪流發送 ---
        for target_id in TARGET_ID_LIST:
            chunk_size = 30 # 一次最多傳送 30 檔標的
            total_matched = len(matched_stocks)
            
            # 第一則訊息：發送標題與總結
            # header_message = f"📈 【動能突破選股結果出爐】\n\n🎯 條件：RSI>60, KD(60) & 5MA 近 {DayInterval} 日雙金叉\n共發現 {total_matched} 檔符合標的：\n"
            # header_message = f"📈 【動能突破選股結果出爐】\n\n🎯 滿足以下條件：條件：RSI > 60\n2. KD(60) K值近 {DayInterval} 日向上突破 50\n3. 5MA 近 {DayInterval} 日向上突破 60MA\n\n符合標的：\n共發現 {total_matched} 檔符合標的：\n"
            header_message = f"📈 【動能突破選股結果出爐】\n\n🎯 滿足以下條件：\n1. RSI > 60\n2. KD(60) K值近 {DayInterval} 日向上突破 50\n3. 5MA 近 {DayInterval} 日向上突破 60MA\n4. 成交量大於 1000 張\n\n符合標的：\n共發現 {total_matched} 檔符合標的：\n"
            send_line_message(header_message, LINE_CHANNEL_ACCESS_TOKEN, target_id)
            
            # 分批發送名單
            for i in range(0, total_matched, chunk_size):
                chunk_list = matched_stocks[i:i + chunk_size]
                message = ""
                for s in chunk_list:
                    message += f"• {s}\n"
                send_line_message(message, LINE_CHANNEL_ACCESS_TOKEN, target_id)
                time.sleep(1) # 避免發太快被 LINE 阻擋
    else:
        print("\n今日無符合條件的股票。")
        # send_line_message("\n今日無符合「動能突破與雙重金叉」條件的股票。", LINE_CHANNEL_ACCESS_TOKEN, TARGET_ID)
        for target_id in TARGET_ID_LIST:
            send_line_message("\n今日無符合「動能突破與雙重金叉」條件的股票。", LINE_CHANNEL_ACCESS_TOKEN, target_id)


if __name__ == "__main__":
    main()
    
    
# =============================================================================
# new_stock_list = get_all_tw_stocks_with_names()
# n = 3
# 
# # 將 items 轉成 list 再切片，然後轉回 dict
# first_n = dict(list(new_stock_list.items())[:n])
# 
# print(first_n)
# =============================================================================


# =============================================================================
# print("前五檔上市:", new_stock_list[:5])
# print('-'*50)
# print("最後五檔上櫃:", new_stock_list[-5:])
# =============================================================================

    
    