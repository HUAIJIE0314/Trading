import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import time
from tqdm import tqdm
import random
import os
import matplotlib.pyplot as plt

from utils import *


# ==========================================
# --- 參數設定區 ---
# ==========================================
DayInterval = 3 # 3 days
filterFlag = True # True / False


# LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
# TARGET_ID = os.environ.get('TARGET_ID')

# --- 參數設定區 ---
IMGBB_API_KEY = "48058fdc3f77f36c3565becf99a8e75a"
# 1. 請填入你在 LINE Developers 申請的 Channel Access Token
LINE_CHANNEL_ACCESS_TOKEN = "gbWfkE+jnMW8L9OB4agKPulEeKwzBP95WQ4Non4I6Q5lVCnNdik/l6cJ6PhV/krB7ss5mtjtr66K06m2VU1njN9sbUtfv1HftPlHyrwYCeKCOCqKMdz05lWboSg9FX0G3Wtocisn8hZ2IFFT50WrgwdB04t89/1O/w1cDnyilFU=" # "你的_CHANNEL_ACCESS_TOKEN_請填這"
# 2. 請填入你的 User ID 或 Group ID (通常是 U 開頭或 C 開頭的一串亂碼)
# TARGET_ID = "Ue64e679cfb6307bbe458a1490037f648" # "你的_USER_ID_或_GROUP_ID_請填這" 

# TARGET_ID = "C404155e7f01a3fd4dbb8fdf425f90991"

# TARGET_ID_LIST = ["Ue64e679cfb6307bbe458a1490037f648", "C404155e7f01a3fd4dbb8fdf425f90991", "C904d5fa59a1fdf3afc8cf95ae41c1b9d"]
TARGET_ID_LIST = ["Ue64e679cfb6307bbe458a1490037f648"]

RSI_PERIOD = 14
KD_K, KD_D, KD_SMOOTH = 60, 3, 3 # KD 指標的參數：60期、平滑3、D值3

# stock_list = ['2330.TW', '2317.TW', '2454.TW', '2603.TW', '2382.TW', '2337.TW']
# interest_list = ['2330', '2317', '2454', '2603', '2382', '2337', '3231', '2356', '2495', '5498']

interest_list = ["1717",
"2356",
"3481",
"4989",
"6116",
"8070"]


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


def main():
    # print("啟動進階選股程式，開始掃描...")
    print(f"啟動進階選股程式 (近{DayInterval}日雙金叉 + RSI>60)，開始掃描...")
    
    matched_stocks = []
    
    # 取得 {代號: 中文名} 的字典
    # stock_dict = get_all_tw_stocks_with_names() 
    # stock_dict = stock_dict[:5]
    
    # 取得政府 Open API {代號: 中文名} 的字典
    try:
        stock_dict = get_all_tw_stocks_with_names() 
    except Exception as e:
        print(f"❌ 取得股票清單失敗: {e}")
        return
    
    if filterFlag == True:
        # 過濾出符合 interest_list 的標的
        filtered_list = {k: v for k, v in stock_dict.items() if k[:4] in interest_list}
        print(f"過濾完成，準備掃描以下 {len(filtered_list)} 檔標的...")
        stock_dict = filtered_list
    else:
        print(f"未啟用過濾，將掃描全台股 {len(stock_dict)} 檔標的 (時間較長)...")
    
    # 只取出代號來跑迴圈，加上 tqdm 進度條
    for stock_symbol in tqdm(stock_dict.keys(), desc="掃描台股進度"):
        
        # 取得對應的中文公司名稱
        stock_name = stock_dict[stock_symbol] 
        
        # 把代號丟進策略裡去檢查
        if check_stock_strategy(stock_symbol):
            # 如果符合條件，把「代號 + 中文名」整包存進清單裡！
            # matched_stocks.append(f"{stock_symbol} ({stock_name})")
            # 去除後綴方便 utils 回測抓取
            clean_ticker = stock_symbol[:4]
            matched_stocks.append((clean_ticker, stock_name))
            
        # time.sleep(0.6) # 避免 yfinance 阻擋
        time.sleep(random.uniform(0.5, 0.7))
        
    # 彙整結果並發送 LINE
    if matched_stocks:
        
        #  # --- 修改這裡：對 List 裡的每一個 ID 輪流發送 ---
        #  for target_id in TARGET_ID_LIST:
        #      chunk_size = 30 # 一次最多傳送 30 檔標的
        #      total_matched = len(matched_stocks)
        #      
        #      # 第一則訊息：發送標題與總結
        #      # header_message = f"📈 【動能突破選股結果出爐】\n\n🎯 條件：RSI>60, KD(60) & 5MA 近 {DayInterval} 日雙金叉\n共發現 {total_matched} 檔符合標的：\n"
        #      # header_message = f"📈 【動能突破選股結果出爐】\n\n🎯 滿足以下條件：條件：RSI > 60\n2. KD(60) K值近 {DayInterval} 日向上突破 50\n3. 5MA 近 {DayInterval} 日向上突破 60MA\n\n符合標的：\n共發現 {total_matched} 檔符合標的：\n"
        #      header_message = f"📈 【動能突破選股結果出爐】\n\n🎯 滿足以下條件：\n1. RSI > 60\n2. KD(60) K值近 {DayInterval} 日向上突破 50\n3. 5MA 近 {DayInterval} 日向上突破 60MA\n4. 成交量大於 1000 張\n\n符合標的：\n共發現 {total_matched} 檔符合標的：\n"
        #      send_line_message(header_message, LINE_CHANNEL_ACCESS_TOKEN, target_id)
        #      
        #      # 分批發送名單
        #      for i in range(0, total_matched, chunk_size):
        #          chunk_list = matched_stocks[i:i + chunk_size]
        #          message = ""
        #          for s in chunk_list:
        #              message += f"• {s}\n"
        #          send_line_message(message, LINE_CHANNEL_ACCESS_TOKEN, target_id)
        #          time.sleep(1) # 避免發太快被 LINE 阻擋
        
        
        # print("\n🔄 開始對符合條件的標的進行 30/60/120 天回測計算...")
        # backtest_results = []
        # 
        # for stock_symbol, stock_name in tqdm(matched_stocks, desc="計算回測數據"):
        #     # 確保傳給 run_backtest 的 TICKER 是乾淨的 4 碼數字 (去掉 .TW 或 .TWO)
        #     clean_ticker = stock_symbol[:4] 
        #     
        #     # 分別取得 30, 60, 120 天的回測結果
        #     ret_30, win_30 = run_backtest(TICKER=clean_ticker, BACKTEST_DAYS=30, DayInterval=DayInterval)
        #     ret_60, win_60 = run_backtest(TICKER=clean_ticker, BACKTEST_DAYS=60, DayInterval=DayInterval)
        #     ret_120, win_120 = run_backtest(TICKER=clean_ticker, BACKTEST_DAYS=120, DayInterval=DayInterval)
        #     
        #     # 計算平均勝率與平均報酬
        #     avg_win_rate = (win_30 + win_60 + win_120) / 3
        #     avg_return = (ret_30 + ret_60 + ret_120) / 3
        #     
        #     backtest_results.append({
        #         'symbol': clean_ticker,
        #         'name': stock_name,
        #         'win_30': win_30, 'win_60': win_60, 'win_120': win_120,
        #         'ret_30': ret_30, 'ret_60': ret_60, 'ret_120': ret_120,
        #         'avg_win_rate': avg_win_rate,
        #         'avg_return': avg_return
        #     })
        #     
        # # 依照條件進行排序
        # sorted_by_win_rate = sorted(backtest_results, key=lambda x: x['avg_win_rate'], reverse=True)
        # sorted_by_return = sorted(backtest_results, key=lambda x: x['avg_return'], reverse=True)
        # 
        # print("\n✅ 回測計算完成，準備推播訊息...")
        # 
        # # 對清單內的每個 LINE ID 發送訊息
        # for target_id in TARGET_ID_LIST:
        #     chunk_size = 20 # 一次最多傳送 20 檔標的
        #     
        #     # ---------------------------------------------------------
        #     # 🏆 Stage 1: 推播勝率優先榜
        #     # ---------------------------------------------------------
        #     stage1_header = (
        #         f"🏆 【Stage 1: 勝率優先榜】 🏆\n"
        #         f"依 30/60/120 天平均勝率排序\n"
        #         f"共發現 {len(matched_stocks)} 檔標的\n"
        #         f"----------------------"
        #     )
        #     send_line_message(stage1_header, LINE_CHANNEL_ACCESS_TOKEN, target_id)
        #     time.sleep(1)
        #     
        #     for i in range(0, len(sorted_by_win_rate), chunk_size):
        #         chunk_list = sorted_by_win_rate[i:i + chunk_size]
        #         message = ""
        #         for rank, s in enumerate(chunk_list, start=i+1):
        #             message += (
        #                 f"第{rank}名: {s['symbol']} {s['name']}\n"
        #                 f"📊 平均勝率: {s['avg_win_rate']*100:.1f}%\n"
        #                 f"   (30/60/120: {s['win_30']*100:.0f}% / {s['win_60']*100:.0f}% / {s['win_120']*100:.0f}%)\n"
        #                 f"💰 平均報酬: {s['avg_return']*100:.1f}%\n"
        #                 f"   (30/60/120: {s['ret_30']*100:.1f}% / {s['ret_60']*100:.1f}% / {s['ret_120']*100:.1f}%)\n"
        #                 f"----------------------\n"
        #             )
        #         send_line_message(message.strip(), LINE_CHANNEL_ACCESS_TOKEN, target_id)
        #         time.sleep(1)
        # 
        #     # ---------------------------------------------------------
        #     # 🚀 Stage 2: 推播報酬率優先榜
        #     # ---------------------------------------------------------
        #     stage2_header = (
        #         f"🚀 【Stage 2: 報酬優先榜】 🚀\n"
        #         f"依 30/60/120 天平均報酬率排序\n"
        #         f"----------------------"
        #     )
        #     send_line_message(stage2_header, LINE_CHANNEL_ACCESS_TOKEN, target_id)
        #     time.sleep(1)
        #     
        #     for i in range(0, len(sorted_by_return), chunk_size):
        #         chunk_list = sorted_by_return[i:i + chunk_size]
        #         message = ""
        #         for rank, s in enumerate(chunk_list, start=i+1):
        #             message += (
        #                 f"第{rank}名: {s['symbol']} {s['name']}\n"
        #                 f"💰 平均報酬: {s['avg_return']*100:.1f}%\n"
        #                 f"   (30/60/120: {s['ret_30']*100:.1f}% / {s['ret_60']*100:.1f}% / {s['ret_120']*100:.1f}%)\n"
        #                 f"📊 平均勝率: {s['avg_win_rate']*100:.1f}%\n"
        #                 f"   (30/60/120: {s['win_30']*100:.0f}% / {s['win_60']*100:.0f}% / {s['win_120']*100:.0f}%)\n"
        #                 f"----------------------\n"
        #             )
        #         send_line_message(message.strip(), LINE_CHANNEL_ACCESS_TOKEN, target_id)
        #         time.sleep(1)
        
        
        print(f"\n✅ 掃描完成，發現 {len(matched_stocks)} 檔符合條件標的。")
        print("🔄 開始進行 30/60/120 天回測計算並準備可視化圖表...")
        
        backtest_results = []
        
        # 進行多時段回測
        for clean_ticker, stock_name in tqdm(matched_stocks, desc="計算回測數據"):
            # 分別取得 30, 60, 120 天的回測結果 (報酬率, 勝率)
            ret_30, win_30 = run_backtest(TICKER=clean_ticker, BACKTEST_DAYS=30, DayInterval=DayInterval)
            ret_60, win_60 = run_backtest(TICKER=clean_ticker, BACKTEST_DAYS=60, DayInterval=DayInterval)
            ret_120, win_120 = run_backtest(TICKER=clean_ticker, BACKTEST_DAYS=120, DayInterval=DayInterval)
            
            # 計算 3 段時段的平均
            avg_win_rate = (win_30 + win_60 + win_120) / 3
            avg_return = (ret_30 + ret_60 + ret_120) / 3
            
            backtest_results.append({
                'symbol': clean_ticker,
                'name': stock_name,
                'win_30': win_30, 'win_60': win_60, 'win_120': win_120,
                'ret_30': ret_30, 'ret_60': ret_60, 'ret_120': ret_120,
                'avg_win_rate': avg_win_rate,
                'avg_return': avg_return
            })
            
        # 依照條件進行排序
        # Stage 1: 平均勝率 由高~低
        sorted_by_win_rate = sorted(backtest_results, key=lambda x: x['avg_win_rate'], reverse=True)
        # Stage 2: 平均報酬 由高~低
        sorted_by_return = sorted(backtest_results, key=lambda x: x['avg_return'], reverse=True)
        
        print("\n📊 數據彙整與排序完成。")

        # ==========================================
        # 🌟 核心更新：生成圖表與 LINE 推播
        # ==========================================
        
        # --- A. 準備圖片與上傳 (先上傳一次，節省 API 次數) ---
        print("🎨 正在生成 Stage 1 & 2 可視化圖表並上傳...")
        
        # 生成 Stage 1 勝率圖表
        temp_img_win = "temp_stage1_win.png"
        chart_win_local = generate_ranking_chart(
            sorted_by_win_rate, 
            'avg_win_rate', 
            f'Stage 1: 勝率優先榜 (Top 5)\n(RSI>60 + 近{DayInterval}日雙金叉條件)',
            temp_img_win
        )
        url_img_win = upload_to_imgbb(chart_win_local, IMGBB_API_KEY)
        
        # 生成 Stage 2 報酬圖表
        temp_img_ret = "temp_stage2_ret.png"
        chart_ret_local = generate_ranking_chart(
            sorted_by_return, 
            'avg_return', 
            f'Stage 2: 報酬優先榜 (Top 5)\n(30/60/120天平均)',
            temp_img_ret
        )
        url_img_ret = upload_to_imgbb(chart_ret_local, IMGBB_API_KEY)
        
        # 清理本地臨時圖片 (上傳後就不用了)
        if chart_win_local and os.path.exists(chart_win_local): os.remove(chart_win_local)
        if chart_ret_local and os.path.exists(chart_ret_local): os.remove(chart_ret_local)
        
        
        # 🌟 B. 準備第 1 名詳細 120 回測圖 (新功能) ---
        url_img_detailed = None
        if sorted_by_return:
            print("🎨 正在生成第 1 名詳細 120 回測圖...")
            top_stock_return = sorted_by_return[0] # 取報酬率第 1 名
            clean_ticker_top = top_stock_return['symbol']
            stock_name_top = top_stock_return['name']
            
            # 生成詳細圖表本地檔案 (120天)
            temp_img_detailed = "temp_detailed_backtest.png"
            chart_detailed_local = generate_detailed_backtest_plot(clean_ticker_top, stock_name_top, BACKTEST_DAYS=120, DayInterval=DayInterval, filename=temp_img_detailed)
            
            # 上傳至 ImgBB
            url_img_detailed = upload_to_imgbb(chart_detailed_local, IMGBB_API_KEY)
            
            # 清理本地檔案
            if chart_detailed_local and os.path.exists(chart_detailed_local): os.remove(chart_detailed_local)
        
        
        
        if not url_img_win and not url_img_ret and not url_img_detailed:
            print("⚠️ 警告: 圖表上傳失敗，LINE 推播將只包含文字訊息。")
        else:
            print("✅ 圖表上傳成功。")

        # --- B. 對所有接收者輪流發送 (結合圖片與文字) ---
        chunk_size = 20 # 文字訊息 chunk 依舊留著, 縮小為 20 筆
        
        for target_id in TARGET_ID_LIST:
            # print(f"📤 正在發送訊息給 {target_id[:5]}...")
            
            # ---------------------------------------------------------
            #🏆🏆🏆 Stage 1: 推播勝率優先榜 🏆🏆🏆
            # ---------------------------------------------------------
            
            # 1. 發送 Stage 1 標題
            stage1_header = (
                f"🏆🏆🏆 【Stage 1: 勝率優先榜】 🏆🏆🏆\n"
                f"🎯 條件：RSI>60, KD(60) & 5MA 近 {DayInterval} 日雙金叉\n"
                f"依 30/60/120 天平均勝率排序\n"
                f"共發現 {len(matched_stocks)} 檔符合標的：\n"
                f"----------------------------"
            )
            send_line_message(stage1_header, LINE_CHANNEL_ACCESS_TOKEN, target_id)
            time.sleep(0.5)
            
            # 🌟 2. 發送 Stage 1 圖表圖片
            if url_img_win:
                send_line_image(url_img_win, LINE_CHANNEL_ACCESS_TOKEN, target_id)
                time.sleep(1)
            
            # 3. 分批發送詳細明細 (文字)
            send_line_message("📋詳細回測明細 (Stage 1):", LINE_CHANNEL_ACCESS_TOKEN, target_id)
            for i in range(0, len(sorted_by_win_rate), chunk_size):
                chunk_list = sorted_by_win_rate[i:i + chunk_size]
                message = ""
                for rank, s in enumerate(chunk_list, start=i+1):
                    # 優化文字排版：將勝率和報酬拆開，更易讀
                    message += (
                        f"🏆第{rank}名: {s['symbol']} {s['name']}\n"
                        f"📊 [平均勝率]: {s['avg_win_rate']*100:.1f}%\n"
                        f"   (30D: {s['win_30']*100:.0f}% / 60D: {s['win_60']*100:.0f}% / 120D: {s['win_120']*100:.0f}%)\n"
                        f"💰 [平均報酬]: {s['avg_return']*100:.1f}%\n"
                        f"   (30D: {s['ret_30']*100:.1f}% / 60D: {s['ret_60']*100:.1f}% / 120D: {s['ret_120']*100:.1f}%)\n"
                        f"----------------------------\n"
                    )
                send_line_message(message.strip(), LINE_CHANNEL_ACCESS_TOKEN, target_id)
                time.sleep(1) # 避免發太快被 LINE 阻擋

            time.sleep(2) # Stage 間隔久一點

            # ---------------------------------------------------------
            #🚀🚀🚀 Stage 2: 推播報酬優先榜 🚀🚀🚀
            # ---------------------------------------------------------
            
            # 1. 發送 Stage 2 標題 (加入明顯區隔)
            stage2_header = (
                f"\n\n🚀🚀🚀 【Stage 2: 報酬優先榜】 🚀🚀🚀\n"
                f"依 30/60/120 天平均報酬率排序\n"
                f"----------------------------"
            )
            send_line_message(stage2_header.strip(), LINE_CHANNEL_ACCESS_TOKEN, target_id)
            time.sleep(0.5)
            
            # 🌟 2. 發送 Stage 2 圖表圖片
            if url_img_ret:
                send_line_image(url_img_ret, LINE_CHANNEL_ACCESS_TOKEN, target_id)
                time.sleep(1)
            
            # 3. 分批發送詳細明細 (文字)
            send_line_message("📋詳細回測明細 (Stage 2):", LINE_CHANNEL_ACCESS_TOKEN, target_id)
            for i in range(0, len(sorted_by_return), chunk_size):
                chunk_list = sorted_by_return[i:i + chunk_size]
                message = ""
                for rank, s in enumerate(chunk_list, start=i+1):
                    # 排版與上同
                    message += (
                        f"🚀第{rank}名: {s['symbol']} {s['name']}\n"
                        f"💰 [平均報酬]: {s['avg_return']*100:.1f}%\n"
                        f"   (30D: {s['ret_30']*100:.1f}% / 60D: {s['ret_60']*100:.1f}% / 120D: {s['ret_120']*100:.1f}%)\n"
                        f"📊 [平均勝率]: {s['avg_win_rate']*100:.1f}%\n"
                        f"   (30D: {s['win_30']*100:.0f}% / 60D: {s['win_60']*100:.0f}% / 120D: {s['win_120']*100:.0f}%)\n"
                        f"----------------------------\n"
                    )
                send_line_message(message.strip(), LINE_CHANNEL_ACCESS_TOKEN, target_id)
                time.sleep(1) # 避免發太快被 LINE 阻擋
            
            # ---------------------------------------------------------
            #特別推播：第 1 名詳細 120 回測圖 🌟🌟🌟
            # ---------------------------------------------------------
            if url_img_detailed:
                # 這裡取出第 1 名資訊，加入清楚說明
                top_name = sorted_by_return[0]['name']
                top_symbol = sorted_by_return[0]['symbol']
                top_ret = sorted_by_return[0]['avg_return']
                
                detailed_header = (
                    f"\n\n🥇 本日績效王 (依平均報酬) 之詳細回測：\n"
                    f"👉 👉 👉 {top_symbol} {top_name}\n"
                    f"💰 平均報酬 (30/60/120): {top_ret*100:.1f}%\n"
                    f"以下為該股過去 120 天之詳細時序圖 (包含買賣點、指標與資金曲線)：\n"
                    f"----------------------------"
                )
                send_line_message(detailed_header.strip(), LINE_CHANNEL_ACCESS_TOKEN, target_id); time.sleep(0.5)
                
                # 發送詳細圖片
                send_line_image(url_img_detailed, LINE_CHANNEL_ACCESS_TOKEN, target_id); time.sleep(1)
                
                
                
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

    
    